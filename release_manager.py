import os
import sys
import json
import hashlib
import argparse
import subprocess
import zipfile
import concurrent.futures
from pathlib import Path

try:
    from loguru import logger
    from nc_py_api import Nextcloud, NextcloudException
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    sys.exit("Missing libs. Run: pip install loguru nc-py-api requests urllib3")

# --- CONFIGURATION ---
NC_URL = "https://next-qa.sdsz.dev"
NC_USER = "pavel.sheshko"
NC_PASS = "9wKet-2z4tc-pKqHA-TniPy-LQxDB"
MAX_WORKERS = 20

# --- LOGGING ---
logger.remove()
logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | {message}", level="INFO")
logger.add("release.log", rotation="5 MB", level="DEBUG")

# --- GLOBAL CACHE ---
_DIR_CACHE = set()


# --- HELPERS ---

def get_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(cmd: list) -> bool:
    try:
        logger.info(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True, encoding='utf-8')
        return True
    except subprocess.CalledProcessError:
        return False


def get_nc_client() -> Nextcloud:
    retry = Retry(total=3, status_forcelist=[500, 502, 503, 504], allowed_methods=["PUT", "GET", "MKCOL"])
    adapter = HTTPAdapter(max_retries=retry)
    nc = Nextcloud(nextcloud_url=NC_URL, nc_auth_user=NC_USER, nc_auth_pass=NC_PASS,
                   session_args={"verify": True, "http_adapter": adapter})
    try:
        nc.users.get_user(NC_USER)  # Test auth
        return nc
    except Exception:
        logger.critical("Nextcloud auth failed")
        sys.exit(1)


# --- CORE LOGIC ---

def ensure_remote_dir(nc: Nextcloud, remote_path: str):
    """Recursively creates directories with caching."""
    remote_path = remote_path.replace("\\", "/").lstrip("/")
    parent = str(Path(remote_path).parent).replace("\\", "/")

    if parent == "." or parent in _DIR_CACHE:
        return

    parts = parent.split("/")
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        if current in _DIR_CACHE: continue

        try:
            nc.files.mkdir(current)
            _DIR_CACHE.add(current)
        except NextcloudException as e:
            err = str(e)
            if any(x in err for x in ["already exists", "405", "409", "423"]):
                _DIR_CACHE.add(current)
            else:
                logger.warning(f"Mkdir error ({current}): {e}")


def upload_chunked(nc: Nextcloud, local: Path, remote: str) -> bool:
    """Uploads file using a stream."""
    try:
        ensure_remote_dir(nc, remote)
        with open(local, "rb") as f:
            nc.files.upload_stream(remote, f)
        return True
    except Exception as e:
        logger.error(f"Upload failed [{local.name}]: {e}")
        return False


def prepare_package(mode, path, prod_id, ver, temp_dir):
    base_url = f"versions/{prod_id}/{ver}"
    files_map = []
    manifest = {"product_id": prod_id, "version": ver, "base_url": base_url, "package_mode": mode, "files": []}

    if mode == "zip":
        zip_name = f"{prod_id}_{ver}.zip"
        zip_file = temp_dir / zip_name
        logger.info(f"Zipping {path} -> {zip_name}")

        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in path.rglob('*'):
                if f.is_file() and f != zip_file:
                    zf.write(f, f.relative_to(path))

        manifest["files"].append({"path": zip_name, "hash": get_sha256(zip_file)})
        files_map.append((zip_file, zip_name))
    else:
        logger.info(f"Scanning {path}...")
        for f in path.rglob('*'):
            if f.is_file():
                rel = f.relative_to(path).as_posix()
                manifest["files"].append({"path": rel, "hash": get_sha256(f)})
                files_map.append((f, rel))

    man_path = temp_dir / f"{prod_id}_{ver}.json"
    with open(man_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    return man_path, files_map


# --- MAIN ---

def main():
    parser = argparse.ArgumentParser(description="Release Manager")
    parser.add_argument("mode", choices=["zip", "files"])
    parser.add_argument("path", type=Path)
    parser.add_argument("product_id")
    parser.add_argument("version")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()

    if not args.path.exists():
        sys.exit(f"Path not found: {args.path}")

    # 1. BUILD (Optional)
    if args.build:
        spec = f"{args.path.name}.spec"
        # Fixed: using --noconfirm instead of -y
        cmd = [sys.executable, "-m", "PyInstaller", "--distpath", str(args.path.parent),
               "--workpath", str(args.path.parent.parent / "build"), "--clean", "--noconfirm", spec]
        if not run_cmd(cmd): sys.exit(1)

    # 2. PACKAGE
    temp_dir = Path("release_artifacts")
    temp_dir.mkdir(exist_ok=True)
    manifest, upload_list = prepare_package(args.mode, args.path, args.product_id, args.version, temp_dir)

    logger.info(f"Manifest: {manifest.name} | Files: {len(upload_list)}")

    if not args.upload and input("Upload? (y/n): ").lower() != 'y':
        sys.exit(0)

    # 3. UPLOAD
    try:
        nc = get_nc_client()
        remote_root = f"SCT/Updater/versions/{args.product_id}/{args.version}"

        # A. Manifest
        logger.info("Uploading manifest...")
        if not upload_chunked(nc, manifest, f"SCT/Updater/versions/{args.product_id}/{manifest.name}"):
            sys.exit("Manifest upload failed")

        # B. Content
        logger.info(f"Uploading content ({args.mode})...")
        failures = []

        if len(upload_list) == 1:
            local, remote = upload_list[0]
            if not upload_chunked(nc, local, f"{remote_root}/{remote}"): failures.append(local)
        else:
            with concurrent.futures.ThreadPoolExecutor(MAX_WORKERS) as pool:
                # Fixed: Syntax error in f-string and dictionary comprehension
                futures = {pool.submit(upload_chunked, nc, loc, f"{remote_root}/{rem}"): loc for loc, rem in
                           upload_list}
                for fut in concurrent.futures.as_completed(futures):
                    if not fut.result(): failures.append(futures[fut])

        if failures:
            logger.error(f"Failed to upload {len(failures)} files.")
            sys.exit(1)

        logger.success("Done!")

    except Exception as e:
        logger.critical(f"Fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()