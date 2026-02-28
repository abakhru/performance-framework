"""
test_discovery.py — Unit tests for dashboard/discovery.py

Covers Postman parsing, OpenAPI conversion, HAR/WSDL/API Blueprint/RAML parsers,
auth detection, weight assignment, schema stubs, and SLO baseline probe.
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "dashboard"))

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


# ── parse_har ──────────────────────────────────────────────────────────────────


class TestParseHar:
    def test_parse_har_basic(self):
        """Mixed GET/POST requests are extracted with correct method and path."""
        har = {
            "log": {
                "entries": [
                    {"request": {"method": "GET", "url": "https://api.example.com/users"}},
                    {
                        "request": {
                            "method": "POST",
                            "url": "https://api.example.com/users",
                            "postData": {"text": '{"name":"Alice"}'},
                        }
                    },
                    {"request": {"method": "GET", "url": "https://api.example.com/orders"}},
                ]
            }
        }
        result = discovery.parse_har(har)
        eps = result["endpoints"]
        assert len(eps) == 3
        methods = {ep["method"] for ep in eps}
        assert "GET" in methods and "POST" in methods

    def test_parse_har_deduplicates(self):
        """Duplicate method+path combinations appear only once."""
        har = {
            "log": {
                "entries": [
                    {"request": {"method": "GET", "url": "https://api.example.com/items"}},
                    {"request": {"method": "GET", "url": "https://api.example.com/items"}},
                ]
            }
        }
        result = discovery.parse_har(har)
        assert len(result["endpoints"]) == 1

    def test_parse_har_body_from_postdata(self):
        """JSON postData text is parsed into the body field."""
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "method": "POST",
                            "url": "https://api.example.com/items",
                            "postData": {"text": '{"key": "value"}'},
                        }
                    }
                ]
            }
        }
        result = discovery.parse_har(har)
        ep = result["endpoints"][0]
        assert ep["body"] == {"key": "value"}

    def test_parse_har_group_from_path(self):
        """Group is inferred from the first path segment."""
        har = {
            "log": {
                "entries": [
                    {"request": {"method": "GET", "url": "https://api.example.com/api/v1/users"}},
                ]
            }
        }
        result = discovery.parse_har(har)
        assert result["endpoints"][0]["group"] == "api"


# ── parse_wsdl ─────────────────────────────────────────────────────────────────


class TestParseWsdl:
    _SAMPLE_WSDL = """<?xml version="1.0"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/"
             xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
             name="Calculator">
  <portType name="CalculatorPortType">
    <operation name="Add"><input/><output/></operation>
    <operation name="Subtract"><input/><output/></operation>
  </portType>
  <service name="Calculator">
    <port name="CalculatorPort" binding="tns:CalculatorBinding">
      <soap:address location="http://example.com/calculator"/>
    </port>
  </service>
</definitions>"""

    def test_parse_wsdl_operations(self):
        """WSDL with 2 operations produces 2 endpoint dicts."""
        result = discovery.parse_wsdl(self._SAMPLE_WSDL)
        eps = result["endpoints"]
        assert len(eps) == 2

    def test_parse_wsdl_method_is_post(self):
        """All SOAP operations use POST method."""
        result = discovery.parse_wsdl(self._SAMPLE_WSDL)
        assert all(ep["method"] == "POST" for ep in result["endpoints"])

    def test_parse_wsdl_invalid_xml(self):
        """Invalid XML returns error key rather than raising."""
        result = discovery.parse_wsdl("not xml at all")
        assert "error" in result
        assert result["endpoints"] == []


# ── parse_api_blueprint ────────────────────────────────────────────────────────


class TestParseApiBlueprint:
    _SAMPLE = """# My API

# Group Users

## List Users [GET /users]

## Create User [POST /users]

# Group Products

## List Products [GET /products]
"""

    def test_parse_apib_endpoint_count(self):
        """3 resource definitions → 3 endpoint dicts."""
        result = discovery.parse_api_blueprint(self._SAMPLE)
        assert len(result["endpoints"]) == 3

    def test_parse_apib_methods(self):
        """GET and POST methods are extracted correctly."""
        result = discovery.parse_api_blueprint(self._SAMPLE)
        methods = {ep["method"] for ep in result["endpoints"]}
        assert "GET" in methods and "POST" in methods

    def test_parse_apib_group_from_path(self):
        """Group is derived from first path segment."""
        result = discovery.parse_api_blueprint(self._SAMPLE)
        groups = {ep["group"] for ep in result["endpoints"]}
        assert "users" in groups or "products" in groups


# ── detect_auth_from_openapi ───────────────────────────────────────────────────


class TestDetectAuthFromOpenapi:
    def test_bearer_scheme(self):
        """HTTP Bearer securityScheme → type='bearer'."""
        spec = {"components": {"securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}}}}
        auth = discovery.detect_auth_from_openapi(spec)
        assert auth is not None
        assert auth["type"] == "bearer"
        assert auth["header"] == "Authorization"

    def test_apikey_scheme(self):
        """API key in header → type='apiKey' with correct header name."""
        spec = {
            "components": {"securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Token"}}}
        }
        auth = discovery.detect_auth_from_openapi(spec)
        assert auth is not None
        assert auth["type"] == "apiKey"
        assert auth["header"] == "X-API-Token"

    def test_no_schemes(self):
        """Spec with no securitySchemes returns None."""
        assert discovery.detect_auth_from_openapi({"openapi": "3.0.0"}) is None


# ── assign_weights ─────────────────────────────────────────────────────────────


class TestAssignWeights:
    def test_get_weight(self):
        """GET endpoints get weight 3."""
        eps = [{"method": "GET", "path": "/users", "type": "rest"}]
        result = discovery.assign_weights(eps)
        assert result[0]["weight"] == 3

    def test_post_weight(self):
        """POST endpoints get weight 2."""
        eps = [{"method": "POST", "path": "/users", "type": "rest"}]
        result = discovery.assign_weights(eps)
        assert result[0]["weight"] == 2

    def test_delete_weight(self):
        """DELETE endpoints get weight 1."""
        eps = [{"method": "DELETE", "path": "/users/1", "type": "rest"}]
        result = discovery.assign_weights(eps)
        assert result[0]["weight"] == 1

    def test_health_weight(self):
        """Health/root paths get weight 0 regardless of method."""
        eps = [{"method": "GET", "path": "/health", "type": "rest"}]
        result = discovery.assign_weights(eps)
        assert result[0]["weight"] == 0

    def test_graphql_query_weight(self):
        """GraphQL query group gets weight 3."""
        eps = [{"type": "graphql", "group": "query", "path": "/graphql"}]
        result = discovery.assign_weights(eps)
        assert result[0]["weight"] == 3

    def test_graphql_mutation_weight(self):
        """GraphQL mutation group gets weight 1."""
        eps = [{"type": "graphql", "group": "mutation", "path": "/graphql"}]
        result = discovery.assign_weights(eps)
        assert result[0]["weight"] == 1


# ── _schema_to_stub ────────────────────────────────────────────────────────────


class TestSchemaToStub:
    def test_string_type(self):
        assert discovery._schema_to_stub({"type": "string"}, {}) == ""

    def test_integer_type(self):
        assert discovery._schema_to_stub({"type": "integer"}, {}) == 0

    def test_boolean_type(self):
        assert discovery._schema_to_stub({"type": "boolean"}, {}) is False

    def test_array_type(self):
        result = discovery._schema_to_stub({"type": "array", "items": {"type": "string"}}, {})
        assert result == [""]

    def test_object_type(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        }
        result = discovery._schema_to_stub(schema, {})
        assert result == {"name": "", "age": 0}

    def test_nested_object(self):
        schema = {
            "type": "object",
            "properties": {
                "address": {
                    "type": "object",
                    "properties": {"street": {"type": "string"}},
                }
            },
        }
        result = discovery._schema_to_stub(schema, {})
        assert result == {"address": {"street": ""}}

    def test_ref_resolution(self):
        spec = {
            "components": {
                "schemas": {
                    "Item": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                    }
                }
            }
        }
        result = discovery._schema_to_stub({"$ref": "#/components/schemas/Item"}, spec)
        assert result == {"id": 0}

    def test_email_format(self):
        result = discovery._schema_to_stub({"type": "string", "format": "email"}, {})
        assert "@" in result


# ── baseline_slo_probe ─────────────────────────────────────────────────────────


class TestBaselineSloProbe:
    def test_probe_returns_p95(self):
        """Mocked responses produce a valid p95_ms value."""
        call_count = {"n": 0}

        def fake_get(url, headers, timeout=5):
            call_count["n"] += 1
            return 200, b'{"ok":true}'

        with patch.object(discovery, "http_get", side_effect=fake_get):
            eps = [{"method": "GET", "path": "/health", "weight": 1}]
            # Override health path weight so it gets sampled
            result = discovery.baseline_slo_probe("http://example.com", eps, {}, sample=1)

        assert result["p95_ms"] is not None
        assert result["error_rate"] == 0.0
        assert 0.0 <= result["apdex_score"] <= 1.0

    def test_probe_no_endpoints_returns_none(self):
        """No GET endpoints → all None values."""
        result = discovery.baseline_slo_probe("http://example.com", [], {})
        assert result["p95_ms"] is None
        assert result["error_rate"] is None

    def test_probe_counts_errors(self):
        """4xx responses increment error rate."""

        def fake_get(url, headers, timeout=5):
            return 404, b""

        with patch.object(discovery, "http_get", side_effect=fake_get):
            eps = [{"method": "GET", "path": "/missing", "weight": 1}]
            result = discovery.baseline_slo_probe("http://example.com", eps, {}, sample=1)

        assert result["error_rate"] > 0


class TestCrawlUrl:
    """Tests for crawl_url()."""

    BASE = "http://example.com"

    def _fake_get(self, responses: dict):
        """Return a side_effect fn that maps url → (status, bytes)."""

        def _get(url, headers, timeout=6):
            url_norm = url.split("?")[0].split("#")[0]
            for key, val in responses.items():
                if url_norm.endswith(key) or url_norm == key:
                    return val
            return (200, b"")

        return _get

    def test_extracts_links_from_html(self):
        """Basic anchor hrefs become GET endpoints."""
        html = b'<html><body><a href="/api/users">users</a><a href="/api/posts">posts</a></body></html>'
        with patch.object(discovery, "http_get", side_effect=self._fake_get({self.BASE: (200, html)})):
            result = discovery.crawl_url(self.BASE, {})
        paths = {ep["path"] for ep in result["endpoints"]}
        assert "/api/users" in paths
        assert "/api/posts" in paths

    def test_extracts_form_actions(self):
        """<form method=POST action=/api/submit> creates a POST endpoint."""
        html = b'<html><body><form method="POST" action="/api/submit"><input type="submit"></form></body></html>'
        with patch.object(discovery, "http_get", side_effect=self._fake_get({self.BASE: (200, html)})):
            result = discovery.crawl_url(self.BASE, {})
        eps = {(ep["method"], ep["path"]) for ep in result["endpoints"]}
        assert ("POST", "/api/submit") in eps

    def test_scans_js_files_for_endpoints(self):
        """JS files are fetched and scanned for fetch() patterns."""
        html = b'<html><head><script src="/app.js"></script></head></html>'
        js = b"fetch('/api/data').then(r => r.json())"
        responses = {self.BASE: (200, html), "/app.js": (200, js)}
        with patch.object(discovery, "http_get", side_effect=self._fake_get(responses)):
            result = discovery.crawl_url(self.BASE, {})
        paths = {ep["path"] for ep in result["endpoints"]}
        assert "/api/data" in paths
        assert result["scripts_scanned"] == 1

    def test_same_origin_enforcement(self):
        """Links to external domains are not followed or added as endpoints."""
        html = b'<html><body><a href="https://evil.com/steal">x</a><a href="/safe">y</a></body></html>'
        with patch.object(discovery, "http_get", side_effect=self._fake_get({self.BASE: (200, html)})):
            result = discovery.crawl_url(self.BASE, {})
        paths = {ep["path"] for ep in result["endpoints"]}
        assert "/safe" in paths
        assert not any("evil.com" in p for p in paths)

    def test_static_assets_filtered(self):
        """Links to .css, .png, .js etc are not added as API endpoints."""
        html = b'<html><head><link href="/style.css"><img src="/logo.png"></head><body><a href="/api/v1">ok</a></body></html>'
        with patch.object(discovery, "http_get", side_effect=self._fake_get({self.BASE: (200, html)})):
            result = discovery.crawl_url(self.BASE, {})
        paths = {ep["path"] for ep in result["endpoints"]}
        assert "/api/v1" in paths
        assert "/style.css" not in paths
        assert "/logo.png" not in paths

    def test_deduplication(self):
        """Same method+path combo only appears once."""
        html = b'<html><body><a href="/api/items">a</a><a href="/api/items">b</a></body></html>'
        with patch.object(discovery, "http_get", side_effect=self._fake_get({self.BASE: (200, html)})):
            result = discovery.crawl_url(self.BASE, {})
        paths = [ep["path"] for ep in result["endpoints"]]
        assert paths.count("/api/items") == 1

    def test_pages_crawled_count(self):
        """pages_crawled reflects visited page count."""
        html = b"<html><body>nothing</body></html>"
        with patch.object(discovery, "http_get", side_effect=self._fake_get({self.BASE: (200, html)})):
            result = discovery.crawl_url(self.BASE, {})
        assert result["pages_crawled"] == 1

    def test_max_pages_limit(self):
        """Crawler stops after max_pages pages regardless of links found."""
        # Every page links to 10 sub-paths
        links = "".join(f'<a href="/p{i}">x</a>' for i in range(20))
        html = f"<html><body>{links}</body></html>".encode()
        # All sub-pages also return the same HTML so queue would grow unbounded
        with patch.object(discovery, "http_get", return_value=(200, html)):
            result = discovery.crawl_url(self.BASE, {}, max_pages=3)
        assert result["pages_crawled"] <= 3

    def test_failed_request_skipped(self):
        """Status 0 (network error) pages are skipped gracefully."""
        with patch.object(discovery, "http_get", return_value=(0, b"")):
            result = discovery.crawl_url(self.BASE, {})
        assert result["endpoints"] == []

    def test_inline_js_scan(self):
        """Inline JS in page body is scanned for API paths."""
        html = b"<html><body><script>axios.get('/api/inline')</script></body></html>"
        with patch.object(discovery, "http_get", side_effect=self._fake_get({self.BASE: (200, html)})):
            result = discovery.crawl_url(self.BASE, {})
        paths = {ep["path"] for ep in result["endpoints"]}
        assert "/api/inline" in paths
