"""E2E: Full stack — k6 smoke run → InfluxDB → dashboard reads results.

bd-e2e-fullstack: End-to-end performance test cycle.
"""

import os

import pytest


class TestFullStack:
    """bd-e2e-fullstack: Full k6 → InfluxDB → dashboard cycle."""

    @pytest.mark.skip(reason="Requires a live target BASE_URL — set env var and unskip")
    def test_k6_smoke_run_stores_metrics(self, influx_harness, dashboard_harness):
        """bd-e2e-fullstack: k6 smoke run completes and metrics appear in InfluxDB."""
        from api_tests.harness.k6 import K6Harness

        base_url = os.environ.get("BASE_URL", "")
        if not base_url:
            pytest.skip("BASE_URL not set")

        h = K6Harness(
            test_case=None,
            profile="smoke",
            base_url=base_url,
            influx_url="http://localhost:8086",
        )
        h.Launch()
        h.Wait()
        h.AssertGoodExitCode()

        # Verify metrics landed in InfluxDB
        rows = influx_harness.query('from(bucket:"k6") |> range(start: -5m) |> limit(n:1)')
        assert len(rows) > 0, "Expected k6 metrics in InfluxDB after smoke run"

        # Verify dashboard can read the run
        with dashboard_harness.client as client:
            r = client.get("/runs")
        assert r.status_code == 200
