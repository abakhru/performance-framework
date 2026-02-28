"""Fixtures for InfluxDB component tests.

Requires: a running InfluxDB (docker-compose up influxdb OR local influxd).
Run standalone: pytest tests/components/influxdb/ -v
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


@pytest.fixture(scope="module")
def influx_harness():
    """InfluxDBHarness pointed at the local docker-compose InfluxDB."""
    from api_tests.harness.influxdb import InfluxDBHarness

    h = InfluxDBHarness(
        test_case=None,
        url="http://localhost:8086",
        org="matrix",
        bucket="k6",
        token="matrix-k6-token",
        use_subprocess=False,
    )
    h.wait_for_ready(timeout=10.0)
    yield h


@pytest.fixture(scope="session", autouse=True)
def combine_coverage():
    yield
    subprocess.run(["coverage", "combine"], check=False, cwd=str(REPO_ROOT))
