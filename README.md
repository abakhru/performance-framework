# k6 Performance Framework

A self-hosted performance testing framework built on [k6](https://k6.io) with a live dashboard, InfluxDB time-series storage, and a browser UI. Point it at any HTTP/REST/GraphQL service via `endpoints.json` or auto-discover from a Postman collection or OpenAPI spec.

---

## Prerequisites

Tool versions are pinned in `.mise.toml`. Install [mise](https://mise.jdx.dev) then:

```bash
just install          # mise install + uv sync + build custom k6 binary
just init             # copy .env.example → .env
```

**Services** (started via Docker Compose):

| Service | Purpose | Port |
|---|---|---|
| InfluxDB v2 | Metrics storage | 8086 |
| k6 (xk6-influxdb) | Load generator | 6565 |

```bash
just influx-up
```

---

## Quick Start

```bash
# Edit .env — set BASE_URL and auth vars at minimum
just dashboard        # start dashboard + InfluxDB, open http://localhost:5656
```

Or run headless from the CLI:

```bash
just smoke            # 2 VUs · 30s sanity check
just ramp             # 0→N VUs ramp · hold · ramp down
just soak             # sustained load endurance
just stress           # step-up to breaking point
just spike            # instant burst resilience
```

---

## Configuration

Copy `.env.example` for a full template. Core variables:

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `https://...` | Target base URL |
| `VUS` | `10` | Max virtual users |
| `DURATION` | `60s` | Hold duration |
| `RAMP_DURATION` | `30s` | Ramp up/down duration |

**Auth** — fill only the fields matching your auth mode:

| Variable(s) | Mode |
|---|---|
| `AUTH_TOKEN` | Bearer token |
| `AUTH_BASIC_USER` + `AUTH_BASIC_PASS` | HTTP Basic |
| `AUTH_API_KEY` + `AUTH_API_KEY_HEADER` | API Key |
| `AUTH_HOST` + `AUTH_REALM` + `AUTH_CLIENT_ID` + `AUTH_CLIENT_SECRET` | Keycloak client credentials |

**InfluxDB** (defaults work with `just influx-up`):

| Variable | Default |
|---|---|
| `INFLUXDB_URL` | `http://localhost:8086` |
| `INFLUXDB_ORG` | `matrix` |
| `INFLUXDB_BUCKET` | `k6` |
| `INFLUXDB_TOKEN` | `matrix-k6-token` |

---

## Load Profiles

| Profile | Shape | Use case |
|---|---|---|
| **smoke** | 2 VUs · 30s fixed | Sanity check — validates all endpoints respond correctly |
| **ramp** | 0 → VUS → 0 | Standard load test with configurable ramp and hold |
| **soak** | VUS · `SOAK_DURATION` | Endurance — find memory leaks and connection exhaustion |
| **stress** | Step-up to `STRESS_VUS` | Find the breaking point |
| **spike** | Instant burst to `SPIKE_VUS` | Resilience — sudden traffic surge |

---

## Endpoints Config

`k6/config/endpoints.json` defines what gets tested. Minimal example:

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

**Endpoint fields:**

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
| `checks` | no | Pass/fail assertions (see below) |
| `data_file` | no | CSV file name for data-driven injection |

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

Populate endpoints without hand-authoring JSON: use the **Discover tab** in the dashboard to import from a Postman collection, OpenAPI/Swagger spec, or live URL scan.

---

## Dashboard

Start with `just dashboard` → `http://localhost:5656`.

| Tab | Purpose |
|---|---|
| **Execute** | Configure and launch runs from the browser |
| **Overview** | Real-time RPS, latency charts, Apdex gauge |
| **Endpoints** | Per-operation breakdown with p95 trend sparklines |
| **History** | Past runs with SLO verdict, diff view, and baseline comparison |
| **Discover** | Import endpoints from Postman, OpenAPI, or URL scan |

Other features: environment profiles, webhook notifications on run finish, SVG pass/fail badges, HTML/CSV export, multi-target parallel runs, and plugin hooks (`hooks/*.py`).

---

## Directory Structure

```
.
├── dashboard/          # Python dashboard server (FastAPI)
│   ├── server.py
│   ├── index.html
│   └── routers/        # Route modules
├── k6/
│   ├── config/
│   │   └── endpoints.json   # ← main config file
│   ├── lib/            # auth, request, metrics, data helpers
│   ├── scenarios/      # weighted endpoint + ordered sequence runners
│   └── main.js         # entry point: setup / default / teardown
├── hooks/              # optional Python plugins (on_run_start, on_run_finish)
├── data/               # optional CSV files for data-driven load injection
├── bin/k6              # custom k6 binary (built by just build)
├── .env.example
├── .mise.toml
├── docker-compose.yml
└── justfile
```

---

## Common Commands

```bash
just install            # bootstrap everything
just dashboard          # start dashboard + InfluxDB
just smoke              # quick sanity run
just ramp               # standard load test
just json ramp          # run ramp, save results to out/
just influx-run ramp    # run directly to InfluxDB (no dashboard)
just dash ramp          # run ramp with dashboard server
just lint               # ruff check
just typecheck          # ty check
just ci                 # lint + typecheck + test
just clean              # remove out/, caches
```
