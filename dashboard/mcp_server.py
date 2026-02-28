"""
mcp_server.py — FastMCP server for the k6 performance framework.

Exposes discovery, config management, and run control as MCP tools,
mounted at /mcp on the main FastAPI application.

Tools
-----
  discover_url          OpenAPI → GraphQL → REST probe for any URL
  crawl_url             Crawl pages + JS + GraphQL introspection
  parse_har             Extract endpoints from an HTTP Archive (HAR) dict
  parse_postman         Extract endpoints from a Postman collection dict
  parse_wsdl            Extract SOAP operations from a WSDL string
  parse_api_blueprint   Extract resources from API Blueprint markdown
  parse_raml            Extract resources from RAML YAML

  list_saved_configs    List all saved endpoint config files
  load_saved_config     Return a specific saved endpoint config
  save_endpoint_config  Write a new named endpoint config + activate it

  run_status            Current k6 run status
  start_run             Start a k6 load test
  stop_run              Terminate the running k6 process

Resources
---------
  perf://endpoints            Active endpoint config (endpoints.json)
  perf://configs/saved        Index of all saved configs
  perf://run/status           Live k6 run status
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure dashboard/ is on the path so shared modules resolve
_DASHBOARD = Path(__file__).parent
if str(_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD))

from fastmcp import FastMCP  # noqa: E402

# ── Lazy imports from the existing dashboard modules ───────────────────────────
# We import lazily inside tool functions so that the MCP module can be imported
# in tests or standalone mode without requiring the full FastAPI app.

mcp: FastMCP = FastMCP(
    name="luna",
    instructions="""
Luna — Testing as a Service for engineering teams and autonomous AI agents.

QUICKSTART (one tool call):
  Use test_service(url="https://my-api.com") to discover endpoints, run a smoke
  test, and get structured pass/fail results in a single call.

STEP-BY-STEP WORKFLOW:
  1. discover_url(url)          → find API endpoints (OpenAPI/GraphQL/REST probe)
  2. save_endpoint_config(...)  → activate the discovered endpoints
  3. start_run(base_url, ...)   → launch k6 load test (smoke/ramp/soak/stress/spike)
  4. wait_for_run(run_id)       → block until run completes, returns metrics
  5. get_run_history()          → review past runs and SLO verdicts

DISCOVERY — supported sources:
  discover_url    OpenAPI / Swagger → GraphQL introspection → REST probe
  crawl_url       Follow HTML links + scan JS + GraphQL introspection
  parse_postman   Postman Collection v2.x dict
  parse_har       HTTP Archive (HAR) dict
  parse_wsdl      SOAP/WSDL XML string
  parse_api_blueprint  API Blueprint markdown
  parse_raml      RAML YAML string
  baseline_slo_probe   Measure real p95/error-rate baselines before testing

LOAD PROFILES:
  smoke   2 VUs · 30 s — sanity check (default)
  ramp    0 → N VUs → 0 — standard load test
  soak    sustained load for hours — memory/connection endurance
  stress  step-up to breaking point — capacity planning
  spike   instant burst — auto-scaling / queue resilience

AUTH MODES (pass via auth_token or env):
  Bearer token, API key, Basic auth, OAuth2 client credentials, AWS SigV4

RESOURCES:
  perf://endpoints     active endpoint config
  perf://run/status    live k6 run status
  perf://history       past run history with SLO verdicts
  perf://health        service health
""",
)


# ── Discovery tools ────────────────────────────────────────────────────────────


@mcp.tool
def discover_url(url: str, token: str = "") -> dict:
    """
    Probe *url* for an API spec: tries OpenAPI/Swagger, then GraphQL
    introspection, then common REST paths.

    Returns a dict with keys: source, endpoints, setup, teardown.
    source is one of: openapi | graphql | rest-probe | none.
    """
    from discovery import discover_url as _discover_url

    return _discover_url(url.rstrip("/"), token)


@mcp.tool
def crawl_url(url: str, token: str = "", max_pages: int = 30) -> dict:
    """
    Crawl *url*: follow same-origin HTML links, scan JS files for API paths,
    then attempt GraphQL introspection on any discovered graphql-like paths.

    Returns endpoints, pages_crawled, scripts_scanned, graphql_schemas_scanned.
    """
    from discovery import crawl_url as _crawl_url

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return _crawl_url(url.rstrip("/"), headers, max_pages=max_pages)


@mcp.tool
def parse_har(har: dict) -> dict:
    """
    Parse an HTTP Archive (HAR) object and return unique request patterns
    as endpoint dicts (method, path, body, group).
    """
    from discovery import parse_har as _parse_har

    return _parse_har(har.get("har", har))


@mcp.tool
def parse_postman(collection: dict) -> dict:
    """
    Parse a Postman Collection v2.x dict and return endpoint config dict
    with REST and GraphQL endpoints.
    """
    from discovery import parse_postman as _parse_postman

    return _parse_postman(collection.get("collection", collection))


@mcp.tool
def parse_wsdl(wsdl: str) -> dict:
    """
    Parse a WSDL XML string and return SOAP operation endpoints with
    pre-built envelope body stubs.
    """
    from discovery import parse_wsdl as _parse_wsdl

    return _parse_wsdl(wsdl)


@mcp.tool
def parse_api_blueprint(blueprint: str) -> dict:
    """
    Parse API Blueprint markdown and extract resource + action endpoint dicts.
    """
    from discovery import parse_api_blueprint as _parse_api_blueprint

    return _parse_api_blueprint(blueprint)


@mcp.tool
def parse_raml(raml: str) -> dict:
    """
    Parse a RAML YAML string and return endpoint dicts for all declared
    resources and methods (requires pyyaml).
    """
    from discovery import parse_raml as _parse_raml

    return _parse_raml(raml)


@mcp.tool
def baseline_slo_probe(base_url: str, endpoints: list, token: str = "", sample: int = 5) -> dict:
    """
    Make real HTTP requests to up to *sample* GET endpoints and return
    observed p95 latency, error rate, and Apdex score as SLO baselines.
    """
    from discovery import baseline_slo_probe as _probe

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return _probe(base_url.rstrip("/"), endpoints, headers, sample=sample)


# ── Config management tools ────────────────────────────────────────────────────


@mcp.tool
def list_saved_configs() -> list:
    """
    Return metadata for all saved endpoint configs, newest first.
    Each entry: filename, service, source, endpoint_count, saved_at.
    """
    from storage import list_saved_configs as _list

    return _list()


@mcp.tool
def load_saved_config(filename: str) -> dict:
    """
    Load and return a specific saved endpoint config by filename
    (e.g. "my-api_crawl_20260227_143015.json").
    """
    from storage import load_named_config

    cfg = load_named_config(filename)
    if not cfg:
        return {"error": f"Config not found: {filename}"}
    return cfg


@mcp.tool
def save_endpoint_config(
    endpoints: list,
    service: str = "my-api",
    source: str = "manual",
    base_url: str = "",
    auth_token: str = "",
) -> dict:
    """
    Save *endpoints* as the active endpoint config and write a uniquely-named
    backup to k6/config/saved/.

    Returns {"ok": True, "filename": "<generated-name>.json"}.
    """
    from app_state import state
    from storage import save_named_config

    config = {
        "service": service,
        "endpoints": endpoints,
        "setup": [],
        "teardown": [],
        "_source": source,
        "_base_url": base_url,
        "_auth_token": auth_token,
    }
    state.save_endpoints(config)
    filename = save_named_config(config)
    return {"ok": True, "filename": filename, "endpoint_count": len(endpoints)}


# ── Run control tools ──────────────────────────────────────────────────────────


@mcp.tool
def run_status() -> dict:
    """
    Return the current k6 run status: status, run_id, profile,
    started_at (ISO), elapsed_s.
    """
    from datetime import UTC, datetime

    from lifecycle import _k6_lock, _k6_state

    with _k6_lock:
        sa = _k6_state.get("started_at")
        return {
            "status": _k6_state["status"],
            "run_id": _k6_state.get("run_id"),
            "profile": _k6_state.get("profile"),
            "started_at": sa.isoformat() if sa else None,
            "elapsed_s": int((datetime.now(UTC) - sa).total_seconds()) if sa else None,
        }


@mcp.tool
def start_run(
    base_url: str,
    auth_token: str = "",
    profile: str = "smoke",
    vus: int = 10,
    duration: int = 60,
) -> dict:
    """
    Start a k6 load test against *base_url*.

    profile: smoke | ramp | soak | stress | spike
    vus: number of virtual users
    duration: test duration in seconds

    Returns {"status": "starting", "run_id": "…"}.
    """
    import threading
    import uuid

    from app_state import state
    from lifecycle import _k6_lock, _k6_state, run_k6_supervised

    valid = ("smoke", "ramp", "soak", "stress", "spike")
    if profile not in valid:
        return {"error": f"profile must be one of: {', '.join(valid)}"}

    cfg = {
        "base_url": base_url,
        "auth_token": auth_token,
        "auth_basic_user": "",
        "auth_api_key": "",
        "auth_api_key_header": "X-API-Key",
        "auth_host": "",
        "auth_realm": "master",
        "auth_client_id": "",
        "auth_client_secret": "",
        "vus": str(vus),
        "duration": f"{duration}s",
        "ramp_duration": "30s",
    }
    run_id = str(uuid.uuid4())
    with _k6_lock:
        if _k6_state["status"] != "idle":
            return {"error": f"run already {_k6_state['status']}"}
        _k6_state["status"] = "starting"
        _k6_state["run_id"] = run_id
    threading.Thread(
        target=run_k6_supervised,
        args=(profile, cfg, run_id, state.ep_cfg_ref, state.op_group_ref),
        daemon=True,
    ).start()
    return {"status": "starting", "run_id": run_id, "profile": profile}


@mcp.tool
def stop_run() -> dict:
    """Terminate the currently running k6 process."""
    from lifecycle import _k6_lock, _k6_state

    with _k6_lock:
        proc = _k6_state.get("proc")
        if not proc:
            return {"error": "no run in progress"}
        _k6_state["status"] = "stopping"
    proc.terminate()
    return {"status": "stopping"}


@mcp.tool
def generate_test_plan(url: str = "", token: str = "") -> dict:
    """Generate a test plan from the current endpoint config or by discovering a URL."""
    import sys
    from pathlib import Path

    repo_root = Path(__file__).parent.parent
    sys.path.insert(0, str(repo_root))
    from api_tests.generator import TestGenerator

    try:
        if url:
            gen = TestGenerator.from_discovery(url, token=token)
        else:
            gen = TestGenerator.from_endpoints_json()
        plan = gen.generate_test_plan()
        return {
            "service": plan.service,
            "total": len(plan),
            "entries": [{"name": e.name, "method": e.method, "path": e.path} for e in plan.entries],
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool
def run_api_tests(suite: str = "api", base_url: str = "", auth_token: str = "") -> dict:
    """Trigger a pytest suite and return results."""
    import sys
    from pathlib import Path

    repo_root = Path(__file__).parent.parent
    sys.path.insert(0, str(repo_root))
    from api_tests.runner import TestRunner

    runner = TestRunner()
    result = runner.run(suite=suite, base_url=base_url, auth_token=auth_token)
    return {
        "passed": result.passed,
        "failed": result.failed,
        "errors": result.errors,
        "total": result.total,
        "success": result.success,
        "duration_ms": result.duration_ms,
    }


@mcp.tool
def test_service(
    url: str,
    auth_token: str = "",
    profile: str = "smoke",
    vus: int = 2,
    duration: int = 30,
    save_config: bool = True,
) -> dict:
    """
    ONE-SHOT: Discover endpoints from *url*, optionally save the config, start a k6
    load test, wait for completion, and return structured results.

    This is the primary tool for autonomous agents — a single call does everything.

    Args:
        url:         Target service base URL (e.g. "https://api.example.com")
        auth_token:  Bearer token for authenticated services
        profile:     smoke | ramp | soak | stress | spike  (default: smoke)
        vus:         Virtual users (default: 2 for smoke)
        duration:    Test duration in seconds (default: 30)
        save_config: If True, save discovered endpoints as the active config

    Returns dict with keys:
        success, run_id, profile, elapsed_s, endpoint_count, source,
        endpoints (list), error (if any)
    """
    import threading
    import time
    import uuid

    # Step 1: Discover endpoints
    from discovery import discover_url as _discover_url

    try:
        discovered = _discover_url(url.rstrip("/"), auth_token)
    except Exception as exc:
        return {"success": False, "error": f"Discovery failed: {exc}"}

    endpoints = discovered.get("endpoints", [])
    source = discovered.get("source", "unknown")

    if not endpoints:
        return {
            "success": False,
            "error": "No endpoints discovered. Try crawl_url() or supply a Postman collection.",
            "source": source,
            "url": url,
        }

    # Step 2: Save config
    if save_config:
        from app_state import state
        from storage import save_named_config

        config = {
            "service": url.split("//")[-1].split("/")[0],
            "endpoints": endpoints,
            "setup": [],
            "teardown": [],
            "_source": source,
            "_base_url": url,
            "_auth_token": auth_token,
        }
        state.save_endpoints(config)
        save_named_config(config)

    # Step 3: Start run
    from app_state import state as _state
    from lifecycle import _k6_lock, _k6_state, run_k6_supervised

    valid = ("smoke", "ramp", "soak", "stress", "spike")
    if profile not in valid:
        return {"success": False, "error": f"profile must be one of {valid}"}

    cfg = {
        "base_url": url,
        "auth_token": auth_token,
        "auth_basic_user": "",
        "auth_api_key": "",
        "auth_api_key_header": "X-API-Key",
        "auth_host": "",
        "auth_realm": "master",
        "auth_client_id": "",
        "auth_client_secret": "",
        "vus": str(vus),
        "duration": f"{duration}s",
        "ramp_duration": "30s",
    }
    run_id = str(uuid.uuid4())

    with _k6_lock:
        if _k6_state["status"] not in ("idle", "finished", "error"):
            return {
                "success": False,
                "error": f"A run is already {_k6_state['status']}. Call stop_run() first.",
                "run_id": _k6_state.get("run_id"),
            }
        _k6_state["status"] = "starting"
        _k6_state["run_id"] = run_id

    threading.Thread(
        target=run_k6_supervised,
        args=(profile, cfg, run_id, _state.ep_cfg_ref, _state.op_group_ref),
        daemon=True,
    ).start()

    # Step 4: Wait for completion
    timeout = max(duration + 60, 120)
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        with _k6_lock:
            status = _k6_state.get("status", "idle")
            _ = _k6_state.get("started_at")
        if status in ("finished", "idle", "error"):
            break
        time.sleep(2)

    with _k6_lock:
        final_status = _k6_state.get("status", "unknown")
    elapsed = int(time.monotonic() - start)

    return {
        "success": final_status in ("finished", "idle"),
        "run_id": run_id,
        "profile": profile,
        "elapsed_s": elapsed,
        "endpoint_count": len(endpoints),
        "source": source,
        "endpoints": [
            {"name": e.get("name"), "method": e.get("method"), "path": e.get("path")} for e in endpoints[:20]
        ],
        "status": final_status,
        "url": url,
    }


@mcp.tool
def wait_for_run(run_id: str = "", timeout_s: int = 300) -> dict:
    """
    Block until the current k6 run completes (or timeout_s is reached).

    Useful when you call start_run() and want to poll for results without
    busy-waiting in your own loop.

    Args:
        run_id:    Optional run ID returned by start_run() — used for validation only.
        timeout_s: Maximum seconds to wait (default 300).

    Returns dict with: status, run_id, elapsed_s, timed_out.
    """
    import time

    from lifecycle import _k6_lock, _k6_state

    start = time.monotonic()
    current_run_id = None
    while time.monotonic() - start < timeout_s:
        with _k6_lock:
            status = _k6_state.get("status", "idle")
            current_run_id = _k6_state.get("run_id")
        if status in ("finished", "idle", "error"):
            break
        time.sleep(2)

    elapsed = int(time.monotonic() - start)
    timed_out = elapsed >= timeout_s

    with _k6_lock:
        final = _k6_state.get("status", "unknown")

    return {
        "status": final,
        "run_id": current_run_id,
        "elapsed_s": elapsed,
        "timed_out": timed_out,
        "success": final in ("finished", "idle") and not timed_out,
    }


@mcp.tool
def get_run_history(limit: int = 10) -> list:
    """
    Return the most recent k6 run records, newest first.

    Each record includes: run_id, profile, base_url, started_at, duration_s,
    p95_ms, error_rate, apdex_score, slo_pass (bool), endpoint_count.

    Useful for agents that need to compare runs, check regression, or report
    quality trends over time.
    """
    from queries import get_run_history as _get_runs

    try:
        runs = _get_runs(limit=limit)
        return runs if isinstance(runs, list) else []
    except Exception as exc:
        return [{"error": str(exc)}]


@mcp.tool
def luna_health() -> dict:
    """
    Return health status of the Luna service and its dependencies.

    Checks: dashboard (always up if this returns), k6 binary, InfluxDB connectivity.
    Safe to call before any other tool to verify the service is ready.

    Returns dict with: status ("ok"|"degraded"), dashboard, k6, influxdb, version.
    """
    import shutil
    from pathlib import Path

    import influx as _influx

    # Check k6
    repo_root = Path(__file__).parent.parent
    k6_bin = repo_root / "bin" / "k6"
    k6_ok = k6_bin.exists() or bool(shutil.which("k6"))

    # Check InfluxDB
    influx_ok = False
    try:
        influx_ok = _influx.health_check() if hasattr(_influx, "health_check") else True
    except Exception:
        pass

    overall = "ok" if k6_ok else "degraded"

    return {
        "status": overall,
        "dashboard": "ok",
        "k6": "ok" if k6_ok else "not_found — run: just build",
        "influxdb": "ok" if influx_ok else "unreachable — run: just influx-up",
        "mcp_tools": [
            "test_service",
            "discover_url",
            "crawl_url",
            "parse_postman",
            "parse_har",
            "parse_wsdl",
            "save_endpoint_config",
            "list_saved_configs",
            "load_saved_config",
            "start_run",
            "stop_run",
            "run_status",
            "wait_for_run",
            "get_run_history",
            "generate_test_plan",
            "run_api_tests",
            "baseline_slo_probe",
            "luna_health",
        ],
    }


# ── Resources ──────────────────────────────────────────────────────────────────


@mcp.resource("perf://endpoints")
def resource_endpoints() -> dict:
    """Active endpoint config (the current k6/config/endpoints.json)."""
    from app_state import state

    return state.endpoint_config


@mcp.resource("perf://configs/saved")
def resource_saved_configs() -> list:
    """Index of all saved endpoint configs, newest first."""
    from storage import list_saved_configs as _list

    return _list()


@mcp.resource("perf://run/status")
def resource_run_status() -> dict:
    """Live k6 run status."""
    return run_status()


@mcp.resource("perf://history")
def resource_history() -> list:
    """Past k6 run history with SLO verdicts."""
    return get_run_history(limit=20)


@mcp.resource("perf://health")
def resource_health() -> dict:
    """Luna service health: dashboard, k6, InfluxDB."""
    return luna_health()


# ── Prompts (reusable workflow templates) ──────────────────────────────────────


@mcp.prompt
def quickstart_prompt(url: str, auth_token: str = "") -> str:
    """One-shot prompt: test any service from scratch."""
    token_hint = f', auth_token="{auth_token}"' if auth_token else ""
    return f"""Use the Luna testing framework to validate the service at {url}.

Steps to follow:
1. Call luna_health() to confirm the framework is ready.
2. Call test_service(url="{url}"{token_hint}, profile="smoke") to discover
   endpoints and run a smoke test in one call.
3. Report back: how many endpoints were discovered, did all pass, what was
   the p95 latency, and are there any SLO violations?

If test_service reports failures, call get_run_history(limit=1) for more detail.
"""


@mcp.prompt
def load_test_prompt(url: str, profile: str = "ramp", vus: int = 10, duration: int = 60) -> str:
    """Prompt for a full load test with manual steps."""
    return f"""Run a {profile} load test against {url} using Luna.

Steps:
1. Call luna_health() — confirm k6 and InfluxDB are reachable.
2. Call discover_url(url="{url}") to map all API endpoints.
3. Call save_endpoint_config(endpoints=<result>, base_url="{url}") to activate them.
4. Call start_run(base_url="{url}", profile="{profile}", vus={vus}, duration={duration}).
5. Call wait_for_run(timeout_s={duration + 90}) to block until it finishes.
6. Call get_run_history(limit=1) and summarise: p95 ms, error rate, Apdex, SLO pass/fail.
"""


@mcp.prompt
def slo_baseline_prompt(url: str, auth_token: str = "") -> str:
    """Measure latency/error baselines before writing SLO thresholds."""
    token_hint = f', auth_token="{auth_token}"' if auth_token else ""
    return f"""Establish SLO baselines for the service at {url}.

Steps:
1. Call discover_url(url="{url}"{token_hint}) to enumerate endpoints.
2. Call baseline_slo_probe(base_url="{url}", endpoints=<result>{token_hint}, sample=10)
   to make real HTTP requests and measure p95 latency and error rate.
3. Recommend SLO thresholds based on the observed values:
   - p95_ms: observed_p95 × 1.5 (headroom)
   - error_rate: max(0.01, observed_error_rate × 2)
   - apdex_score: 0.85 if observed_p95 < 500 else 0.75
4. Return a JSON snippet showing the recommended "slos" block for endpoints.json.
"""
