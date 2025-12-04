# Environment Setup
## Create local environment
```bash
  python -m venv .venv
````

## Activation of venv

**Windows**

```bash
  .venv\Scripts\activate
```

**macOS and Linux**

```bash
  source .venv/bin/activate
```

## Install dependencies

```bash
  pip install -r requirements.txt
```

-----

# Release Manager Usage

The `release_manager.py` script handles building, packaging, and uploading releases to Nextcloud.

**Syntax:**

```bash
  uv run --active release_manager.py [mode] [path] [product_id] [version] [flags]
```

**Arguments:**

  * `mode`:
      * `zip`: Archives the contents of `path` into a single `.zip` file and uploads it.
      * `files`: Uploads files individually (preserves structure).
  * `path`: Path to the build/dist directory. **Note:** Contents are placed at the root of the release.
  * `product_id`: Unique identifier (e.g., `nextcloud_cli`).
  * `version`: Version string (e.g., `1.0.0`).

**Flags:**
  * `--active`: Runs UV using current .venv of a project.
  * `--build`: Runs PyInstaller before packaging (requires a matching `.spec` file).
  * `--upload`: Uploads immediately without confirmation prompt.
  * `--include [path]`: Adds a directory to the release (preserved as a subfolder).

### Examples

**1. Build, Zip, and Upload (Standard Workflow)**
Builds `.exe` from spec, zips contents of `dist/Nextcloud_CLI`, and uploads as version `1.0.0`.

```bash
  uv run --active release_manager.py zip build/dist/Nextcloud_CLI nextcloud_cli 1.0.0 --build --upload
```

**2. Include Configuration Folder**
Includes a `config/` folder alongside the executable inside the archive.

```bash
  uv run --active release_manager.py zip dist/Nextcloud_CLI nextcloud_cli 1.0.0 --include config --upload
```

**3. Upload in "Files" Mode**
Uploads files individually without zipping.

```bash
  uv run --active release_manager.py files dist/Nextcloud_CLI nextcloud_cli 1.0.0 --upload
```

## Optimization: UPX Compression

To significantly reduce the size of the generated `.exe` file (and consequently the final `.zip` archive), it is recommended to use **UPX** (Ultimate Packer for eXecutables).

**Setup Steps:**
1. Download the latest version of UPX from the official [GitHub releases page](https://github.com/upx/upx/releases).
2. Extract the downloaded archive.
3. Copy the `upx.exe` file directly into your virtual environment's scripts folder:
   * **Path:** `.venv\Scripts\` (Windows)

PyInstaller automatically detects UPX in this folder and will use it to compress the binary during the `--build` process.

# Nextcloud CLI Utility

The `nextcloud_cli.py` script provides a command-line interface for interacting with Nextcloud, supporting parallel transfers and recursive operations.

**Syntax:**

```bash
  uv run --active nextcloud_cli.py [action] [flags]
````

**Actions:**

  * `upload`: Uploads a single local file to Nextcloud.
  * `download`: Downloads a single remote file.
  * `list`: Recursively lists all files in a remote directory.
  * `download-dir`: Downloads a remote directory recursively with parallel processing.

**Flags:**

  * `-l`, `--local-path`: Path to local file or directory (Required for transfers).
  * `-r`, `--remote-path`: Target path on Nextcloud.
  * `-f`, `--force`: Overwrite existing local files without warning.
  * `-j`, `--jobs`: Number of parallel threads for directory downloads (Default: 5).

### Examples

**1. Recursive List**
Lists all files in a remote folder and its subfolders to stdout.

```bash
  uv run --active nextcloud_cli.py list -r /Project/Builds
```

**2. Parallel Directory Download**
Downloads a remote folder recursively using 10 parallel threads to speed up the process.

```bash
  uv run --active nextcloud_cli.py download-dir -r /Project/Builds -l ./local_builds -j 10 --force
```

**3. Single File Upload**
Uploads a specific file to the server.

```bash
  uv run --active nextcloud_cli.py upload -l ./dist/app.exe -r /Releases/app.exe
```