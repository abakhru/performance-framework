"""Lighthouse UI performance audit routes."""

from fastapi import APIRouter, HTTPException
from lighthouse_runner import get_result, get_status, list_history, run_lighthouse

router = APIRouter(prefix="/lighthouse")


@router.post("/run")
async def start_run(body: dict):
    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(400, "url required")
    device = body.get("device", "desktop")
    if device not in ("desktop", "mobile"):
        device = "desktop"
    categories = body.get("categories") or []
    run_id = run_lighthouse(url, device, categories)
    return {"run_id": run_id, "status": "running"}


@router.get("/status/{run_id}")
async def run_status(run_id: str):
    return get_status(run_id)


@router.get("/result/{run_id}")
async def run_result(run_id: str):
    result = get_result(run_id)
    if result is None:
        raise HTTPException(404, "Result not found")
    return result


@router.get("/history")
async def history():
    return list_history()
