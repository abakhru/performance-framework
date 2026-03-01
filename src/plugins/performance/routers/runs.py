"""Run history, snapshots, ops, SLO, reports, CSV, badge, diff, and baseline routes."""

import csv
import io
import re

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse

from core.state import state
from core.storage import load_state, save_state
from plugins.performance.queries import RunQueries
from plugins.performance.report import build_html_report
from plugins.performance.runner import make_badge_svg

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

router = APIRouter(prefix="/runs")

_CSV_EMPTY_HEADERS = ["ts", "elapsed_s", "vus", "rps", "p50_ms", "p75_ms", "p95_ms", "p99_ms", "avg_ms", "total_reqs"]


def _validate_uuid(run_id: str) -> None:
    if not UUID_RE.match(run_id):
        raise HTTPException(400, "invalid run id")


@router.get("")
async def get_runs():
    return RunQueries.build_runs()


@router.get("/diff")
async def get_run_diff(a: str, b: str):
    if not (UUID_RE.match(a) and UUID_RE.match(b)):
        raise HTTPException(400, "invalid run ids")
    return RunQueries.compute_diff(a, b)


@router.get("/baseline")
async def get_baseline():
    return {"baseline_run_id": load_state().get("baseline_run_id")}


@router.post("/{run_id}/baseline")
async def set_baseline(run_id: str):
    _validate_uuid(run_id)
    s = load_state()
    s["baseline_run_id"] = run_id
    save_state(s)
    return {"ok": True}


@router.delete("/baseline")
async def clear_baseline():
    s = load_state()
    s.pop("baseline_run_id", None)
    save_state(s)
    return {"ok": True}


@router.get("/{run_id}/snapshots")
async def get_snapshots(run_id: str):
    _validate_uuid(run_id)
    return RunQueries.fetch_snapshots(run_id)


@router.get("/{run_id}/ops")
async def get_ops(run_id: str):
    _validate_uuid(run_id)
    return RunQueries.fetch_ops(run_id)


@router.get("/{run_id}/slo")
async def get_slo(run_id: str):
    _validate_uuid(run_id)
    return RunQueries.fetch_slo(run_id, state.endpoint_config)


@router.get("/{run_id}/report", response_class=HTMLResponse)
async def get_report(run_id: str):
    _validate_uuid(run_id)
    runs_data = RunQueries.build_runs()
    run_meta = next((r for r in runs_data.get("runs", []) if r.get("run_id") == run_id), {})
    snapshots_data = RunQueries.fetch_snapshots(run_id)
    ops_data = RunQueries.fetch_ops(run_id)
    html = build_html_report(
        run_id,
        run_meta,
        snapshots_data.get("snapshots", []),
        ops_data.get("ops", []),
    )
    return HTMLResponse(html)


@router.get("/{run_id}/csv")
async def get_csv(run_id: str):
    _validate_uuid(run_id)
    snaps = RunQueries.fetch_snapshots(run_id).get("snapshots", [])
    buf = io.StringIO()
    writer = csv.writer(buf)
    if snaps:
        writer.writerow(list(snaps[0].keys()))
        for snap in snaps:
            writer.writerow(list(snap.values()))
    else:
        writer.writerow(_CSV_EMPTY_HEADERS)
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="run_{run_id[:8]}.csv"'},
    )


@router.get("/{run_id}/badge")
async def get_badge(run_id: str):
    _validate_uuid(run_id)
    slo = RunQueries.fetch_slo(run_id, state.endpoint_config)
    svg = make_badge_svg(slo.get("verdict", "unknown"))
    return Response(content=svg.encode("utf-8"), media_type="image/svg+xml")
