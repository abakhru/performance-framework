"""k6 REST API proxy."""

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

K6_API_BASE = "http://127.0.0.1:6565"

router = APIRouter()


@router.api_route("/k6/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_k6(path: str, request: Request):
    url = f"{K6_API_BASE}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.request(
                method=request.method,
                url=url,
                content=await request.body(),
                headers={"Content-Type": request.headers.get("Content-Type", "application/json")},
            )
        return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
    except httpx.RequestError:
        return JSONResponse({"error": "k6 api unavailable"}, status_code=503)
