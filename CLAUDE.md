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

This module is released through the shared tool in the SCT Updater repository (`tools/release/app_release.py`), not with its own `release_manager.py` (kept only for the legacy PyInstaller `zip` releases until the migration is finished).

Files that drive the release in this repository:
- `sct_app.toml`: module id, Python minor version (3.13), `launcher` (the exe name users and scripts call; the Rust launcher is built and shipped by the tool), files to ship (`nextcloud_cli.py` becomes `__main__.py`).
- `requirements.in`: runtime dependencies only (no PyInstaller, no release tooling).
- `requirements.lock`: exact versions with hashes. Regenerate with `app_release.py lock <this repo>` whenever `requirements.in` changes, and commit it.

Rules:
- Use `AsyncNextcloud` (the synchronous `Nextcloud` client is removed in nc-py-api 0.31).
- Do not rely on the script location or `sys.executable`; the launcher starts the module with `SCT_ROOT` set to the Updater folder.
- Python 3.13 for everything (`.python-version`).

Full process, layout and status: `docs/module-release.md` in the SCT Updater repository. Keep it and this section in sync.
