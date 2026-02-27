#!/usr/bin/env python3
"""
k6 Dashboard Server  ·  Matrix Perf
-------------------------------------
Modes:
  python3 dashboard/server.py          → standalone (no k6, use Run tab to launch)
  python3 dashboard/server.py smoke    → immediate smoke run (legacy CLI mode)
  python3 dashboard/server.py ramp     → immediate ramp run  (legacy CLI mode)

  uvicorn dashboard.server:app --reload --port 5656  → dev mode with auto-reload

HTTP API:
  GET  /                       → dashboard HTML
  GET  /k6/*                   → proxy to k6 REST API :6565
  GET  /runs                   → run history list
  GET  /runs/<id>/snapshots    → time-series for a run
  GET  /runs/<id>/ops          → per-op summary for a run
  GET  /runs/<id>/slo          → SLO verdict for a run
  GET  /runs/<id>/report       → self-contained HTML report
  GET  /runs/<id>/csv          → snapshot CSV download
  GET  /runs/<id>/badge        → SVG pass/fail badge
  GET  /runs/diff?a=<id>&b=<id> → metric diff between two runs
  GET  /runs/baseline          → current baseline run_id
  POST /runs/<id>/baseline     → set baseline run
  DELETE /runs/baseline        → clear baseline
  GET  /run/status             → current k6 process state
  GET  /run/config             → env-var defaults for the Run tab form
  POST /run/start              → start a k6 run (JSON body: config fields)
  POST /run/stop               → stop the current k6 run
  POST /run/multi              → start k6 against multiple targets
  POST /run/refresh-token      → update AUTH_TOKEN env var
  GET  /slo/config             → SLO thresholds config
  POST /slo/config             → update SLO thresholds
  GET  /ops/<name>/trend       → per-op trend across runs
  GET  /heatmap                → metric heatmap data
  GET  /profiles               → list environment profiles
  POST /profiles               → create profile
  POST /profiles/<name>/activate → activate profile
  PUT  /profiles/<name>        → update profile
  DELETE /profiles/<name>      → delete profile
  GET  /webhooks               → list webhooks
  POST /webhooks               → register webhook
  POST /webhooks/<id>/test     → fire test payload
  DELETE /webhooks/<id>        → remove webhook
  GET  /data                   → list uploaded data files
  POST /data/upload            → upload a CSV data file
  DELETE /data/<name>          → remove a data file
  GET  /livereload             → SSE stream; sends "reload" event when backend files change
"""

import asyncio
import csv
import io
import json
import os
import re
import sys
import threading
import time
import uuid
import webbrowser
from datetime import UTC, datetime
from pathlib import Path

# Ensure the dashboard directory is on sys.path so local modules resolve
# whether uvicorn is invoked from the project root or from within dashboard/.
_DASHBOARD_DIR = Path(__file__).parent.resolve()
if str(_DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_DIR))

import httpx
import influx as _influx_mod
import uvicorn
from discovery import discover_url as _discover_url, load_repo_postman as _load_repo_postman, parse_postman as _parse_postman
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from influx import INFLUX_BUCKET, influx_query, now as _now
from lifecycle import (
    _k6_lock,
    _k6_state,
    _send_webhook,
    cleanup_orphans,
    compute_slo_checks,
    load_plugin_hooks,
    make_badge_svg,
    run_k6_supervised,
)
from storage import (
    DATA_DIR,
    HOOKS_DIR,
    REPO_ROOT,
    SCRIPT_DIR,
    build_op_group,
    coerce_float as _float,
    coerce_int as _int,
    load_endpoint_config,
    load_profiles,
    load_state,
    load_webhooks,
    save_endpoints_json as _save_endpoints_json_storage,
    save_profiles,
    save_state,
    save_webhooks,
)

# ── Constants ──────────────────────────────────────────────────────────────────

DASHBOARD_PORT = 5656
K6_API_PORT = 6565
K6_API_BASE = f"http://127.0.0.1:{K6_API_PORT}"

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_VALID_PROFILES = ("smoke", "ramp", "soak", "stress", "spike")

# ── Mutable global state ───────────────────────────────────────────────────────

_endpoint_config: dict = load_endpoint_config()
OP_GROUP: dict = build_op_group(_endpoint_config)

# Mutable references shared with lifecycle threads
_ep_cfg_ref: list = [_endpoint_config]
_op_group_ref: list = [OP_GROUP]


def _save_endpoints_json(config: dict) -> None:
    global _endpoint_config, OP_GROUP
    _save_endpoints_json_storage(config)
    _endpoint_config = config
    OP_GROUP = build_op_group(config)
    _ep_cfg_ref[0] = config
    _op_group_ref[0] = OP_GROUP


# ── Env defaults ───────────────────────────────────────────────────────────────


def _env_defaults() -> dict:
    e = os.environ
    return {
        "base_url": e.get("BASE_URL", ""),
        "auth_token": e.get("AUTH_TOKEN", ""),
        "auth_basic_user": e.get("AUTH_BASIC_USER", ""),
        "auth_api_key": "",
        "auth_api_key_header": e.get("AUTH_API_KEY_HEADER", "X-API-Key"),
        "auth_host": e.get("AUTH_HOST", ""),
        "auth_realm": e.get("AUTH_REALM", "master"),
        "auth_client_id": e.get("AUTH_CLIENT_ID", ""),
        "auth_client_secret": "",
        "vus": e.get("VUS", "10"),
        "duration": e.get("DURATION", "60s"),
        "ramp_duration": e.get("RAMP_DURATION", "30s"),
    }


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(docs_url="/docs", redoc_url=None)


@app.on_event("startup")
async def _startup():
    _load_env()
    _init_influx()
    DATA_DIR.mkdir(exist_ok=True)
    HOOKS_DIR.mkdir(exist_ok=True)
    load_plugin_hooks()


# ── Live-reload SSE ────────────────────────────────────────────────────────────

_reload_queues: list[asyncio.Queue] = []
_reload_lock = threading.Lock()


def _broadcast_reload() -> None:
    with _reload_lock:
        queues = list(_reload_queues)
    for q in queues:
        try:
            q.put_nowait("reload")
        except Exception:
            pass


def _watch_files() -> None:
    """Poll dashboard .py/.html files and broadcast a reload on any mtime change."""
    watched_exts = (".py", ".html")

    def _scan() -> dict:
        result = {}
        for ext in watched_exts:
            for p in SCRIPT_DIR.glob(f"*{ext}"):
                try:
                    result[str(p)] = p.stat().st_mtime
                except OSError:
                    pass
        return result

    mtimes = _scan()
    while True:
        time.sleep(1)
        current = _scan()
        if current != mtimes:
            mtimes = current
            _broadcast_reload()


@app.get("/livereload")
async def livereload():
    q: asyncio.Queue = asyncio.Queue()
    with _reload_lock:
        _reload_queues.append(q)

    async def event_stream():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"event: {msg}\ndata: {{}}\n\n"
                except TimeoutError:
                    yield ": ping\n\n"
        finally:
            with _reload_lock:
                try:
                    _reload_queues.remove(q)
                except ValueError:
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Static ─────────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
async def index():
    return HTMLResponse((SCRIPT_DIR / "index.html").read_text(encoding="utf-8"))


# ── k6 proxy ───────────────────────────────────────────────────────────────────


@app.api_route("/k6/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_k6(path: str, request: Request):
    url = f"{K6_API_BASE}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.request(
                method=request.method,
                url=url,
                content=await request.body(),
                headers={"Content-Type": request.headers.get("Content-Type", "application/json")},
            )
        return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
    except httpx.RequestError:
        return JSONResponse({"error": "k6 api unavailable"}, status_code=503)


# ── Runs ───────────────────────────────────────────────────────────────────────


@app.get("/runs")
async def get_runs():
    return _build_runs()


@app.get("/runs/diff")
async def get_run_diff(a: str, b: str):
    if not (UUID_RE.match(a) and UUID_RE.match(b)):
        raise HTTPException(400, "invalid run ids")
    return _compute_diff(a, b)


@app.get("/runs/baseline")
async def get_baseline():
    return {"baseline_run_id": load_state().get("baseline_run_id")}


@app.post("/runs/{run_id}/baseline")
async def set_baseline(run_id: str):
    if not UUID_RE.match(run_id):
        raise HTTPException(400, "invalid run id")
    state = load_state()
    state["baseline_run_id"] = run_id
    save_state(state)
    return {"ok": True}


@app.delete("/runs/baseline")
async def clear_baseline():
    state = load_state()
    state.pop("baseline_run_id", None)
    save_state(state)
    return {"ok": True}


@app.get("/runs/{run_id}/snapshots")
async def get_snapshots(run_id: str):
    if not UUID_RE.match(run_id):
        raise HTTPException(400, "invalid run id")
    return _fetch_snapshots(run_id)


@app.get("/runs/{run_id}/ops")
async def get_ops(run_id: str):
    if not UUID_RE.match(run_id):
        raise HTTPException(400, "invalid run id")
    return _fetch_ops(run_id)


@app.get("/runs/{run_id}/slo")
async def get_slo(run_id: str):
    if not UUID_RE.match(run_id):
        raise HTTPException(400, "invalid run id")
    return _fetch_slo(run_id)


@app.get("/runs/{run_id}/report", response_class=HTMLResponse)
async def get_report(run_id: str):
    if not UUID_RE.match(run_id):
        raise HTTPException(400, "invalid run id")
    return HTMLResponse(_build_html_report(run_id))


@app.get("/runs/{run_id}/csv")
async def get_csv(run_id: str):
    if not UUID_RE.match(run_id):
        raise HTTPException(400, "invalid run id")
    data = _fetch_snapshots(run_id)
    snaps = data.get("snapshots", [])
    buf = io.StringIO()
    writer = csv.writer(buf)
    if snaps:
        writer.writerow(list(snaps[0].keys()))
        for snap in snaps:
            writer.writerow(list(snap.values()))
    else:
        writer.writerow(
            [
                "ts",
                "elapsed_s",
                "vus",
                "rps",
                "p50_ms",
                "p75_ms",
                "p95_ms",
                "p99_ms",
                "avg_ms",
                "total_reqs",
            ]
        )
    filename = f"run_{run_id[:8]}.csv"
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/runs/{run_id}/badge")
async def get_badge(run_id: str):
    if not UUID_RE.match(run_id):
        raise HTTPException(400, "invalid run id")
    slo = _fetch_slo(run_id)
    svg = make_badge_svg(slo.get("verdict", "unknown"))
    return Response(content=svg.encode("utf-8"), media_type="image/svg+xml")


# ── Run control ────────────────────────────────────────────────────────────────


@app.get("/run/status")
async def run_status():
    with _k6_lock:
        sa = _k6_state.get("started_at")
        return {
            "status": _k6_state["status"],
            "run_id": _k6_state.get("run_id"),
            "profile": _k6_state.get("profile"),
            "started_at": sa.isoformat() if sa else None,
            "elapsed_s": int((datetime.now(UTC) - sa).total_seconds()) if sa else None,
        }


@app.get("/run/config")
async def run_config():
    return _env_defaults()


@app.post("/run/start")
async def run_start(body: dict):
    profile = body.pop("profile", "smoke")
    if profile not in _VALID_PROFILES:
        raise HTTPException(400, f"profile must be one of: {', '.join(_VALID_PROFILES)}")
    defaults = _env_defaults()
    cfg = {k: body.get(k) or defaults.get(k, "") for k in defaults}
    run_id = str(uuid.uuid4())
    with _k6_lock:
        if _k6_state["status"] != "idle":
            raise HTTPException(409, f"run already {_k6_state['status']}")
        _k6_state["status"] = "starting"
        _k6_state["run_id"] = run_id
    threading.Thread(
        target=run_k6_supervised,
        args=(profile, cfg, run_id, _ep_cfg_ref, _op_group_ref),
        daemon=True,
    ).start()
    return {"status": "starting", "profile": profile, "run_id": run_id}


@app.post("/run/stop")
async def run_stop():
    with _k6_lock:
        proc = _k6_state.get("proc")
        if not proc:
            raise HTTPException(400, "no run in progress")
        _k6_state["status"] = "stopping"
    proc.terminate()
    return {"status": "stopping"}


@app.post("/run/multi")
async def run_multi(body: dict):
    targets = body.get("targets", [])
    if not targets or not isinstance(targets, list):
        raise HTTPException(400, "targets array required")
    profile = body.get("profile", "smoke")
    if profile not in _VALID_PROFILES:
        raise HTTPException(400, "invalid profile")
    run_ids = []
    for target in targets:
        base_url = target.get("base_url", "")
        label = target.get("label", base_url)
        cfg = {**_env_defaults(), **body}
        cfg["base_url"] = base_url
        run_id = str(uuid.uuid4())
        run_ids.append({"run_id": run_id, "label": label, "base_url": base_url})
        threading.Thread(
            target=run_k6_supervised,
            args=(profile, cfg, run_id, _ep_cfg_ref, _op_group_ref),
            daemon=True,
        ).start()
    return {"status": "starting", "runs": run_ids}


@app.post("/run/refresh-token")
async def refresh_token(body: dict):
    token = body.get("token", "")
    if not token:
        raise HTTPException(400, "token required")
    os.environ["AUTH_TOKEN"] = token
    return {"ok": True, "message": "Token updated. Takes effect on next request cycle."}


# ── SLO config ─────────────────────────────────────────────────────────────────


@app.get("/slo/config")
async def get_slo_config():
    return _endpoint_config.get("slos", {})


@app.post("/slo/config")
async def set_slo_config(body: dict):
    _endpoint_config["slos"] = body
    _save_endpoints_json(_endpoint_config)
    return {"ok": True}


# ── Endpoints config ───────────────────────────────────────────────────────────


@app.get("/config/endpoints")
async def get_endpoints_config():
    return _endpoint_config


@app.post("/endpoints/save")
async def save_endpoints(body: dict):
    _save_endpoints_json(body)
    return {"ok": True}


# ── Ops trend ──────────────────────────────────────────────────────────────────


@app.get("/ops/{op_name}/trend")
async def op_trend(op_name: str, runs: int = 10):
    if not re.match(r"^[\w\-]+$", op_name):
        raise HTTPException(400, "invalid op name")
    return _fetch_op_trend(op_name, runs)


# ── Heatmap ────────────────────────────────────────────────────────────────────

_VALID_HEATMAP_METRICS = {"p95_ms", "p99_ms", "avg_ms", "error_rate", "apdex_score"}


@app.get("/heatmap")
async def heatmap(metric: str = "p95_ms", days: int = 90):
    if metric not in _VALID_HEATMAP_METRICS:
        raise HTTPException(400, "invalid metric")
    return _fetch_heatmap(metric, days)


# ── Profiles ───────────────────────────────────────────────────────────────────


@app.get("/profiles")
async def list_profiles():
    return load_profiles()


@app.post("/profiles")
async def create_profile(body: dict):
    name = body.get("name", "")
    if not name:
        raise HTTPException(400, "name required")
    profiles = load_profiles()
    profiles[name] = body
    save_profiles(profiles)
    return body


@app.post("/profiles/{name}/activate")
async def activate_profile(name: str):
    profiles = load_profiles()
    profile = profiles.get(name)
    if profile is None:
        raise HTTPException(404)
    return {"ok": True, "profile": profile}


@app.put("/profiles/{name}")
async def update_profile(name: str, body: dict):
    profiles = load_profiles()
    profiles[name] = {**body, "name": name}
    save_profiles(profiles)
    return profiles[name]


@app.delete("/profiles/{name}")
async def delete_profile(name: str):
    profiles = load_profiles()
    if name not in profiles:
        raise HTTPException(404)
    del profiles[name]
    save_profiles(profiles)
    return {"ok": True}


# ── Webhooks ───────────────────────────────────────────────────────────────────


@app.get("/webhooks")
async def list_webhooks():
    return load_webhooks()


@app.post("/webhooks")
async def create_webhook(body: dict):
    new_hook = {**body, "id": str(uuid.uuid4())}
    hooks = load_webhooks()
    hooks.append(new_hook)
    save_webhooks(hooks)
    return new_hook


@app.post("/webhooks/{hook_id}/test")
async def test_webhook(hook_id: str):
    hooks = load_webhooks()
    hook = next((h for h in hooks if h.get("id") == hook_id), None)
    if hook is None:
        raise HTTPException(404)
    payload = {
        "event": "test",
        "run_id": str(uuid.uuid4()),
        "message": "This is a test webhook payload",
        "timestamp": _now(),
    }
    threading.Thread(target=_send_webhook, args=(hook, payload), daemon=True).start()
    return {"ok": True, "message": "Test webhook fired"}


@app.delete("/webhooks/{hook_id}")
async def delete_webhook(hook_id: str):
    hooks = load_webhooks()
    new_hooks = [h for h in hooks if h.get("id") != hook_id]
    if len(new_hooks) == len(hooks):
        raise HTTPException(404)
    save_webhooks(new_hooks)
    return {"ok": True}


# ── Data files ─────────────────────────────────────────────────────────────────


@app.get("/data")
async def list_data():
    files = []
    if DATA_DIR.is_dir():
        for f in sorted(DATA_DIR.glob("*.csv")):
            try:
                with open(f) as fh:
                    reader = csv.reader(fh)
                    headers = next(reader, [])
                    row_count = sum(1 for _ in reader)
                files.append({"name": f.stem, "filename": f.name, "columns": headers, "row_count": row_count})
            except Exception:
                files.append({"name": f.stem, "filename": f.name})
    return {"files": files}


@app.post("/data/upload")
async def upload_data(body: dict):
    name = re.sub(r"[^a-zA-Z0-9_\-]", "_", body.get("name", "data"))
    content = body.get("content", "")
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / f"{name}.csv").write_text(content, encoding="utf-8")
    return {"ok": True, "name": name}


@app.delete("/data/{name}")
async def delete_data(name: str):
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
    f = DATA_DIR / f"{safe}.csv"
    if not f.exists():
        raise HTTPException(404)
    f.unlink()
    return {"ok": True}


# ── Discovery ──────────────────────────────────────────────────────────────────


@app.get("/discover/postman-collection")
async def discover_postman_collection():
    return _load_repo_postman()


@app.get("/discover/url")
async def discover_url(url: str = "", token: str = ""):
    return _discover_url(url.rstrip("/"), token)


@app.post("/discover/postman")
async def parse_postman(body: dict):
    collection = body.get("collection", body)
    return _parse_postman(collection)


# ── InfluxDB query helpers (pure functions) ────────────────────────────────────


def _build_runs() -> dict:
    start_rows = influx_query(f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "k6_run_start")
  |> pivot(rowKey:["_time","run_id","profile"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time","run_id","profile","base_url"])
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 200)
''')
    starts: dict[str, dict] = {}
    for r in start_rows:
        rid = r.get("run_id", "")
        if rid and rid not in starts:
            starts[rid] = {
                "run_id": rid,
                "profile": r.get("profile", ""),
                "base_url": r.get("base_url", ""),
                "started_at": r.get("_time", ""),
                "status": "running",
            }

    final_rows = influx_query(f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "k6_run_final")
  |> pivot(rowKey:["_time","run_id"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["run_id","status","total_reqs","error_rate",
                    "p50_ms","p75_ms","p90_ms","p95_ms","p99_ms",
                    "avg_ms","min_ms","med_ms","ttfb_avg","checks_rate",
                    "data_sent","data_received","vus_max","duration_s",
                    "apdex_score","s2xx","s3xx","s4xx","s5xx","conn_reuse_rate",
                    "lat_b50","lat_b200","lat_b500","lat_b1000",
                    "lat_b2000","lat_b5000","lat_binf"])
''')
    finals: dict[str, dict] = {}
    for r in final_rows:
        rid = r.get("run_id", "")
        if rid:
            finals[rid] = r

    runs = []
    for rid, start in starts.items():
        row = dict(start)
        if rid in finals:
            f = finals[rid]
            row["status"] = f.get("status", "finished")
            row["total_reqs"] = _int(f.get("total_reqs"))
            row["error_rate"] = _float(f.get("error_rate"))
            row["p50_ms"] = _float(f.get("p50_ms"))
            row["p75_ms"] = _float(f.get("p75_ms"))
            row["p90_ms"] = _float(f.get("p90_ms"))
            row["p95_ms"] = _float(f.get("p95_ms"))
            row["p99_ms"] = _float(f.get("p99_ms"))
            row["avg_ms"] = _float(f.get("avg_ms"))
            row["min_ms"] = _float(f.get("min_ms"))
            row["med_ms"] = _float(f.get("med_ms"))
            row["ttfb_avg"] = _float(f.get("ttfb_avg"))
            row["checks_rate"] = _float(f.get("checks_rate"))
            row["data_sent"] = _float(f.get("data_sent"))
            row["data_received"] = _float(f.get("data_received"))
            row["vus_max"] = _int(f.get("vus_max"))
            row["duration_s"] = _int(f.get("duration_s"))
            row["apdex_score"] = _float(f.get("apdex_score"))
            row["s2xx"] = _int(f.get("s2xx"))
            row["s3xx"] = _int(f.get("s3xx"))
            row["s4xx"] = _int(f.get("s4xx"))
            row["s5xx"] = _int(f.get("s5xx"))
            row["conn_reuse_rate"] = _float(f.get("conn_reuse_rate"))
            row["lat_b50"] = _int(f.get("lat_b50"))
            row["lat_b200"] = _int(f.get("lat_b200"))
            row["lat_b500"] = _int(f.get("lat_b500"))
            row["lat_b1000"] = _int(f.get("lat_b1000"))
            row["lat_b2000"] = _int(f.get("lat_b2000"))
            row["lat_b5000"] = _int(f.get("lat_b5000"))
            row["lat_binf"] = _int(f.get("lat_binf"))
        runs.append(row)

    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return {"runs": runs}


def _fetch_snapshots(run_id: str) -> dict:
    rows = influx_query(f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "k6_snapshot" and r.run_id == "{run_id}")
  |> pivot(rowKey:["_time","run_id"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time","elapsed_s","vus","rps",
                    "p50_ms","p75_ms","p95_ms","p99_ms","avg_ms","total_reqs"])
  |> sort(columns: ["_time"])
''')
    return {
        "run_id": run_id,
        "snapshots": [
            {
                "ts": r.get("_time", ""),
                "elapsed_s": _int(r.get("elapsed_s")) or 0,
                "vus": _int(r.get("vus")) or 0,
                "rps": _float(r.get("rps")) or 0.0,
                "p50_ms": _float(r.get("p50_ms")) or 0.0,
                "p75_ms": _float(r.get("p75_ms")) or 0.0,
                "p95_ms": _float(r.get("p95_ms")) or 0.0,
                "p99_ms": _float(r.get("p99_ms")) or 0.0,
                "avg_ms": _float(r.get("avg_ms")) or 0.0,
                "total_reqs": _int(r.get("total_reqs")) or 0,
            }
            for r in rows
        ],
    }


def _fetch_ops(run_id: str) -> dict:
    rows = influx_query(f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "k6_op" and r.run_id == "{run_id}")
  |> pivot(rowKey:["_time","run_id","op_name","op_group"],
           columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["op_name","op_group","reqs","errors",
                    "avg_ms","min_ms","max_ms","p90_ms","p95_ms","p99_ms"])
  |> sort(columns: ["op_group","op_name"])
''')
    return {
        "run_id": run_id,
        "ops": [
            {
                "op_name": r.get("op_name", ""),
                "op_group": r.get("op_group", ""),
                "reqs": _int(r.get("reqs")) or 0,
                "errors": _int(r.get("errors")) or 0,
                "avg_ms": _float(r.get("avg_ms")),
                "min_ms": _float(r.get("min_ms")),
                "max_ms": _float(r.get("max_ms")),
                "p90_ms": _float(r.get("p90_ms")),
                "p95_ms": _float(r.get("p95_ms")),
                "p99_ms": _float(r.get("p99_ms")),
            }
            for r in rows
        ],
    }


def _fetch_slo(run_id: str) -> dict:
    slo_rows = influx_query(f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -90d)
  |> filter(fn: (r) => r._measurement == "k6_run_slo" and r.run_id == "{run_id}")
  |> pivot(rowKey:["_time","run_id"], columnKey: ["_field"], valueColumn: "_value")
''')
    if slo_rows:
        row = slo_rows[0]
        verdict = row.get("verdict", "unknown")
        checks = {}
        slos = _endpoint_config.get("slos", {})
        for metric in slos:
            pass_key = f"{metric}_pass"
            pass_val = row.get(pass_key)
            if pass_val is not None:
                checks[metric] = {
                    "threshold": float(slos[metric]),
                    "pass": bool(int(float(pass_val))),
                }
        return {"verdict": verdict, "checks": checks}

    final_rows = influx_query(f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -90d)
  |> filter(fn: (r) => r._measurement == "k6_run_final" and r.run_id == "{run_id}")
  |> pivot(rowKey:["_time","run_id"], columnKey: ["_field"], valueColumn: "_value")
''')
    if not final_rows:
        return {"verdict": "unknown", "checks": {}}

    row = final_rows[0]
    fields = {
        "p95_ms": _float(row.get("p95_ms")),
        "p99_ms": _float(row.get("p99_ms")),
        "error_rate": _float(row.get("error_rate")),
        "checks_rate": _float(row.get("checks_rate")),
        "apdex_score": _float(row.get("apdex_score")),
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    slos = _endpoint_config.get("slos", {})
    if not slos:
        return {"verdict": "unknown", "checks": {}}
    slo_checks = compute_slo_checks(slos, fields)
    if not slo_checks:
        return {"verdict": "unknown", "checks": {}}
    verdict = "pass" if all(c["pass"] for c in slo_checks.values()) else "fail"
    return {"verdict": verdict, "checks": slo_checks}


def _compute_diff(id_a: str, id_b: str) -> dict:
    rows = influx_query(f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -90d)
  |> filter(fn: (r) => r._measurement == "k6_run_final" and
            (r.run_id == "{id_a}" or r.run_id == "{id_b}"))
  |> pivot(rowKey:["_time","run_id"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["run_id","total_reqs","error_rate","p50_ms","p75_ms",
                    "p90_ms","p95_ms","p99_ms","avg_ms","checks_rate",
                    "apdex_score","duration_s","vus_max"])
''')
    run_a: dict = {}
    run_b: dict = {}
    for row in rows:
        rid = row.get("run_id", "")
        if rid == id_a:
            run_a = row
        elif rid == id_b:
            run_b = row

    numeric_keys = [
        "total_reqs",
        "error_rate",
        "p50_ms",
        "p75_ms",
        "p90_ms",
        "p95_ms",
        "p99_ms",
        "avg_ms",
        "checks_rate",
        "apdex_score",
        "duration_s",
        "vus_max",
    ]
    metrics_a = {k: _float(run_a.get(k)) for k in numeric_keys}
    metrics_b = {k: _float(run_b.get(k)) for k in numeric_keys}

    diff = {}
    for k in numeric_keys:
        a = metrics_a.get(k)
        b = metrics_b.get(k)
        if a is None or b is None:
            continue
        delta = b - a
        pct = (delta / a * 100) if a != 0 else None
        diff[k] = {
            "a": a,
            "b": b,
            "delta": delta,
            "pct": round(pct, 2) if pct is not None else None,
        }

    return {
        "run_a": {**{"run_id": id_a}, **{k: v for k, v in metrics_a.items() if v is not None}},
        "run_b": {**{"run_id": id_b}, **{k: v for k, v in metrics_b.items() if v is not None}},
        "diff": diff,
    }


def _fetch_op_trend(op_name: str, n: int) -> dict:
    rows = influx_query(f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -90d)
  |> filter(fn: (r) => r._measurement == "k6_op" and r.op_name == "{op_name}")
  |> pivot(rowKey:["_time","run_id","op_name"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time","run_id","p95_ms","avg_ms","errors","reqs"])
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {n})
  |> sort(columns: ["_time"])
''')
    return {
        "op_name": op_name,
        "trend": [
            {
                "run_id": r.get("run_id", ""),
                "ts": r.get("_time", ""),
                "p95_ms": _float(r.get("p95_ms")),
                "avg_ms": _float(r.get("avg_ms")),
                "reqs": _int(r.get("reqs")),
                "errors": _int(r.get("errors")),
            }
            for r in rows
        ],
    }


def _fetch_heatmap(metric: str, days: int) -> dict:
    rows = influx_query(f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{days}d)
  |> filter(fn: (r) => r._measurement == "k6_run_final" and r._field == "{metric}")
  |> keep(columns: ["_time", "_value", "run_id"])
  |> sort(columns: ["_time"])
''')
    by_date: dict = {}
    for r in rows:
        date = (r.get("_time") or "")[:10]
        if not date:
            continue
        v = _float(r.get("_value"))
        if v is None:
            continue
        by_date.setdefault(date, []).append(v)
    result = [
        {
            "date": date,
            "value": sum(vals) / len(vals),
            "min": min(vals),
            "max": max(vals),
            "run_count": len(vals),
        }
        for date, vals in sorted(by_date.items())
    ]
    return {"metric": metric, "days": days, "data": result}


def _build_html_report(run_id: str) -> str:
    runs_data = _build_runs()
    run_meta = next((r for r in runs_data.get("runs", []) if r.get("run_id") == run_id), {})
    snapshots_data = _fetch_snapshots(run_id)
    ops_data = _fetch_ops(run_id)

    run_json = json.dumps(run_meta)
    snaps_json = json.dumps(snapshots_data.get("snapshots", []))
    ops_json = json.dumps(ops_data.get("ops", []))
    generated_at = _now()

    snaps = snapshots_data.get("snapshots", [])
    p95_vals = [s.get("p95_ms", 0) for s in snaps if s.get("p95_ms") is not None]
    if p95_vals and len(p95_vals) > 1:
        p95_max = max(p95_vals) or 1
        p95_min = min(p95_vals)
        width, height = 400, 60
        pts = []
        for i, v in enumerate(p95_vals):
            x = i / (len(p95_vals) - 1) * width
            y = height - ((v - p95_min) / (p95_max - p95_min + 0.001)) * height
            pts.append(f"{x:.1f},{y:.1f}")
        sparkline_path = "M " + " L ".join(pts)
        sparkline_svg = (
            f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'style="display:block;margin:auto">'
            f'<path d="{sparkline_path}" fill="none" stroke="#6c63ff" stroke-width="2"/>'
            f"</svg>"
        )
    else:
        sparkline_svg = "<p style='color:#888'>Not enough snapshot data for sparkline.</p>"

    def card(label, value, fmt=lambda v: str(v)):
        val_str = fmt(value) if value is not None else "N/A"
        return f'<div class="card"><div class="card-label">{label}</div><div class="card-value">{val_str}</div></div>'

    cards_html = (
        card("Total Requests", run_meta.get("total_reqs"), lambda v: f"{v:,}")
        + card("P95 Latency", run_meta.get("p95_ms"), lambda v: f"{v:.1f} ms")
        + card("Error Rate", run_meta.get("error_rate"), lambda v: f"{v * 100:.2f}%")
        + card("Apdex Score", run_meta.get("apdex_score"), lambda v: f"{v:.3f}")
        + card("Duration", run_meta.get("duration_s"), lambda v: f"{v}s")
    )

    ops_rows = ""
    for op in ops_data.get("ops", []):
        p95 = op.get("p95_ms")
        avg = op.get("avg_ms")
        ops_rows += (
            f"<tr>"
            f"<td>{op.get('op_name', '')}</td>"
            f"<td>{op.get('op_group', '')}</td>"
            f"<td>{op.get('reqs', 0)}</td>"
            f"<td>{op.get('errors', 0)}</td>"
            f"<td>{'N/A' if avg is None else f'{avg:.1f}'}</td>"
            f"<td>{'N/A' if p95 is None else f'{p95:.1f}'}</td>"
            f"</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Performance Report — {run_id[:8]}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: #0f1117; color: #e2e8f0; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 4px; }}
  .meta {{ color: #64748b; font-size: 0.875rem; margin-bottom: 24px; }}
  .cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 32px; }}
  .card {{ background: #1a1d27; border: 1px solid #2d3148; border-radius: 8px; padding: 16px 24px; min-width: 140px; }}
  .card-label {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }}
  .card-value {{ font-size: 1.5rem; font-weight: 700; margin-top: 4px; color: #6c63ff; }}
  .section {{ background: #1a1d27; border: 1px solid #2d3148; border-radius: 8px; padding: 24px; margin-bottom: 24px; }}
  h2 {{ font-size: 1rem; margin: 0 0 16px 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  th {{ text-align: left; padding: 8px 12px; background: #242736; border-bottom: 1px solid #2d3148; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #1a1d27; }}
  .footer {{ color: #64748b; font-size: 0.75rem; margin-top: 24px; }}
</style>
</head>
<body>
<h1>Performance Report</h1>
<div class="meta">
  Run ID: <code>{run_id}</code> &nbsp;|&nbsp;
  Profile: {run_meta.get("profile", "N/A")} &nbsp;|&nbsp;
  Status: {run_meta.get("status", "N/A")} &nbsp;|&nbsp;
  Started: {run_meta.get("started_at", "N/A")}
</div>
<div class="cards">{cards_html}</div>
<div class="section">
  <h2>P95 Latency Over Time</h2>
  {sparkline_svg}
</div>
<div class="section">
  <h2>Per-Operation Metrics</h2>
  <table>
    <thead><tr>
      <th>Operation</th><th>Group</th><th>Requests</th>
      <th>Errors</th><th>Avg (ms)</th><th>P95 (ms)</th>
    </tr></thead>
    <tbody>{ops_rows}</tbody>
  </table>
</div>
<div class="footer">Generated at {generated_at} &nbsp;|&nbsp; run_id: {run_id}</div>
<script>
const RUN = {run_json};
const SNAPSHOTS = {snaps_json};
const OPS = {ops_json};
</script>
</body>
</html>"""


# ── Startup helpers ────────────────────────────────────────────────────────────


def _load_env() -> None:
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    _influx_mod.INFLUX_URL = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
    _influx_mod.INFLUX_ORG = os.environ.get("INFLUXDB_ORG", "matrix")
    _influx_mod.INFLUX_BUCKET = os.environ.get("INFLUXDB_BUCKET", "k6")
    _influx_mod.INFLUX_TOKEN = os.environ.get("INFLUXDB_TOKEN", "matrix-k6-token")
    os.environ["K6_INFLUXDB_ORGANIZATION"] = _influx_mod.INFLUX_ORG
    os.environ["K6_INFLUXDB_BUCKET"] = _influx_mod.INFLUX_BUCKET
    os.environ["K6_INFLUXDB_TOKEN"] = _influx_mod.INFLUX_TOKEN


def _init_influx() -> None:
    print(f"[dashboard] Connecting to InfluxDB at {_influx_mod.INFLUX_URL}…", flush=True)
    if _influx_mod.init_influx():
        cleanup_orphans()


# ── Entry point ────────────────────────────────────────────────────────────────


def main():
    cli_profile = sys.argv[1] if len(sys.argv) > 1 else None
    standalone = cli_profile is None

    _load_env()
    _init_influx()
    DATA_DIR.mkdir(exist_ok=True)
    HOOKS_DIR.mkdir(exist_ok=True)
    load_plugin_hooks()

    threading.Thread(target=_watch_files, daemon=True, name="file-watcher").start()

    url = f"http://localhost:{DASHBOARD_PORT}"
    print(f"[dashboard] Dashboard → {url}", flush=True)

    if standalone:
        print("[dashboard] Standalone mode — use the Run tab to start a test", flush=True)
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        uvicorn.run(app, host="127.0.0.1", port=DASHBOARD_PORT, log_level="warning")
    else:
        _valid = ("smoke", "ramp", "soak", "stress", "spike")
        if cli_profile not in _valid:
            print(
                f"[dashboard] Unknown profile '{cli_profile}'. Use one of: {', '.join(_valid)}.",
                flush=True,
            )
            sys.exit(1)

        cfg = _env_defaults()
        supervisor = threading.Thread(
            target=run_k6_supervised,
            args=(cli_profile, cfg, None, _ep_cfg_ref, _op_group_ref),
            daemon=False,
        )
        supervisor.start()
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

        try:
            # Run uvicorn in a background thread so supervisor.join() controls exit
            srv = threading.Thread(
                target=uvicorn.run,
                kwargs={
                    "app": app,
                    "host": "127.0.0.1",
                    "port": DASHBOARD_PORT,
                    "log_level": "warning",
                },
                daemon=True,
            )
            srv.start()
            supervisor.join()
        except KeyboardInterrupt:
            with _k6_lock:
                proc = _k6_state.get("proc")
            if proc:
                proc.terminate()
            supervisor.join(timeout=10)


if __name__ == "__main__":
    main()
