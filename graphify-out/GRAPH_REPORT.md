# Graph Report - Nextcloud_CLI  (2026-11-24)

## Corpus Check
- 5 files · ~2,827 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 7 file(s) not represented in the graph (top: (none) 3, .spec 1, .in 1)

## Summary
- 79 nodes · 125 edges · 9 communities (4 shown, 5 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `be5f0fbb`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Environment Setup
- nextcloud_cli.py
- AsyncNextcloud
- [1.2.0]
- list_store_blobs
- upload_chunked
- CLAUDE.md
- status_of

## God Nodes (most connected - your core abstractions)
1. `run()` - 9 edges
2. `upload_chunked()` - 9 edges
3. `upload_all()` - 8 edges
4. `upload_runtime_share()` - 8 edges
5. `download_directory_parallel()` - 7 edges
6. `download_file()` - 7 edges
7. `list_files_recursive()` - 7 edges
8. `ensure_parent_exists()` - 6 edges
9. `upload_file()` - 6 edges
10. `main()` - 5 edges

## Surprising Connections (you probably didn't know these)
- `get_nc_client()` --references--> `AsyncNextcloud`  [EXTRACTED]
  release_manager.py →   _Bridges community 5 → community 2_
- `main()` --calls--> `asyncio`  [EXTRACTED]
  nextcloud_cli.py →   _Bridges community 1 → community 2_
- `download_file()` --calls--> `status_of()`  [EXTRACTED]
  nextcloud_cli.py → nextcloud_cli.py  _Bridges community 2 → community 8_
- `list_store_blobs()` --references--> `AsyncNextcloud`  [EXTRACTED]
  release_manager.py →   _Bridges community 4 → community 2_
- `upload_runtime_share()` --calls--> `list_store_blobs()`  [EXTRACTED]
  release_manager.py → release_manager.py  _Bridges community 4 → community 5_

## Import Cycles
- None detected.

## Communities (9 total, 5 thin omitted)

### Community 0 - "Environment Setup"
Cohesion: 0.18
Nodes (10): Activation of venv, Create local environment, Environment Setup, Examples, Examples, Install dependencies, Nextcloud CLI Utility, Optimization: UPX Compression (+2 more)

### Community 2 - "AsyncNextcloud"
Cohesion: 0.18
Nodes (8): download_directory_parallel(), fetch(), download_file(), ensure_parent_exists(), get_nc_client(), list_files_recursive(), run(), upload_file()

### Community 3 - "[1.2.0]"
Cohesion: 0.33
Nodes (5): [1.0.0], [1.2.0], Added, Changed, Changelog

### Community 5 - "upload_chunked"
Cohesion: 0.15
Nodes (11): ensure_remote_dir(), get_nc_client(), get_sha256(), main(), prepare_package(), store_path(), upload_all(), worker() (+3 more)

## Knowledge Gaps
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `upload_chunked()` connect `upload_chunked` to `nextcloud_cli.py`, `AsyncNextcloud`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `download_file()` connect `AsyncNextcloud` to `status_of`, `nextcloud_cli.py`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Why does `run()` connect `AsyncNextcloud` to `nextcloud_cli.py`?**
  _High betweenness centrality (0.042) - this node is a cross-community bridge._