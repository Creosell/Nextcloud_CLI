import os
import sys
import argparse
import asyncio
from pathlib import Path

# External libs
from loguru import logger
from dotenv import load_dotenv
from nc_py_api import AsyncNextcloud, NextcloudException

# --- Constants & Config ---
MAX_DIR_CREATE_RETRIES = 3
DIR_CREATE_RETRY_DELAY_SEC = 1.0
MAX_NETWORK_RETRIES = 2
NETWORK_RETRY_DELAY_SEC = 2.0
REQUEST_TIMEOUT_SEC = 60
APP_VERSION = "1.1.1"
DEFAULT_CONCURRENCY = 5

# --- Logging Setup ---
# The caller reads the output as UTF-8 whatever the console code page is.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
logger.remove()
LOG_FOLDER = Path("logs")
os.makedirs(LOG_FOLDER, exist_ok=True)
LOG_FILE = LOG_FOLDER / "nextcloud_cli_log.txt"

logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | {message}", level="INFO")
logger.add(
    LOG_FILE,
    level="DEBUG",
    rotation="5 MB",
    compression="zip",
    enqueue=True,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
)


def get_nc_client() -> AsyncNextcloud:
    """Creates the async Nextcloud client from the credentials in the environment or the .env file."""
    load_dotenv()
    url = os.environ.get("NC_SERVER_URL_QC")
    user = os.environ.get("NC_USER_QC")
    password = os.environ.get("NC_PASSWORD_QC")

    if not all([url, user, password]):
        logger.error("Missing credentials in .env.")
        raise ValueError("Nextcloud credentials missing.")

    return AsyncNextcloud(
        nextcloud_url=url, nc_auth_user=user, nc_auth_pass=password,
        npa_timeout=REQUEST_TIMEOUT_SEC, npa_timeout_dav=REQUEST_TIMEOUT_SEC,
    )


def status_of(error: Exception) -> int:
    """Returns the HTTP status code carried by a Nextcloud error, or 0 when it has none."""
    return getattr(error, "status_code", 0)


async def list_files_recursive(nc: AsyncNextcloud, remote_path: str) -> list:
    """Recursively lists all files in a remote directory."""
    file_list = []
    try:
        for item in await nc.files.listdir(remote_path):
            if item.is_dir:
                file_list.extend(await list_files_recursive(nc, item.user_path))
            else:
                file_list.append(item.user_path)
    except NextcloudException as e:
        logger.error(f"Failed to list '{remote_path}': {e}")
    return file_list


async def ensure_parent_exists(nc: AsyncNextcloud, remote_path: str) -> bool:
    """Recursively creates the missing parent directories of a remote path."""
    remote_path = remote_path.replace("\\", "/")
    path_parts = remote_path.lstrip("/").split('/')[:-1]

    current_path = ""
    for part in path_parts:
        current_path = (current_path + "/" + part).lstrip('/')
        for attempt in range(MAX_DIR_CREATE_RETRIES):
            try:
                await nc.files.mkdir(current_path)
                break
            except NextcloudException as e:
                if status_of(e) in (405, 409) or "already exists" in str(e): break
                if status_of(e) == 423 and attempt < MAX_DIR_CREATE_RETRIES - 1:
                    await asyncio.sleep(DIR_CREATE_RETRY_DELAY_SEC)
                    continue
                logger.error(f"Failed to create dir {current_path}: {e}")
                return False
            except Exception:
                return False
    return True


async def upload_file(nc: AsyncNextcloud, local_path: str, remote_path: str) -> bool:
    """Uploads a local file to a remote path."""
    remote_path = remote_path.replace("\\", "/").lstrip("/")
    if not await ensure_parent_exists(nc, remote_path): return False

    try:
        content = Path(local_path).read_bytes()
    except Exception as e:
        logger.error(f"Read error {local_path}: {e}")
        return False

    for attempt in range(MAX_NETWORK_RETRIES + 1):
        try:
            await nc.files.upload(remote_path, content)
            logger.info(f"Uploaded: {local_path} -> {remote_path}")
            return True
        except Exception as e:
            if attempt < MAX_NETWORK_RETRIES:
                await asyncio.sleep(NETWORK_RETRY_DELAY_SEC)
            else:
                logger.error(f"Upload failed {remote_path}: {e}")
    return False


async def download_file(nc: AsyncNextcloud, remote_path: str, local_path: str, force: bool) -> bool:
    """Downloads a remote file to a local path."""
    remote_path = remote_path.replace("\\", "/").lstrip("/")
    local_obj = Path(local_path)

    if local_obj.exists() and not force:
        logger.warning(f"Skipped (exists): {local_path}")
        return False

    for attempt in range(MAX_NETWORK_RETRIES + 1):
        try:
            local_obj.parent.mkdir(parents=True, exist_ok=True)
            content = await nc.files.download(remote_path)
            local_obj.write_bytes(content)
            logger.info(f"Downloaded: {remote_path}")
            return True
        except NextcloudException as e:
            if status_of(e) == 404 or "404" in str(e):
                logger.error(f"Not found: {remote_path}")
                return False
            if attempt < MAX_NETWORK_RETRIES:
                await asyncio.sleep(NETWORK_RETRY_DELAY_SEC)
            else:
                logger.error(f"Download failed {remote_path}: {e}")
        except Exception as e:
            if attempt < MAX_NETWORK_RETRIES:
                await asyncio.sleep(NETWORK_RETRY_DELAY_SEC)
            else:
                logger.error(f"Error {remote_path}: {e}")
    return False


async def download_directory_parallel(nc: AsyncNextcloud, remote_base: str, local_base: str, force: bool,
                                      concurrency: int) -> bool:
    """Downloads a remote directory recursively, keeping its structure, with bounded concurrency."""
    logger.info(f"Scanning remote directory: {remote_base}")
    all_files = await list_files_recursive(nc, remote_base)

    if not all_files:
        logger.warning("No files found to download.")
        return True

    logger.info(f"Found {len(all_files)} files. Starting download with {concurrency} parallel tasks.")
    gate = asyncio.Semaphore(concurrency)
    r_base = remote_base.strip("/")

    async def fetch(remote_file: str) -> bool:
        # e.g. remote: /data/imgs/1.jpg, base: /data/ -> rel: imgs/1.jpg
        r_file = remote_file.strip("/")
        rel_path = r_file[len(r_base):].lstrip("/") if r_file.startswith(r_base) else Path(r_file).name
        async with gate:
            return await download_file(nc, remote_file, str(Path(local_base) / rel_path), force)

    results = await asyncio.gather(*(fetch(f) for f in all_files))
    success_count = results.count(True)
    logger.info(f"Batch completed: {success_count}/{len(all_files)} files downloaded successfully.")
    return success_count == len(all_files)


async def run(args: argparse.Namespace) -> bool:
    """Executes the requested action and returns whether it succeeded."""
    try:
        nc = get_nc_client()
    except Exception:
        return False

    if args.action == "upload":
        return await upload_file(nc, args.local_path, args.remote_path)
    if args.action == "download":
        return await download_file(nc, args.remote_path, args.local_path, args.force)
    if args.action == "download-dir":
        return await download_directory_parallel(nc, args.remote_path, args.local_path, args.force, args.jobs)

    files = await list_files_recursive(nc, args.remote_path)
    for f in files: print(f)
    logger.info(f"Found {len(files)} files.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Nextcloud CLI Utility", formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument("action", choices=["upload", "download", "list", "download-dir"], help="Action to perform.")
    parser.add_argument("-l", "--local-path", required=False, help="Local path.")
    parser.add_argument("-r", "--remote-path", required=True, help="Remote path.")
    parser.add_argument("-f", "--force", action="store_true", help="Overwrite local files.")
    parser.add_argument("-j", "--jobs", type=int, default=DEFAULT_CONCURRENCY, help="Number of parallel tasks.")

    args = parser.parse_args()
    logger.info(f"Nextcloud CLI {APP_VERSION}")

    if args.action in ["upload", "download", "download-dir"] and not args.local_path:
        parser.error(f"--local-path is required for {args.action}.")

    sys.exit(0 if asyncio.run(run(args)) else 1)


if __name__ == "__main__":
    main()
