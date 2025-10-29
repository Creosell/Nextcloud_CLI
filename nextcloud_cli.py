# /// script
# dependencies = [
#   "loguru",
#   "dotenv",
#   "nc_py_api",
#   "requests",
#   "urllib3"
# ]
# requires-python = ">=3.9"
# ///

import os
import sys
import argparse
from pathlib import Path

# External libs
from loguru import logger
from dotenv import load_dotenv
from nc_py_api import Nextcloud
from nc_py_api.exceptions import NextcloudException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Logging Setup ---
# Remove default loguru handler to configure our own
logger.remove()
LOG_FILE = "nextcloud_cli.log"

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
    enqueue=True,  # makes logging safe for multiple processes
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
)
logger.info("Application started. Full log is available in {}", LOG_FILE)

# --- Constants and Configuration ---
CHUNK_SIZE = 1024 * 1024  # 1Mb

# Nextcloud WebDAV Retry Strategy
# Retries on server errors (5xx) for both upload (PUT) and download (GET)
retry_strategy = Retry(
    total=3,  # Retry 3 times
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["PUT", "GET"],
)
adapter = HTTPAdapter(max_retries=retry_strategy)


def get_nc_client() -> Nextcloud:
    """Initializes and returns the Nextcloud client from .env credentials."""
    # Load environment variables from .env file
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
        timeout=60,  # Total request timeout
        session_args={
            "verify": True,
            "http_adapter": adapter,
            "session_reuse": True,
        },
    )
    return nc


def ensure_parent_exists(nc: Nextcloud, remote_path: str) -> bool:
    """Create parent directories for the remote path if they do not exist."""
    # Strip leading slash and get parent path object
    path_obj = Path(remote_path.lstrip("/")).parent
    if not path_obj.parts:
        return True  # Root or direct child of root

    current_path = ""
    for part in path_obj.parts:
        current_path = str(Path(current_path) / part)
        try:
            nc.files.mkdir(current_path)
            logger.debug("Created remote directory: {}", current_path)
        except NextcloudException as e:
            # Check for "path already exists" or similar 4xx error codes
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
    """Uploads a single local file to a remote path in Nextcloud."""
    remote_path = remote_path.lstrip("/")

    # 1. Ensure remote parent folders exist
    if not ensure_parent_exists(nc, remote_path):
        logger.error("Failed to ensure parent directories exist for: {}", remote_path)
        return False

    try:
        # 2. Perform upload (Nextcloud API overwrites by default)
        with open(local_path, "rb") as f:
            nc.files.upload_stream(remote_path, f, chunk_size=CHUNK_SIZE)

        logger.info("Upload successful: '{}' -> '{}'", local_path, remote_path)
        return True

    except FileNotFoundError:
        logger.error("Local file not found: {}", local_path)
        return False
    except NextcloudException as e:
        logger.error("Nextcloud upload failed for '{}': {}", remote_path, e)
        return False
    except Exception as e:
        logger.error("Unexpected upload error for '{}': {}", local_path, e)
        return False


def download_file(nc: Nextcloud, remote_path: str, local_path: str, force_overwrite: bool) -> bool:
    """Downloads a single remote file to a local path."""
    remote_path = remote_path.lstrip("/")
    local_path_obj = Path(local_path)

    # 1. Check local file existence and overwrite flag
    if local_path_obj.exists() and not force_overwrite:
        logger.error("Local file exists and --force not specified: {}", local_path)
        return False

    try:
        # 2. Ensure local parent directory exists
        local_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # 3. Perform download
        with local_path_obj.open("wb") as f:
            nc.files.download_stream(remote_path, f)

        logger.info("Download successful: '{}' -> '{}'", remote_path, local_path)
        return True

    except NextcloudException as e:
        if "404" in str(e):
            logger.error("Remote file not found in Nextcloud: {}", remote_path)
        else:
            logger.error("Nextcloud download failed for '{}': {}", remote_path, e)
        return False
    except Exception as e:
        logger.error("Unexpected download error for '{}': {}", remote_path, e)
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
        # Note: Nextcloud API overwrites by default. --force is mainly relevant for download.
        logger.info("Starting UPLOAD operation.")
        success = upload_file(nc_client, args.local_path, args.remote_path)

    elif args.action == "download":
        logger.info("Starting DOWNLOAD operation.")
        # args.force is used here to potentially overwrite the local file
        success = download_file(nc_client, args.remote_path, args.local_path, args.force)

    if success:
        logger.info("Operation successfully completed.")
        sys.exit(0)
    else:
        logger.error("Operation failed. See log file for details: {}", LOG_FILE)
        sys.exit(1)


if __name__ == "__main__":
    main()