"""Health check router — /health endpoint for agents and load balancers."""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(tags=["health"])

_REPO_ROOT = Path(__file__).parents[2]


def _influx_health_check() -> bool:
    """Return True if InfluxDB is reachable."""
    try:
        import influx as _influx

        req = urllib.request.Request(
            f"{_influx.INFLUX_URL}/health",
            headers={"Authorization": f"Token {_influx.INFLUX_TOKEN}"},
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


@router.get("/health")
async def health() -> dict:
    """Return Luna service health.

    Always returns 200. Check the 'status' field for 'ok' or 'degraded'.
    Safe for agents to call before any other operation.
    """
    from lifecycle import _k6_lock, _k6_state

    # k6 binary
    k6_bin = _REPO_ROOT / "bin" / "k6"
    k6_ok = k6_bin.exists() or bool(shutil.which("k6"))

    # InfluxDB
    influx_ok = _influx_health_check()

    # k6 run status
    with _k6_lock:
        run_status = _k6_state.get("status", "idle")
        run_id = _k6_state.get("run_id")

    overall = "ok" if (k6_ok and influx_ok) else "degraded"

    return {
        "status": overall,
        "service": "luna",
        "version": "1.0.0",
        "components": {
            "dashboard": "ok",
            "k6": "ok" if k6_ok else "not_found",
            "influxdb": "ok" if influx_ok else "unreachable",
        },
        "run": {
            "status": run_status,
            "run_id": run_id,
        },
        "docs": "/docs",
        "mcp": "/mcp",
    }


@router.get("/ready")
async def ready() -> dict:
    """Kubernetes-style readiness probe. Returns 200 when dashboard is up."""
    return {"ready": True}
