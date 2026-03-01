"""
plugins/performance — k6 performance testing plugin.

Provides run lifecycle management, InfluxDB metrics queries, HTML reports,
and all FastAPI routes for executing and observing k6 runs.
"""

from fastapi import APIRouter

from plugins.base import PluginMeta
from plugins.performance.routers import (
    analytics,
    data_files,
    endpoints,
    profiles,
    proxy,
    run_control,
    runs,
    slo,
    webhooks,
)

# Aggregate router — all performance sub-routers are included here
router = APIRouter(tags=["Performance"])
router.include_router(runs.router)
router.include_router(run_control.router)
router.include_router(slo.router)
router.include_router(analytics.router)
router.include_router(endpoints.router)
router.include_router(profiles.router)
router.include_router(data_files.router)
router.include_router(webhooks.router)
router.include_router(proxy.router)

plugin = PluginMeta(
    name="performance",
    description="k6 load test execution, InfluxDB metrics, SLO checks and run reports.",
    router=router,
    tags=["Performance"],
    version="1.0.0",
)
