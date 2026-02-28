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
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

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


def _resolve_ref(ref: str, spec: dict) -> dict:
    """Resolve a $ref pointer in an OpenAPI spec (inline only, no external files)."""
    if not ref.startswith("#/"):
        return {}
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return {}
        node = node[part]
    return node if isinstance(node, dict) else {}


def _schema_to_stub(schema: dict, spec: dict, depth: int = 0) -> object:
    """Convert a JSON Schema dict to a stub value suitable for a request body."""
    if depth > 4 or not isinstance(schema, dict):
        return None
    if "$ref" in schema:
        schema = _resolve_ref(schema["$ref"], spec)
        if not schema:
            return None
    t = schema.get("type", "object")
    if t == "string":
        fmt = schema.get("format", "")
        if fmt == "date-time":
            return "2024-01-01T00:00:00Z"
        if fmt == "date":
            return "2024-01-01"
        if fmt == "email":
            return "user@example.com"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        enum = schema.get("enum", [])
        return enum[0] if enum else ""
    elif t in ("integer", "number"):
        return 0
    elif t == "boolean":
        return False
    elif t == "array":
        items = schema.get("items", {})
        return [_schema_to_stub(items, spec, depth + 1)]
    elif t == "object" or "properties" in schema:
        props = schema.get("properties", {})
        return {k: _schema_to_stub(v, spec, depth + 1) for k, v in props.items()}
    elif "allOf" in schema:
        merged: dict = {}
        for sub in schema.get("allOf", []):
            sub_stub = _schema_to_stub(sub, spec, depth + 1)
            if isinstance(sub_stub, dict):
                merged.update(sub_stub)
        return merged
    elif "oneOf" in schema or "anyOf" in schema:
        variants = schema.get("oneOf") or schema.get("anyOf") or []
        return _schema_to_stub(variants[0], spec, depth + 1) if variants else {}
    return {}


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
            # Extract body stub from requestBody schema
            body = None
            req_body = op.get("requestBody", {}) or {}
            content = req_body.get("content", {}) or {}
            for _ct, ct_val in content.items():
                if isinstance(ct_val, dict):
                    schema = ct_val.get("schema", {})
                    if schema:
                        body = _schema_to_stub(schema, spec)
                    break
            endpoints.append(
                {
                    "name": name,
                    "group": group,
                    "type": "rest",
                    "method": method,
                    "path": path,
                    "weight": 1,
                    "body": body,
                    "checks": {"status": check_status},
                }
            )
    return endpoints


def detect_auth_from_openapi(spec: dict) -> dict | None:
    """Read securitySchemes (OpenAPI 3) or securityDefinitions (Swagger 2) and return auth config."""
    schemes = spec.get("components", {}).get("securitySchemes", {}) or {}
    if not schemes:
        schemes = spec.get("securityDefinitions", {}) or {}
    for _name, scheme in schemes.items():
        if not isinstance(scheme, dict):
            continue
        stype = scheme.get("type", "").lower()
        if stype == "http":
            sub = scheme.get("scheme", "").lower()
            if sub == "bearer":
                return {"type": "bearer", "header": "Authorization"}
            if sub == "basic":
                return {"type": "basic", "header": "Authorization"}
        elif stype == "apikey":
            location = scheme.get("in", "header")
            header_name = scheme.get("name", "X-API-Key")
            if location == "header":
                return {"type": "apiKey", "header": header_name}
        elif stype == "oauth2":
            return {"type": "bearer", "header": "Authorization"}
    return None


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


# ── Weight heuristics ──────────────────────────────────────────────────────────

_HEALTH_PATHS = frozenset(["/", "/health", "/healthz", "/ping", "/status", "/api"])


def assign_weights(endpoints: list) -> list:
    """Assign traffic weights in-place: GET→3, POST/PUT/PATCH→2, DELETE→1, health/root→0."""
    for ep in endpoints:
        path = (ep.get("path") or "/").lower()
        method = (ep.get("method") or "GET").upper()
        ep_type = ep.get("type", "rest")
        if path in _HEALTH_PATHS:
            ep["weight"] = 0
        elif ep_type == "graphql":
            ep["weight"] = 1 if ep.get("group") == "mutation" else 3
        elif method == "GET":
            ep["weight"] = 3
        elif method in ("POST", "PUT", "PATCH"):
            ep["weight"] = 2
        elif method == "DELETE":
            ep["weight"] = 1
        else:
            ep["weight"] = 1
    return endpoints


# ── SLO baseline probe ─────────────────────────────────────────────────────────


def baseline_slo_probe(base_url: str, endpoints: list, headers: dict, sample: int = 5) -> dict:
    """Probe a sample of GET endpoints; measure response times; return SLO baselines."""
    get_eps = [ep for ep in endpoints if (ep.get("method") or "GET").upper() == "GET" and ep.get("weight", 1) > 0]
    sampled = get_eps[:sample]

    times: list = []
    errors = 0
    total_requests = 0

    for ep in sampled:
        path = ep.get("path", "/")
        url = base_url.rstrip("/") + path
        for _ in range(3):
            start = time.perf_counter()
            status, _body = http_get(url, headers, timeout=5)
            elapsed_ms = (time.perf_counter() - start) * 1000
            total_requests += 1
            if status > 0:
                times.append(elapsed_ms)
                if status >= 400:
                    errors += 1
            else:
                errors += 1

    if not times:
        return {"p95_ms": None, "error_rate": None, "apdex_score": None}

    times.sort()
    p95_idx = min(int(len(times) * 0.95), len(times) - 1)
    p95 = times[p95_idx]
    error_rate = errors / total_requests if total_requests else 0

    # Apdex: T = 500ms; satisfied < T, tolerating < 4T
    T = 500.0
    satisfied = sum(1 for t in times if t < T)
    tolerating = sum(1 for t in times if T <= t < 4 * T)
    total_apdex = len(times)
    apdex = (satisfied + tolerating / 2) / total_apdex if total_apdex else 1.0

    return {
        "p95_ms": round(p95, 1),
        "error_rate": round(error_rate, 4),
        "apdex_score": round(apdex, 3),
    }


# ── HAR parser ─────────────────────────────────────────────────────────────────


def parse_har(har: dict) -> dict:
    """Parse an HTTP Archive (HAR); extract unique request patterns by method+path."""
    log = har.get("log", har) if isinstance(har, dict) else {}
    entries = log.get("entries", [])

    seen: set = set()
    endpoints: list = []

    for entry in entries:
        req = entry.get("request", {})
        method = (req.get("method") or "GET").upper()
        url_str = req.get("url", "")

        try:
            parsed = urllib.parse.urlparse(url_str)
            path = parsed.path or "/"
        except Exception:
            path = "/"

        key = f"{method}:{path}"
        if key in seen:
            continue
        seen.add(key)

        # Extract body from postData
        post_data = req.get("postData", {}) or {}
        body = None
        if post_data:
            text = post_data.get("text", "")
            if text:
                try:
                    body = json.loads(text)
                except Exception:
                    body = text

        segs = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
        group = segs[0] if segs else "root"
        name = re.sub(r"[^a-zA-Z0-9]+", "_", f"{method}_{path}").strip("_") or "endpoint"

        endpoints.append(
            {
                "name": name,
                "group": group,
                "type": "rest",
                "method": method,
                "path": path,
                "weight": 1,
                "body": body,
                "checks": {"status": 200},
            }
        )

    return {"endpoints": endpoints, "setup": [], "teardown": []}


# ── WSDL parser ────────────────────────────────────────────────────────────────

_WSDL_NS = {
    "wsdl": "http://schemas.xmlsoap.org/wsdl/",
    "soap": "http://schemas.xmlsoap.org/wsdl/soap/",
    "soap12": "http://schemas.xmlsoap.org/wsdl/soap12/",
}


def parse_wsdl(wsdl_text: str) -> dict:
    """Parse WSDL XML; extract SOAP operations and generate endpoint stubs."""
    try:
        root = ET.fromstring(wsdl_text)
    except ET.ParseError as e:
        return {"error": str(e), "endpoints": [], "setup": [], "teardown": []}

    # Service name for grouping
    service_name = "soap"
    svc = root.find("wsdl:service", _WSDL_NS)
    if svc is None:
        svc = root.find("service")
    if svc is not None:
        service_name = svc.get("name", "soap")

    # SOAP endpoint path
    soap_path = "/soap"
    for port in (root.findall(".//wsdl:port", _WSDL_NS) or root.findall(".//port")):
        for addr in port:
            loc = addr.get("location", "")
            if loc:
                try:
                    soap_path = urllib.parse.urlparse(loc).path or "/soap"
                except Exception:
                    pass
                break

    # Extract operations from portType
    endpoints: list = []
    for pt in root.findall(".//wsdl:portType", _WSDL_NS) or root.findall(".//portType"):
        for op in pt.findall("wsdl:operation", _WSDL_NS) or pt.findall("operation"):
            op_name = op.get("name", "operation")
            name = re.sub(r"[^a-zA-Z0-9]+", "_", op_name).strip("_") or "operation"
            soap_body = (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                f"<soap:Body><{op_name} xmlns=\"{service_name}\"></{op_name}></soap:Body>"
                "</soap:Envelope>"
            )
            endpoints.append(
                {
                    "name": name,
                    "group": service_name,
                    "type": "rest",
                    "method": "POST",
                    "path": soap_path,
                    "weight": 1,
                    "body": soap_body,
                    "checks": {"status": 200},
                }
            )

    return {"endpoints": endpoints, "setup": [], "teardown": []}


# ── API Blueprint parser ────────────────────────────────────────────────────────

_APIB_RESOURCE_RE = re.compile(
    r"^#{1,2}\s+(?:.*?\s+)?\[([A-Z]+)\s+(/[^\]]+)\]",
    re.MULTILINE,
)
_APIB_ACTION_RE = re.compile(
    r"^###\s+([A-Z]+)\s+(/[^\s\[{]+)",
    re.MULTILINE,
)
_APIB_GROUP_RE = re.compile(r"^#\s+(?:Group\s+)?(.+?)(?:\s+\[|$)", re.MULTILINE)


def parse_api_blueprint(text: str) -> dict:
    """Parse API Blueprint markdown; extract resources and actions as endpoint dicts."""
    endpoints: list = []
    seen: set = set()

    # Collect group names from top-level headings
    groups_by_pos: list = [(m.start(), re.sub(r"[^a-zA-Z0-9 ]", "", m.group(1)).strip().lower().replace(" ", "_") or "api") for m in _APIB_GROUP_RE.finditer(text)]

    def group_for_pos(pos: int) -> str:
        name = "api"
        for start, gname in groups_by_pos:
            if start <= pos:
                name = gname
        return name

    for m in _APIB_RESOURCE_RE.finditer(text):
        method = m.group(1).upper()
        path = m.group(2)
        key = f"{method}:{path}"
        if key in seen:
            continue
        seen.add(key)
        segs = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
        group = segs[0] if segs else group_for_pos(m.start())
        name = re.sub(r"[^a-zA-Z0-9]+", "_", f"{method}_{path}").strip("_") or "endpoint"
        endpoints.append(
            {
                "name": name,
                "group": group,
                "type": "rest",
                "method": method,
                "path": path,
                "weight": 1,
                "body": None,
                "checks": {"status": 200},
            }
        )

    for m in _APIB_ACTION_RE.finditer(text):
        method = m.group(1).upper()
        path = m.group(2)
        key = f"{method}:{path}"
        if key in seen:
            continue
        seen.add(key)
        segs = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
        group = segs[0] if segs else group_for_pos(m.start())
        name = re.sub(r"[^a-zA-Z0-9]+", "_", f"{method}_{path}").strip("_") or "endpoint"
        endpoints.append(
            {
                "name": name,
                "group": group,
                "type": "rest",
                "method": method,
                "path": path,
                "weight": 1,
                "body": None,
                "checks": {"status": 200},
            }
        )

    return {"endpoints": endpoints, "setup": [], "teardown": []}


# ── RAML parser ────────────────────────────────────────────────────────────────

_RAML_HTTP_METHODS = frozenset(["get", "post", "put", "patch", "delete", "head", "options"])


def parse_raml(text: str) -> dict:
    """Parse RAML YAML; walk resources recursively; extract methods and examples."""
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return {"error": "pyyaml not installed", "endpoints": [], "setup": [], "teardown": []}

    try:
        spec = yaml.safe_load(text)
    except Exception as e:
        return {"error": str(e), "endpoints": [], "setup": [], "teardown": []}

    if not isinstance(spec, dict):
        return {"endpoints": [], "setup": [], "teardown": []}

    endpoints: list = []

    def walk(node: dict, parent_path: str = "") -> None:
        for key, value in node.items():
            if not isinstance(key, str) or not key.startswith("/"):
                continue
            path = parent_path + key
            segs = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
            group = segs[0] if segs else "api"
            if isinstance(value, dict):
                for mkey, mval in value.items():
                    if mkey.lower() not in _RAML_HTTP_METHODS:
                        continue
                    method = mkey.upper()
                    name = re.sub(r"[^a-zA-Z0-9]+", "_", f"{method}_{path}").strip("_") or "endpoint"
                    body = None
                    if isinstance(mval, dict):
                        body_spec = mval.get("body", {}) or {}
                        for _ct, ct_val in (body_spec.items() if isinstance(body_spec, dict) else []):
                            if isinstance(ct_val, dict):
                                example = ct_val.get("example")
                                if example:
                                    body = example
                                    break
                    endpoints.append(
                        {
                            "name": name,
                            "group": group,
                            "type": "rest",
                            "method": method,
                            "path": path,
                            "weight": 1,
                            "body": body,
                            "checks": {"status": 200},
                        }
                    )
                walk(value, path)

    walk(spec)
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
