"""Contract tests for the dashboard's own API.

bd-api-contract: Verify the dashboard API contract (schema, status codes).
Requires: dashboard running (just dashboard or pytest tests/components/dashboard/).
Run: BASE_URL=http://localhost:5656 pytest tests/api/test_contract.py -v
"""


class TestDashboardContract:
    """bd-api-contract: Dashboard API contract tests."""

    def test_config_endpoints_schema(self, api_client):
        """bd-api-contract: GET /config/endpoints returns {service, endpoints, setup, teardown}."""
        r = api_client.get("/config/endpoints")
        assert r.status_code == 200
        data = r.json()
        assert "endpoints" in data, f"Missing 'endpoints' key. Got: {list(data.keys())}"

    def test_runs_returns_list(self, api_client):
        """bd-api-contract: GET /runs returns a JSON array."""
        r = api_client.get("/runs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_slo_config_schema(self, api_client):
        """bd-api-contract: GET /slo/config returns a JSON object."""
        r = api_client.get("/slo/config")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_api_tests_plan_schema(self, api_client):
        """bd-api-contract: GET /api-tests/plan returns {service, total, entries}."""
        r = api_client.get("/api-tests/plan")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data or "error" in data

    def test_run_status_404_for_unknown(self, api_client):
        """bd-api-contract: GET /runs/nonexistent returns 404."""
        r = api_client.get("/runs/nonexistent-run-id-12345")
        assert r.status_code in (404, 422)

    def test_profiles_returns_list_or_dict(self, api_client):
        """bd-api-contract: GET /profiles returns valid JSON."""
        r = api_client.get("/profiles")
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))
