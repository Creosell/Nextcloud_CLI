import os
import sys
import argparse
import time
from pathlib import Path

# External libs
from loguru import logger
from dotenv import load_dotenv
from nc_py_api import Nextcloud, NextcloudException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Constants for Directory Creation Retry
MAX_DIR_CREATE_RETRIES = 3
DIR_CREATE_RETRY_DELAY_SEC = 1.0 # 1 second delay

# Constants for Network Operation Retry
MAX_NETWORK_RETRIES = 2  # Max attempts for file transfer itself
NETWORK_RETRY_DELAY_SEC = 2.0  # 2 seconds delay

# --- Logging Setup ---
logger.remove()

LOG_FOLDER = Path("logs")
os.makedirs(LOG_FOLDER, exist_ok=True)
LOG_FILE = LOG_FOLDER / "nextcloud_cli_log.txt"

APP_VERSION = "1.0.0"

# Add a handler for the console output (INFO level)
logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | {message}", level="INFO")

# Add a handler for the file output (DEBUG level for full detail)
logger.add(
    LOG_FILE,
    level="DEBUG",
    rotation="5 MB",
    compression="zip",
    enqueue=True,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
)

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

    url = os.environ.get("NC_SERVER_URL_QC")
    user = os.environ.get("NC_USER_QC")
    password = os.environ.get("NC_PASSWORD_QC")

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

    remote_path = remote_path.replace("\\", "/")
    path_parts = remote_path.lstrip("/").split('/')
    dir_parts = path_parts[:-1]

    current_path = ""
    for part in dir_parts:
        current_path = (current_path + "/" + part).lstrip('/')

        # --- RETRY LOGIC FOR MKCOL (Directory Creation) ---
        for attempt in range(MAX_DIR_CREATE_RETRIES):
            try:
                nc.files.mkdir(current_path)
                logger.debug("Created remote directory: {}", current_path)
                break  # Success: break out of the retry loop

            except NextcloudException as e:
                error_str = str(e)

                # Success/Ignorable Errors: Directory already exists (409 Conflict) or 405 Method Not Allowed
                if "already exists" in error_str or "409" in error_str or "405" in error_str:
                    logger.debug("Remote directory already exists/uncreatable (Code 405/409): {}", current_path)
                    break  # Success: The directory exists, move on

                # Failure due to locking/race condition (423 Locked)
                elif "423" in error_str:
                    if attempt < MAX_DIR_CREATE_RETRIES - 1:
                        logger.warning("Directory locked (423). Retrying in {}s for: {}", DIR_CREATE_RETRY_DELAY_SEC,
                                       current_path)
                        time.sleep(DIR_CREATE_RETRY_DELAY_SEC)
                        continue  # Go to next attempt
                    else:
                        logger.error("Failed to create directory after {} attempts: {}, error: {}",
                                     MAX_DIR_CREATE_RETRIES, current_path, e)
                        return False  # Max retries reached

                # Critical Failures
                else:
                    logger.warning("Failed to create directory: {}, unexpected error: {}", current_path, e)
                    return False

            except Exception as e:
                # Handle connection errors or other exceptions
                logger.warning("Failed to create directory: {}, unexpected error: {}", current_path, e)
                return False

    return True


def upload_file(nc: Nextcloud, local_path: str, remote_path: str) -> bool:
    """Uploads a single local file to a remote path in Nextcloud using direct content upload."""
    remote_path = remote_path.replace("\\", "/").lstrip("/")

    if not ensure_parent_exists(nc, remote_path):
        logger.error("Failed to ensure parent directories exist for: {}", remote_path)
        return False

    try:
        with open(local_path, "rb") as f:
            file_content = f.read()

    except FileNotFoundError:
        logger.error("Local file not found: {}", local_path)
        return False
    except Exception as e:
        logger.error("Unexpected error reading local file '{}': {}", local_path, e)
        return False

    # --- RETRY LOGIC FOR UPLOAD ---
    for attempt in range(MAX_NETWORK_RETRIES + 1):
        try:
            nc.files.upload(remote_path, file_content)
            logger.info("Upload successful: '{}' -> '{}'".format(local_path, remote_path))
            return True

        except NextcloudException as e:
            error_str = str(e)

            # Check for temporary network/server errors (e.g., 5xx status codes)
            if any(status in error_str for status in ["500", "502", "503", "504"]):
                if attempt < MAX_NETWORK_RETRIES:
                    logger.warning(
                        "Upload failed due to temporary server error. Retrying in {}s (Attempt {}/{}) for: {}",
                        NETWORK_RETRY_DELAY_SEC, attempt + 1, MAX_NETWORK_RETRIES + 1, remote_path
                    )
                    time.sleep(NETWORK_RETRY_DELAY_SEC)
                    continue  # Retry loop continues
                else:
                    logger.error("Upload failed permanently after {} attempts for '{}': {}", MAX_NETWORK_RETRIES + 1,
                                 remote_path, e)
                    return False
            else:
                # Permanent failure (e.g., 401 Unauthorized, 403 Forbidden)
                logger.error("Nextcloud upload failed for '{}': {}", remote_path, e)
                return False

        except Exception as e:
            # Catch other unexpected network/request exceptions
            if attempt < MAX_NETWORK_RETRIES:
                logger.warning("Network error during upload. Retrying in {}s (Attempt {}/{}): {}",
                               NETWORK_RETRY_DELAY_SEC, attempt + 1, MAX_NETWORK_RETRIES + 1, e)
                time.sleep(NETWORK_RETRY_DELAY_SEC)
                continue
            else:
                logger.error("Unexpected upload error for '{}': {}".format(local_path, e))
                return False

    return False  # Should be unreachable if logic is sound


def download_file(nc: Nextcloud, remote_path: str, local_path: str, force_overwrite: bool) -> bool:
    """Downloads a single remote file to a local path using direct content download."""
    remote_path = remote_path.replace("\\", "/").lstrip("/")
    local_path_obj = Path(local_path)

    if local_path_obj.exists() and not force_overwrite:
        logger.error("Local file exists and --force not specified: {}", local_path)
        return False

    # --- RETRY LOGIC FOR DOWNLOAD ---
    for attempt in range(MAX_NETWORK_RETRIES + 1):
        try:
            # 1. Ensure local parent directories exist
            local_path_obj.parent.mkdir(parents=True, exist_ok=True)

            # 2. Use nc.files.download to get content as bytes
            file_content_bytes = nc.files.download(remote_path)

            # 3. Write the bytes directly to the local file
            with local_path_obj.open("wb") as f:
                f.write(file_content_bytes)

            logger.info(
                "Download successful: '{}' -> '{}'. Local file saved as raw bytes. Please use a UTF-8 aware editor.".format(
                    remote_path, local_path))
            return True  # Success: Exit the function

        except NextcloudException as e:
            error_str = str(e)

            # 404 Not Found is a permanent, non-retriable error
            if "404" in error_str:
                logger.error("Remote file not found in Nextcloud: {}", remote_path)
                return False

            # Temporary network/server errors (e.g., 5xx status codes)
            if any(status in error_str for status in ["500", "502", "503", "504"]):
                if attempt < MAX_NETWORK_RETRIES:
                    logger.warning("Download failed due to temporary server error. Retrying in {}s (Attempt {}/{}).",
                                   NETWORK_RETRY_DELAY_SEC, attempt + 1, MAX_NETWORK_RETRIES + 1)
                    time.sleep(NETWORK_RETRY_DELAY_SEC)
                    continue  # Retry loop continues
                else:
                    logger.error("Download failed permanently after {} attempts for '{}': {}", MAX_NETWORK_RETRIES + 1,
                                 remote_path, e)
                    return False
            else:
                # Other permanent failures (e.g., 401, 403)
                logger.error("Nextcloud download failed for '{}': {}", remote_path, e)
                return False

        except Exception as e:
            # Catch other unexpected errors (e.g., network timeout)
            if attempt < MAX_NETWORK_RETRIES:
                logger.warning("Network error during download. Retrying in {}s (Attempt {}/{}): {}",
                               NETWORK_RETRY_DELAY_SEC, attempt + 1, MAX_NETWORK_RETRIES + 1, e)
                time.sleep(NETWORK_RETRY_DELAY_SEC)
                continue
            else:
                logger.error("Unexpected download error for '{}': {}".format(remote_path, e))
                return False

    return False  # Should be unreachable


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

    logger.info(f"Nextcloud CLI {APP_VERSION}")

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