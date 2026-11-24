# CLAUDE.md

## Project Map (graphify)

Knowledge graph of the codebase is stored in `graphify-out/` (`graph.json`, `graph.html`, `GRAPH_REPORT.md`). Use it to navigate before broad grep searches.

- Start with `graphify-out/GRAPH_REPORT.md` (community hubs, most connected nodes).
- CLI: `C:\Users\Pavel\.claude\tools\graphify\venv\Scripts\graphify.exe` (not in PATH):
  - `graphify explain "Symbol"` — node and its neighbors
  - `graphify path "A" "B"` — shortest path between two nodes
  - `graphify update .` — rebuild the graph after code changes (AST only, no LLM)
- Git hooks rebuild the graph after commit/checkout/merge/rewrite (`graphify hook status`).
- Freshness: compare `Built from commit` in `GRAPH_REPORT.md` with `git rev-parse HEAD`; run `graphify update .` if stale.

## Release (Screen Check Suite)

This module is released through the shared tool in the SCT Updater repository (`tools/release/app_release.py`) (the former PyInstaller `release_manager.py` is removed).

Files that drive the release in this repository:
- `sct_app.toml`: module `id`, `launcher` (the exe name users and scripts call; the Rust launcher is built and shipped by the tool), `title` and `icon` (`assets/app.ico`, shown by Windows for the launcher), `obsolete` (old exe names the Updater deletes on install: `Nextcloud_CLI.exe`; add the old name there whenever the launcher is renamed), files to ship (`nextcloud_cli.py` becomes `__main__.py`).
- `requirements.in`: runtime dependencies only (no PyInstaller, no release tooling).
- `requirements.lock`: exact versions with hashes. It is updated automatically by `app_release.py app` whenever `requirements.in` changes (commit it); `app_release.py upgrade <this repo>` moves the versions forward.

Rules:
- Use `AsyncNextcloud` (the synchronous `Nextcloud` client is removed in nc-py-api 0.31).
- Do not rely on the script location or `sys.executable`; the launcher starts the module with `SCT_ROOT` set to the Updater folder.
- Python 3.13 for everything (`.python-version`).

Full process, layout and status: `docs/module-release.md` in the SCT Updater repository. Keep it and this section in sync.
