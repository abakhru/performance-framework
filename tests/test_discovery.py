"""
test_discovery.py — Unit tests for dashboard/discovery.py

Issue: Modularization of server.py
Tests cover Postman parsing, OpenAPI conversion, REST probing, and UA headers.
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

import discovery

# ── parse_postman ──────────────────────────────────────────────────────────────


class TestParsePostman:
    def test_parse_postman_rest(self, sample_postman):
        """A plain REST GET request is converted to a rest-type endpoint."""
        result = discovery.parse_postman(sample_postman)
        eps = result["endpoints"]
        assert len(eps) == 1
        ep = eps[0]
        assert ep["type"] == "rest"
        assert ep["method"] == "GET"
        assert "/api/v1/objects" in ep["path"] or ep["path"].endswith("objects")
        assert "name" in ep
        assert "group" in ep

    def test_parse_postman_graphql(self, sample_postman_graphql):
        """A GraphQL body-mode request is converted to a graphql-type endpoint."""
        result = discovery.parse_postman(sample_postman_graphql)
        eps = result["endpoints"]
        assert len(eps) == 1
        ep = eps[0]
        assert ep["type"] == "graphql"
        assert "query" in ep
        assert ep["query"] != ""

    def test_parse_postman_nested_folder(self):
        """Items inside a folder use the folder name as group."""
        collection = {
            "item": [
                {
                    "name": "Users",
                    "item": [
                        {
                            "name": "List Users",
                            "request": {
                                "method": "GET",
                                "url": {"path": ["api", "users"]},
                                "body": {},
                            },
                        }
                    ],
                }
            ]
        }
        result = discovery.parse_postman(collection)
        eps = result["endpoints"]
        assert len(eps) == 1
        assert eps[0]["group"] == "Users"

    def test_parse_postman_empty_collection(self):
        """An empty collection returns an empty endpoints list."""
        result = discovery.parse_postman({"item": []})
        assert result["endpoints"] == []
        assert result["setup"] == []
        assert result["teardown"] == []

    def test_parse_postman_skips_items_without_request(self):
        """Folder-level items without 'request' keys are skipped."""
        collection = {
            "item": [
                {"name": "Folder A", "item": []},  # empty folder
                {
                    "name": "Real",
                    "request": {
                        "method": "GET",
                        "url": {"path": ["health"]},
                        "body": {},
                    },
                },
            ]
        }
        result = discovery.parse_postman(collection)
        assert len(result["endpoints"]) == 1


# ── openapi_to_endpoints ───────────────────────────────────────────────────────


class TestOpenapiToEndpoints:
    def test_openapi_to_endpoints_basic(self, sample_openapi_spec):
        """Minimal OpenAPI spec produces one endpoint per path/method."""
        eps = discovery.openapi_to_endpoints(sample_openapi_spec)
        # 2 methods on /api/users + 1 method on /api/users/{id}
        assert len(eps) == 3

    def test_openapi_group_from_path(self, sample_openapi_spec):
        """Group is derived from the first non-template path segment."""
        eps = discovery.openapi_to_endpoints(sample_openapi_spec)
        groups = {ep["group"] for ep in eps}
        # All paths start with 'api', so first non-{} segment is 'api'
        assert groups == {"api"}

    def test_openapi_check_status_from_responses(self):
        """Endpoint check_status uses the first 2xx response code found."""
        spec = {
            "paths": {
                "/items": {
                    "post": {
                        "operationId": "createItem",
                        "responses": {"201": {"description": "Created"}},
                    }
                }
            }
        }
        eps = discovery.openapi_to_endpoints(spec)
        assert len(eps) == 1
        assert eps[0]["checks"]["status"] == 201

    def test_openapi_skips_extension_methods(self):
        """Methods starting with 'x-' are ignored."""
        spec = {
            "paths": {
                "/things": {
                    "get": {"responses": {"200": {}}},
                    "x-custom": {"responses": {}},
                }
            }
        }
        eps = discovery.openapi_to_endpoints(spec)
        assert len(eps) == 1
        assert eps[0]["method"] == "GET"

    def test_openapi_empty_paths(self):
        """Spec with no paths returns empty list."""
        eps = discovery.openapi_to_endpoints({"openapi": "3.0.0"})
        assert eps == []


# ── http_get UA header ─────────────────────────────────────────────────────────


class TestHttpGetUA:
    def test_http_get_includes_user_agent(self):
        """http_get must include a User-Agent header in every request."""
        captured = {}

        def fake_urlopen(req, timeout=5, context=None):
            captured["ua"] = req.get_header("User-agent")
            raise Exception("abort")  # stop after capturing

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            discovery.http_get("http://example.com/", {})

        assert "ua" in captured
        assert captured["ua"] is not None
        assert len(captured["ua"]) > 0

    def test_http_get_returns_zero_on_exception(self):
        """On a network error http_get returns (0, b'')."""
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            status, body = discovery.http_get("http://example.com/", {})
        assert status == 0
        assert body == b""


# ── probe_rest_endpoints ───────────────────────────────────────────────────────


class TestProbeRestEndpoints:
    def test_probe_rest_skips_non_json(self):
        """Endpoints that return non-JSON 200 bodies are not included."""

        def fake_get(url, headers, timeout=4):
            return 200, b"<html>not json</html>"

        with patch.object(discovery, "http_get", side_effect=fake_get):
            result = discovery.probe_rest_endpoints("http://example.com", {})

        assert result == []

    def test_probe_rest_includes_json_endpoints(self):
        """Endpoints that return valid JSON 200 bodies are included."""

        def fake_get(url, headers, timeout=4):
            if url.endswith("/api"):
                return 200, b'{"ok": true}'
            return 0, b""

        with patch.object(discovery, "http_get", side_effect=fake_get):
            result = discovery.probe_rest_endpoints("http://example.com", {})

        assert len(result) == 1
        assert result[0]["path"] == "/api"
        assert result[0]["type"] == "rest"
        assert result[0]["method"] == "GET"
