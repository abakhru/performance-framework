"""Visual QA agent routes."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from visual_qa import get_run, list_runs, load_profiles, start_run

router = APIRouter(prefix="/visual-qa")


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

    for k, v in (body.get("extra_headers") or {}).items():
        headers[str(k)] = str(v)

    return headers


@router.post("/run")
async def start_vqa_run(body: dict):
    """Start a Visual QA run. Returns run_id immediately; run executes in background."""
    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "url required")

    agent_ids: list[str] = body.get("agents") or []
    if isinstance(agent_ids, str):
        agent_ids = [a.strip() for a in agent_ids.split(",") if a.strip()]

    extra_headers = _build_headers(body)
    run_id = start_run(url, agent_ids, extra_headers=extra_headers or None)
    return {"run_id": run_id, "status": "running"}


@router.get("/status/{run_id}")
async def run_status(run_id: str):
    """Poll a Visual QA run for current status."""
    run = get_run(run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id!r} not found")
    done = sum(1 for r in run.results if r.bugs is not None or r.error is not None)
    return {
        "run_id": run_id,
        "status": run.status,
        "progress": {"done": done, "total": len(run.agents)},
    }


@router.get("/result/{run_id}")
async def run_result(run_id: str):
    """Return full VQARun results once complete."""
    run = get_run(run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id!r} not found")
    return asdict(run)


@router.get("/agents")
async def list_agents():
    """List all 31 available agent profiles."""
    profiles = load_profiles()
    agents = []
    for p in profiles.values():
        agents.append(
            {
                "id": p["id"],
                "name": p["name"],
                "specialty": p["specialty"],
                "check_types": p["check_types"],
                "group": p.get("group", "other"),
            }
        )
    # Return grouped
    groups: dict[str, list] = {}
    for a in agents:
        groups.setdefault(a["group"], []).append(a)
    return {"agents": agents, "groups": groups, "total": len(agents)}


@router.get("/history")
async def history(limit: int = 20):
    """Return summary of recent Visual QA runs."""
    runs = list_runs(limit=limit)
    summaries = []
    for run in runs:
        total_bugs = sum(len(r.bugs) for r in run.results)
        critical = sum(1 for r in run.results for b in r.bugs if b.bug_priority >= 8)
        summaries.append(
            {
                "run_id": run.run_id,
                "url": run.url,
                "status": run.status,
                "agents": len(run.agents),
                "total_bugs": total_bugs,
                "critical_bugs": critical,
                "created_at": run.created_at,
                "completed_at": run.completed_at,
            }
        )
    return summaries
