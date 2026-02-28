"""API Tests router — trigger and report test runs from the dashboard."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["api-tests"])


class RunRequest(BaseModel):
    suite: str = "api"
    base_url: str = ""
    auth_token: str = ""


class RunResponse(BaseModel):
    passed: int
    failed: int
    errors: int
    skipped: int
    total: int
    duration_ms: float
    suite: str
    success: bool


@router.post("/api-tests/run", response_model=RunResponse)
async def run_tests(req: RunRequest) -> RunResponse:
    """Trigger a pytest suite run and return results."""
    import asyncio
    import sys
    from pathlib import Path

    repo_root = Path(__file__).parents[2]
    sys.path.insert(0, str(repo_root))

    from api_tests.runner import TestRunner

    loop = asyncio.get_running_loop()
    runner = TestRunner()
    result = await loop.run_in_executor(
        None,
        lambda: runner.run(suite=req.suite, base_url=req.base_url, auth_token=req.auth_token),
    )

    return RunResponse(
        passed=result.passed,
        failed=result.failed,
        errors=result.errors,
        skipped=result.skipped,
        total=result.total,
        duration_ms=result.duration_ms,
        suite=result.suite,
        success=result.success,
    )


@router.get("/api-tests/results")
async def get_results() -> dict:
    """Return the last test run result."""
    import sys
    from pathlib import Path

    repo_root = Path(__file__).parents[2]
    sys.path.insert(0, str(repo_root))

    from api_tests.runner import get_last_result

    result = get_last_result()
    if result is None:
        return {"message": "No test run yet"}
    return {
        "passed": result.passed,
        "failed": result.failed,
        "errors": result.errors,
        "skipped": result.skipped,
        "total": result.total,
        "duration_ms": result.duration_ms,
        "suite": result.suite,
        "success": result.success,
    }


@router.get("/api-tests/plan")
async def get_plan(base_url: str = "", token: str = "") -> dict:
    """Return the generated test plan without executing tests."""
    import sys
    from pathlib import Path

    repo_root = Path(__file__).parents[2]
    sys.path.insert(0, str(repo_root))

    from api_tests.generator import TestGenerator

    try:
        gen = TestGenerator.from_endpoints_json()
        plan = gen.generate_test_plan()
        return {
            "service": plan.service,
            "base_url": plan.base_url,
            "total": len(plan),
            "entries": [
                {
                    "name": e.name,
                    "method": e.method,
                    "path": e.path,
                    "group": e.group,
                    "type": e.endpoint_type,
                    "expected_status": e.expected_status,
                }
                for e in plan.entries
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}
