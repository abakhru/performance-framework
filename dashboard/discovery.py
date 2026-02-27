"""
discovery.py — API autodiscovery helpers for the k6 dashboard.

Supports:
  - Postman collection parsing
  - OpenAPI / Swagger spec conversion
  - GraphQL introspection
  - REST endpoint probing (common path heuristics)

Public API:
  load_repo_postman() → dict
  parse_postman(collection) → dict
  discover_url(base_url, token) → dict
"""

import json
import re
import ssl
import urllib.error
import urllib.request

from storage import REPO_ROOT

# ── Constants ──────────────────────────────────────────────────────────────────

_POSTMAN_COLLECTION = REPO_ROOT / "Matrix-Strike48_collections.postman_collection.json"

_OPENAPI_PATHS = [
    "/openapi.json",
    "/swagger.json",
    "/api/openapi.json",
    "/api/swagger.json",
    "/api/v1/openapi.json",
    "/docs/openapi.json",
    "/api-docs",
    "/api/docs",
    "/api/v1/swagger.json",
    "/v1/openapi.json",
    "/v2/openapi.json",
    "/swagger/v1/swagger.json",
]
_GRAPHQL_PATHS = ["/graphql", "/api/graphql", "/api/v1alpha", "/api/v1/graphql"]

_COMMON_REST_PATHS = [
    "/",
    "/api",
    "/api/v1",
    "/v1",
    "/v2",
    "/objects",
    "/items",
    "/users",
    "/products",
    "/orders",
    "/posts",
    "/resources",
    "/data",
    "/entries",
    "/records",
    "/events",
    "/api/objects",
    "/api/items",
    "/api/users",
    "/api/v1/users",
    "/api/v1/items",
]

# Browser-like UA so services don't block discovery requests
_DISCOVERY_UA = "Mozilla/5.0 (compatible; PerfFramework/1.0)"

# SSL context that skips verification for scanning internal/dev services
_NO_VERIFY_CTX = ssl.create_default_context()
_NO_VERIFY_CTX.check_hostname = False
_NO_VERIFY_CTX.verify_mode = ssl.CERT_NONE


# ── HTTP helpers ───────────────────────────────────────────────────────────────


def http_get(url: str, headers: dict, timeout: int = 5) -> tuple[int, bytes]:
    """Simple GET using urllib; returns (status_code, body_bytes)."""
    merged = {"User-Agent": _DISCOVERY_UA, **headers}
    req = urllib.request.Request(url, headers=merged)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_NO_VERIFY_CTX) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""


def http_post_json(url: str, payload: dict, headers: dict, timeout: int = 5) -> tuple[int, bytes]:
    """Simple POST using urllib; returns (status_code, body_bytes)."""
    data = json.dumps(payload).encode()
    h = {"Content-Type": "application/json", "User-Agent": _DISCOVERY_UA, **headers}
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_NO_VERIFY_CTX) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception:
        return 0, b""


# ── Postman collection ─────────────────────────────────────────────────────────


def load_repo_postman() -> dict:
    """Load the bundled Postman collection JSON; returns error dict on failure."""
    try:
        with open(_POSTMAN_COLLECTION, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}


def postman_item_to_endpoint(item: dict, group: str) -> dict | None:
    """Convert a single Postman item into an endpoint dict."""
    req = item.get("request", {})
    if not req:
        return None
    body = req.get("body", {}) or {}
    mode = body.get("mode", "")
    name_raw = item.get("name", "unnamed")
    name = re.sub(r"[^a-zA-Z0-9]+", "_", name_raw).strip("_") or "endpoint"

    # Extract URL path
    url_obj = req.get("url", {})
    if isinstance(url_obj, str):
        parts = url_obj.split("/", 3)
        path = "/" + parts[-1] if "/" in url_obj else url_obj
    else:
        path_parts = url_obj.get("path", []) or []
        path = "/" + "/".join(p for p in path_parts if isinstance(p, str) and not p.startswith(":"))

    if not path or path == "/":
        path = "/"

    if mode == "graphql":
        gql = body.get("graphql", {}) or {}
        query_str = gql.get("query", "")
        try:
            variables = json.loads(gql.get("variables", "{}") or "{}")
        except Exception:
            variables = {}
        return {
            "name": name,
            "group": group,
            "type": "graphql",
            "path": path,
            "weight": 1,
            "query": query_str,
            "variables": variables,
            "checks": {"status": 200, "no_graphql_errors": True, "has_data": True},
        }
    else:
        method = req.get("method", "GET").upper()
        raw_body = body.get("raw", None)
        try:
            parsed_body = json.loads(raw_body) if raw_body else None
        except Exception:
            parsed_body = None
        return {
            "name": name,
            "group": group,
            "type": "rest",
            "method": method,
            "path": path,
            "weight": 1,
            "body": parsed_body,
            "checks": {"status": 200},
        }


def parse_postman(collection: dict) -> dict:
    """Walk a Postman collection and return an endpoint config dict."""
    endpoints: list = []

    def walk(items, group_name="default"):
        for item in items:
            if "item" in item:
                walk(item["item"], item.get("name", group_name))
            elif "request" in item:
                ep = postman_item_to_endpoint(item, group_name)
                if ep:
                    endpoints.append(ep)

    walk(collection.get("item", []))
    return {"endpoints": endpoints, "setup": [], "teardown": []}


# ── OpenAPI ────────────────────────────────────────────────────────────────────


def openapi_to_endpoints(spec: dict) -> list:
    """Convert an OpenAPI/Swagger spec's paths into endpoint dicts."""
    endpoints = []
    paths = spec.get("paths", {}) or {}
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        segs = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
        group = segs[0] if segs else "api"
        for method, op in methods.items():
            if method.startswith("x-") or not isinstance(op, dict):
                continue
            method = method.upper()
            op_id = op.get("operationId") or f"{method}_{path}"
            name = re.sub(r"[^a-zA-Z0-9]+", "_", op_id).strip("_") or "endpoint"
            responses = op.get("responses", {}) or {}
            check_status = 200
            for code in responses:
                try:
                    c = int(code)
                    if 200 <= c < 300:
                        check_status = c
                        break
                except Exception:
                    pass
            endpoints.append(
                {
                    "name": name,
                    "group": group,
                    "type": "rest",
                    "method": method,
                    "path": path,
                    "weight": 1,
                    "body": None,
                    "checks": {"status": check_status},
                }
            )
    return endpoints


# ── GraphQL introspection ──────────────────────────────────────────────────────


def graphql_introspection(url: str, token: str) -> dict | None:
    """Run GraphQL introspection and return endpoint config dict, or None."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    introspection_query = {
        "query": """
{
  __schema {
    queryType { fields { name description args { name } } }
    mutationType { fields { name description args { name } } }
  }
}
"""
    }
    status, body = http_post_json(url, introspection_query, headers, timeout=8)
    if status != 200 or not body:
        return None
    try:
        data = json.loads(body)
    except Exception:
        return None
    schema = data.get("data", {}).get("__schema", {})
    if not schema:
        return None

    endpoints = []
    query_type = schema.get("queryType") or {}
    for field in query_type.get("fields") or []:
        fname = field.get("name", "")
        if not fname:
            continue
        args = field.get("args") or []
        var_defs = ", ".join(f"${a['name']}: String" for a in args[:3])
        arg_use = ", ".join(f"{a['name']}: ${a['name']}" for a in args[:3])
        q = (
            f"query {fname}"
            f"{('(' + var_defs + ')') if var_defs else ''}"
            f" {{ {fname}{('(' + arg_use + ')') if arg_use else ''} {{ __typename }} }}"
        )
        path_part = url.split("//", 1)[-1].split("/", 1)
        ep_path = ("/" + path_part[1]) if len(path_part) > 1 else "/graphql"
        endpoints.append(
            {
                "name": fname,
                "group": "query",
                "type": "graphql",
                "path": ep_path,
                "weight": 1,
                "query": q,
                "variables": {},
                "checks": {"status": 200, "no_graphql_errors": True, "has_data": True},
            }
        )

    mutation_type = schema.get("mutationType") or {}
    for field in mutation_type.get("fields") or []:
        fname = field.get("name", "")
        if not fname:
            continue
        endpoints.append(
            {
                "name": fname,
                "group": "mutation",
                "type": "graphql",
                "path": "/graphql",
                "weight": 1,
                "query": f"mutation {fname} {{ {fname} {{ __typename }} }}",
                "variables": {},
                "checks": {"status": 200, "no_graphql_errors": True, "has_data": True},
            }
        )

    return {"endpoints": endpoints, "setup": [], "teardown": []}


# ── REST probe ─────────────────────────────────────────────────────────────────


def probe_rest_endpoints(base_url: str, headers: dict) -> list:
    """Probe common REST collection paths; return those that respond with JSON."""
    endpoints = []
    seen_paths: set = set()
    for path in _COMMON_REST_PATHS:
        if path in seen_paths:
            continue
        status, body = http_get(base_url + path, headers, timeout=4)
        if status == 200 and body:
            try:
                json.loads(body)  # must be valid JSON
                seen_paths.add(path)
                segs = [s for s in path.strip("/").split("/") if s]
                group = segs[-1] if segs else "root"
                name = re.sub(r"[^a-zA-Z0-9]+", "_", group).strip("_") or "root"
                endpoints.append(
                    {
                        "name": name,
                        "group": group,
                        "type": "rest",
                        "method": "GET",
                        "path": path,
                        "weight": 1,
                        "body": None,
                        "checks": {"status": 200},
                    }
                )
            except Exception:
                pass
    return endpoints


# ── URL discovery (main entry point) ──────────────────────────────────────────


def discover_url(base_url: str, token: str) -> dict:
    """
    Try OpenAPI → GraphQL → REST probe in order.
    Returns an endpoint config dict with a 'source' key indicating what was found.
    """
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    # Try OpenAPI/Swagger
    for opath in _OPENAPI_PATHS:
        target = base_url + opath
        status, body = http_get(target, headers, timeout=5)
        if status == 200 and body:
            try:
                spec = json.loads(body)
                if "paths" in spec or "openapi" in spec or "swagger" in spec:
                    eps = openapi_to_endpoints(spec)
                    return {
                        "source": "openapi",
                        "source_url": target,
                        "endpoints": eps,
                        "setup": [],
                        "teardown": [],
                    }
            except Exception:
                pass

    # Try GraphQL introspection
    for gpath in _GRAPHQL_PATHS:
        target = base_url + gpath
        result = graphql_introspection(target, token)
        if result:
            return {"source": "graphql", "source_url": target, **result}

    # Fallback: probe common REST collection paths
    eps = probe_rest_endpoints(base_url, headers)
    if eps:
        return {
            "source": "rest-probe",
            "source_url": base_url,
            "endpoints": eps,
            "setup": [],
            "teardown": [],
        }

    return {
        "source": "none",
        "endpoints": [],
        "setup": [],
        "teardown": [],
        "error": "No discoverable API spec found at standard paths",
    }
