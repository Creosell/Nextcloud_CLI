# Graph Report - Nextcloud_CLI  (2026-11-09)

## Corpus Check
- 3 files · ~1,402 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 1, .spec 1)

## Summary
- 42 nodes · 58 edges · 7 communities (3 shown, 4 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2dd75b9d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Environment Setup
- Nextcloud
- [1.2.0]
- list_files_recursive
- main
- get_nc_client

## God Nodes (most connected - your core abstractions)
1. `main()` - 8 edges
2. `list_files_recursive()` - 7 edges
3. `upload_file()` - 6 edges
4. `download_file()` - 6 edges
5. `download_directory_parallel()` - 6 edges
6. `ensure_parent_exists()` - 5 edges
7. `get_nc_client()` - 4 edges
8. `Environment Setup` - 4 edges
9. `Changelog` - 3 edges
10. `[1.2.0]` - 3 edges

## Surprising Connections (you probably didn't know these)
- `download_directory_parallel()` --indirect_call--> `download_file()`  [INFERRED]
  nextcloud_cli.py → nextcloud_cli.py  _Bridges community 2 → community 4_
- `get_nc_client()` --references--> `Nextcloud`  [EXTRACTED]
  nextcloud_cli.py →   _Bridges community 6 → community 2_
- `main()` --calls--> `get_nc_client()`  [EXTRACTED]
  nextcloud_cli.py → nextcloud_cli.py  _Bridges community 6 → community 5_
- `main()` --calls--> `list_files_recursive()`  [EXTRACTED]
  nextcloud_cli.py → nextcloud_cli.py  _Bridges community 4 → community 5_
- `main()` --calls--> `upload_file()`  [EXTRACTED]
  nextcloud_cli.py → nextcloud_cli.py  _Bridges community 2 → community 5_

## Import Cycles
- None detected.

## Communities (7 total, 4 thin omitted)

### Community 0 - "Environment Setup"
Cohesion: 0.20
Nodes (9): Activation of venv, Create local environment, Environment Setup, Examples, Examples, Install dependencies, Nextcloud CLI Utility, Optimization: UPX Compression (+1 more)

### Community 2 - "Nextcloud"
Cohesion: 0.36
Nodes (3): download_file(), ensure_parent_exists(), upload_file()

### Community 3 - "[1.2.0]"
Cohesion: 0.33
Nodes (5): [1.0.0], [1.2.0], Added, Changed, Changelog

## Knowledge Gaps
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `upload_file()` connect `Nextcloud` to `nextcloud_cli.py`, `main`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Why does `download_file()` connect `Nextcloud` to `nextcloud_cli.py`, `list_files_recursive`, `main`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Why does `download_directory_parallel()` connect `list_files_recursive` to `nextcloud_cli.py`, `Nextcloud`, `main`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._