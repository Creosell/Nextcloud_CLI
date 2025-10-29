import os
import sys
import argparse
from pathlib import Path

# External libs
from loguru import logger
from dotenv import load_dotenv
from nc_py_api import Nextcloud, NextcloudException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Logging Setup ---
logger.remove()

LOG_FOLDER = Path("logs")
os.makedirs(LOG_FOLDER, exist_ok=True)
LOG_FILE = LOG_FOLDER / "nextcloud_cli_log.txt"

# Add a handler for the console output (INFO level)
logger.add(
    sys.stderr,
    level="INFO",
    format="{time:HH:mm:ss} | <level>{level: <8}</level> | {message}",
    colorize=True,
)

# Add a handler for the file output (DEBUG level for full detail)
logger.add(
    LOG_FILE,
    level="DEBUG",
    rotation="10 MB",
    compression="zip",
    enqueue=True,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
)
logger.info("Application started. Full log is available in {}", LOG_FILE)

# --- Constants and Configuration ---

# Nextcloud WebDAV Retry Strategy
retry_strategy = Retry(
    total=3,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["PUT", "GET"],
)
adapter = HTTPAdapter(max_retries=retry_strategy)


def get_nc_client() -> Nextcloud:
    """Initializes and returns the Nextcloud client from .env credentials."""
    load_dotenv()

    url = os.environ.get("NC_SERVER_URL")
    user = os.environ.get("NC_USER")
    password = os.environ.get("NC_PASSWORD")

    if not all([url, user, password]):
        logger.error("Missing Nextcloud credentials in environment or .env file.")
        raise ValueError("Nextcloud credentials missing.")

    logger.debug("Initializing Nextcloud client for: {}", url)
    nc = Nextcloud(
        nextcloud_url=url,
        nc_auth_user=user,
        nc_auth_pass=password,
        timeout=60,
        session_args={
            "verify": True,
            "http_adapter": adapter,
            "session_reuse": True,
        },
    )
    return nc


def ensure_parent_exists(nc: Nextcloud, remote_path: str) -> bool:
    """Create parent directories for the remote path if they do not exist."""
    path_obj = Path(remote_path.lstrip("/")).parent
    if not path_obj.parts:
        return True

    current_path = ""
    for part in path_obj.parts:
        current_path = str(Path(current_path) / part)
        try:
            nc.files.mkdir(current_path)
            logger.debug("Created remote directory: {}", current_path)
        except NextcloudException as e:
            if "already exists" in str(e) or "405" in str(e) or "409" in str(e):
                logger.debug("Remote directory already exists: {}", current_path)
            else:
                logger.warning("Failed to create directory: {}, error: {}", current_path, e)
                return False
        except Exception as e:
            logger.warning("Failed to create directory: {}, unexpected error: {}", current_path, e)
            return False
    return True


def upload_file(nc: Nextcloud, local_path: str, remote_path: str) -> bool:
    """Uploads a single local file to a remote path in Nextcloud using direct content upload."""
    # Path Normalization: replace backslashes with forward slashes
    remote_path = remote_path.replace("\\", "/")

    remote_path = remote_path.lstrip("/")

    if not ensure_parent_exists(nc, remote_path):
        logger.error("Failed to ensure parent directories exist for: {}", remote_path)
        return False

    try:
        # Read file content as raw bytes
        with open(local_path, "rb") as f:
            file_content = f.read()

        # Use the simplified API
        nc.files.upload(remote_path, file_content)

        logger.info("Upload successful: '{}' -> '{}'".format(local_path, remote_path))
        return True

    except FileNotFoundError:
        logger.error("Local file not found: {}", local_path)
        return False
    except NextcloudException as e:
        logger.error("Nextcloud upload failed for '{}': {}", remote_path, e)
        return False
    except Exception as e:
        logger.error("Unexpected upload error for '{}': {}".format(local_path, e))
        return False


def download_file(nc: Nextcloud, remote_path: str, local_path: str, force_overwrite: bool) -> bool:
    """Downloads a single remote file to a local path using direct content download."""
    # Path Normalization: replace backslashes with forward slashes
    remote_path = remote_path.replace("\\", "/")

    remote_path = remote_path.lstrip("/")
    local_path_obj = Path(local_path)

    if local_path_obj.exists() and not force_overwrite:
        logger.error("Local file exists and --force not specified: {}", local_path)
        return False

    try:
        # 1. Ensure local parent directories exist
        local_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # 2. Use nc.files.download to get content as bytes (most reliable method)
        file_content_bytes = nc.files.download(remote_path)

        # 3. Write the bytes directly to the local file
        with local_path_obj.open("wb") as f:
            f.write(file_content_bytes)

        logger.info(
            "Download successful: '{}' -> '{}'. Local file saved as raw bytes. Please use a UTF-8 aware editor.".format(
                remote_path, local_path))
        return True

    except NextcloudException as e:
        if "404" in str(e):
            logger.error("Remote file not found in Nextcloud: {}", remote_path)
        else:
            logger.error("Nextcloud download failed for '{}': {}", remote_path, e)
        return False
    except Exception as e:
        logger.error("Unexpected download error for '{}': {}".format(remote_path, e))
        return False


# --- Main Application Logic ---

def main():
    """Main function to parse arguments and execute the action."""
    parser = argparse.ArgumentParser(
        description="Nextcloud CLI Uploader/Downloader Utility.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "action",
        choices=["upload", "download"],
        help="Action to perform: 'upload' or 'download'."
    )
    parser.add_argument(
        "-l", "--local-path",
        required=True,
        help="Local file path."
    )
    parser.add_argument(
        "-r", "--remote-path",
        required=True,
        help="Remote Nextcloud path (e.g., /config/my_file.json)."
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force overwrite of the local file on download (Nextcloud overwrites remote files by default)."
    )

    args = parser.parse_args()

    try:
        nc_client = get_nc_client()
    except ValueError:
        logger.critical("Aborting operation due to missing credentials.")
        sys.exit(1)
    except Exception as e:
        logger.critical("Could not initialize Nextcloud client: {}", e)
        sys.exit(1)

    success = False

    if args.action == "upload":
        logger.info("Starting UPLOAD operation.")
        success = upload_file(nc_client, args.local_path, args.remote_path)

    elif args.action == "download":
        logger.info("Starting DOWNLOAD operation.")
        success = download_file(nc_client, args.remote_path, args.local_path, args.force)

    if success:
        logger.info("Operation successfully completed.")
        sys.exit(0)
    else:
        logger.error("Operation failed. See log file for details: {}", LOG_FILE)
        sys.exit(1)


if __name__ == "__main__":
    main()