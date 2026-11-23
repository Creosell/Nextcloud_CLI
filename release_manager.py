# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "loguru",
#     "nc-py-api",
#     "requests",
#     "urllib3",
#     "pyinstaller",
#     "python-dotenv",
# ]
# ///

import asyncio
import os
import sys
import json
import hashlib
import argparse
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from loguru import logger
from dotenv import load_dotenv
from nc_py_api import AsyncNextcloud, NextcloudException

# Импортируем PyInstaller напрямую для вызова из кода
import PyInstaller.__main__

load_dotenv(Path(__file__).parent / ".env")

# --- CONFIGURATION ---
NC_URL = os.environ["NC_URL"]
NC_USER = os.environ["NC_USER"]
NC_PASS = os.environ["NC_PASS"]
MAX_WORKERS = 20
UPLOAD_RETRIES = 3

# --- LOGGING ---
logger.remove()
logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | {message}", level="INFO")
logger.add("release.log", rotation="5 MB", level="DEBUG")

# --- GLOBAL CACHE ---
_DIR_CACHE = set()
_DIR_LOCK: asyncio.Lock | None = None


# --- HELPERS ---

def get_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


async def get_nc_client() -> AsyncNextcloud:
    """Creates an authenticated async Nextcloud client; exits the process on auth failure."""
    nc = AsyncNextcloud(nextcloud_url=NC_URL, nc_auth_user=NC_USER, nc_auth_pass=NC_PASS)
    try:
        await nc.users.get_user(NC_USER)  # Test auth
        return nc
    except Exception:
        logger.critical("Nextcloud auth failed")
        sys.exit(1)


# --- CORE LOGIC ---

async def ensure_remote_dir(nc: AsyncNextcloud, remote_path: str):
    """Recursively creates the parent directories of a remote path with caching."""
    parent = PurePosixPath(remote_path.replace("\\", "/")).parent

    if parent.parts in ((), ("/",)) or str(parent) in _DIR_CACHE:
        return

    async with _DIR_LOCK:
        for current in reversed([parent, *parent.parents]):
            current = str(current).lstrip("/")
            if current in ("", ".") or current in _DIR_CACHE: continue

            try:
                await nc.files.mkdir(current)
                _DIR_CACHE.add(current)
            except NextcloudException as e:
                if any(x in str(e) for x in ["already exists", "405", "409", "423"]):
                    _DIR_CACHE.add(current)
                else:
                    logger.warning(f"Mkdir error ({current}): {e}")


async def upload_chunked(nc: AsyncNextcloud, local: Path, remote: str) -> bool:
    """Uploads a file as a stream, retrying on failure."""
    for attempt in range(1, UPLOAD_RETRIES + 1):
        try:
            await ensure_remote_dir(nc, remote)
            await nc.files.upload_stream(remote, local)
            return True
        except Exception as e:
            if attempt == UPLOAD_RETRIES:
                logger.error(f"Upload failed [{local.name}]: {e}")
                return False
            logger.debug(f"Upload retry {attempt} [{local.name}]: {e}")
            await asyncio.sleep(attempt)
    return False


def prepare_package(mode, path, include_path, prod_id, ver, temp_dir):
    base_url = f"versions/{prod_id}/{ver}"
    files_map = []
    manifest = {"product_id": prod_id, "version": ver, "base_url": base_url, "package_mode": mode, "files": []}

    sources = [(path, False)]

    if include_path:
        if include_path.exists():
            sources.append((include_path, True))
            logger.info(f"Including directory as subfolder: {include_path.name}")
        else:
            logger.warning(f"Include path ignored (not found): {include_path}")

    if mode == "zip":
        zip_name = f"{prod_id}_{ver}.zip"
        zip_file = temp_dir / zip_name
        logger.info(f"Zipping content to -> {zip_name}")

        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for src_path, keep_folder_name in sources:
                for f in src_path.rglob('*'):
                    if f.is_file() and f != zip_file:
                        rel = f.relative_to(src_path)
                        arcname = Path(src_path.name) / rel if keep_folder_name else rel
                        zf.write(f, arcname)

        manifest["files"].append({"path": zip_name, "hash": get_sha256(zip_file)})
        files_map.append((zip_file, zip_name))
    else:
        logger.info("Scanning files...")
        for src_path, keep_folder_name in sources:
            for f in src_path.rglob('*'):
                if f.is_file():
                    rel = f.relative_to(src_path)
                    final_rel_path = (Path(src_path.name) / rel).as_posix() if keep_folder_name else rel.as_posix()

                    if any(d['path'] == final_rel_path for d in manifest['files']):
                        logger.warning(f"Duplicate file path detected and skipped: {final_rel_path}")
                        continue

                    manifest["files"].append({"path": final_rel_path, "hash": get_sha256(f)})
                    files_map.append((f, final_rel_path))

    man_path = temp_dir / f"{prod_id}_{ver}.json"
    with open(man_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    return man_path, files_map


# --- MAIN ---

def main():
    parser = argparse.ArgumentParser(description="Release Manager")
    parser.add_argument("mode", choices=["zip", "files"])
    parser.add_argument("path", type=Path, help="Main build directory (contents go to root)")
    parser.add_argument("product_id")
    parser.add_argument("version")
    parser.add_argument("--include", type=Path, help="Additional folder (preserved as subfolder)")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()

    if not args.path.exists():
        sys.exit(f"Main path not found: {args.path}")

    # 1. BUILD (Optional)
    if args.build:
        # Convert to absolute paths to avoid confusion
        spec_file = args.path.name + ".spec"
        dist_path = args.path.parent.resolve()
        work_path = (args.path.parent.parent / "build").resolve()

        logger.info(f"Starting PyInstaller build for {spec_file}...")
        logger.info(f"Dist: {dist_path} | Work: {work_path}")

        try:
            # Use PyInstaller API directly instead of subprocess to avoid distutils/path conflicts
            PyInstaller.__main__.run([
                spec_file,
                "--distpath", str(dist_path),
                "--workpath", str(work_path),
                "--clean",
                "--noconfirm"
            ])
            logger.success("Build complete.")
        except SystemExit as e:
            # PyInstaller uses sys.exit() on completion. We catch it to continue the script.
            if e.code != 0:
                logger.error("PyInstaller failed.")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Build crashed: {e}")
            sys.exit(1)

    # 2. PACKAGE
    temp_dir = Path("release_artifacts")
    temp_dir.mkdir(exist_ok=True)

    try:
        manifest, upload_list = prepare_package(
            args.mode, args.path, args.include, args.product_id, args.version, temp_dir
        )
    except Exception as e:
        logger.critical(f"Packaging failed: {e}")
        sys.exit(1)

    logger.info(f"Manifest: {manifest.name} | Files to upload: {len(upload_list)}")

    if not args.upload and input("Upload? (y/n): ").lower() != 'y':
        sys.exit(0)

    # 3. UPLOAD
    try:
        asyncio.run(upload_all(args, manifest, upload_list))
    except SystemExit:
        raise
    except Exception as e:
        logger.critical(f"Fatal: {e}")
        sys.exit(1)


async def upload_all(args, manifest: Path, upload_list: list):
    """Uploads the manifest and then the package content with bounded concurrency."""
    global _DIR_LOCK
    _DIR_LOCK = asyncio.Lock()

    nc = await get_nc_client()
    remote_root = f"SCT/Updater/versions/{args.product_id}/{args.version}"

    # A. Manifest
    logger.info("Uploading manifest...")
    if not await upload_chunked(nc, manifest, f"SCT/Updater/versions/{args.product_id}/{manifest.name}"):
        sys.exit("Manifest upload failed")

    # B. Content
    logger.info(f"Uploading content ({args.mode})...")
    sem = asyncio.Semaphore(MAX_WORKERS)

    async def worker(loc: Path, rem: str) -> bool:
        async with sem:
            return await upload_chunked(nc, loc, f"{remote_root}/{rem}")

    results = await asyncio.gather(*(worker(loc, rem) for loc, rem in upload_list))
    failures = [loc for (loc, _), ok in zip(upload_list, results) if not ok]

    if failures:
        logger.error(f"Failed to upload {len(failures)} files.")
        sys.exit(1)

    logger.success("Done!")


if __name__ == "__main__":
    main()