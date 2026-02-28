"""API discovery routes: URL introspection, Postman, HAR, WSDL, API Blueprint, RAML."""

from discovery import baseline_slo_probe as _baseline_slo_probe
from discovery import crawl_url as _crawl_url
from discovery import discover_url as _discover_url
from discovery import load_repo_postman as _load_repo_postman
from discovery import parse_api_blueprint as _parse_api_blueprint
from discovery import parse_har as _parse_har
from discovery import parse_postman as _parse_postman
from discovery import parse_raml as _parse_raml
from discovery import parse_wsdl as _parse_wsdl
from fastapi import APIRouter

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
