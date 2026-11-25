# Environment Setup

The module runs on Python 3.13 (`.python-version`); dependencies are in `requirements.in` (locked in `uv.lock` for development and in `requirements.lock` for the release).

```bash
  uv sync
```

Credentials are read from `.env` (`NC_SERVER_URL_QC`, `NC_USER_QC`, `NC_PASSWORD_QC`), which is not committed.

-----

# Nextcloud CLI Utility

The `nextcloud_cli.py` script provides a command-line interface for interacting with Nextcloud, supporting parallel transfers and recursive operations.

**Syntax:**

```bash
  uv run nextcloud_cli.py [action] [flags]
```

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
  uv run nextcloud_cli.py list -r /Project/Builds
```

**2. Parallel Directory Download**
Downloads a remote folder recursively using 10 parallel threads to speed up the process.

```bash
  uv run nextcloud_cli.py download-dir -r /Project/Builds -l ./local_builds -j 10 --force
```

**3. Single File Upload**
Uploads a specific file to the server.

```bash
  uv run nextcloud_cli.py upload -l ./dist/app.exe -r /Releases/app.exe
```
# Release through the Screen Check Suite tool

The module is described by `sct_app.toml`, `requirements.in` and `requirements.lock` in this repository. Releases are made from the SCT Updater repository:

```bash
uv run tools/release/app_release.py app <path to this repo> --upload
```

The version is taken from `pyproject.toml` and `APP_VERSION` (they must agree; a version can still be passed as the last argument). The tool uploads the code and only the wheels that are missing on the server; the Updater installs them into `apps/nextcloud_cli`. Full process and rules: `docs/module-release.md` in the SCT Updater repository.

To test the module the way clients get it, release it to the `dev` list (`app` with `--upload`) and update a test Updater running with `NC_CHANNEL=dev`.
