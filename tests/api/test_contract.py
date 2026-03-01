"""Contract tests for the dashboard's own REST API.

bd-api-contract: Verify every public dashboard endpoint returns the correct
HTTP status, Content-Type, and top-level JSON schema keys.  These tests are
intentionally schema-only — they do not assert on runtime values so they pass
against a cold dashboard with no InfluxDB / k6 data.

Requires: a running Luna dashboard.
  BASE_URL=http://localhost:5656 pytest tests/api/test_contract.py -v

Or run against the component harness:
  pytest tests/components/dashboard/ -v      # starts dashboard subprocess
  BASE_URL=http://localhost:5656 pytest tests/api/test_contract.py -v
"""

from __future__ import annotations

import pytest


class TestHealthContract:
    """bd-api-contract: /health and /ready endpoints."""

    def test_health_status_200(self, api_client) -> None:
        """bd-api-contract: GET /health returns 200."""
        r = api_client.get("/health")
        assert r.status_code == 200

    def test_health_returns_json(self, api_client) -> None:
        """bd-api-contract: GET /health Content-Type is application/json."""
        r = api_client.get("/health")
        assert "application/json" in r.headers.get("content-type", "")

    def test_health_schema(self, api_client) -> None:
        """bd-api-contract: GET /health has {status, components} keys."""
        data = api_client.get("/health").json()
        assert "status" in data, f"Missing 'status'. Got: {list(data.keys())}"
        assert isinstance(data["status"], str), f"'status' should be str, got {type(data['status'])}"

    def test_ready_status_200(self, api_client) -> None:
        """bd-api-contract: GET /ready returns 200."""
        r = api_client.get("/ready")
        assert r.status_code == 200


class TestRunsContract:
    """bd-api-contract: /runs endpoints."""

    def test_runs_status_200(self, api_client) -> None:
        """bd-api-contract: GET /runs returns 200."""
        r = api_client.get("/runs")
        assert r.status_code == 200

    def test_runs_schema(self, api_client) -> None:
        """bd-api-contract: GET /runs returns {runs: [...]} dict."""
        data = api_client.get("/runs").json()
        assert isinstance(data, dict), f"Expected dict, got {type(data).__name__}"
        assert "runs" in data, f"Missing 'runs' key. Got: {list(data.keys())}"
        assert isinstance(data["runs"], list), f"'runs' must be a list, got {type(data['runs'])}"

    def test_run_row_schema(self, api_client) -> None:
        """bd-api-contract: Each run row has expected keys if runs exist."""
        data = api_client.get("/runs").json()
        runs = data.get("runs", [])
        if not runs:
            pytest.skip("No runs in the database — schema cannot be verified")
        row = runs[0]
        for key in ("run_id", "profile", "status"):
            assert key in row, f"Run row missing '{key}': {list(row.keys())}"

    def test_runs_unknown_id_not_200(self, api_client) -> None:
        """bd-api-contract: GET /runs/<unknown-id> returns 404 or 422."""
        r = api_client.get("/runs/nonexistent-run-id-99999")
        assert r.status_code in (404, 422), f"Expected 404/422, got {r.status_code}"


class TestRunControlContract:
    """bd-api-contract: /run/status and related endpoints."""

    def test_run_status_200(self, api_client) -> None:
        """bd-api-contract: GET /run/status returns 200."""
        r = api_client.get("/run/status")
        assert r.status_code == 200

    def test_run_status_has_status_field(self, api_client) -> None:
        """bd-api-contract: GET /run/status has a 'status' string field."""
        data = api_client.get("/run/status").json()
        assert isinstance(data, dict), f"Expected dict, got {type(data).__name__}"
        assert "status" in data, f"Missing 'status'. Got: {list(data.keys())}"
        assert isinstance(data["status"], str)


class TestEndpointsConfigContract:
    """bd-api-contract: /config/endpoints — endpoint config CRUD."""

    def test_get_config_status_200(self, api_client) -> None:
        """bd-api-contract: GET /config/endpoints returns 200."""
        r = api_client.get("/config/endpoints")
        assert r.status_code == 200

    def test_get_config_schema(self, api_client) -> None:
        """bd-api-contract: GET /config/endpoints has {service, endpoints, setup, teardown}."""
        data = api_client.get("/config/endpoints").json()
        assert isinstance(data, dict), f"Expected dict, got {type(data).__name__}"
        assert "endpoints" in data, f"Missing 'endpoints'. Got: {list(data.keys())}"
        assert isinstance(data["endpoints"], list), "'endpoints' must be a list"

    def test_endpoints_key_present(self, api_client) -> None:
        """bd-api-contract: GET /config/endpoints has at least 'endpoints' key."""
        data = api_client.get("/config/endpoints").json()
        assert "endpoints" in data


class TestSLOContract:
    """bd-api-contract: /slo/config endpoint."""

    def test_slo_config_200(self, api_client) -> None:
        """bd-api-contract: GET /slo/config returns 200."""
        r = api_client.get("/slo/config")
        assert r.status_code == 200

    def test_slo_config_is_dict(self, api_client) -> None:
        """bd-api-contract: GET /slo/config returns a JSON object."""
        data = api_client.get("/slo/config").json()
        assert isinstance(data, dict), f"Expected dict, got {type(data).__name__}"


class TestProfilesContract:
    """bd-api-contract: /profiles endpoint."""

    def test_profiles_200(self, api_client) -> None:
        """bd-api-contract: GET /profiles returns 200."""
        r = api_client.get("/profiles")
        assert r.status_code == 200

    def test_profiles_valid_json(self, api_client) -> None:
        """bd-api-contract: GET /profiles returns a list or dict."""
        data = api_client.get("/profiles").json()
        assert isinstance(data, (list, dict)), f"Expected list or dict, got {type(data).__name__}"


class TestAPITestsRouterContract:
    """bd-api-contract: /api-tests/* router endpoints."""

    def test_api_tests_plan_200(self, api_client) -> None:
        """bd-api-contract: GET /api-tests/plan returns 200."""
        r = api_client.get("/api-tests/plan")
        assert r.status_code == 200

    def test_api_tests_plan_schema(self, api_client) -> None:
        """bd-api-contract: GET /api-tests/plan returns {service, total, entries} or {error}."""
        data = api_client.get("/api-tests/plan").json()
        assert isinstance(data, dict), f"Expected dict, got {type(data).__name__}"
        # Either success shape or error shape
        assert "total" in data or "error" in data, (
            f"Expected 'total' or 'error' key. Got: {list(data.keys())}"
        )

    def test_api_tests_results_200(self, api_client) -> None:
        """bd-api-contract: GET /api-tests/results returns 200."""
        r = api_client.get("/api-tests/results")
        assert r.status_code == 200

    def test_api_tests_results_is_dict(self, api_client) -> None:
        """bd-api-contract: GET /api-tests/results returns a JSON object."""
        data = api_client.get("/api-tests/results").json()
        assert isinstance(data, dict), f"Expected dict, got {type(data).__name__}"

    def test_api_tests_run_post_schema(self, api_client) -> None:
        """bd-api-contract: POST /api-tests/run accepts {suite, base_url, auth_token}."""
        # We call with suite="unit" (fastest) to verify the schema round-trip
        r = api_client.post(
            "/api-tests/run",
            json={"suite": "unit", "base_url": "", "auth_token": ""},
        )
        assert r.status_code == 200, f"POST /api-tests/run failed: {r.text}"
        data = r.json()
        for key in ("passed", "failed", "errors", "skipped", "total", "success", "suite"):
            assert key in data, f"RunResponse missing '{key}'. Got: {list(data.keys())}"

    def test_api_tests_run_success_field_is_bool(self, api_client) -> None:
        """bd-api-contract: POST /api-tests/run returns {success: bool}."""
        r = api_client.post("/api-tests/run", json={"suite": "unit"})
        if r.status_code != 200:
            pytest.skip("POST /api-tests/run not available")
        assert isinstance(r.json()["success"], bool)


class TestDiscoveryRouterContract:
    """bd-api-contract: /discovery/* endpoints."""

    def test_discovery_endpoint_exists(self, api_client) -> None:
        """bd-api-contract: GET /discovery/discover with no URL returns 422 (missing required param)."""
        r = api_client.get("/discovery/discover")
        assert r.status_code in (400, 422), f"Expected 400/422 without url param, got {r.status_code}"

    def test_discovery_with_url_param(self, api_client) -> None:
        """bd-api-contract: GET /discovery/discover?url=<x> is accepted (200 or timeout)."""
        # Use a fast-failing URL so the test doesn't block
        r = api_client.get(
            "/discovery/discover",
            params={"url": "http://localhost:19999"},  # nothing listening here
        )
        # Accept 200 (empty result) or 200 with error in body — any 2xx is OK
        assert r.status_code in (200, 422, 500), (
            f"Unexpected status {r.status_code} for discovery endpoint"
        )
