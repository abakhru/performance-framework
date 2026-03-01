"""Run lifecycle control: status, config, start, stop, multi-target, token refresh."""

import os
import threading
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from core.state import state
from plugins.performance.runner import _k6_lock, _k6_state, run_k6_supervised

_VALID_PROFILES = ("smoke", "ramp", "soak", "stress", "spike")

router = APIRouter(prefix="/run")


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


def get_env_defaults() -> dict:
    """Public accessor used by main server at startup."""
    return _env_defaults()


@router.get("/status")
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


@router.get("/config")
async def run_config():
    return _env_defaults()


@router.post("/start")
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
        args=(profile, cfg, run_id, state.ep_cfg_ref, state.op_group_ref),
        daemon=True,
    ).start()
    return {"status": "starting", "profile": profile, "run_id": run_id}


@router.post("/stop")
async def run_stop():
    with _k6_lock:
        proc = _k6_state.get("proc")
        if not proc:
            raise HTTPException(400, "no run in progress")
        _k6_state["status"] = "stopping"
    proc.terminate()
    return {"status": "stopping"}


@router.post("/multi")
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
        cfg = {**_env_defaults(), **body, "base_url": base_url}
        run_id = str(uuid.uuid4())
        run_ids.append({"run_id": run_id, "label": label, "base_url": base_url})
        threading.Thread(
            target=run_k6_supervised,
            args=(profile, cfg, run_id, state.ep_cfg_ref, state.op_group_ref),
            daemon=True,
        ).start()
    return {"status": "starting", "runs": run_ids}


@router.post("/refresh-token")
async def refresh_token(body: dict):
    token = body.get("token", "")
    if not token:
        raise HTTPException(400, "token required")
    os.environ["AUTH_TOKEN"] = token
    return {"ok": True, "message": "Token updated. Takes effect on next request cycle."}
