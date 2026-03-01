"""Fixtures for dashboard component tests.

Runs the FastAPI dashboard as a real subprocess with coverage instrumentation.
Run standalone: pytest tests/components/dashboard/ -v
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


@pytest.fixture(scope="module")
def dashboard_harness(tmp_path_factory):
    """FastAPIHarness — dashboard running as real subprocess with coverage."""
    from api_tests.harness.fastapi import FastAPIHarness

    tmp = tmp_path_factory.mktemp("dashboard")
    h = FastAPIHarness(
        test_case=None,
        port=15656,  # offset port to avoid collisions
        coverage=True,
        own_dir=str(tmp),
        stdout_path=str(tmp / "stdout.log"),
        stderr_path=str(tmp / "stderr.log"),
    )
    h.Launch()
    try:
        h.wait_for_ready(timeout=20.0)
    except TimeoutError:
        h.Kill()
        h.Wait()
        raise
    yield h
    h.Terminate()
    h.Wait()


@pytest.fixture(scope="session", autouse=True)
def combine_coverage():
    yield
    subprocess.run(["coverage", "combine"], check=False, cwd=str(REPO_ROOT))
