# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.3.0]

Versions 1.1.0 and 1.2.0 were never released; production stays on 1.0.0, so this entry holds all changes since it.

### Added
- **`download-dir` action**: recursive parallel directory download with preserved folder structure
- **Parallel downloads**: configurable concurrency via `--jobs` / `-j` flag (default: 5 parallel tasks)
- **`list` action**: recursively list all files in a remote directory

### Changed
- Credentials loaded from `.env` via `python-dotenv` — no hardcoded values
- Migrated from the deprecated sync `Nextcloud` client to `AsyncNextcloud` (asyncio tasks instead of threads; `requests`/`urllib3` are no longer used directly)
- Released through the Screen Check Suite release tool as a module with its own wheels on the shared embedded Python; the launcher is `Nextcloud CLI.exe`

### Removed
- PyInstaller build and `release_manager.py`

---

## [1.0.0]

Initial release. Core functionality: upload and download single files to/from Nextcloud via WebDAV. Credentials via `.env`.
