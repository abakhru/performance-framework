# Generic k6 Performance Framework
# Run `just` to see available commands.
# Edit k6/config/endpoints.json to target any HTTP service.

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
INFLUXDB_URL       := env_var_or_default("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_ORG       := env_var_or_default("INFLUXDB_ORG", "matrix")
INFLUXDB_BUCKET    := env_var_or_default("INFLUXDB_BUCKET", "k6")
INFLUXDB_TOKEN     := env_var_or_default("INFLUXDB_TOKEN", "matrix-k6-token")

_auth_env := "--env AUTH_TOKEN=" + AUTH_TOKEN + \
             " --env AUTH_HOST=" + AUTH_HOST + \
             " --env AUTH_REALM=" + AUTH_REALM + \
             " --env AUTH_CLIENT_ID=" + AUTH_CLIENT_ID + \
             " --env AUTH_CLIENT_SECRET=" + AUTH_CLIENT_SECRET

# Show available commands (default)
[private]
default: help

# List all available commands
help:
    @just --list

# ── Setup ─────────────────────────────────────────────────────────────────────

# Install all tools via mise (k6, just, xk6) and sync Python deps
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

# ── InfluxDB ──────────────────────────────────────────────────────────────────

# Start InfluxDB 2.x via Docker Compose (dashboard storage backend); skips if already running
influx-up:
    @if docker ps --format '{{{{.Names}}}}' | grep -q '^influxdb$'; then \
      echo "InfluxDB already running"; \
    else \
      docker compose up -d influxdb && echo "InfluxDB started"; \
    fi
    @echo "InfluxDB UI → http://localhost:8086  (org: matrix · bucket: k6 · token: matrix-k6-token)"

# Stop InfluxDB
influx-down:
    docker compose down

# Open InfluxDB UI in browser
influx-ui:
    open http://localhost:8086

# Run smoke test and write raw k6 metrics directly to InfluxDB (bypasses dashboard)
# Requires: just build  (uses bin/k6 with xk6-output-influxdb extension)
smoke-influx:
    @test -f bin/k6 || (echo "ERROR: bin/k6 not found — run: just build" && exit 1)
    K6_INFLUXDB_ORGANIZATION={{INFLUXDB_ORG}} \
    K6_INFLUXDB_BUCKET={{INFLUXDB_BUCKET}} \
    K6_INFLUXDB_TOKEN={{INFLUXDB_TOKEN}} \
    bin/k6 run \
      --env BASE_URL={{BASE_URL}} \
      {{_auth_env}} \
      --env LOAD_PROFILE=smoke \
      --out xk6-influxdb={{INFLUXDB_URL}} \
      k6/main.js

# Run ramp test and write raw k6 metrics directly to InfluxDB (bypasses dashboard)
# Requires: just build  (uses bin/k6 with xk6-output-influxdb extension)
ramp-influx:
    @test -f bin/k6 || (echo "ERROR: bin/k6 not found — run: just build" && exit 1)
    K6_INFLUXDB_ORGANIZATION={{INFLUXDB_ORG}} \
    K6_INFLUXDB_BUCKET={{INFLUXDB_BUCKET}} \
    K6_INFLUXDB_TOKEN={{INFLUXDB_TOKEN}} \
    bin/k6 run \
      --env BASE_URL={{BASE_URL}} \
      {{_auth_env}} \
      --env LOAD_PROFILE=ramp \
      --env VUS={{VUS}} \
      --env DURATION={{DURATION}} \
      --env RAMP_DURATION={{RAMP_DURATION}} \
      --out xk6-influxdb={{INFLUXDB_URL}} \
      k6/main.js

# Copy .env.example → .env (skips if .env already exists)
init:
    @if [ -f .env ]; then echo ".env already exists, skipping"; else cp .env.example .env && echo "Created .env — fill in your credentials"; fi

# Fetch a token via Keycloak client credentials and print it
get-token:
    @curl -sf \
      --data-urlencode "grant_type=client_credentials" \
      --data-urlencode "client_id={{AUTH_CLIENT_ID}}" \
      --data-urlencode "client_secret={{AUTH_CLIENT_SECRET}}" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      "{{AUTH_HOST}}/realms/{{AUTH_REALM}}/protocol/openid-connect/token" \
      | jq -r .access_token

# ── Running Tests ──────────────────────────────────────────────────────────────

# Run smoke test (2 VUs, 30s) — quick sanity check
smoke:
    k6 run \
      --env BASE_URL={{BASE_URL}} \
      {{_auth_env}} \
      --env LOAD_PROFILE=smoke -v \
      k6/main.js

# Run ramp load test (0 → VUS over RAMP_DURATION, hold DURATION, ramp back)
ramp:
    k6 run \
      --env BASE_URL={{BASE_URL}} \
      {{_auth_env}} -v \
      --env LOAD_PROFILE=ramp \
      --env VUS={{VUS}} \
      --env DURATION={{DURATION}} \
      --env RAMP_DURATION={{RAMP_DURATION}} \
      k6/main.js

# Run soak test (sustained load at VUS for SOAK_DURATION — endurance/memory leak)
SOAK_DURATION := env_var_or_default("SOAK_DURATION", "10m")
soak:
    k6 run \
      --env BASE_URL={{BASE_URL}} \
      {{_auth_env}} -v \
      --env LOAD_PROFILE=soak \
      --env VUS={{VUS}} \
      --env RAMP_DURATION={{RAMP_DURATION}} \
      --env SOAK_DURATION={{SOAK_DURATION}} \
      k6/main.js

# Run stress test (step-up to STRESS_VUS across 4 stages — find breaking point)
STRESS_VUS := env_var_or_default("STRESS_VUS", "50")
stress:
    k6 run \
      --env BASE_URL={{BASE_URL}} \
      {{_auth_env}} -v \
      --env LOAD_PROFILE=stress \
      --env STRESS_VUS={{STRESS_VUS}} \
      --env DURATION={{DURATION}} \
      --env RAMP_DURATION={{RAMP_DURATION}} \
      k6/main.js

# Run spike test (instant burst to SPIKE_VUS for SPIKE_DURATION — resilience)
SPIKE_VUS      := env_var_or_default("SPIKE_VUS", "100")
SPIKE_DURATION := env_var_or_default("SPIKE_DURATION", "30s")
spike:
    k6 run \
      --env BASE_URL={{BASE_URL}} \
      {{_auth_env}} -v \
      --env LOAD_PROFILE=spike \
      --env VUS={{VUS}} \
      --env SPIKE_VUS={{SPIKE_VUS}} \
      --env SPIKE_DURATION={{SPIKE_DURATION}} \
      --env DURATION={{DURATION}} \
      --env RAMP_DURATION={{RAMP_DURATION}} \
      k6/main.js

# Run smoke test and write JSON results to out/results-<timestamp>.json
smoke-json:
    @mkdir -p out
    k6 run \
      --env BASE_URL={{BASE_URL}} \
      {{_auth_env}} \
      --env LOAD_PROFILE=smoke \
      --out json=out/results-$(date +%Y%m%d-%H%M%S).json \
      k6/main.js

# Start dashboard only (no k6) — use the Run tab to launch tests from the browser
dashboard: influx-up
    INFLUXDB_URL={{INFLUXDB_URL}} \
    INFLUXDB_ORG={{INFLUXDB_ORG}} \
    INFLUXDB_BUCKET={{INFLUXDB_BUCKET}} \
    INFLUXDB_TOKEN={{INFLUXDB_TOKEN}} \
    uv run uvicorn dashboard.server:app --host 127.0.0.1 --port 5656 --reload --reload-dir dashboard

# Run smoke test with custom dashboard at http://localhost:5656
smoke-dashboard:
    BASE_URL={{BASE_URL}} \
    AUTH_TOKEN={{AUTH_TOKEN}} \
    AUTH_HOST={{AUTH_HOST}} \
    AUTH_REALM={{AUTH_REALM}} \
    AUTH_CLIENT_ID={{AUTH_CLIENT_ID}} \
    AUTH_CLIENT_SECRET={{AUTH_CLIENT_SECRET}} \
    INFLUXDB_URL={{INFLUXDB_URL}} \
    INFLUXDB_ORG={{INFLUXDB_ORG}} \
    INFLUXDB_BUCKET={{INFLUXDB_BUCKET}} \
    INFLUXDB_TOKEN={{INFLUXDB_TOKEN}} \
    uv run python dashboard/server.py smoke

# Run ramp test with custom dashboard at http://localhost:5656
ramp-dashboard:
    BASE_URL={{BASE_URL}} \
    AUTH_TOKEN={{AUTH_TOKEN}} \
    AUTH_HOST={{AUTH_HOST}} \
    AUTH_REALM={{AUTH_REALM}} \
    AUTH_CLIENT_ID={{AUTH_CLIENT_ID}} \
    AUTH_CLIENT_SECRET={{AUTH_CLIENT_SECRET}} \
    VUS={{VUS}} \
    DURATION={{DURATION}} \
    RAMP_DURATION={{RAMP_DURATION}} \
    INFLUXDB_URL={{INFLUXDB_URL}} \
    INFLUXDB_ORG={{INFLUXDB_ORG}} \
    INFLUXDB_BUCKET={{INFLUXDB_BUCKET}} \
    INFLUXDB_TOKEN={{INFLUXDB_TOKEN}} \
    uv run python dashboard/server.py ramp

# Run ramp test and write JSON results to out/results-<timestamp>.json
ramp-json:
    @mkdir -p out
    k6 run \
      --env BASE_URL={{BASE_URL}} \
      {{_auth_env}} \
      --env LOAD_PROFILE=ramp \
      --env VUS={{VUS}} \
      --env DURATION={{DURATION}} \
      --env RAMP_DURATION={{RAMP_DURATION}} \
      --out json=out/results-$(date +%Y%m%d-%H%M%S).json \
      k6/main.js

# ── Docker ────────────────────────────────────────────────────────────────────

# Build the Docker image
docker-build:
    docker build -t matrix-k6 .

# Run smoke test inside Docker
docker-smoke:
    docker run --rm \
      -e BASE_URL={{BASE_URL}} \
      -e AUTH_TOKEN={{AUTH_TOKEN}} \
      -e AUTH_HOST={{AUTH_HOST}} \
      -e AUTH_REALM={{AUTH_REALM}} \
      -e AUTH_CLIENT_ID={{AUTH_CLIENT_ID}} \
      -e AUTH_CLIENT_SECRET={{AUTH_CLIENT_SECRET}} \
      -e LOAD_PROFILE=smoke \
      matrix-k6

# Run smoke test inside Docker with custom dashboard at http://localhost:5656
docker-smoke-dashboard:
    docker run --rm -p 5656:5656 \
      -e BASE_URL={{BASE_URL}} \
      -e AUTH_TOKEN={{AUTH_TOKEN}} \
      -e AUTH_HOST={{AUTH_HOST}} \
      -e AUTH_REALM={{AUTH_REALM}} \
      -e AUTH_CLIENT_ID={{AUTH_CLIENT_ID}} \
      -e AUTH_CLIENT_SECRET={{AUTH_CLIENT_SECRET}} \
      -e LOAD_PROFILE=smoke \
      matrix-k6 smoke

# Run ramp test inside Docker with custom dashboard at http://localhost:5656
docker-ramp-dashboard:
    docker run --rm -p 5656:5656 \
      -e BASE_URL={{BASE_URL}} \
      -e AUTH_TOKEN={{AUTH_TOKEN}} \
      -e AUTH_HOST={{AUTH_HOST}} \
      -e AUTH_REALM={{AUTH_REALM}} \
      -e AUTH_CLIENT_ID={{AUTH_CLIENT_ID}} \
      -e AUTH_CLIENT_SECRET={{AUTH_CLIENT_SECRET}} \
      -e LOAD_PROFILE=ramp \
      -e VUS={{VUS}} \
      -e DURATION={{DURATION}} \
      -e RAMP_DURATION={{RAMP_DURATION}} \
      matrix-k6 ramp

# Run ramp test inside Docker
docker-ramp:
    docker run --rm \
      -e BASE_URL={{BASE_URL}} \
      -e AUTH_TOKEN={{AUTH_TOKEN}} \
      -e AUTH_HOST={{AUTH_HOST}} \
      -e AUTH_REALM={{AUTH_REALM}} \
      -e AUTH_CLIENT_ID={{AUTH_CLIENT_ID}} \
      -e AUTH_CLIENT_SECRET={{AUTH_CLIENT_SECRET}} \
      -e LOAD_PROFILE=ramp \
      -e VUS={{VUS}} \
      -e DURATION={{DURATION}} \
      -e RAMP_DURATION={{RAMP_DURATION}} \
      matrix-k6

# ── Python / uv ───────────────────────────────────────────────────────────────

# Install / sync all Python dependencies (including dev group)
py-sync:
    uv sync --all-groups

# Add a runtime dependency  e.g. just py-add httpx
py-add dep:
    uv add {{dep}}

# Add a dev-only dependency  e.g. just py-add-dev pytest
py-add-dev dep:
    uv add --group dev {{dep}}

# Lint with ruff
lint:
    uv run ruff check dashboard/ tests/

# Lint + auto-fix
lint-fix:
    uv run ruff check --fix dashboard/ tests/

# Format with ruff
fmt:
    uv run ruff format dashboard/ tests/

# Type-check with ty
typecheck:
    uv run ty check dashboard/

# Run Python tests
test:
    uv run pytest

# Run lint + typecheck + tests
check-all: lint typecheck test

# ── Utilities ─────────────────────────────────────────────────────────────────

# Check that k6 is installed
check:
    @k6 version && echo "k6 is installed" || echo "k6 not found — run: just install"

# Show current env var values (masks secrets)
env:
    @echo "BASE_URL           = {{BASE_URL}}"
    @echo "--- auth (static) ---"
    @echo "AUTH_TOKEN         = $([ -n '{{AUTH_TOKEN}}' ] && echo '****' || echo '(not set)')"
    @echo "--- auth (client credentials) ---"
    @echo "AUTH_HOST          = {{AUTH_HOST}}"
    @echo "AUTH_REALM         = {{AUTH_REALM}}"
    @echo "AUTH_CLIENT_ID     = {{AUTH_CLIENT_ID}}"
    @echo "AUTH_CLIENT_SECRET = $([ -n '{{AUTH_CLIENT_SECRET}}' ] && echo '****' || echo '(not set)')"
    @echo "--- load ---"
    @echo "VUS                = {{VUS}}"
    @echo "DURATION           = {{DURATION}}"
    @echo "RAMP_DURATION      = {{RAMP_DURATION}}"

# Clean output files
clean:
    rm -rf out/
