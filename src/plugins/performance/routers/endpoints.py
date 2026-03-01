"""Endpoint configuration routes."""

from fastapi import APIRouter, HTTPException

from core.state import state
from core.storage import list_saved_configs, load_named_config, save_named_config

router = APIRouter()


@router.get("/config/endpoints")
async def get_endpoints_config():
    return state.endpoint_config


@router.post("/endpoints/save")
async def save_endpoints(body: dict):
    state.save_endpoints(body)
    filename = save_named_config(body)
    return {"ok": True, "filename": filename}


@router.get("/configs/saved")
async def get_saved_configs():
    return list_saved_configs()


@router.get("/configs/saved/{name}")
async def get_saved_config(name: str):
    cfg = load_named_config(name)
    if not cfg:
        raise HTTPException(404, "Config not found")
    return cfg
