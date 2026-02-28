"""Component tests for the discovery module.

bd-discovery-component: Verify endpoint discovery and parsing logic.
Run standalone: pytest tests/components/discovery/ -v
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[3] / "dashboard"))
import discovery


class TestDiscoveryParsers:
    """bd-discovery-component: Parser functions return valid endpoint configs."""

    def test_parse_postman_rest(self):
        """bd-discovery-component: parse_postman converts REST requests."""
        collection = {
            "item": [
                {
                    "name": "List Users",
                    "request": {
                        "method": "GET",
                        "url": {"path": ["api", "v1", "users"]},
                        "body": {},
                    },
                }
            ]
        }
        result = discovery.parse_postman(collection)
        assert "endpoints" in result
        assert len(result["endpoints"]) == 1
        ep = result["endpoints"][0]
        assert ep["type"] == "rest"
        assert ep["method"] == "GET"

    def test_parse_postman_graphql(self):
        """bd-discovery-component: parse_postman converts GraphQL requests."""
        collection = {
            "item": [
                {
                    "name": "Get User",
                    "request": {
                        "method": "POST",
                        "url": {"path": ["graphql"]},
                        "body": {
                            "mode": "graphql",
                            "graphql": {"query": "{ user { id } }", "variables": "{}"},
                        },
                    },
                }
            ]
        }
        result = discovery.parse_postman(collection)
        eps = result["endpoints"]
        assert len(eps) == 1
        assert eps[0]["type"] == "graphql"

    def test_parse_openapi_spec(self):
        """bd-discovery-component: parse OpenAPI spec extracts paths."""
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/api/users": {"get": {"operationId": "listUsers", "responses": {"200": {"description": "OK"}}}},
                "/api/users/{id}": {"get": {"operationId": "getUser", "responses": {"200": {"description": "OK"}}}},
            },
        }

        def fake_http_get(url, headers, timeout=5):
            return 200, json.dumps(spec).encode()

        with patch.object(discovery, "http_get", side_effect=fake_http_get):
            result = discovery.discover_url("http://example.com", "")

        assert "endpoints" in result

    def test_parse_har(self):
        """bd-discovery-component: parse_har extracts API calls from HAR."""
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "method": "GET",
                            "url": "https://api.example.com/users",
                            "headers": [],
                            "postData": None,
                        },
                        "response": {"status": 200},
                    }
                ]
            }
        }
        result = discovery.parse_har(har)
        assert "endpoints" in result
