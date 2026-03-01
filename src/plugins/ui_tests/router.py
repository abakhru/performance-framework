"""UI Tests router — trigger Playwright UI test suites from the dashboard.

Endpoints:
    POST /ui-tests/run     — start a UI test suite run (async, non-blocking)
    GET  /ui-tests/results — last completed UI test run result
    GET  /ui-tests/status  — whether a UI run is currently in progress
    GET  /ui-tests/list    — enumerate available UI test files and markers

Run modes:
    suite = "all"        → tests/ui/        (all UI tests)
    suite = "smoke"      → tests/ui/smoke/  (smoke marker)
    suite = "regression" → tests/ui/regression/

Options:
    headed   = false  → headless Chromium (CI-safe default)
    headed   = true   → visible browser window (local debugging)
    markers          → arbitrary pytest -m expression, e.g. "smoke and not slow"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["ui-tests"])

_REPO_ROOT = Path(__file__).parents[2]

# Module-level state so GET /ui-tests/status and /results can inspect it
_ui_running: bool = False
_ui_last_result: dict | None = None

_UI_SUITE_MAP: dict[str, str] = {
    "all": "ui",
    "smoke": "ui-smoke",
    "regression": "ui-regression",
}


class UIRunRequest(BaseModel):
    suite: str = "all"
    headed: bool = False
    markers: str = ""
    base_url: str = ""


class UIRunResponse(BaseModel):
    passed: int
    failed: int
    errors: int
    skipped: int
    total: int
    duration_ms: float
    suite: str
    success: bool
    headed: bool


@router.post("/ui-tests/run", response_model=UIRunResponse)
async def run_ui_tests(req: UIRunRequest) -> UIRunResponse:
    """Trigger a Playwright UI test suite run and return results.

    The server runs pytest in an executor so the dashboard stays responsive.
    Playwright must be installed (`just ui-install`) for tests to execute.

    Pass `headed=true` to open a visible browser window (requires a display).
    """
    global _ui_running, _ui_last_result

    sys.path.insert(0, str(_REPO_ROOT))
    from api_tests.runner import TestRunner

    suite_key = _UI_SUITE_MAP.get(req.suite, "ui")

    extra: list[str] = []
    if not req.headed:
        extra += ["--headed=false"] if _playwright_supports_headed_flag() else []

    env_overrides: dict[str, str] = {}
    if not req.headed:
        env_overrides["HEADLESS"] = "1"
    else:
        env_overrides["HEADLESS"] = "0"
    if req.base_url:
        env_overrides["BASE_URL"] = req.base_url

    _ui_running = True
    try:
        loop = asyncio.get_running_loop()
        runner = TestRunner()
        result = await loop.run_in_executor(
            None,
            lambda: runner.run(
                suite=suite_key,
                markers=req.markers,
                extra_args=extra,
            ),
        )
    finally:
        _ui_running = False

    _ui_last_result = {
        "passed": result.passed,
        "failed": result.failed,
        "errors": result.errors,
        "skipped": result.skipped,
        "total": result.total,
        "duration_ms": result.duration_ms,
        "suite": result.suite,
        "success": result.success,
        "headed": req.headed,
    }
    return UIRunResponse(**_ui_last_result)


@router.get("/ui-tests/results")
async def get_ui_results() -> dict:
    """Return the last UI test run result, or a message if none has run yet."""
    if _ui_last_result is None:
        return {"message": "No UI test run yet"}
    return _ui_last_result


@router.get("/ui-tests/status")
async def get_ui_status() -> dict:
    """Return whether a UI test run is currently in progress."""
    return {"running": _ui_running}


@router.get("/ui-tests/list")
async def list_ui_tests() -> dict:
    """List available UI test files and the markers they use."""
    ui_root = _REPO_ROOT / "tests" / "ui"
    if not ui_root.exists():
        return {"error": "tests/ui/ directory not found", "suites": []}

    suites = []
    for test_file in sorted(ui_root.rglob("test_*.py")):
        relative = test_file.relative_to(_REPO_ROOT)
        # Determine suite category from parent directory name
        parts = relative.parts
        category = parts[2] if len(parts) > 2 else "other"
        suites.append(
            {
                "file": str(relative),
                "category": category,
                "run_with": f"pytest {relative} -v",
            }
        )

    return {
        "total_files": len(suites),
        "available_markers": ["smoke", "regression", "sanity"],
        "available_suites": list(_UI_SUITE_MAP.keys()),
        "files": suites,
    }


def _playwright_supports_headed_flag() -> bool:
    """Check if the installed pytest-playwright version supports --headed flag."""
    try:
        import importlib.util

        return importlib.util.find_spec("playwright") is not None
    except Exception:
        return False
