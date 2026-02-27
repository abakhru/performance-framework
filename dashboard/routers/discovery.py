"""API discovery routes: URL introspection, Postman collection parsing."""

from discovery import discover_url as _discover_url
from discovery import load_repo_postman as _load_repo_postman
from discovery import parse_postman as _parse_postman
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
