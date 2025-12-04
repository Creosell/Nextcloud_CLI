import os
import sys
import argparse
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# External libs
from loguru import logger
from dotenv import load_dotenv
from nc_py_api import Nextcloud, NextcloudException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Constants & Config ---
MAX_DIR_CREATE_RETRIES = 3
DIR_CREATE_RETRY_DELAY_SEC = 1.0
MAX_NETWORK_RETRIES = 2
NETWORK_RETRY_DELAY_SEC = 2.0
APP_VERSION = "1.2.0"
DEFAULT_CONCURRENCY = 5

# --- Logging Setup ---
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

# HTTP Retry Strategy
retry_strategy = Retry(total=3, status_forcelist=[500, 502, 503, 504], allowed_methods=["PUT", "GET"])


def get_nc_client(pool_size: int = DEFAULT_CONCURRENCY) -> Nextcloud:
    """Init Nextcloud client with optimized connection pool for parallelism."""
    load_dotenv()
    url = os.environ.get("NC_SERVER_URL_QC")
    user = os.environ.get("NC_USER_QC")
    password = os.environ.get("NC_PASSWORD_QC")

    if not all([url, user, password]):
        logger.error("Missing credentials in .env.")
        raise ValueError("Nextcloud credentials missing.")

    # Configure adapter with pool size matching threads to avoid handshake overhead
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=pool_size,
        pool_maxsize=pool_size
    )

    return Nextcloud(
        nextcloud_url=url, nc_auth_user=user, nc_auth_pass=password, timeout=60,
        session_args={"verify": True, "http_adapter": adapter, "session_reuse": True}
    )


def list_files_recursive(nc: Nextcloud, remote_path: str) -> list:
    """Recursively list all files in a remote directory."""
    file_list = []
    try:
        items = nc.files.listdir(remote_path)
        for item in items:
            if item.is_dir:
                file_list.extend(list_files_recursive(nc, item.user_path))
            else:
                file_list.append(item.user_path)
    except NextcloudException as e:
        logger.error(f"Failed to list '{remote_path}': {e}")
    return file_list


def ensure_parent_exists(nc: Nextcloud, remote_path: str) -> bool:
    """Recursively create parent directories if missing."""
    remote_path = remote_path.replace("\\", "/")
    path_parts = remote_path.lstrip("/").split('/')[:-1]

    current_path = ""
    for part in path_parts:
        current_path = (current_path + "/" + part).lstrip('/')
        for attempt in range(MAX_DIR_CREATE_RETRIES):
            try:
                nc.files.mkdir(current_path)
                break
            except NextcloudException as e:
                err = str(e)
                if any(x in err for x in ["already exists", "409", "405"]): break
                if "423" in err and attempt < MAX_DIR_CREATE_RETRIES - 1:
                    time.sleep(DIR_CREATE_RETRY_DELAY_SEC)
                    continue
                logger.error(f"Failed to create dir {current_path}: {e}")
                return False
            except Exception:
                return False
    return True


def upload_file(nc: Nextcloud, local_path: str, remote_path: str) -> bool:
    """Upload local file to remote path."""
    remote_path = remote_path.replace("\\", "/").lstrip("/")
    if not ensure_parent_exists(nc, remote_path): return False

    try:
        with open(local_path, "rb") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Read error {local_path}: {e}")
        return False

    for attempt in range(MAX_NETWORK_RETRIES + 1):
        try:
            nc.files.upload(remote_path, content)
            logger.info(f"Uploaded: {local_path} -> {remote_path}")
            return True
        except Exception as e:
            if attempt < MAX_NETWORK_RETRIES:
                time.sleep(NETWORK_RETRY_DELAY_SEC)
            else:
                logger.error(f"Upload failed {remote_path}: {e}")
    return False


def download_file(nc: Nextcloud, remote_path: str, local_path: str, force: bool) -> bool:
    """Download remote file to local path."""
    remote_path = remote_path.replace("\\", "/").lstrip("/")
    local_obj = Path(local_path)

    if local_obj.exists() and not force:
        logger.warning(f"Skipped (exists): {local_path}")
        return False

    for attempt in range(MAX_NETWORK_RETRIES + 1):
        try:
            local_obj.parent.mkdir(parents=True, exist_ok=True)
            content = nc.files.download(remote_path)
            with local_obj.open("wb") as f:
                f.write(content)
            logger.info(f"Downloaded: {remote_path}")
            return True
        except NextcloudException as e:
            if "404" in str(e):
                logger.error(f"Not found: {remote_path}")
                return False
            if attempt < MAX_NETWORK_RETRIES:
                time.sleep(NETWORK_RETRY_DELAY_SEC)
            else:
                logger.error(f"Download failed {remote_path}: {e}")
        except Exception as e:
            if attempt < MAX_NETWORK_RETRIES:
                time.sleep(NETWORK_RETRY_DELAY_SEC)
            else:
                logger.error(f"Error {remote_path}: {e}")
    return False


def download_directory_parallel(nc: Nextcloud, remote_base: str, local_base: str, force: bool,
                                concurrency: int) -> bool:
    """Orchestrates parallel download of a directory."""
    logger.info(f"Scanning remote directory: {remote_base}")
    all_files = list_files_recursive(nc, remote_base)

    if not all_files:
        logger.warning("No files found to download.")
        return True

    logger.info(f"Found {len(all_files)} files. Starting download with {concurrency} threads.")

    tasks = []
    # Use ThreadPoolExecutor for parallel I/O
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for remote_file in all_files:
            # Calculate relative path to maintain structure
            # e.g. remote: /data/imgs/1.jpg, base: /data/ -> rel: imgs/1.jpg
            # local: C:/downloads/ + imgs/1.jpg

            # Normalize paths for calculation
            r_base = remote_base.strip("/")
            r_file = remote_file.strip("/")

            if r_file.startswith(r_base):
                rel_path = r_file[len(r_base):].lstrip("/")
            else:
                rel_path = Path(r_file).name  # Fallback

            local_target = Path(local_base) / rel_path

            # Submit task
            tasks.append(executor.submit(download_file, nc, remote_file, str(local_target), force))

        # Wait for completion
        results = [t.result() for t in as_completed(tasks)]

    success_count = results.count(True)
    logger.info(f"Batch completed: {success_count}/{len(all_files)} files downloaded successfully.")
    return success_count == len(all_files)


def main():
    parser = argparse.ArgumentParser(description="Nextcloud CLI Utility", formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument("action", choices=["upload", "download", "list", "download-dir"], help="Action to perform.")
    parser.add_argument("-l", "--local-path", required=False, help="Local path.")
    parser.add_argument("-r", "--remote-path", required=True, help="Remote path.")
    parser.add_argument("-f", "--force", action="store_true", help="Overwrite local files.")
    parser.add_argument("-j", "--jobs", type=int, default=DEFAULT_CONCURRENCY, help="Number of parallel threads.")

    args = parser.parse_args()
    logger.info(f"Nextcloud CLI {APP_VERSION}")

    if args.action in ["upload", "download", "download-dir"] and not args.local_path:
        parser.error(f"--local-path is required for {args.action}.")

    try:
        # Pass concurrency to client to adjust connection pool size
        nc = get_nc_client(pool_size=args.jobs)
    except Exception:
        sys.exit(1)

    success = True
    if args.action == "upload":
        success = upload_file(nc, args.local_path, args.remote_path)
    elif args.action == "download":
        success = download_file(nc, args.remote_path, args.local_path, args.force)
    elif args.action == "download-dir":
        success = download_directory_parallel(nc, args.remote_path, args.local_path, args.force, args.jobs)
    elif args.action == "list":
        files = list_files_recursive(nc, args.remote_path)
        for f in files: print(f)
        logger.info(f"Found {len(files)} files.")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()