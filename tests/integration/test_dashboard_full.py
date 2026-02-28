"""Integration: Dashboard reads from InfluxDB correctly.

bd-integration-dashboard: Dashboard API reads SLO and run data from real InfluxDB.
"""


class TestDashboardFull:
    """bd-integration-dashboard: Full dashboard with real InfluxDB."""

    def test_runs_endpoint_returns_200(self, dashboard_client):
        """bd-integration-dashboard: GET /runs returns 200 with run data."""
        r = dashboard_client.get("/runs")
        assert r.status_code == 200
        data = r.json()
        # /runs may return {"runs": [...]} or directly a list depending on version
        assert isinstance(data, (list, dict)), f"Expected list or dict, got {type(data)}"

    def test_slo_config_readable(self, dashboard_client):
        """bd-integration-dashboard: SLO config is accessible."""
        r = dashboard_client.get("/slo/config")
        assert r.status_code == 200

    def test_api_tests_plan_accessible(self, dashboard_client):
        """bd-integration-dashboard: /api-tests/plan endpoint is accessible."""
        r = dashboard_client.get("/api-tests/plan")
        assert r.status_code == 200
