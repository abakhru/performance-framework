"""API discovery routes: URL introspection, Postman, HAR, WSDL, API Blueprint, RAML.

Also exposes test-suite generation + execution routes:
    POST /discover/generate        — generate test artefacts from endpoint config
    POST /discover/execute         — run selected suites against a generated dir
    GET  /discover/generated       — list all generated test dirs
    GET  /discover/generated/{dir} — full detail for one generated dir
"""

from __future__ import annotations

import asyncio

from discovery import baseline_slo_probe as _baseline_slo_probe
from discovery import crawl_url as _crawl_url
from discovery import discover_url as _discover_url
from discovery import load_repo_postman as _load_repo_postman
from discovery import parse_api_blueprint as _parse_api_blueprint
from discovery import parse_har as _parse_har
from discovery import parse_postman as _parse_postman
from discovery import parse_raml as _parse_raml
from discovery import parse_wsdl as _parse_wsdl
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/discover")


@router.get("/postman-collection")
async def discover_postman_collection():
    return _load_repo_postman()


@router.get("/url")
async def discover_url(url: str = "", token: str = ""):
    return _discover_url(url.rstrip("/"), token)


@router.post("/postman")
async def parse_postman(body: dict):
    return _parse_postman(body.get("collection", body))


@router.post("/har")
async def parse_har(body: dict):
    return _parse_har(body.get("har", body))


@router.post("/wsdl")
async def parse_wsdl(body: dict):
    return _parse_wsdl(body.get("wsdl", ""))


@router.post("/api-blueprint")
async def parse_api_blueprint(body: dict):
    return _parse_api_blueprint(body.get("blueprint", ""))


@router.post("/raml")
async def parse_raml(body: dict):
    return _parse_raml(body.get("raml", ""))


@router.get("/crawl")
async def crawl(url: str = "", token: str = "", max_pages: int = 30):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return _crawl_url(url.rstrip("/"), headers, max_pages=max_pages)


@router.get("/slos")
async def discover_slos(url: str = "", token: str = ""):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    result = _discover_url(url.rstrip("/"), token)
    eps = result.get("endpoints", [])
    return _baseline_slo_probe(url.rstrip("/"), eps, headers)


# ── Test-suite generation + execution ─────────────────────────────────────────


@router.post("/generate")
async def generate_tests(body: dict):
    """
    Generate test artefacts from a discovered endpoint config.

    Body:
        config      (dict)       — endpoint config (from discover_url or endpoints.json)
        base_url    (str)        — override base URL
        suites      (list[str])  — which artefacts: ["api","ui","perf","lighthouse"]
                                   defaults to all four
    Returns:
        {dir_name, base_url, endpoints_count, suites_generated, files, created_at}
    """
    from dataclasses import asdict

    from test_codegen import generate_suite

    config = body.get("config") or {}
    base_url = (body.get("base_url") or config.get("base_url") or "").strip()
    suites = body.get("suites") or ["api", "ui", "perf", "lighthouse"]

    if not config and not base_url:
        raise HTTPException(400, "config or base_url required")

    loop = asyncio.get_running_loop()
    suite = await loop.run_in_executor(None, lambda: generate_suite(config, base_url, suites))
    return asdict(suite)


@router.post("/execute")
async def execute_tests(body: dict):
    """
    Execute one or more test suites for a previously generated directory.

    Body:
        dir_name    (str)        — generated directory name
        suites      (list[str])  — suites to run: ["api","ui","perf","lighthouse"]
        base_url    (str)        — override BASE_URL
        token       (str)        — Bearer token

    Returns:
        {dir_name, results: {suite: SuiteResult}, overall_passed}
    """
    from dataclasses import asdict

    from test_codegen import run_suite

    dir_name = (body.get("dir_name") or "").strip()
    if not dir_name:
        raise HTTPException(400, "dir_name required")

    suites = body.get("suites") or ["api", "ui", "perf", "lighthouse"]
    base_url = (body.get("base_url") or "").strip()
    token = (body.get("token") or "").strip()

    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, lambda: run_suite(dir_name, suites, base_url, token))

    return {
        "dir_name": dir_name,
        "results": {k: asdict(v) for k, v in results.items()},
        "overall_passed": all(v.status == "passed" for v in results.values()),
    }


@router.get("/generated")
async def list_generated_suites(limit: int = 20):
    """List all generated test suite directories, newest first."""
    from test_codegen import list_generated

    return list_generated(limit=limit)


@router.get("/generated/{dir_name}")
async def get_generated_suite(dir_name: str):
    """Full metadata + file list + results for a specific generated suite."""
    from test_codegen import get_generated

    data = get_generated(dir_name)
    if data is None:
        raise HTTPException(404, f"Generated suite {dir_name!r} not found")
    return data
