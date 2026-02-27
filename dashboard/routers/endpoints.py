"""Endpoint configuration routes."""

from app_state import state
from fastapi import APIRouter

router = APIRouter()


@router.get("/config/endpoints")
async def get_endpoints_config():
    return state.endpoint_config


@router.post("/endpoints/save")
async def save_endpoints(body: dict):
    state.save_endpoints(body)
    return {"ok": True}
