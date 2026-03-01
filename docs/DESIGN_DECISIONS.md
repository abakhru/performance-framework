# Design Decisions

A record of every significant architectural and implementation decision, the options considered, and the reason each choice was made. Read this before changing a structural pattern.

---

## 1. `src/` layout as the single Python root

**Decision:** All Python source lives under `src/`. `pyproject.toml` declares `where = ["src"]` for package discovery and `pythonpath = ["src", "."]` for pytest.

**Alternatives considered:**
- Keep the original flat layout (`dashboard/`, `api_tests/`, `luna_cli/` at project root)
- Namespace packages without a `src/` wrapper

**Why `src/`:**
- Prevents accidental imports of uninstalled code (the classic "editable install" trap where `import dashboard` can shadow the installed package)
- Forces all inter-package imports to be explicit and package-absolute (`from core.storage import …` instead of `from storage import …`)
- Eliminates the old `sys.path.insert(0, dashboard_dir)` hacks that were scattered through `server.py`, `api_tests/generator.py`, and test conftest files
- Standard modern Python project layout; immediately legible to new contributors

**Trade-off:** One extra directory level. Acceptable given the clarity gained.

---

## 2. Plugin architecture with auto-discovery

**Decision:** Every feature is a plugin in `src/plugins/<name>/`. Each plugin exports `plugin = PluginMeta(...)`. The server calls `register_all()` at startup, which uses `pkgutil.iter_modules` to find and load all plugins.

**Alternatives considered:**
- Explicit router list in `server.py` (the original approach — 15 `app.include_router(...)` lines)
- Entry-point based discovery via `importlib.metadata`
- Configuration file listing active plugins

**Why auto-discovery via `pkgutil`:**
- Adding a feature requires zero changes to `server.py`. The plugin is picked up just by existing.
- `pkgutil.iter_modules` is stdlib — no extra dependency
- Failures are caught per-plugin and logged without crashing the server, enabling graceful degradation
- Entry-point discovery was overkill for a single-repo project; config files would create a sync problem

**Trade-off:** Plugin load order is important. The `_PREFERRED_ORDER` list in `plugins/__init__.py` controls it explicitly for the known plugins. New plugins land at the end alphabetically.

---

## 3. `src/core/` for shared infrastructure

**Decision:** Shared path constants, file I/O, InfluxDB client, and app state live in `src/core/`. Plugins import from `core.*`; `core` never imports from `plugins.*`.

**Alternatives considered:**
- Keeping shared utilities inside `dashboard/` (the original location)
- Splitting per-concern into separate top-level packages (`src/storage/`, `src/influx/`)

**Why `src/core/`:**
- Clear dependency direction: `core` ← `plugins` ← `dashboard`. Nothing in `core` depends on a plugin.
- All path constants computed once in `core/config.py`; no module computes `REPO_ROOT` from `__file__` independently
- Compact — four files cover all shared concerns without over-engineering

**`core/config.py` specifically:** Every previous module computed `REPO_ROOT = Path(__file__).parent.parent` from its own `__file__`, creating fragility when files moved. `config.py` anchors the root once from `src/core/config.py` and exports all derived paths.

---

## 4. Merging scattered performance routers into one plugin

**Decision:** The original 9 separate router files (`run_control.py`, `runs.py`, `slo.py`, `analytics.py`, `endpoints.py`, `profiles.py`, `data_files.py`, `webhooks.py`, `proxy.py`) are preserved as files but grouped inside `src/plugins/performance/routers/`. The plugin's `__init__.py` aggregates them into a single `router`.

**Alternatives considered:**
- Merge all into one large `router.py` file
- Keep all 9 as top-level separate plugins

**Why grouped sub-routers:**
- Preserves the clean separation of concerns within the performance domain
- Aggregation at the `__init__.py` level means the server sees one plugin, not nine
- Easy to find: all performance-related route logic is in one directory

---

## 5. `src/api_tests/` kept separate from `src/plugins/`

**Decision:** The test execution framework (`generator.py`, `runner.py`, `framework/`, `harness/`) is at `src/api_tests/` rather than `src/plugins/api_tests/`.

**Why separate:**
- Generated test files (written to `data/generated-tests/`) import `from api_tests.framework import …`. Those files run outside the dashboard process (via `pytest` subprocess). If the package were at `plugins.api_tests`, those generated imports would need to include `plugins.` — leaking the internal structure into user-visible generated code.
- `api_tests` is a standalone test framework usable independently of the dashboard (e.g., `LunaClient` in CI)
- The `test_generator` plugin (which *generates* the test files) lives in `src/plugins/test_generator/` and depends on `api_tests` as a library — that dependency direction is clean.

---

## 6. 31 AI visual QA agents as a plugin

**Decision:** All 31 tester personas, their prompts, and the Playwright capture + Anthropic API call flow live in `src/plugins/visual_qa/`. Profiles are defined in the Cursor skill file at `.cursor/skills/visual-qa/SKILL.md` and loaded at runtime by `agents.py`.

**Why one plugin, not 31:**
- A single `start_run(url, agents)` call fans out via `ThreadPoolExecutor`. The orchestration is inside the plugin, not in the server.
- Plugin = unit of deployment / activation. Having 31 plugins for what is conceptually one feature would bloat the registry and make the server harder to reason about.

**Agent profile storage:** JSON embedded in the Cursor skill SKILL.md file. At runtime, `load_profiles()` parses the skill file's embedded JSON block. This makes it easy for IDE-assisted workflows to see and edit agent profiles, while keeping them in version control alongside the code.

---

## 7. `PluginMeta` dataclass over Protocol/ABC

**Decision:** `src/plugins/base.py` defines `PluginMeta` as a `@dataclass`, not as an abstract base class or Protocol.

**Why dataclass:**
- Plugins don't need to inherit from anything — they just set `plugin = PluginMeta(...)`. This is more Pythonic (composition over inheritance) and easier to test.
- A Protocol would require every plugin to implement specific methods. Since routers are the primary extension point and FastAPI already provides a clean interface for that, there's no need for an additional method contract.
- Dataclass gives free `__repr__`, equality, and JSON-serialisability (via `dataclasses.asdict`) for observability endpoints.

---

## 8. No `sys.path` manipulation in production code

**Decision:** Zero `sys.path.insert` calls in `src/`. The old `server.py` had `sys.path.insert(0, dashboard_dir)` at module level; `api_tests/generator.py` had `sys.path.insert(0, REPO_ROOT / "dashboard")`.

**Why eliminated:**
- `sys.path` manipulation is fragile, order-dependent, and invisible to static analysis tools (mypy, ruff, IDEs)
- With `src/` on the Python path (via `pyproject.toml`), all imports resolve cleanly via the package system
- Ruff's `I001` (import order) and `F401` (unused import) rules work correctly when imports are explicit

---

## 9. Data files moved from `dashboard/` into `data/`

**Decision:** Runtime state files (`state.json`, `profiles.json`, `webhooks.json`) that were previously inside `dashboard/` are now referenced from `data/` (via `core/config.py` constants).

**Why:**
- `dashboard/` should contain only code and the single static HTML file, not runtime data
- `data/` is already gitignored; runtime-generated files should be gitignored
- Separates "source" from "output" — easier to clean up (`just clean`) without risking source files

---

## 10. Single `index.html` SPA, no frontend build step

**Decision:** The dashboard UI is a single HTML file with inline CSS and JavaScript. No React, no Webpack, no npm.

**Why:**
- Zero build pipeline complexity — change a file, refresh the browser
- `livereload.py` watches `src/dashboard/index.html` and pushes a websocket reload, giving fast iteration
- The dashboard is a developer/operator tool, not a consumer product. Operational simplicity takes priority over DX tooling sophistication.
- A build step would require maintaining a separate `package.json`, lockfile, and CI job just for the frontend

**Trade-off:** Large single file (5000+ lines). Mitigated by consistent naming conventions, CSS design tokens, and clear JavaScript function boundaries. If the UI grows significantly, migrating to a lightweight framework (Preact, Solid) is feasible by adding a `/static/` mount in `server.py`.

---

## 11. MCP server for AI agent integration

**Decision:** A FastMCP server is mounted at `/mcp` in `server.py`. This exposes dashboard tools (`test_service`, `run_k6`, `get_results`) to any MCP-compatible agent.

**Why MCP over REST-only:**
- AI agents (Claude, GPT-4o) natively understand MCP tools — no custom adapter code per agent
- The primary use case is autonomous agents, not just human operators
- FastMCP mounts as a sub-application; it doesn't conflict with the existing REST API

---

## 12. `just` as the sole task runner

**Decision:** All runnable commands are defined in `justfile`. No `Makefile`, no `npm run`, no bare `python -m` in docs.

**Why:**
- `just --list` gives a complete, self-documenting command catalogue (enforced by the `help` default target)
- Targets are simple strings, not Makefile edge cases
- The workspace rule in `.cursor/rules/task-runner.mdc` enforces this universally

---

## 13. pytest with `src/` on `pythonpath`, no conftest path hacks

**Decision:** `pyproject.toml` declares `pythonpath = ["src", "."]` for pytest. Unit test conftest files no longer manipulate `sys.path`.

**Old pattern (removed):**
```python
# tests/unit/conftest.py
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "dashboard"))
```

**New pattern:**
```toml
# pyproject.toml
[tool.pytest.ini_options]
pythonpath = ["src", "."]
```

**Why:** The old pattern was fragile and duplicated the `sys.path.insert` anti-pattern from production code. `pythonpath` in `pyproject.toml` is the correct, declarative, IDE-aware way to set the test Python path.

---

## 14. Visual QA run storage in `data/visual-qa/`

**Decision:** VQA runs are persisted as individual JSON files in `data/visual-qa/<run_id>.json`. There is no database.

**Why file-based storage:**
- No additional service dependency (no PostgreSQL, Redis, etc.)
- JSON files are human-readable and easy to inspect/debug
- Runs are append-only — no update/delete conflicts
- `list_runs()` sorts by `mtime` which is correct for recency ordering

**Trade-off:** Not suitable for very high run volumes (thousands per day). At that scale, an SQLite database (same zero-service footprint) would be more appropriate.

---

## 15. Lighthouse audits via subprocess, not the Node API

**Decision:** `plugins/lighthouse/runner.py` calls `lighthouse` as a subprocess rather than using a Python-Node bridge.

**Why subprocess:**
- Lighthouse is a Node.js tool. A subprocess call is the simplest, most stable interface.
- No Python binding library to maintain. `subprocess.run(["lighthouse", url, "--output=json"])` is sufficient.
- Audit results are captured as JSON from stdout and persisted to `data/lighthouse/`.
