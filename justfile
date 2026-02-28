# Generic k6 Performance Framework — edit k6/config/endpoints.json to target any HTTP service.

set dotenv-load := true

BASE_URL           := env_var_or_default("BASE_URL", "https://ai-beta-us-east-2.devo.cloud")
AUTH_TOKEN         := env_var_or_default("AUTH_TOKEN", "")
AUTH_HOST          := env_var_or_default("AUTH_HOST", "")
AUTH_REALM         := env_var_or_default("AUTH_REALM", "master")
AUTH_CLIENT_ID     := env_var_or_default("AUTH_CLIENT_ID", "")
AUTH_CLIENT_SECRET := env_var_or_default("AUTH_CLIENT_SECRET", "")
VUS                := env_var_or_default("VUS", "10")
DURATION           := env_var_or_default("DURATION", "60s")
RAMP_DURATION      := env_var_or_default("RAMP_DURATION", "30s")
SOAK_DURATION      := env_var_or_default("SOAK_DURATION", "10m")
STRESS_VUS         := env_var_or_default("STRESS_VUS", "50")
SPIKE_VUS          := env_var_or_default("SPIKE_VUS", "100")
SPIKE_DURATION     := env_var_or_default("SPIKE_DURATION", "30s")
INFLUXDB_URL       := env_var_or_default("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_ORG       := env_var_or_default("INFLUXDB_ORG", "matrix")
INFLUXDB_BUCKET    := env_var_or_default("INFLUXDB_BUCKET", "k6")
INFLUXDB_TOKEN     := env_var_or_default("INFLUXDB_TOKEN", "matrix-k6-token")

# Common k6 env flags (auth + base URL + load shape)
_k6_env := "--env BASE_URL=" + BASE_URL + \
            " --env AUTH_TOKEN=" + AUTH_TOKEN + \
            " --env AUTH_HOST=" + AUTH_HOST + \
            " --env AUTH_REALM=" + AUTH_REALM + \
            " --env AUTH_CLIENT_ID=" + AUTH_CLIENT_ID + \
            " --env AUTH_CLIENT_SECRET=" + AUTH_CLIENT_SECRET + \
            " --env VUS=" + VUS + \
            " --env DURATION=" + DURATION + \
            " --env RAMP_DURATION=" + RAMP_DURATION

# Common Docker -e flags
_docker_env := "-e BASE_URL=" + BASE_URL + \
               " -e AUTH_TOKEN=" + AUTH_TOKEN + \
               " -e AUTH_HOST=" + AUTH_HOST + \
               " -e AUTH_REALM=" + AUTH_REALM + \
               " -e AUTH_CLIENT_ID=" + AUTH_CLIENT_ID + \
               " -e AUTH_CLIENT_SECRET=" + AUTH_CLIENT_SECRET + \
               " -e VUS=" + VUS + \
               " -e DURATION=" + DURATION + \
               " -e RAMP_DURATION=" + RAMP_DURATION

[private]
default: help

# List all commands
help:
    @just --list

# ── Setup ──────────────────────────────────────────────────────────────────────

# Bootstrap: install tools via mise and sync Python deps
install:
    mise install
    uv sync --all-groups
    @just build

# Build local k6 binary with xk6-dashboard, xk6-output-influxdb, xk6-faker → ./bin/k6
build:
    @mkdir -p bin
    GOROOT=$(env -i PATH=/opt/homebrew/bin:/usr/bin:/bin go env GOROOT) \
      go run go.k6.io/xk6/cmd/xk6@v1.3.5 build v1.6.1 \
      --with github.com/grafana/xk6-dashboard@v0.8.0 \
      --with github.com/grafana/xk6-output-influxdb@latest \
      --with github.com/grafana/xk6-faker@latest \
      --output bin/k6

# Copy .env.example → .env (skips if already exists)
init:
    @[ -f .env ] && echo ".env already exists, skipping" || (cp .env.example .env && echo "Created .env — fill in your credentials")

# ── InfluxDB ───────────────────────────────────────────────────────────────────

# Start InfluxDB via Docker Compose (skips if already running)
influx-up:
    @docker ps --format '{{{{.Names}}}}' | grep -q '^influxdb$' \
      && echo "InfluxDB already running" \
      || docker compose up -d influxdb
    @echo "InfluxDB → http://localhost:8086  (org: matrix · bucket: k6 · token: matrix-k6-token)"

# Stop InfluxDB
influx-down:
    docker compose down

# Open InfluxDB UI in browser
influx-ui:
    open http://localhost:8086

# ── k6 Tests ───────────────────────────────────────────────────────────────────

# Run smoke test (2 VUs, 30s — quick sanity check)
smoke:
    k6 run {{_k6_env}} --env LOAD_PROFILE=smoke -v k6/main.js

# Run ramp load test (0 → VUS over RAMP_DURATION, hold DURATION)
ramp:
    k6 run {{_k6_env}} --env LOAD_PROFILE=ramp -v k6/main.js

# Run soak test (sustained load for SOAK_DURATION — endurance/memory leak)
soak:
    k6 run {{_k6_env}} --env LOAD_PROFILE=soak --env SOAK_DURATION={{SOAK_DURATION}} -v k6/main.js

# Run stress test (step-up to STRESS_VUS — find breaking point)
stress:
    k6 run {{_k6_env}} --env LOAD_PROFILE=stress --env STRESS_VUS={{STRESS_VUS}} -v k6/main.js

# Run spike test (instant burst to SPIKE_VUS — resilience check)
spike:
    k6 run {{_k6_env}} --env LOAD_PROFILE=spike \
      --env SPIKE_VUS={{SPIKE_VUS}} --env SPIKE_DURATION={{SPIKE_DURATION}} -v k6/main.js

# Run a profile writing JSON to out/  e.g. just json ramp
json profile="smoke":
    @mkdir -p out
    k6 run {{_k6_env}} --env LOAD_PROFILE={{profile}} \
      --out json=out/results-$(date +%Y%m%d-%H%M%S).json k6/main.js

# Run a profile writing metrics to InfluxDB via bin/k6  e.g. just influx-run ramp
influx-run profile="smoke":
    @test -f bin/k6 || (echo "ERROR: bin/k6 not found — run: just build" && exit 1)
    K6_INFLUXDB_ORGANIZATION={{INFLUXDB_ORG}} \
    K6_INFLUXDB_BUCKET={{INFLUXDB_BUCKET}} \
    K6_INFLUXDB_TOKEN={{INFLUXDB_TOKEN}} \
    bin/k6 run {{_k6_env}} --env LOAD_PROFILE={{profile}} \
      --out xk6-influxdb={{INFLUXDB_URL}} k6/main.js

# ── Dashboard ──────────────────────────────────────────────────────────────────

# Start dashboard only (use the Run tab to launch tests)
dashboard: influx-up
    uv run uvicorn dashboard.server:app --host 127.0.0.1 --port 5656 \
      --reload --reload-dir dashboard

# Run a profile with the dashboard server  e.g. just dash ramp
dash profile="smoke":
    uv run python dashboard/server.py {{profile}}

# ── Docker ─────────────────────────────────────────────────────────────────────

# Build Docker image
docker-build:
    docker build -t matrix-k6 .

# Run a profile in Docker  e.g. just docker-run ramp
docker-run profile="smoke":
    docker run --rm {{_docker_env}} -e LOAD_PROFILE={{profile}} matrix-k6

# Run a profile in Docker with dashboard on :5656  e.g. just docker-dash ramp
docker-dash profile="smoke":
    docker run --rm -p 5656:5656 {{_docker_env}} -e LOAD_PROFILE={{profile}} matrix-k6 {{profile}}

# ── Python ─────────────────────────────────────────────────────────────────────

# Sync Python dependencies
py-sync:
    uv sync --all-groups

# Add a runtime dependency  e.g. just py-add httpx
py-add dep:
    uv add {{dep}}

# Add a dev dependency  e.g. just py-add-dev pytest
py-add-dev dep:
    uv add --group dev {{dep}}

# Lint with ruff
lint:
    uv run ruff check dashboard/ tests/ api_tests/

# Lint, fix, and format
fix:
    uv run ruff check --fix dashboard/ tests/ api_tests/
    uv run ruff format dashboard/ tests/ api_tests/

# Type-check with ty
typecheck:
    uv run ty check dashboard/

# Run tests
test:
    uv run pytest

# Run unit tests only
test-unit:
    uv run pytest tests/unit/ -v

# Run per-component tests (each component in isolation)
test-components:
    uv run pytest tests/components/ -v

# Run integration tests (multi-component, needs local services)
test-integration:
    uv run pytest tests/integration/ -v

# Run E2E tests (full stack)
test-e2e:
    uv run pytest tests/e2e/ -v

# Run API smoke tests against a live target (set BASE_URL env var)
test-api:
    uv run pytest tests/api/ -v

# Combine and report coverage after running tests
coverage:
    uv run coverage combine
    uv run coverage html
    uv run coverage report

# Lint + typecheck + test
ci: lint typecheck test

# ── Utilities ──────────────────────────────────────────────────────────────────

# Fetch a Keycloak token via client credentials
get-token:
    @curl -sf \
      --data-urlencode "grant_type=client_credentials" \
      --data-urlencode "client_id={{AUTH_CLIENT_ID}}" \
      --data-urlencode "client_secret={{AUTH_CLIENT_SECRET}}" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      "{{AUTH_HOST}}/realms/{{AUTH_REALM}}/protocol/openid-connect/token" \
      | jq -r .access_token

# Show current env values (masks secrets)
env:
    @echo "BASE_URL           = {{BASE_URL}}"
    @echo "AUTH_TOKEN         = $([ -n '{{AUTH_TOKEN}}' ] && echo '****' || echo '(not set)')"
    @echo "AUTH_HOST          = {{AUTH_HOST}}"
    @echo "AUTH_REALM         = {{AUTH_REALM}}"
    @echo "AUTH_CLIENT_ID     = {{AUTH_CLIENT_ID}}"
    @echo "AUTH_CLIENT_SECRET = $([ -n '{{AUTH_CLIENT_SECRET}}' ] && echo '****' || echo '(not set)')"
    @echo "VUS                = {{VUS}}"
    @echo "DURATION           = {{DURATION}}"
    @echo "RAMP_DURATION      = {{RAMP_DURATION}}"

# Check that k6 is installed
check:
    @k6 version || echo "k6 not found — run: just install"

# Clean output files and caches
clean:
    rm -rf out/
    find . -type d -name __pycache__ -exec rm -rf {} +
    rm -rf .ruff_cache .pytest_cache

# ── Agent / Luna ───────────────────────────────────────────────────────────────

# Start Luna dashboard + InfluxDB, print the MCP connection URL
agent-start: influx-up
    @echo ""
    @echo "╔══════════════════════════════════════════════════════╗"
    @echo "║  Luna is starting…                                   ║"
    @echo "║  Dashboard  →  http://localhost:5656                  ║"
    @echo "║  MCP        →  http://localhost:5656/mcp              ║"
    @echo "║  Health     →  http://localhost:5656/health           ║"
    @echo "║  API Docs   →  http://localhost:5656/docs              ║"
    @echo "╚══════════════════════════════════════════════════════╝"
    @echo ""
    uv run uvicorn dashboard.server:app --host 0.0.0.0 --port 5656 \
      --reload --reload-dir dashboard

# Test any service in one command  e.g. just test-service url=https://api.example.com profile=smoke
test-service url profile="smoke" auth="":
    @echo "Luna: testing {{url}} with profile={{profile}}"
    uv run python -c "from api_tests.luna import LunaClient; luna = LunaClient(); result = luna.test_service('{{url}}', token='{{auth}}', profile='{{profile}}'); print(result.summary); exit(0 if result.success else 1)"

# Print MCP server connection info for agents
mcp-info:
    @echo "MCP server:  http://localhost:5656/mcp"
    @echo "Transport:   streamable-http (spec 2025-03-26)"
    @echo ""
    @echo "Connect with Claude Desktop — add to claude_desktop_config.json:"
    @echo '  "luna": {'
    @echo '    "command": "npx",'
    @echo '    "args": ["-y", "mcp-remote", "http://localhost:5656/mcp"]'
    @echo '  }'
    @echo ""
    @echo "Connect with Python (mcp library):"
    @echo '  from mcp import ClientSession'
    @echo '  from mcp.client.streamable_http import streamablehttp_client'

# Run the Luna Python client in interactive mode (REPL)
luna-repl:
    uv run python -c "from api_tests.luna import LunaClient; luna = LunaClient(); print('LunaClient connected to', luna._base_url); print('luna.health()         ->', luna.health()); print('luna.list_configs()   ->', len(luna.list_configs()), 'configs'); print(); print('Try: luna.test_service(\"https://your-api.com\")')"

# Show Luna health status
luna-health:
    @curl -sf http://localhost:5656/health | python3 -m json.tool || echo "Luna is not running — run: just agent-start"
