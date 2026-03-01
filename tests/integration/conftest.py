"""Integration test fixtures — composes FastAPIHarness + InfluxDBHarness.

Requires: docker-compose up influxdb (or local InfluxDB).
Run standalone: pytest tests/integration/ -v
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


@pytest.fixture(scope="session")
def influx_harness():
    from api_tests.harness.influxdb import InfluxDBHarness

    h = InfluxDBHarness(test_case=None, url="http://localhost:8086")
    h.wait_for_ready(timeout=15.0)
    yield h


@pytest.fixture(scope="session")
def dashboard_harness(influx_harness, tmp_path_factory):
    from api_tests.harness.fastapi import FastAPIHarness

    tmp = tmp_path_factory.mktemp("dashboard_integration")
    h = FastAPIHarness(
        test_case=None,
        port=25656,
        coverage=True,
        own_dir=str(tmp),
        stdout_path=str(tmp / "stdout.log"),
        stderr_path=str(tmp / "stderr.log"),
    )
    h.Launch()
    h.wait_for_ready(timeout=20.0)
    yield h
    h.Terminate()
    h.Wait()


@pytest.fixture(scope="function")
def dashboard_client(dashboard_harness):
    with dashboard_harness.client as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def combine_coverage():
    yield
    subprocess.run(["coverage", "combine"], check=False, cwd=str(REPO_ROOT))
