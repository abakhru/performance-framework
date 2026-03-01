# Architecture

This document describes how the Luna Performance Framework is structured, how its layers interact, and the rationale behind each major structural choice.

---

## Layer Model

```
┌─────────────────────────────────────────────────────────────────┐
│                         Clients                                 │
│   Browser (dashboard UI)  ·  AI agents (MCP)  ·  CLI (Luna)    │
└────────────────────────────┬────────────────────────────────────┘
                             │  HTTP / MCP / Python SDK
┌────────────────────────────▼────────────────────────────────────┐
│                    src/dashboard/server.py                       │
│  FastAPI app factory  ·  auth middleware  ·  plugin mounting    │
└──────┬──────────┬──────────┬──────────┬──────────┬─────────────┘
       │          │          │          │          │
  plugins/   plugins/   plugins/   plugins/   plugins/
 performance discovery lighthouse visual_qa  ui_tests  …
       │
  src/core/        ← used by all plugins
  config.py        Path constants
  storage.py       File I/O
  state.py         Shared mutable state
  influx.py        InfluxDB client
```

### Layer 1 — `src/core/`

Stateless infrastructure utilities shared across every plugin. No plugin-specific logic lives here.

| Module | Responsibility |
|---|---|
| `config.py` | Single source of truth for all filesystem paths and config defaults |
| `storage.py` | Read/write JSON data files; type coercions |
| `state.py` | Singleton `AppState` that holds the live endpoint config and op-group mappings |
| `influx.py` | InfluxDB HTTP write, Flux query, and line-protocol helpers |

### Layer 2 — `src/plugins/`

Each plugin is a self-contained directory that owns its business logic, FastAPI routes, and (optionally) a CLI entry-point. Plugins are auto-discovered at startup via `pkgutil` — no manual wiring in `server.py`.

```
src/plugins/
├── __init__.py         # register_all() + get_plugins()
├── base.py             # PluginMeta dataclass
├── performance/        # k6 runner, InfluxDB queries, run routes
├── discovery/          # URL crawl, Postman/HAR/OpenAPI/WSDL parsing
├── test_generator/     # Multi-type test suite codegen + execution
├── lighthouse/         # Lighthouse audit runner
├── visual_qa/          # 31 Claude Vision API tester agents
└── ui_tests/           # Playwright test execution
```

Plugin structure (minimum):

```
src/plugins/my_feature/
├── __init__.py     ← exports: plugin = PluginMeta(name=..., router=...)
├── router.py       ← FastAPI APIRouter
└── engine.py       ← business logic (no FastAPI imports here)
```

### Layer 3 — `src/dashboard/`

Thin shell that wires everything together. `server.py` calls `register_all()` and mounts each plugin's router. It owns no business logic.

### Layer 4 — `src/api_tests/`

The test execution framework used by the `test_generator` plugin and by external `luna.py` callers. Kept separate from `plugins/` because it is also referenced by generated test files that run outside the dashboard process.

### Layer 5 — `src/cli/`

Luna interactive REPL and Typer/Click CLI commands. Uses `api_tests.luna.LunaClient` to communicate with the dashboard HTTP API.

---

## Request Flow

```
Browser/agent → FastAPI middleware (_APIKeyMiddleware)
             → plugin router (e.g., /run, /discover, /visual-qa)
             → plugin business logic (engine.py / runner.py / agents.py)
             → core.storage / core.influx / core.state
             → external services (k6, InfluxDB, Lighthouse, Anthropic API)
```

---

## Plugin Discovery

`src/plugins/__init__.py` iterates sub-packages with `pkgutil.iter_modules` at startup. Any package that exports `plugin = PluginMeta(...)` is registered. Load order follows `_PREFERRED_ORDER` then alphabetical for extras.

```python
# src/plugins/__init__.py (simplified)
for name, is_pkg in pkgutil.iter_modules(plugins_dir):
    mod = importlib.import_module(f"plugins.{name}")
    if hasattr(mod, "plugin"):
        _PLUGINS.append(mod.plugin)
```

This means adding a feature is:

1. Create `src/plugins/my_feature/`
2. Write `__init__.py` with `plugin = PluginMeta(...)`
3. Done — no changes elsewhere

---

## Data Flow: k6 Run

```
1. Browser → POST /run/start
2. run_control router → run_k6_supervised() in performance/runner.py
3. runner.py spawns k6 subprocess, starts poller_loop thread
4. k6 → InfluxDB (xk6-output-influxdb)
5. poller_loop → GET http://localhost:6565/ (k6 REST API)
6. poller_loop → core.influx.influx_query (real-time metrics)
7. Browser polling → GET /k6/v1/metrics → runs router
8. On finish → finalize_run() → lifecycle hooks → webhooks
```

---

## Data Flow: Visual QA

```
1. Browser/CLI → POST /visual-qa/run  { url, agents }
2. visual_qa/router → start_run() in visual_qa/agents.py
3. agents.py → Playwright → captures screenshot + accessibility tree + console logs
4. For each agent (parallel via ThreadPoolExecutor):
   a. build_prompt(agent_profile, page_state)
   b. Anthropic Claude Vision API → bug report JSON
   c. parse_bugs() → list[BugReport]
5. Persist VQARun to data/visual-qa/<run_id>.json
6. Browser → GET /visual-qa/result/<run_id>
```

---

## Data Flow: Test Generation

```
1. Browser → POST /discover/generate  { endpoints_config, base_url, suites }
2. discovery/router → test_generator/codegen.generate_suite()
3. codegen creates timestamped directory data/generated-tests/<id>/
4. Writes: test_api_smoke.py, test_ui_playwright.py,
           endpoints_perf.json, lighthouse_urls.json, metadata.json
5. Browser → POST /discover/execute  { dir_name, suites }
6. codegen.run_suite() → subprocess pytest / lighthouse / k6
7. Results appended to data/generated-tests/<id>/results/<suite>.json
```

---

## Key External Dependencies

| Dependency | Purpose | Where used |
|---|---|---|
| k6 (custom xk6 build) | Load generation | `bin/k6` — called by `performance/runner.py` |
| InfluxDB v2 | Metrics time-series storage | `core/influx.py` |
| Playwright | Browser automation | `plugins/visual_qa/`, `plugins/ui_tests/`, `tests/ui/` |
| Anthropic Claude | Vision AI for VQA agents | `plugins/visual_qa/agents.py` |
| Lighthouse (via npm) | Web performance auditing | `plugins/lighthouse/runner.py` |
| FastAPI + uvicorn | HTTP API server | `src/dashboard/server.py` |
| FastMCP | MCP server for AI agents | `src/dashboard/mcp_server.py` |

---

## Python Path Contract

`src/` is the single Python root. `pyproject.toml` declares:

```toml
[tool.pytest.ini_options]
pythonpath = ["src", "."]

[tool.setuptools.packages.find]
where = ["src"]
```

All imports within `src/` use the package-absolute form:

```python
from core.storage import load_state       # not from ..storage
from plugins.performance.runner import …  # not from lifecycle
```

No `sys.path` manipulation anywhere in `src/`. The old `dashboard/` `sys.path.insert` pattern is gone.
