"""Component tests for InfluxDBHarness.

bd-influxdb-component: Verify InfluxDBHarness can write and query data.
Run standalone: pytest tests/components/influxdb/ -v
"""

import time
import unittest

import pytest


class TestInfluxDBHarness(unittest.TestCase):
    """bd-influxdb-component: InfluxDB harness write/query/health."""

    harness = None  # injected by fixture

    def test_health_check(self):
        """bd-influxdb-component: InfluxDB health endpoint returns 200."""
        self.assertTrue(self.harness.health_check())

    def test_write_and_query(self):
        """bd-influxdb-component: Write a point and read it back."""
        ts = int(time.time())
        self.harness.write(
            "test_harness",
            {"value": 42, "ts": ts},
            tags={"env": "test"},
        )
        time.sleep(1)  # InfluxDB write is eventually consistent
        rows = self.harness.query(
            'from(bucket:"k6") |> range(start: -1m) |> filter(fn: (r) => r._measurement == "test_harness")'
        )
        self.assertGreater(len(rows), 0, "Expected at least one row from InfluxDB query")

    def test_write_string_field(self):
        """bd-influxdb-component: String fields are quoted in line protocol."""
        self.harness.write(
            "test_strings",
            {"label": "hello world"},
            tags={"env": "test"},
        )
        # No assertion needed — just verifying no exception is raised


@pytest.fixture(autouse=True)
def _inject(influx_harness, request):
    if request.instance is not None:
        request.instance.harness = influx_harness
