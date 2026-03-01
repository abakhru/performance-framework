# Luna Performance Framework

A self-hosted performance testing platform built on [k6](https://github.com/grafana/k6) with a live dashboard, InfluxDB time-series storage, AI-powered visual QA agents, and a plugin architecture designed for extensibility.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Features](#features)
- [Configuration](#configuration)
- [Dashboard Tabs](#dashboard-tabs)
- [Load Profiles](#load-profiles)
- [Endpoints Config](#endpoints-config)
- [Plugins](#plugins)
- [Agent Integration](#agent-integration)
- [CLI Reference](#cli-reference)
- [Directory Structure](#directory-structure)
- [Docs](#docs)
- [Attribution](#attribution)

---

## Quick Start

Tool versions are pinned in `.mise.toml`. Install [mise](https://mise.jdx.dev) then:

```bash
just install          # mise install + uv sync + build custom k6 binary
just init             # copy .env.example → .env  (fill in BASE_URL at minimum)
just dashboard        # start dashboard + InfluxDB → http://localhost:5656
```

Or run headless:

```bash
just smoke            # 2 VUs · 30s sanity check
just ramp             # 0→N VUs ramp · hold · ramp down
just stress           # step-up to breaking point
just soak             # sustained load endurance
just spike            # instant burst resilience
```

---

## Architecture Overview

The codebase lives entirely under `src/` with three layers:

```
src/
├── core/           # Shared infrastructure — config, storage, InfluxDB, app state
├── plugins/        # Auto-discovered feature modules (add one = new feature)
│   ├── performance/    k6 run lifecycle, queries, reports, and all run routes
│   ├── discovery/      API endpoint discovery from URLs, Postman, HAR, OpenAPI
│   ├── lighthouse/     Google Lighthouse web audits
│   ├── visual_qa/      31 AI-powered visual QA tester agents
│   ├── ui_tests/       Playwright-based UI test execution
│   └── test_generator/ Auto-generate API/UI/k6/Lighthouse test suites
├── api_tests/      # Test execution framework (generator, runner, harness)
├── dashboard/      # FastAPI app factory + static HTML + livereload + MCP server
└── cli/            # Luna interactive REPL and CLI commands
```

**Adding a new feature** takes 2 steps — no changes to `server.py` needed:

```
1. mkdir src/plugins/my_feature/
2. Create __init__.py with:  plugin = PluginMeta(name=..., router=...)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design rationale and [docs/PLUGINS.md](docs/PLUGINS.md) for the plugin authoring guide.

---

## Features

| Feature | Description |
|---|---|
| **k6 Load Testing** | Smoke, ramp, soak, stress, spike profiles with live metrics |
| **Live Dashboard** | Real-time RPS, latency charts, Apdex gauge, per-endpoint sparklines |
| **InfluxDB Storage** | Time-series metrics storage with Flux queries |
| **API Discovery** | Auto-discover endpoints from URLs, Postman, HAR, OpenAPI, WSDL |
| **Test Generation** | Auto-generate pytest, Playwright, k6, Lighthouse test suites |
| **Visual QA Agents** | 31 AI tester personas via Claude Vision API |
| **Lighthouse Audits** | Performance, accessibility, SEO, best-practices scores |
| **Playwright UI Tests** | Browser automation against the dashboard |
| **SLO Enforcement** | p95 latency, error rate, Apdex thresholds with SVG badges |
| **Webhooks** | Configurable HTTP notifications on run completion |
| **Plugin Hooks** | Drop Python files in `hooks/` to extend run lifecycle |
| **MCP Server** | AI agent integration via Model Context Protocol |
| **Luna CLI** | Interactive REPL for one-shot API testing |

---

## Configuration

Copy `.env.example` for the full template:

```bash
cp .env.example .env
```

### Core

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `https://...` | Target base URL for all tests |
| `VUS` | `10` | Max virtual users |
| `DURATION` | `60s` | Hold phase duration |
| `RAMP_DURATION` | `30s` | Ramp up/down duration |
| `SOAK_DURATION` | `10m` | Soak test duration |
| `STRESS_VUS` | `50` | Peak VUs for stress test |
| `SPIKE_VUS` | `100` | Burst VUs for spike test |

### Auth

Fill only the fields that match your auth mode:

| Variable(s) | Auth mode |
|---|---|
| `AUTH_TOKEN` | Static Bearer token |
| `AUTH_BASIC_USER` + `AUTH_BASIC_PASS` | HTTP Basic |
| `AUTH_API_KEY` + `AUTH_API_KEY_HEADER` | API Key header |
| `AUTH_HOST` + `AUTH_REALM` + `AUTH_CLIENT_ID` + `AUTH_CLIENT_SECRET` | Keycloak client credentials |

### InfluxDB

| Variable | Default |
|---|---|
| `INFLUXDB_URL` | `http://localhost:8086` |
| `INFLUXDB_ORG` | `matrix` |
| `INFLUXDB_BUCKET` | `k6` |
| `INFLUXDB_TOKEN` | `matrix-k6-token` |

### Visual QA

| Variable | Default | Description |
|---|---|---|
| `VISUAL_QA_AI_KEY` | — | Anthropic API key (required for VQA agents) |
| `VISUAL_QA_AI_MODEL` | `claude-3-5-sonnet-20241022` | Claude model to use |

---

## Dashboard Tabs

Start with `just dashboard` → `http://localhost:5656`

| Tab | Purpose |
|---|---|
| **Discover** | Import endpoints from Postman, OpenAPI, URL scan; auto-generate test suites |
| **Execute** | Configure VUs, duration, auth and launch runs from the browser |
| **Overview** | Real-time RPS, latency charts, Apdex gauge per run |
| **Endpoints** | Per-operation p95 trend sparklines and error breakdown |
| **History** | Past runs with SLO verdict, diff view, and baseline comparison |
| **HTTP** | Raw HTTP log during an active run |
| **Lighthouse** | Trigger and view Lighthouse audits |
| **Visual QA** | Run AI visual tester agents against any URL |
| **Log** | Live server event log |

---

## Load Profiles

| Profile | Shape | Typical use |
|---|---|---|
| **smoke** | 2 VUs · 30s | Sanity — validate all endpoints respond correctly |
| **ramp** | 0 → VUS → 0 | Standard load test with configurable ramp and hold |
| **soak** | VUS · SOAK_DURATION | Endurance — find memory leaks and connection exhaustion |
| **stress** | Step-up to STRESS_VUS | Find the service breaking point |
| **spike** | Instant burst to SPIKE_VUS | Resilience — sudden traffic surge |

---

## Endpoints Config

`k6/config/endpoints.json` defines what gets tested. Use the **Discover tab** to populate it automatically, or hand-author:

```json
{
  "service": "My API",
  "slos": {
    "p95_ms": 500,
    "error_rate": 0.01,
    "apdex_score": 0.85
  },
  "endpoints": [
    {
      "name": "ListUsers",
      "group": "users",
      "type": "rest",
      "method": "GET",
      "path": "/api/users",
      "weight": 3,
      "checks": { "status": 200, "body_path": "data" }
    },
    {
      "name": "SearchAgents",
      "group": "agents",
      "type": "graphql",
      "path": "/api/graphql",
      "weight": 1,
      "query": "query { agents { id name } }",
      "checks": { "status": 200, "no_graphql_errors": true }
    }
  ]
}
```

**Fields:**

| Field | Required | Description |
|---|---|---|
| `name` | yes | Unique identifier — used as metric tag |
| `group` | yes | Group label for aggregation |
| `type` | yes | `"rest"` or `"graphql"` |
| `path` | yes | Path appended to `BASE_URL` |
| `weight` | no (1) | Relative selection probability |
| `method` | REST only | HTTP verb |
| `body` | REST only | Static JSON body |
| `query` | GraphQL only | Query/mutation string |
| `variables` | GraphQL only | Static variables |
| `headers` | no | Extra headers merged with auth |
| `checks` | no | Pass/fail assertions |
| `data_file` | no | CSV file for data-driven injection |

**Check types:**

| Key | Description |
|---|---|
| `status` | Expected HTTP status code |
| `body_path` | Dot-path must exist and be non-null |
| `header_present` | Response header must be present |
| `max_duration_ms` | Request must complete within N ms |
| `body_contains` | Response body must contain substring |
| `no_graphql_errors` | GraphQL `errors` must be absent |
| `has_data` | GraphQL `data` must be non-null |

---

## Plugins

Every feature is a plugin. Plugins live in `src/plugins/<name>/` and export a `PluginMeta` object. The server discovers and mounts them automatically at startup.

| Plugin | Prefix | Description |
|---|---|---|
| `performance` | `/run`, `/runs`, `/slo`, … | k6 run lifecycle and metrics |
| `discovery` | `/discover` | API endpoint auto-discovery |
| `test_generator` | `/discover/generate` | Test suite codegen + execution |
| `lighthouse` | `/lighthouse` | Lighthouse audits |
| `visual_qa` | `/visual-qa` | AI visual QA agents |
| `ui_tests` | `/ui-tests` | Playwright UI test runner |

See [docs/PLUGINS.md](docs/PLUGINS.md) to create your own plugin.

---

## Agent Integration

Luna is designed to be called by autonomous AI agents.

**Python one-shot:**

```python
from api_tests.luna import LunaClient

result = LunaClient().test_service("https://api.example.com")
result.assert_success()
```

**CLI one-shot:**

```bash
just test-service url=https://api.example.com profile=smoke
```

**MCP (Claude, GPT-4o, any MCP client):**

```
Connect to: http://localhost:5656/mcp
Primary tool: test_service
```

See [docs/AGENTS.md](docs/AGENTS.md) for the full agent integration guide.

---

## CLI Reference

```bash
# Bootstrap
just install            # mise + uv sync + build k6
just init               # create .env from template

# InfluxDB
just influx-up          # start InfluxDB via Docker
just influx-down        # stop InfluxDB
just influx-ui          # open InfluxDB UI

# Dashboard
just dashboard          # start dashboard + InfluxDB (reload-enabled)
just dash ramp          # run 'ramp' with dashboard

# k6 headless
just smoke              # 2 VUs · 30s
just ramp               # standard ramp
just soak               # endurance
just stress             # breaking point
just spike              # burst
just json ramp          # run + save JSON results to out/
just influx-run ramp    # run directly to InfluxDB

# Python quality
just lint               # ruff check src/ tests/
just fix                # ruff check --fix + format
just typecheck          # ty check src/
just test               # pytest (unit)
just test-unit          # unit tests only
just test-components    # component tests
just test-integration   # integration tests (needs services)
just test-e2e           # end-to-end tests (full stack)
just coverage           # coverage report

# CI gate
just ci                 # lint + typecheck + test

# Test generation (Discover → suites)
just gen-tests url=https://api.example.com
just run-tests <dir_name>
just gen-list

# Visual QA agents
just vqa url=https://example.com
just vqa-list
just vqa-show <run_id>
just vqa-agents

# UI tests (Playwright)
just ui-install         # install Playwright browsers
just test-ui-smoke      # smoke suite
just test-ui-regression # regression suite
just test-ui            # all UI tests
just test-ui-headed     # headed browser (debug)

# Luna CLI / Agent
just agent-start        # start dashboard + print MCP URL
just cli                # launch Luna interactive REPL
just cli-test url=https://api.example.com
just cli-health
just test-service url=https://api.example.com

# Utilities
just env                # print current env vars
just check              # verify k6 is installed
just clean              # remove out/, caches
```

---

## Directory Structure

```
.
├── src/                    # All Python source code
│   ├── core/               # Shared infrastructure
│   │   ├── config.py       # Central path constants
│   │   ├── storage.py      # File I/O helpers
│   │   ├── state.py        # Shared app state
│   │   └── influx.py       # InfluxDB client
│   ├── plugins/            # Auto-discovered feature plugins
│   │   ├── base.py         # PluginMeta base class
│   │   ├── performance/    # k6 runner, queries, report, routes
│   │   ├── discovery/      # Endpoint discovery engine + routes
│   │   ├── lighthouse/     # Lighthouse runner + routes
│   │   ├── visual_qa/      # AI agents, CLI, routes
│   │   ├── ui_tests/       # Playwright routes
│   │   └── test_generator/ # Test suite codegen
│   ├── api_tests/          # Test execution framework
│   │   ├── framework/      # Base test case classes
│   │   ├── harness/        # Service harnesses (FastAPI, k6, InfluxDB)
│   │   ├── generator.py    # Test suite generator
│   │   └── runner.py       # Test runner
│   ├── dashboard/          # FastAPI app factory + static UI
│   │   ├── server.py       # App factory + plugin mounting
│   │   └── index.html      # Dashboard single-page app
│   └── cli/                # Luna interactive CLI
├── k6/                     # k6 JavaScript source
│   ├── main.js             # Entry point (setup/default/teardown)
│   ├── config/             # endpoints.json + saved configs
│   ├── lib/                # auth, request, metrics, data helpers
│   └── scenarios/          # Weighted endpoint + ordered sequence runners
├── tests/                  # Test suites
│   ├── unit/               # Unit tests (no external services)
│   ├── components/         # Component tests
│   ├── integration/        # Integration tests (need services)
│   ├── e2e/                # End-to-end tests
│   ├── api/                # API contract + smoke tests
│   └── ui/                 # Playwright dashboard tests
├── hooks/                  # Plugin hooks (on_run_start, on_run_finish)
├── data/                   # Runtime data (gitignored)
├── docs/                   # Design docs
├── bin/k6                  # Custom xk6 binary (built by just build)
├── .env.example
├── .mise.toml
├── docker-compose.yml
├── pyproject.toml
└── justfile
```

---

## Docs

| Document | Description |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Overall design, layer breakdown, key decisions |
| [docs/PLUGINS.md](docs/PLUGINS.md) | How to create and register a new plugin |
| [docs/AGENTS.md](docs/AGENTS.md) | AI agent integration guide (MCP, Python, CLI) |
| [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md) | Why each major decision was made |
| [docs/TESTING.md](docs/TESTING.md) | Test strategy and how to run each suite |

---

## Attribution

- **[k6](https://github.com/grafana/k6)** — load testing engine, © Grafana Labs, [AGPL-3.0](https://github.com/grafana/k6/blob/master/LICENSE.md)
- **[xk6-output-influxdb](https://github.com/grafana/xk6-output-influxdb)** — InfluxDB v2 output extension
- **[xk6-dashboard](https://github.com/grafana/xk6-dashboard)** — built-in k6 web dashboard extension
- **[xk6-faker](https://github.com/grafana/xk6-faker)** — fake data generation for k6 scripts
- **[Anthropic Claude](https://www.anthropic.com)** — Vision API powering the 31 AI visual QA agents
