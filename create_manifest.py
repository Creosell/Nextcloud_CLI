# create_manifest.py
import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
import concurrent.futures  # <-- NEW: Import the thread pool executor

# --- Dependencies for this script ---
# You must install these: pip install loguru nc-py-api requests urllib3
try:
    from loguru import logger
    from nc_py_api import Nextcloud, NextcloudException
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("Error: Missing required libraries.")
    print("Please run: pip install loguru nc-py-api requests urllib3")
    sys.exit(1)

# --- !! HARDCODED NEXTCLOUD CONFIGURATION !! ---
NC_SERVER_URL = "https://next-qa.sdsz.dev"
NC_USER = "pavel.sheshko"
NC_PASSWORD = "9wKet-2z4tc-pKqHA-TniPy-LQxDB"
# -----------------------------------------------

# --- NEW: Configuration for parallel uploads ---
MAX_WORKERS = 20  # Number of parallel upload threads
# -----------------------------------------------


# --- Logging Setup ---
logger.remove()
LOG_FOLDER = Path("logs")
os.makedirs(LOG_FOLDER, exist_ok=True)
LOG_FILE = LOG_FOLDER / "manifest_creator_log.txt"

logger.add(
    sys.stderr,
    level="INFO",
    format="{time:HH:mm:ss} | <level>{level: <8}</level> | {message}",
    colorize=True,
)
logger.add(
    LOG_FILE,
    level="DEBUG",
    rotation="10 MB",
    compression="zip",
    enqueue=True,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
)

# --- Nextcloud Helper Functions (Self-contained) ---

retry_strategy = Retry(
    total=3,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["PUT", "GET"],
)
adapter = HTTPAdapter(max_retries=retry_strategy)


def get_nc_client() -> Nextcloud:
    """Initializes and returns the Nextcloud client from hardcoded credentials."""
    if NC_SERVER_URL == "https://your-nextcloud-server.com" or not NC_USER or not NC_PASSWORD:
        logger.error("Nextcloud credentials are not configured.")
        logger.error("Please edit this script and set NC_SERVER_URL, NC_USER, and NC_PASSWORD.")
        raise ValueError("Nextcloud credentials missing or not configured.")

    logger.debug("Initializing Nextcloud client for: {}", NC_SERVER_URL)
    nc = Nextcloud(
        nextcloud_url=NC_SERVER_URL,
        nc_auth_user=NC_USER,
        nc_auth_pass=NC_PASSWORD,
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
        # Force POSIX (forward) slashes for the API request
        current_path = (Path(current_path) / part).as_posix()

        try:
            nc.files.mkdir(current_path)
            logger.debug("Created remote directory: {}", current_path)
        except NextcloudException as e:
            # We must also catch '423' (Locked) error.
            # This happens when two threads try to create the same parent dir simultaneously.
            # We can safely ignore it, as it means the dir is being created by another thread.
            if "already exists" in str(e) or "405" in str(e) or "409" in str(e) or "423" in str(e):
                logger.debug("Remote directory already exists (or is being created by another thread): {}",
                             current_path)
            else:
                logger.warning("Failed to create directory: {}, error: {}", current_path, e)
                return False
        except Exception as e:
            logger.warning("Failed to create directory: {}, unexpected error: {}", current_path, e)
            return False
    return True


def upload_file(nc: Nextcloud, local_path: str, remote_path: str) -> bool:
    """
    Uploads a single local file to a remote path in Nextcloud.
    This function is now designed to be thread-safe.
    """
    remote_path = remote_path.replace("\\", "/").lstrip("/")

    # This check is thread-safe, as the 'except' block handles race conditions
    if not ensure_parent_exists(nc, remote_path):
        logger.error("Failed to ensure parent directories exist for: {}", remote_path)
        return False

    try:
        with open(local_path, "rb") as f:
            file_content = f.read()

        nc.files.upload(remote_path, file_content)
        # Use DEBUG here to avoid flooding the console
        logger.debug("Upload successful: '{}' -> '{}'".format(local_path, remote_path))
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


# --- SHA256 Helper ---

def get_sha256(file_path):
    """Calculates the SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# --- Manifest Creation Functions ---

def create_zip_manifest(zip_file, product_id, version):
    """
    Generates a 'zip' mode manifest.
    Returns (manifest_path, files_to_upload, source_base_dir) or (None, None, None) on failure.
    """
    zip_path = Path(zip_file)
    if not zip_path.is_file():
        logger.error(f"Error: File not found: {zip_file}")
        return None, None, None

    logger.info(f"Generating 'zip' manifest for: {zip_file}")
    file_name = zip_path.name
    file_hash = get_sha256(zip_path)
    base_url = f"modules/{product_id}/{version}"

    manifest = {
        "product_id": product_id,
        "version": version,
        "base_url": base_url,
        "package_mode": "zip",
        "files": [
            {
                "path": file_name,
                "hash": file_hash
            }
        ]
    }

    output_dir = Path("manifests")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{product_id}_{version}.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    logger.success(f"Manifest created: {output_path}")
    return output_path, [zip_path], zip_path.parent


def create_files_manifest(build_dir, product_id, version):
    """
    Generates a 'files' mode manifest.
    Returns (manifest_path, files_to_upload, source_base_dir) or (None, None, None) on failure.
    """
    build_path = Path(build_dir)
    if not build_path.is_dir():
        logger.error(f"Error: Directory not found: {build_dir}")
        return None, None, None

    base_url = f"modules/{product_id}/{version}"
    manifest_files = []
    upload_file_list = []

    logger.info(f"Scanning directory: {build_path}...")
    for file_path in build_path.rglob('*'):
        if file_path.is_file():
            upload_file_list.append(file_path)
            relative_path = file_path.relative_to(build_path)
            file_hash = get_sha256(file_path)
            manifest_file = {
                "path": relative_path.as_posix(),
                "hash": file_hash
            }
            manifest_files.append(manifest_file)

    manifest = {
        "product_id": product_id,
        "version": version,
        "base_url": base_url,
        "package_mode": "files",
        "files": manifest_files
    }

    output_dir = Path("manifests")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{product_id}_{version}.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    logger.success(f"Manifest created: {output_path}")
    return output_path, upload_file_list, build_path


# --- Upload Logic (Modified for Parallelism) ---

def upload_to_nextcloud(nc_client, manifest_path, files_to_upload, product_id, version, mode, source_base_dir):
    """Handles the complete upload process for manifest and application files."""

    # 1. Upload the manifest file (sequentially)
    logger.info("--- Starting Manifest Upload ---")
    remote_manifest_dir = f"/SCT/Updater/versions/{product_id}"
    remote_manifest_path = f"{remote_manifest_dir}/{manifest_path.name}"

    logger.info(f"Uploading manifest to: {remote_manifest_path}")
    if not upload_file(nc_client, str(manifest_path), remote_manifest_path):
        logger.error("Failed to upload manifest file. Aborting further uploads.")
        return False
    logger.success("Manifest upload complete.")

    # 2. Upload the application files
    logger.info("--- Starting Application Files Upload ---")
    remote_modules_base = f"/SCT/Updater/modules/{product_id}/{version}"

    if mode == 'zip':
        # ZIP mode is just one file, no parallelism needed
        if not files_to_upload:
            logger.error("No zip file found to upload.")
            return False

        zip_file_path = files_to_upload[0]
        remote_path = f"{remote_modules_base}/{zip_file_path.name}"
        logger.info(f"Uploading file: {zip_file_path.name} to {remote_path}")
        if not upload_file(nc_client, str(zip_file_path), remote_path):
            return False  # Failed zip upload

    elif mode == 'files':
        # --- NEW: Parallel Upload Logic ---
        if not files_to_upload:
            logger.warning("No files found in source directory to upload.")
            return True

        total_files = len(files_to_upload)
        logger.info(f"Queuing {total_files} files for parallel upload using {MAX_WORKERS} workers...")

        failed_uploads = []

        # Use ThreadPoolExecutor to manage parallel uploads
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Create a dictionary to map futures to their file paths for logging
            futures_map = {}
            for local_path in files_to_upload:
                relative_path = local_path.relative_to(source_base_dir)
                remote_path = f"{remote_modules_base}/{relative_path.as_posix()}"

                # Submit the upload_file task to the pool
                future = executor.submit(upload_file, nc_client, str(local_path), remote_path)
                futures_map[future] = local_path

            # Process results as they are completed
            for i, future in enumerate(concurrent.futures.as_completed(futures_map)):
                local_path = futures_map[future]
                relative_path_str = local_path.relative_to(source_base_dir).as_posix()

                try:
                    success = future.result()  # Get result (True or False)
                    if success:
                        logger.success(f"({i + 1}/{total_files}) Uploaded: {relative_path_str}")
                    else:
                        logger.warning(f"({i + 1}/{total_files}) FAILED: {relative_path_str}")
                        failed_uploads.append(local_path)
                except Exception as exc:
                    logger.error(f"({i + 1}/{total_files}) CRASHED: {relative_path_str} | Error: {exc}")
                    failed_uploads.append(local_path)

        if failed_uploads:
            logger.error(f"--- Upload finished with {len(failed_uploads)} errors. ---")
            return False
        # --- End of Parallel Logic ---

    logger.success("All application files uploaded successfully.")
    return True


# --- Main Execution ---

def main():
    parser = argparse.ArgumentParser(
        description="Create an update manifest and optionally upload to Nextcloud.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "mode",
        choices=["zip", "files"],
        help="Manifest creation mode."
    )
    parser.add_argument(
        "path",
        help="Path to the source (zip file or build directory)."
    )
    parser.add_argument(
        "product_id",
        help="Unique product identifier (e.g., 'nextcloud_cli')."
    )
    parser.add_argument(
        "version",
        help="Version string (e.g., '1.0.1')."
    )
    # --- NEW ARGUMENT ---
    parser.add_argument(
        "--upload-now",
        action="store_true",
        help="Bypass the (y/n) prompt and upload immediately."
    )

    args = parser.parse_args()

    manifest_path = None
    files_to_upload = []
    source_base_dir = None

    if args.mode == 'zip':
        manifest_path, files_to_upload, source_base_dir = create_zip_manifest(
            args.path, args.product_id, args.version
        )
    elif args.mode == 'files':
        manifest_path, files_to_upload, source_base_dir = create_files_manifest(
            args.path, args.product_id, args.version
        )

    if not manifest_path:
        logger.error("Manifest creation failed. Exiting.")
        sys.exit(1)

    # --- MODIFIED: Ask for Upload (or skip if --upload-now) ---
    upload_confirmed = False
    if args.upload_now:
        logger.info("--upload-now flag detected, proceeding directly to upload.")
        upload_confirmed = True
    else:
        try:
            answer = input(
                f"Do you want to upload {len(files_to_upload)} file(s) and the manifest to Nextcloud? (y/n): ").strip().lower()
            if answer == 'y':
                upload_confirmed = True
        except KeyboardInterrupt:
            logger.warning("\nOperation cancelled by user.")
            sys.exit(1)

    if not upload_confirmed:
        logger.info("Skipping upload. Exiting.")
        sys.exit(0)
    # --- END MODIFIED BLOCK ---

    # --- Proceed with Upload (no changes below) ---
    logger.info("Connecting to Nextcloud...")
    try:
        nc_client = get_nc_client()
        logger.debug(f"Testing connection by fetching user: {NC_USER}")
        nc_client.users.get_user(NC_USER)
        logger.success("Nextcloud connection established.")
    except ValueError as e:
        logger.critical(f"Aborting upload: {e}")
        sys.exit(1)
    except NextcloudException as e:
        logger.critical(f"Nextcloud connection failed (check credentials or URL): {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Could not initialize or connect to Nextcloud client: {e}")
        sys.exit(1)

    success = upload_to_nextcloud(
        nc_client,
        manifest_path,
        files_to_upload,
        args.product_id,
        args.version,
        args.mode,
        source_base_dir
    )

    if success:
        logger.success("Operation successfully completed.")
        sys.exit(0)
    else:
        logger.error("Operation failed during upload. See log for details: {}", LOG_FILE)
        sys.exit(1)


if __name__ == "__main__":
    main()