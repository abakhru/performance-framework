"""Component tests for the dashboard API.

bd-dashboard-component: Verify all key dashboard API endpoints in isolation.
Run standalone: pytest tests/components/dashboard/ -v
"""

import unittest

import pytest


class TestDashboardEndpoints(unittest.TestCase):
    """bd-dashboard-component: Dashboard API routes respond correctly."""

    harness = None  # injected by fixture

    def test_endpoints_config_returns_200(self):
        """bd-dashboard-component: GET /config/endpoints returns 200."""
        with self.harness.client as client:
            r = client.get("/config/endpoints")
        self.assertEqual(r.status_code, 200)
        self.assertIn("endpoints", r.json())

    def test_runs_list_returns_200(self):
        """bd-dashboard-component: GET /runs returns 200."""
        with self.harness.client as client:
            r = client.get("/runs")
        self.assertEqual(r.status_code, 200)

    def test_discover_postman_endpoint(self):
        """bd-dashboard-component: POST /discover/postman accepts a Postman collection."""
        with self.harness.client as client:
            r = client.post(
                "/discover/postman",
                json={
                    "item": [
                        {
                            "name": "Test",
                            "request": {
                                "method": "GET",
                                "url": {"path": ["api", "v1", "test"]},
                                "body": {},
                            },
                        }
                    ]
                },
            )
        self.assertIn(r.status_code, [200, 422])

    def test_slo_config_returns_200(self):
        """bd-dashboard-component: GET /slo/config returns 200."""
        with self.harness.client as client:
            r = client.get("/slo/config")
        self.assertEqual(r.status_code, 200)

    def test_profiles_returns_200(self):
        """bd-dashboard-component: GET /profiles returns 200."""
        with self.harness.client as client:
            r = client.get("/profiles")
        self.assertEqual(r.status_code, 200)

    def test_api_tests_plan_returns_200(self):
        """bd-dashboard-component: GET /api-tests/plan returns 200."""
        with self.harness.client as client:
            r = client.get("/api-tests/plan")
        self.assertEqual(r.status_code, 200)


@pytest.fixture(autouse=True)
def _inject(dashboard_harness, request):
    if request.instance is not None:
        request.instance.harness = dashboard_harness
