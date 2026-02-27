# Matrix/Strike48 k6 Performance Framework

A full-stack, self-hosted performance testing framework built on [k6](https://k6.io) with a live dashboard, InfluxDB time-series storage, and a rich browser UI. Drop-in generic: point it at any HTTP/REST/GraphQL service via `endpoints.json` or auto-discover from a Postman collection, OpenAPI spec, or GraphQL introspection.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Load Profiles](#load-profiles)
- [Dashboard](#dashboard)
  - [Execute Tab](#execute-tab)
  - [Overview Tab](#overview-tab)
  - [Endpoints Tab](#endpoints-tab)
  - [HTTP Metrics Tab](#http-metrics-tab)
  - [Log Tab](#log-tab)
  - [History Tab](#history-tab)
  - [Discover Tab](#discover-tab)
- [Autodiscovery](#autodiscovery)
- [SLO Budget Tracking](#slo-budget-tracking)
- [Comparison Baselines & Diff View](#comparison-baselines--diff-view)
- [Environment Profiles](#environment-profiles)
- [Scenario Builder](#scenario-builder)
- [Auth Token Auto-refresh](#auth-token-auto-refresh)
- [Data-Driven Load Injection](#data-driven-load-injection)
- [Per-Endpoint Latency Sparklines](#per-endpoint-latency-sparklines)
- [Percentile Heatmap](#percentile-heatmap)
- [Export & Reporting](#export--reporting)
- [Webhooks & CI Integration](#webhooks--ci-integration)
- [Multi-Target Runs](#multi-target-runs)
- [Plugin Hooks](#plugin-hooks)
- [Custom Check Definitions](#custom-check-definitions)
- [Distributed k6](#distributed-k6)
- [Endpoints Config Reference](#endpoints-config-reference)
- [Directory Structure](#directory-structure)
- [Architecture](#architecture)

---

## Prerequisites

Tool versions are pinned in `.mise.toml`. Install [mise](https://mise.jdx.dev) then run:

```bash
mise install
```

This installs the pinned versions of `k6` (with InfluxDB extension) and `just`.

**Runtime dependencies:**

| Service | Purpose | Default port |
|---|---|---|
| InfluxDB v2 | Metrics storage | 8086 |
| k6 (xk6-influxdb build) | Load generator | 6565 (REST API) |

Start all services with Docker Compose:

```bash
docker-compose up -d
```

---

## Quick Start

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env — set BASE_URL and AUTH_TOKEN at minimum

# 2. Start the dashboard
python3 dashboard/server.py

# 3. Open http://localhost:5656
# 4. Select a load profile and click START RUN
```

Or run from the CLI without the dashboard:

```bash
just smoke    # 2 VUs · 30s sanity check
just ramp     # 0→N VUs ramp · hold · ramp down
just soak     # sustained load endurance
just stress   # step-up to breaking point
just spike    # instant burst resilience
```

---

## Configuration

All configuration flows through `.env` (loaded at server startup) or the dashboard UI. Copy `.env.example` for a template.

### Core Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BASE_URL` | no | `https://ai-beta-us-east-2.devo.cloud` | Target base URL |
| `LOAD_PROFILE` | no | `smoke` | Active load profile |
| `VUS` | no | `10` | Max virtual users |
| `DURATION` | no | `60s` | Hold duration |
| `RAMP_DURATION` | no | `30s` | Ramp up/down duration |
| `APDEX_T` | no | `500` | Apdex satisfying threshold (ms) |

### Authentication

Fill **only** the fields matching your auth mode — all others are ignored.

| Variable | Description |
|---|---|
| `AUTH_TOKEN` | Bearer token (`Authorization: Bearer …`) |
| `AUTH_BASIC_USER` + `AUTH_BASIC_PASS` | HTTP Basic auth |
| `AUTH_API_KEY` + `AUTH_API_KEY_HEADER` | API key (custom header, default `X-API-Key`) |
| `AUTH_HOST` + `AUTH_REALM` + `AUTH_CLIENT_ID` + `AUTH_CLIENT_SECRET` | Keycloak client_credentials flow |

### InfluxDB

| Variable | Default | Description |
|---|---|---|
| `INFLUXDB_URL` | `http://localhost:8086` | InfluxDB v2 base URL |
| `INFLUXDB_ORG` | `matrix` | InfluxDB organization |
| `INFLUXDB_BUCKET` | `k6` | InfluxDB bucket |
| `INFLUXDB_TOKEN` | `matrix-k6-token` | InfluxDB API token |

---

## Load Profiles

Five built-in profiles cover the most common performance testing patterns:

| Profile | VUs | Shape | Use case |
|---|---|---|---|
| **smoke** | 2 | Fixed 30s | Pre-load sanity check — validates all endpoints return 200 |
| **ramp** | `VUS` | 0→N→0 | Standard load test with configurable ramp and hold |
| **soak** | `VUS` | fixed for hours | Endurance test — find memory leaks, connection exhaustion |
| **stress** | `VUS×2` | step-up | Find breaking point — doubles VUs every 2 min |
| **spike** | `VUS×5` | instant burst | Resilience — slams max VUs instantly then drops back |

---

## Dashboard

The dashboard is a single-page app served at `http://localhost:5656`. It polls k6's REST API at `/v1/status` and `/v1/metrics` every 2 seconds and writes snapshots to InfluxDB for historical analysis.

**Keyboard shortcuts:**

| Key | Action |
|---|---|
| `1` | Execute tab |
| `2` | Overview tab |
| `3` | Endpoints tab |
| `4` | HTTP Metrics tab |
| `5` | Log tab |
| `6` | History tab |
| `7` | Discover tab |
| `t` | Cycle through themes |
| `l` | Toggle live/paused polling |

**Themes:** Matrix · Cyberpunk · Midnight · Amber · Aurora · Arctic

### Execute Tab

Configure and launch a k6 run without touching the CLI. Fields:

- **Load Profile** — profile picker (smoke / ramp / soak / stress / spike)
- **Target** — Base URL
- **Authentication** — all auth modes (Bearer, Basic, API Key, Keycloak)
- **Load parameters** — VUs, Duration, Ramp Duration (shown only for profiles that use them)

Click **START RUN** to launch k6 in a supervised background thread. The dashboard immediately starts polling metrics. Click **STOP RUN** to send SIGTERM to k6 and finalize the run record.

### Overview Tab

Real-time live view while a run is active:

- **Header stats bar** — VUs, total requests, RPS, p95 ms, error rate
- **4-chart time-series row** — RPS + active VUs (shared canvas), p50/p75/p95/p99 latency, p95 + p99 overlay, VU ramp shape
- **Core metric cards** — total reqs, RPS, VUs, error rate, avg/p95/p99 latency, Apdex score, checks pass rate, TTFB, data in/out, connection reuse rate, status class breakdown (2xx/3xx/4xx/5xx)
- **Latency histogram** — 7-bucket bar chart (≤50ms … >5s)
- **Leaderboard** — top 10 slowest operations (p95 bar chart)
- **Threshold checks** — visual pass/fail per defined threshold
- **Apdex gauge** — color-coded score ring (A/B/C/D/F grade)

### Endpoints Tab

Per-operation breakdown table. Refreshes every 2s from live k6 metrics:

- Group filter chips at the top let you isolate one operation group
- Per-op: request count, errors, error %, avg/min/max/p90 ms, p95 latency bar
- Group color coding persists across tabs

### HTTP Metrics Tab

Full k6 metric tree — all standard `http_req_*` metrics (duration, connecting, waiting/TTFB, receiving, sending, TLS handshaking, failed) plus data transferred.

### Log Tab

Live event stream — run start, errors, stop events, and any messages k6 writes to stdout.

### History Tab

Browse all past runs stored in InfluxDB (up to 200, last 30 days):

- **Run list** — profile, base URL, start time, status badge, duration, total requests, p95 ms, error rate, Apdex grade
- **Run detail** — click any row to expand: verdict banner (pass/fail based on SLO), full metric cards, latency histogram, per-operation table, snapshot time-series charts
- **Comparison baseline** — pin any run as baseline; all subsequent run detail views show `+N%` / `-N%` deltas against it
- **Diff view** — select two runs and open a side-by-side comparison table
- **SLO badges** — pass/fail indicator per metric vs. configured SLO thresholds
- **Export** — download run data as HTML report or CSV snapshot

### Discover Tab

Populate `endpoints.json` without hand-authoring JSON. Three discovery methods:

1. **Postman Import** — click "Load from repo" to parse the bundled Postman collection, or drag-and-drop any `.json` collection file
2. **URL Scan** — enter a base URL; the server probes 8 standard OpenAPI/Swagger paths then 4 GraphQL introspection paths
3. **Manual Add** — inline form: name, path, type (REST/GraphQL), group, weight

The **preview table** shows all discovered endpoints with editable group and weight fields. Uncheck rows to exclude them. The **Save bar** offers two modes:
- **Replace all** — overwrites `endpoints.json` entirely
- **Merge with existing** — appends to the existing endpoint list

Saving hot-reloads the server's in-memory config and `OP_GROUP` mapping — no restart needed.

---

## Autodiscovery

The discovery engine probes a live service in this order:

1. **OpenAPI/Swagger** — tries `/openapi.json`, `/swagger.json`, `/api/openapi.json`, `/api/swagger.json`, `/api/v1/openapi.json`, `/docs/openapi.json`, `/api-docs`, `/api/docs`
2. **GraphQL introspection** — tries `/graphql`, `/api/graphql`, `/api/v1alpha`, `/api/v1/graphql` with an introspection query; maps `queryType.fields` → query endpoints and `mutationType.fields` → mutation endpoints

Each discovered endpoint conforms to the standard endpoint object schema so it works immediately with the k6 runner.

For Postman collections, the parser recursively walks folder → request trees. GraphQL items (body mode = `graphql`) produce `type: "graphql"` endpoints with the query pre-populated. REST items produce `type: "rest"` endpoints with method and optional body.

---

## SLO Budget Tracking

Define pass/fail thresholds in `endpoints.json` at the top level:

```json
{
  "service": "My API",
  "slos": {
    "p95_ms":     500,
    "p99_ms":     2000,
    "error_rate": 0.01,
    "checks_rate": 0.99,
    "apdex_score": 0.85
  },
  "endpoints": [ ... ]
}
```

After every run, the dashboard compares final metrics against these thresholds and:
- Writes a `k6_run_slo` measurement to InfluxDB with `pass=1/0` per metric
- Shows a **verdict banner** (green PASS / red FAIL) in the History detail view
- Displays per-metric SLO badges: ✓ `p95 382ms < 500ms` or ✗ `error_rate 2.1% > 1%`

Expose via API:
```
GET /runs/<id>/slo   → { "verdict": "pass", "checks": { "p95_ms": { "value": 382, "threshold": 500, "pass": true }, ... } }
GET /slo/config      → current global SLO thresholds
POST /slo/config     → update thresholds (JSON body)
```

---

## Comparison Baselines & Diff View

### Baselines

Pin any historical run as the reference baseline:

```
POST /runs/<id>/baseline   → sets this run as the baseline
DELETE /runs/baseline      → clears the baseline
GET /runs/baseline         → returns current baseline run_id and summary
```

Once a baseline is set:
- The **header stats bar** shows `+12%` / `-3%` deltas for RPS, p95, error rate
- The **History detail view** shows per-metric delta columns
- The baseline run row is highlighted with a star badge in the run list

### Diff View

Select any two runs in History and click **Compare**:

```
GET /runs/diff?a=<run_id>&b=<run_id>   → side-by-side metric comparison
```

The diff modal shows a table with: metric name · run A value · run B value · absolute delta · % change · direction arrow. Red/green color coding highlights regressions vs. improvements.

---

## Environment Profiles

Named configuration slots — store multiple target environments without editing `.env`:

```
GET  /profiles            → list all profiles
POST /profiles            → create profile (JSON: {name, base_url, auth_token, vus, ...})
PUT  /profiles/<name>     → update profile
DELETE /profiles/<name>   → delete profile
POST /profiles/<name>/activate  → load profile as active config
```

Profiles are stored in `dashboard/profiles.json`. The **Execute tab** shows a profile dropdown; selecting one pre-fills all form fields. Profiles are shown in the History run list so you can filter runs by environment.

Example profile:

```json
{
  "name": "staging",
  "base_url": "https://staging.example.com",
  "auth_token": "eyJ...",
  "vus": "20",
  "duration": "120s",
  "ramp_duration": "30s"
}
```

---

## Scenario Builder

Define ordered user journeys instead of random weighted endpoint selection. Add a `scenarios` array to `endpoints.json`:

```json
{
  "scenarios": [
    {
      "name": "user_journey",
      "weight": 3,
      "think_time": "0.5s",
      "steps": [
        { "ref": "ListAllAgents" },
        { "ref": "GetConversations", "think_time": "1s" },
        { "ref": "GetConversation" }
      ]
    }
  ]
}
```

k6 picks a scenario by weight, then executes steps in order with configurable think-time pauses between them. Steps reference endpoint names from the `endpoints` array.

A **Scenario Builder UI** in the dashboard lets you drag-and-drop endpoints into sequences, set think times, and preview the resulting JSON before saving.

---

## Auth Token Auto-refresh

For long-running soak and stress tests where tokens expire mid-run:

```json
// .env or Execute tab
AUTH_REFRESH_STRATEGY=keycloak   // "keycloak" | "bearer_endpoint" | "none"
AUTH_REFRESH_ENDPOINT=/auth/refresh
AUTH_REFRESH_INTERVAL=3300       // seconds (55 min for 1h tokens)
```

When a request receives a `401` response, `lib/auth.js` automatically:
1. Re-runs the configured auth flow (Keycloak client_credentials or a custom refresh endpoint)
2. Updates the shared auth headers for all VUs
3. Retries the original request once

The dashboard exposes `POST /run/refresh-token` to manually trigger a token refresh mid-run, useful for debugging auth issues.

---

## Data-Driven Load Injection

Feed real user data (IDs, search terms, payloads) into endpoints instead of static variables:

### Upload a data file

```
POST /data/upload     multipart/form-data: file=data.csv, name=users
GET  /data            list uploaded data files
DELETE /data/<name>   remove a data file
```

CSV example (`users.csv`):
```csv
userId,searchTerm,region
abc123,machine learning,us-east
def456,neural network,eu-west
```

### Reference in endpoints.json

```json
{
  "name": "SearchDocs",
  "type": "rest",
  "method": "GET",
  "path": "/api/search",
  "data_file": "users",
  "variables_from_data_file": {
    "q": "searchTerm",
    "region": "region"
  }
}
```

k6 loads the CSV into a `SharedArray` (shared read-only across all VUs, memory-efficient). Each VU iteration picks a row by index (`VU_id % row_count`) for deterministic distribution, or randomly.

A **Data Files panel** in the Discover tab lists uploaded files, shows row count and column names, and lets you preview the first 5 rows.

---

## Per-Endpoint Latency Sparklines

The **Endpoints tab** shows a small inline sparkline chart per operation showing p95 latency trend across the last 10 runs. Immediately surfaces which operations are degrading slowly over deploys.

Data endpoint:
```
GET /ops/<op_name>/trend?runs=10   → [ { run_id, started_at, p95_ms, avg_ms, error_rate }, ... ]
```

Sparklines use the same canvas rendering engine as the Overview charts, color-coded by trend direction: green (improving), amber (stable), red (degrading).

---

## Percentile Heatmap

The **Overview tab** includes a calendar heatmap showing p95 latency intensity by day (last 90 days, configurable):

```
GET /heatmap?metric=p95_ms&days=90   → { days: [ { date, value, run_count }, ... ] }
```

Color scale: dark (fast / few runs) → bright accent (slow / many runs). Hover a cell to see the date, best/worst/avg p95, and run count. Useful for spotting weekly patterns (weekends slow, Monday spikes) or deploy regressions.

---

## Export & Reporting

### HTML Report

```
GET /runs/<id>/report
```

Returns a self-contained single-file HTML report with all charts, metric tables, and SLO verdict — no external dependencies. Suitable for attaching to CI artifacts, emailing to stakeholders, or archiving.

### CSV Export

```
GET /runs/<id>/csv
```

Returns the time-series snapshot data as CSV with columns: `elapsed_s, vus, rps, p50_ms, p75_ms, p95_ms, p99_ms, avg_ms, total_reqs`.

### SVG Badge

```
GET /runs/<id>/badge
```

Returns an SVG pass/fail badge suitable for embedding in GitHub READMEs or PR descriptions:

```markdown
![Performance](http://localhost:5656/runs/latest/badge)
```

---

## Webhooks & CI Integration

Fire an HTTP POST to any URL when a run completes (or fails):

```
GET    /webhooks          list configured webhooks
POST   /webhooks          create: { url, events, secret, name }
DELETE /webhooks/<id>     remove
POST   /webhooks/<id>/test  fire a test payload
```

Events: `run.started`, `run.finished`, `run.failed`, `slo.breached`

Payload on `run.finished`:

```json
{
  "event": "run.finished",
  "run_id": "abc123",
  "profile": "ramp",
  "status": "finished",
  "base_url": "https://api.example.com",
  "duration_s": 120,
  "total_reqs": 8240,
  "error_rate": 0.002,
  "p95_ms": 382,
  "apdex_score": 0.94,
  "slo_verdict": "pass"
}
```

The optional `secret` field enables HMAC-SHA256 request signing — the `X-Perf-Signature` header lets receivers verify authenticity.

**GitHub PR Check example:**

```json
{
  "url": "https://api.github.com/repos/org/repo/statuses/${commit_sha}",
  "events": ["run.finished", "run.failed"],
  "name": "github-status"
}
```

Stored in `dashboard/webhooks.json`. Fired asynchronously in a background thread so they never block the run lifecycle.

---

## Multi-Target Runs

Run the same load profile against multiple base URLs simultaneously — ideal for blue/green comparisons or regional testing:

```
POST /run/multi
{
  "targets": [
    { "base_url": "https://blue.example.com",  "label": "blue"  },
    { "base_url": "https://green.example.com", "label": "green" }
  ],
  "profile": "ramp",
  "vus": 20,
  "duration": "60s"
}
```

Each target gets its own k6 process with a unique `run_id` tagged with `label`. The History tab shows multi-target runs grouped together with an automatic diff view between labels.

---

## Plugin Hooks

Drop Python files into `hooks/` to extend the framework without modifying core code:

```python
# hooks/my_hook.py

def on_run_start(cfg: dict) -> None:
    """Called before k6 launches. cfg contains all run config fields."""
    print(f"[my_hook] Starting {cfg['profile']} against {cfg['base_url']}")

def on_run_finish(result: dict) -> None:
    """Called after k6 exits. result contains all finalized metrics."""
    if result.get("error_rate", 0) > 0.05:
        send_pagerduty_alert(result)
```

Available hooks:

| Hook | Args | Called |
|---|---|---|
| `on_run_start(cfg)` | run config dict | Before k6 launches |
| `on_run_finish(result)` | finalized metrics dict | After k6 exits and metrics are written |
| `on_slo_breach(result, violations)` | metrics + list of breached SLOs | When SLO verdict is `fail` |
| `on_snapshot(snapshot)` | current poll metrics | Every 5s during a live run |

Hooks are discovered at server start and reloaded on each run so you can edit them without restarting the server.

---

## Custom Check Definitions

Extend the check set for any endpoint beyond the built-in `status`, `no_graphql_errors`, and `has_data`:

```json
{
  "name": "SearchUsers",
  "type": "rest",
  "path": "/api/users",
  "checks": {
    "status": 200,
    "body_path": "data.users",
    "header_present": "X-Request-Id",
    "max_duration_ms": 500,
    "body_contains": "\"total\":"
  }
}
```

Supported check types:

| Check key | Type | Description |
|---|---|---|
| `status` | int | Expected HTTP status code |
| `body_path` | string | Dot-path must exist and be non-null |
| `header_present` | string | Response header must be present |
| `max_duration_ms` | int | Request must complete within N ms |
| `body_contains` | string | Response body must contain substring |
| `no_graphql_errors` | bool | GraphQL `errors` array must be absent/empty |
| `has_data` | bool | GraphQL `data` field must be non-null |

The **Discover tab** includes a Custom Checks panel where you can add/edit checks for any endpoint in the current preview table without editing JSON.

---

## Distributed k6

Run at higher VU counts by distributing load across multiple k6 instances.

### k6 Cloud mode

Set `K6_CLOUD_TOKEN` in `.env` and select **Cloud** execution mode in the Execute tab. The dashboard proxies the run through the k6 Cloud REST API and streams results back via the same InfluxDB pipeline.

### k6 Operator (Kubernetes)

For self-hosted distributed runs on Kubernetes, the framework generates a `TestRun` CRD manifest:

```
GET /runs/<id>/k6-manifest   → TestRun YAML for k6-operator
```

Apply it to your cluster:
```bash
kubectl apply -f <(curl http://localhost:5656/runs/latest/k6-manifest)
```

Results are shipped via `xk6-influxdb` output and appear in the History tab alongside local runs.

---

## Endpoints Config Reference

`k6/config/endpoints.json` is the single source of truth for what gets tested:

```json
{
  "service": "My API",

  "slos": {
    "p95_ms": 500,
    "error_rate": 0.01,
    "apdex_score": 0.85
  },

  "scenarios": [
    {
      "name": "browse",
      "weight": 2,
      "think_time": "0.5s",
      "steps": [ { "ref": "ListItems" }, { "ref": "GetItem" } ]
    }
  ],

  "endpoints": [
    {
      "name": "ListUsers",
      "group": "users",
      "type": "rest",
      "method": "GET",
      "path": "/api/users",
      "weight": 3,
      "data_file": "users",
      "headers": { "X-Tenant": "acme" },
      "checks": {
        "status": 200,
        "body_path": "data",
        "max_duration_ms": 300
      }
    },
    {
      "name": "SearchAgents",
      "group": "agents",
      "type": "graphql",
      "path": "/api/v1alpha",
      "weight": 2,
      "query": "query ListAgents { agents { id name } }",
      "variables": {},
      "checks": {
        "status": 200,
        "no_graphql_errors": true,
        "has_data": true
      }
    }
  ],

  "setup": [
    {
      "name": "CreateTestUser",
      "type": "rest",
      "method": "POST",
      "path": "/api/users",
      "variables": { "name": "k6-perf-test" },
      "result_key": "userId",
      "result_path": "data.id"
    }
  ],

  "teardown": [
    {
      "name": "DeleteTestUser",
      "type": "rest",
      "method": "DELETE",
      "path": "/api/users/${data.userId}",
      "requires": ["userId"]
    }
  ]
}
```

### Endpoint Object Fields

| Field | Required | Description |
|---|---|---|
| `name` | yes | Unique identifier — used as metric tag |
| `group` | yes | Group label for aggregation and filtering |
| `type` | yes | `"rest"` or `"graphql"` |
| `path` | yes | URL path appended to `BASE_URL` |
| `weight` | no (default 1) | Relative selection probability |
| `method` | REST only | HTTP verb (GET/POST/PUT/DELETE/PATCH) |
| `body` | REST only | Static JSON request body |
| `query` | GQL only | GraphQL query/mutation string |
| `variables` | GQL only | Static GraphQL variables |
| `variables_from_data` | no | Map `{ gqlVar: dataKey }` from setup/data results |
| `variables_template` | no | Variables with `${timestamp}` substitution |
| `data_file` | no | Name of uploaded CSV data file for data-driven injection |
| `variables_from_data_file` | no | Map column names to variable names |
| `headers` | no | Extra request headers merged with auth headers |
| `requires` | no | Skip if these data keys are missing from setup results |
| `result_key` | setup only | Key name to store result in shared data dict |
| `result_path` | setup only | Dot-path into JSON response to extract result |
| `checks` | no | Check definitions (see Custom Check Definitions) |

---

## Directory Structure

```
.
├── dashboard/
│   ├── server.py          # Python HTTP server — dashboard API + k6 supervisor
│   ├── index.html         # Single-page dashboard application
│   ├── profiles.json      # Named environment profiles (auto-created)
│   ├── webhooks.json      # Configured webhooks (auto-created)
│   └── state.json         # Baseline run_id, active profile (auto-created)
├── hooks/
│   └── *.py               # Plugin hooks — on_run_start, on_run_finish, etc.
├── data/
│   └── *.csv              # Uploaded data files for data-driven load injection
├── k6/
│   ├── config/
│   │   ├── endpoints.json     # Endpoint definitions — the main config file
│   │   └── options.js         # Load profile factory (smoke / ramp / soak / stress / spike)
│   ├── lib/
│   │   ├── auth.js            # Auth strategy: Bearer, Basic, API Key, Keycloak, auto-refresh
│   │   ├── request.js         # executeEndpoint() — REST + GraphQL dispatcher
│   │   ├── metrics.js         # Dynamic per-op Trend/Counter/Rate registration
│   │   └── data.js            # SharedArray loader for data-driven load injection
│   ├── scenarios/
│   │   ├── run-endpoints.js   # Random weighted endpoint executor
│   │   └── run-sequence.js    # Ordered scenario executor (user journeys)
│   └── main.js                # Entry point: setup / default / teardown
├── bin/
│   └── k6                 # k6 binary (xk6-influxdb build)
├── docs/
│   └── history/           # Planning documents and changelogs
├── .env.example           # Environment variable template
├── .mise.toml             # Pinned tool versions
├── docker-compose.yml     # InfluxDB + k6 service stack
├── Dockerfile             # Container build
└── justfile               # Task runner (just smoke, just ramp, etc.)
```

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                     Browser (port 5656)                       │
│  Execute · Overview · Endpoints · HTTP · Log · History · Discover │
└───────────────────────┬───────────────────────────────────────┘
                        │ HTTP API
┌───────────────────────▼───────────────────────────────────────┐
│                  dashboard/server.py                          │
│  Routes: /run/*, /runs/*, /config/*, /discover/*, /profiles/* │
│          /webhooks/*, /data/*, /slo/*, /heatmap, /ops/*/trend │
│  k6 supervisor thread → start / poll / finalize               │
│  Plugin hooks loader  → hooks/*.py                            │
│  Webhook dispatcher   → background thread                     │
└──────────┬───────────────────────┬────────────────────────────┘
           │ subprocess            │ InfluxDB line protocol
┌──────────▼──────────┐  ┌────────▼────────────────────────────┐
│       k6            │  │           InfluxDB v2               │
│  main.js            │  │  Measurements:                      │
│  lib/auth.js        │  │    k6_run_start  k6_run_final       │
│  lib/request.js     │  │    k6_run_slo    k6_snapshot        │
│  lib/metrics.js     │◄─┤    k6_op                            │
│  lib/data.js        │  │                                     │
│  REST API :6565     │  │  Queried by: /runs, /snapshots,     │
└─────────────────────┘  │  /ops, /heatmap, /ops/*/trend      │
                         └─────────────────────────────────────┘
```

### HTTP API Reference

| Method | Path | Description |
|---|---|---|
| GET | `/` | Dashboard HTML |
| GET | `/run/status` | Current k6 process state |
| GET | `/run/config` | Env-var defaults for Execute tab |
| POST | `/run/start` | Launch a k6 run |
| POST | `/run/stop` | Stop the current run |
| POST | `/run/multi` | Multi-target parallel runs |
| POST | `/run/refresh-token` | Refresh auth token mid-run |
| GET | `/runs` | Run history list (last 30d) |
| GET | `/runs/<id>/snapshots` | Time-series data for a run |
| GET | `/runs/<id>/ops` | Per-operation summary |
| GET | `/runs/<id>/slo` | SLO verdict and per-metric checks |
| GET | `/runs/<id>/report` | Self-contained HTML report |
| GET | `/runs/<id>/csv` | Snapshot data as CSV |
| GET | `/runs/<id>/badge` | SVG pass/fail badge |
| GET | `/runs/<id>/k6-manifest` | k6-operator TestRun YAML |
| POST | `/runs/<id>/baseline` | Pin run as comparison baseline |
| DELETE | `/runs/baseline` | Clear baseline |
| GET | `/runs/baseline` | Get current baseline |
| GET | `/runs/diff?a=<id>&b=<id>` | Side-by-side run comparison |
| GET | `/config/endpoints` | Current endpoints.json |
| GET | `/slo/config` | Current SLO thresholds |
| POST | `/slo/config` | Update SLO thresholds |
| GET | `/heatmap` | Per-day p95 heatmap data |
| GET | `/ops/<name>/trend` | Per-op p95 trend across runs |
| GET | `/profiles` | List environment profiles |
| POST | `/profiles` | Create a profile |
| PUT | `/profiles/<name>` | Update a profile |
| DELETE | `/profiles/<name>` | Delete a profile |
| POST | `/profiles/<name>/activate` | Load profile as active config |
| GET | `/webhooks` | List webhooks |
| POST | `/webhooks` | Create a webhook |
| DELETE | `/webhooks/<id>` | Delete a webhook |
| POST | `/webhooks/<id>/test` | Fire a test webhook payload |
| GET | `/data` | List uploaded data files |
| POST | `/data/upload` | Upload a CSV data file |
| DELETE | `/data/<name>` | Delete a data file |
| GET | `/discover/postman-collection` | Serve bundled Postman JSON |
| GET | `/discover/url` | Scan a URL for API spec |
| POST | `/discover/postman` | Parse a Postman collection |
| POST | `/endpoints/save` | Save and hot-reload endpoints.json |
| GET | `/k6/*` | Proxy to k6 REST API `:6565` |
