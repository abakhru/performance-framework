"""Lighthouse UI performance audit routes."""

from fastapi import APIRouter, HTTPException
from lighthouse_runner import get_result, get_status, list_history, run_lighthouse

router = APIRouter(prefix="/lighthouse")


def _build_headers(body: dict) -> dict:
    """Construct extra_headers dict from auth fields in the request body."""
    auth_mode = (body.get("auth_mode") or "none").strip().lower()
    headers: dict = {}

    if auth_mode == "bearer":
        token = (body.get("auth_token") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

    elif auth_mode == "cookie":
        cookie = (body.get("auth_cookie") or "").strip()
        if cookie:
            headers["Cookie"] = cookie

    elif auth_mode == "basic":
        import base64

        user = (body.get("auth_user") or "").strip()
        pwd = (body.get("auth_password") or "").strip()
        if user or pwd:
            encoded = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

    elif auth_mode == "custom":
        name = (body.get("auth_header_name") or "").strip()
        value = (body.get("auth_header_value") or "").strip()
        if name and value:
            headers[name] = value

    # Merge any explicit extra_headers passed directly
    for k, v in (body.get("extra_headers") or {}).items():
        headers[str(k)] = str(v)

    return headers


@router.post("/run")
async def start_run(body: dict):
    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(400, "url required")
    device = body.get("device", "desktop")
    if device not in ("desktop", "mobile"):
        device = "desktop"
    categories = body.get("categories") or []
    extra_headers = _build_headers(body)
    run_id = run_lighthouse(url, device, categories, extra_headers)
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
