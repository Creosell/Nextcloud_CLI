# create_manifest.py
import os
import sys
import json
import hashlib
from pathlib import Path

# --- Configuration ---
# You can change these default values or pass them as arguments
DEFAULT_PRODUCT_ID = "nextcloud_uploader"
DEFAULT_VERSION = "1.0.0"
DEFAULT_BASE_URL = "files/uploader/1.0.0"


# --- Functions ---

def get_sha256(file_path):
    """Calculates the SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        # Read in 4K chunks
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def create_manifest(build_dir, product_id, version, base_url):
    """Generates the file manifest for a given build directory."""

    build_path = Path(build_dir)
    if not build_path.is_dir():
        print(f"Error: Directory not found: {build_dir}")
        return

    manifest_files = []

    print(f"Scanning directory: {build_path}...")

    # Use rglob() to recursively find all files
    for file_path in build_path.rglob('*'):
        if file_path.is_file():
            # Get the relative path from the build_dir root
            # e.g., "lib/loguru/logger.pyc"
            relative_path = file_path.relative_to(build_path)

            # Convert Windows backslashes to forward slashes for the URL
            file_hash = get_sha256(file_path)

            # Use as_posix() to ensure forward slashes
            manifest_file = {
                "path": relative_path.as_posix(),
                "hash": file_hash
            }
            manifest_files.append(manifest_file)
            print(f"  + Added: {relative_path.as_posix()} (hash: {file_hash[:8]}...)")

    # Create the final manifest object
    manifest = {
        "product_id": product_id,
        "version": version,
        "base_url": base_url,
        "files": manifest_files
    }

    # Write the JSON file
    output_filename = f"{product_id}_{version}.json"
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    print(f"\nSuccess! Manifest created: {output_filename}")


# --- Main Execution ---

if __name__ == "__main__":
    # This allows passing the directory as an argument
    # Usage: python create_manifest.py path/to/your/build/dir

    if len(sys.argv) < 2:
        print("Usage: python create_manifest.py <path_to_build_directory> [product_id] [version] [base_url]")
        print(f"Example: python create_manifest.py build/exe.win-amd64-3.13")
        sys.exit(1)

    # Get arguments
    build_directory = sys.argv[1]
    product_id = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PRODUCT_ID
    version = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_VERSION
    base_url = sys.argv[4] if len(sys.argv) > 4 else DEFAULT_BASE_URL

    # Update base_url if it wasn't provided but version was
    if len(sys.argv) <= 4 and len(sys.argv) > 3:
        base_url = f"files/{product_id}/{version}"

    create_manifest(build_directory, product_id, version, base_url)