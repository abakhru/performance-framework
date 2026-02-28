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
    name="perf-framework",
    instructions=(
        "Performance testing assistant for the k6 dashboard. "
        "Use discover_url or crawl_url to find API endpoints, "
        "then save_endpoint_config to activate them, "
        "then start_run to kick off a load test."
    ),
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
