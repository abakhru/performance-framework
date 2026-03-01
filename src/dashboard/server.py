"""
dashboard/server.py — FastAPI application factory.

Startup modes:
  python -m dashboard.server              → standalone (use Run tab to start k6)
  python -m dashboard.server smoke        → legacy CLI mode — immediate smoke run
  uvicorn dashboard.server:app --reload   → dev mode with auto-reload

The server delegates all feature logic to plugins loaded by the registry in
``plugins/__init__.py``.  To add a new feature:

  1. Create ``src/plugins/<name>/``
  2. Add ``__init__.py`` that exports ``plugin = PluginMeta(...)``
  3. The plugin's router is mounted automatically — no changes here needed.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

import core.influx as _influx_mod
from core.config import DASHBOARD_PORT, DASHBOARD_STATIC_DIR, DATA_DIR, HOOKS_DIR, REPO_ROOT
from core.state import state as _app_state
from dashboard.health_router import router as health_router
from dashboard.livereload import router as livereload_router
from dashboard.livereload import start_file_watcher
from dashboard.mcp_server import mcp
from plugins import register_all
from plugins.performance.runner import (
    _k6_lock,
    _k6_state,
    cleanup_orphans,
    load_plugin_hooks,
    run_k6_supervised,
)

# ── Logging ────────────────────────────────────────────────────────────────────

_NOISY_PATHS = ("/k6/v1/status", "/k6/v1/metrics")


class _QuietAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if any(p in msg for p in _NOISY_PATHS):
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"
        return True


logging.getLogger("uvicorn.access").addFilter(_QuietAccessFilter())

# ── Auth middleware ────────────────────────────────────────────────────────────

_AUTH_EXEMPT = {"/", "/health", "/ready", "/index.html", "/favicon.ico"}


class _APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Bearer-token gate activated only when LUNA_API_KEY env var is set.
    In dev mode (no env var) the middleware is a no-op.

    Set:   LUNA_API_KEY=<secret>
    Send:  Authorization: Bearer <secret>   OR   X-Luna-Key: <secret>
    """

    async def dispatch(self, request: Request, call_next):
        api_key = os.environ.get("LUNA_API_KEY", "")
        if not api_key:
            return await call_next(request)

        if request.url.path in _AUTH_EXEMPT or request.url.path.startswith("/static"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        luna_key_header = request.headers.get("X-Luna-Key", "")
        if auth_header == f"Bearer {api_key}" or luna_key_header == api_key:
            return await call_next(request)

        return JSONResponse(
            {"error": "Unauthorized", "detail": "Provide Authorization: Bearer <LUNA_API_KEY>"},
            status_code=401,
        )


# ── Application factory ────────────────────────────────────────────────────────


@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    _load_env()
    _init_influx()
    DATA_DIR.mkdir(exist_ok=True)
    HOOKS_DIR.mkdir(exist_ok=True)
    load_plugin_hooks()
    yield


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    application = FastAPI(docs_url="/docs", redoc_url=None, lifespan=_lifespan)
    application.add_middleware(_APIKeyMiddleware)

    # ── Infrastructure routers ─────────────────────────────────────────────────
    application.include_router(livereload_router)
    application.include_router(health_router)

    # ── Plugin routers (auto-discovered) ──────────────────────────────────────
    for plugin in register_all():
        if plugin.router is not None:
            application.include_router(plugin.router)

    # ── MCP server ─────────────────────────────────────────────────────────────
    application.mount("/mcp", mcp.http_app(path="/"))

    # ── Dashboard UI ───────────────────────────────────────────────────────────
    @application.get("/", response_class=HTMLResponse)
    @application.get("/index.html", response_class=HTMLResponse)
    async def index():
        return HTMLResponse((DASHBOARD_STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    return application


app = create_app()


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

        from plugins.performance.routers.run_control import get_env_defaults

        cfg = get_env_defaults()
        supervisor = threading.Thread(
            target=run_k6_supervised,
            args=(cli_profile, cfg, None, _app_state.ep_cfg_ref, _app_state.op_group_ref),
            daemon=False,
        )
        supervisor.start()
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

        try:
            srv = threading.Thread(
                target=uvicorn.run,
                kwargs={"app": app, "host": "127.0.0.1", "port": DASHBOARD_PORT, "log_level": "info"},
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
