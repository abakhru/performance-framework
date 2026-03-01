"""Analytics routes: per-op trend and metric heatmap."""

import re

from fastapi import APIRouter, HTTPException

from plugins.performance.queries import RunQueries

_VALID_HEATMAP_METRICS = {"p95_ms", "p99_ms", "avg_ms", "error_rate", "apdex_score"}

router = APIRouter()


@router.get("/ops/{op_name}/trend")
async def op_trend(op_name: str, runs: int = 10):
    if not re.match(r"^[\w\-]+$", op_name):
        raise HTTPException(400, "invalid op name")
    return RunQueries.fetch_op_trend(op_name, runs)


@router.get("/heatmap")
async def heatmap(metric: str = "p95_ms", days: int = 90):
    if metric not in _VALID_HEATMAP_METRICS:
        raise HTTPException(400, "invalid metric")
    return RunQueries.fetch_heatmap(metric, days)
