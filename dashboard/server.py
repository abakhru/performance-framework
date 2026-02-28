#!/usr/bin/env python3
"""
k6 Dashboard Server  ·  Matrix Perf
-------------------------------------
Modes:
  python3 dashboard/server.py          → standalone (no k6, use Run tab to launch)
  python3 dashboard/server.py smoke    → immediate smoke run (legacy CLI mode)
  python3 dashboard/server.py ramp     → immediate ramp run  (legacy CLI mode)

  uvicorn dashboard.server:app --reload --port 5656  → dev mode with auto-reload
"""

import os
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure the dashboard directory is on sys.path so local modules resolve
# whether uvicorn is invoked from the project root or from within dashboard/.
_DASHBOARD_DIR = Path(__file__).parent.resolve()
if str(_DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_DIR))

import influx as _influx_mod  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from lifecycle import _k6_lock, _k6_state, cleanup_orphans, load_plugin_hooks, run_k6_supervised  # noqa: E402
from livereload import router as livereload_router  # noqa: E402
from livereload import start_file_watcher  # noqa: E402
from routers import analytics, data_files, endpoints, profiles, proxy, run_control, runs, slo, webhooks  # noqa: E402
from routers import discovery as discovery_router  # noqa: E402
from storage import DATA_DIR, HOOKS_DIR, REPO_ROOT, SCRIPT_DIR  # noqa: E402

DASHBOARD_PORT = 5656


@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    _load_env()
    _init_influx()
    DATA_DIR.mkdir(exist_ok=True)
    HOOKS_DIR.mkdir(exist_ok=True)
    load_plugin_hooks()
    yield


app = FastAPI(docs_url="/docs", redoc_url=None, lifespan=_lifespan)

# ── Register routers ───────────────────────────────────────────────────────────

app.include_router(livereload_router)
app.include_router(proxy.router)
app.include_router(runs.router)
app.include_router(run_control.router)
app.include_router(slo.router)
app.include_router(endpoints.router)
app.include_router(analytics.router)
app.include_router(profiles.router)
app.include_router(webhooks.router)
app.include_router(data_files.router)
app.include_router(discovery_router.router)


# ── Static ─────────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
async def index():
    return HTMLResponse((SCRIPT_DIR / "index.html").read_text(encoding="utf-8"))


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

    start_file_watcher()

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

        from app_state import state
        from routers.run_control import get_env_defaults

        cfg = get_env_defaults()
        supervisor = threading.Thread(
            target=run_k6_supervised,
            args=(cli_profile, cfg, None, state.ep_cfg_ref, state.op_group_ref),
            daemon=False,
        )
        supervisor.start()
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

        try:
            srv = threading.Thread(
                target=uvicorn.run,
                kwargs={"app": app, "host": "127.0.0.1", "port": DASHBOARD_PORT, "log_level": "warning"},
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
