# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.2.0]

### Added
- **`download-dir` action**: recursive parallel directory download with preserved folder structure
- **Parallel downloads**: configurable concurrency via `--jobs` / `-j` flag (default: 5 threads)
- **`list` action**: recursively list all files in a remote directory
- Connection pool size dynamically matched to thread count to minimize handshake overhead

### Changed
- Credentials loaded from `.env` via `python-dotenv` — no hardcoded values
- HTTP adapter configured with per-action pool size for optimal parallel I/O

---

## [1.0.0]

Initial release. Core functionality: upload and download single files to/from Nextcloud via WebDAV. Credentials via `.env`.
