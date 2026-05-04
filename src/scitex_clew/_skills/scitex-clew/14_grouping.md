---
description: |
  [TOPIC] Grouping
  [DETAILS] Collapse related files into single DAG nodes via pattern, directory, or session-bundle groupers while preserving every hash via Merkle roots.
tags: [scitex-clew-grouping]
---

# Grouping (scitex-clew)

Large pipelines emit many per-patient / per-fold / per-seizure files. A raw DAG drawing all of them is unreadable. The grouping API collapses related files into a single visual node while **preserving every underlying hash** — every group carries a Merkle root so aggregate verification is cryptographically meaningful.

## Built-in groupers

| Name | Effect |
|---|---|
| `identity()` | No grouping — every file its own node |
| `drop_all_files()` | Scripts-only DAG (no file nodes at all) |
| `pattern_grouper(regex)` | Collapse files whose basenames match after replacing `regex` |
| `directory_grouper(min_size=10, depth=1)` | Collapse ≥N files in a shared parent dir |
| `session_bundle_grouper(max_files=3)` | If a session emits >N files per role, bundle them |
| `auto()` | Sensible default: patterns → directory → session bundle |
| `compose(*groupers)` | Apply groupers in order (first wins per file) |

## Spec form (JSON/YAML/dict — works in CLI, MCP, config file)

```yaml
grouper:
  type: compose
  steps:
    - {type: pattern, regex: 'P\d{2}'}       # patient codes
    - {type: pattern, regex: 'fold_\d+'}     # ML folds
    - {type: directory, min_size: 10, depth: 2}
    - {type: session_bundle, max_files: 3}
```

## Project config

Place at `<project_root>/.scitex/clew/config.yaml`. `clew.mermaid()` walks up from CWD to find it. Absent → `auto()` is used.

## Python API

```python
import scitex_clew as clew
from scitex_clew.groupers import pattern_grouper, auto, compose

# callable
clew.mermaid(claims=True, grouper=pattern_grouper(r"P\d{2}"))

# dict spec
clew.mermaid(claims=True, grouper={"type": "auto"})

# config.yaml (automatic fallback when grouper=None)
clew.mermaid(claims=True)
```

## Custom groupers

Rare case: register a factory for a project-specific rule.

```python
from scitex_clew.groupers import register_grouper

def my_grouper(entries):
    ...  # returns list[FileEntry | Group]

register_grouper("mine", lambda: my_grouper)
```

Or via spec escape hatch (not honored in MCP):

```yaml
grouper: {type: custom, import: mypkg.groupers:factory}
```

## Merkle roots

Every `Group` carries `root_hash` = SHA-256 over sorted member hashes. A group renders as `✓` only if all members verify; `⚠` otherwise. Individual hashes are never discarded — `clew.dag(format="json")` always exports every file.

## Related

- [quick-start.md](quick-start.md) — first-run tracking
- [common-workflows.md](common-workflows.md) — claims + DAG patterns
