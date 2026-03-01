# Plugin Authoring Guide

This guide explains how to create a new plugin for the Luna Performance Framework. A plugin can add new API routes, a CLI command, or both.

---

## Anatomy of a Plugin

Every plugin is a Python package inside `src/plugins/`:

```
src/plugins/my_feature/
├── __init__.py     ← REQUIRED: exports plugin = PluginMeta(...)
├── engine.py       ← business logic (pure Python, no FastAPI)
├── router.py       ← FastAPI routes
└── cli.py          ← optional CLI entry-point
```

### Minimum viable plugin

```python
# src/plugins/my_feature/__init__.py

from fastapi import APIRouter
from plugins.base import PluginMeta

router = APIRouter(prefix="/my-feature", tags=["My Feature"])

@router.get("/ping")
async def ping():
    return {"status": "ok"}

plugin = PluginMeta(
    name="my_feature",
    description="Does something useful.",
    router=router,
)
```

That's it. The server discovers and mounts it automatically at next startup — no changes to `server.py` needed.

---

## `PluginMeta` Fields

```python
@dataclass
class PluginMeta:
    name: str           # snake_case unique identifier
    description: str    # one-line summary (shown in logs and docs)
    router: APIRouter | None = None  # None for CLI-only plugins
    tags: list[str] = field(default_factory=list)  # OpenAPI tags
    version: str = "1.0.0"
    cli_module: str | None = None  # dotted path to CLI entry-point
```

---

## Recommended Structure

Split business logic from FastAPI:

```python
# engine.py — no FastAPI imports
from core.storage import DATA_DIR

def do_something(param: str) -> dict:
    ...

# router.py
from fastapi import APIRouter, HTTPException
from plugins.my_feature.engine import do_something

router = APIRouter(prefix="/my-feature", tags=["My Feature"])

@router.post("/run")
async def run(body: dict):
    result = do_something(body.get("param", ""))
    return result

# __init__.py
from plugins.base import PluginMeta
from plugins.my_feature.router import router

plugin = PluginMeta(
    name="my_feature",
    description="Does something useful.",
    router=router,
    tags=["My Feature"],
)
```

Keeping `engine.py` free of FastAPI makes it easier to test and reuse (e.g., from the CLI or a justfile target).

---

## Using Core Infrastructure

Import from `core.*` for shared utilities:

```python
from core.config import DATA_DIR, REPO_ROOT
from core.storage import load_state, save_state
from core.influx import influx_query
from core.state import state  # shared AppState singleton
```

Never import from another plugin directly. If two plugins share logic, extract it to `core/` or `src/api_tests/`.

---

## Adding a CLI Command

Expose a `cli.py` module and register it in `PluginMeta.cli_module`:

```python
# src/plugins/my_feature/cli.py
import argparse

def main():
    parser = argparse.ArgumentParser(description="My Feature CLI")
    parser.add_argument("url")
    args = parser.parse_args()
    print(f"Running against {args.url}")

if __name__ == "__main__":
    main()
```

```python
# __init__.py
plugin = PluginMeta(
    name="my_feature",
    description="...",
    router=router,
    cli_module="plugins.my_feature.cli",
)
```

Add a `justfile` target:

```justfile
# Run my-feature CLI (usage: just my-feature-run url=https://...)
my-feature-run url:
    uv run python -m plugins.my_feature.cli {{url}}
```

---

## Adding Tests

Unit tests go in `tests/unit/test_my_feature.py`:

```python
"""
test_my_feature.py — Unit tests for plugins/my_feature/

Feature: My Feature — bd-xyz
Covers: core business logic, edge cases.
"""

import pytest
from plugins.my_feature.engine import do_something

def test_do_something_returns_expected():
    result = do_something("hello")
    assert result["status"] == "ok"
```

Run with:

```bash
just test-unit
```

---

## Plugin Load Order

Plugins load in the order defined in `_PREFERRED_ORDER` inside `src/plugins/__init__.py`:

```python
_PREFERRED_ORDER = [
    "performance",
    "discovery",
    "test_generator",
    "api_tests",
    "ui_tests",
    "lighthouse",
    "visual_qa",
]
```

Any plugin not in this list is appended alphabetically. To control where your plugin appears in the OpenAPI docs and startup log, add it to this list in the desired position.

---

## Existing Plugins Reference

| Plugin | Prefix | Key files |
|---|---|---|
| `performance` | `/run`, `/runs`, `/slo`, `/analytics`, `/endpoints`, `/profiles`, `/data`, `/webhooks`, `/k6` | `runner.py`, `queries.py`, `report.py`, `routers/` |
| `discovery` | `/discover` | `engine.py`, `router.py` |
| `test_generator` | `/discover/generate`, `/discover/execute` | `codegen.py`, `api_tests_router.py` |
| `lighthouse` | `/lighthouse` | `runner.py`, `router.py` |
| `visual_qa` | `/visual-qa` | `agents.py`, `cli.py`, `router.py` |
| `ui_tests` | `/ui-tests` | `router.py` |

---

## Checklist for a New Plugin

- [ ] Created `src/plugins/<name>/` directory
- [ ] `__init__.py` exports `plugin = PluginMeta(...)`
- [ ] Business logic in `engine.py` (no FastAPI imports)
- [ ] Routes in `router.py` with a prefix and tags
- [ ] `justfile` targets for CLI usage
- [ ] Unit tests in `tests/unit/test_<name>.py`
- [ ] Added plugin name to `_PREFERRED_ORDER` in `src/plugins/__init__.py` (if ordering matters)
- [ ] Updated [docs/ARCHITECTURE.md](ARCHITECTURE.md) plugin table
