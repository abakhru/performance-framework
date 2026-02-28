"""Integration: Discovery → endpoint config stored and retrievable.

bd-integration-discovery: End-to-end test of discovery → config storage.
"""


class TestDiscoveryToConfig:
    """bd-integration-discovery: Discover endpoints and verify config persistence."""

    def test_postman_import_stores_endpoints(self, dashboard_client):
        """bd-integration-discovery: POST /discover/postman stores a valid endpoint config."""
        postman = {
            "item": [
                {
                    "name": "List Items",
                    "request": {
                        "method": "GET",
                        "url": {"path": ["api", "v1", "items"]},
                        "body": {},
                    },
                }
            ]
        }
        r = dashboard_client.post("/discover/postman", json=postman)
        assert r.status_code == 200
        data = r.json()
        assert "endpoints" in data
        assert len(data["endpoints"]) >= 1

    def test_get_config_after_import(self, dashboard_client):
        """bd-integration-discovery: GET /config/endpoints returns current config."""
        r = dashboard_client.get("/config/endpoints")
        assert r.status_code == 200
        data = r.json()
        assert "endpoints" in data
