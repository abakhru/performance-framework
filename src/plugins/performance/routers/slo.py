"""SLO configuration routes."""

from fastapi import APIRouter

from core.state import state

router = APIRouter(prefix="/slo")


@router.get("/config")
async def get_slo_config():
    return state.endpoint_config.get("slos", {})


@router.post("/config")
async def set_slo_config(body: dict):
    state.endpoint_config["slos"] = body
    state.save_endpoints(state.endpoint_config)
    return {"ok": True}
