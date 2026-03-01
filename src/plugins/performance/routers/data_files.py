"""CSV data file upload, listing, and deletion routes."""

import csv
import re

from fastapi import APIRouter, HTTPException, Response

from core.storage import DATA_DIR

router = APIRouter(prefix="/data")


@router.get("")
async def list_data():
    files = []
    if DATA_DIR.is_dir():
        for f in sorted(DATA_DIR.glob("*.csv")):
            try:
                with f.open() as fh:
                    reader = csv.reader(fh)
                    headers = next(reader, [])
                    row_count = sum(1 for _ in reader)
                files.append({"name": f.stem, "filename": f.name, "columns": headers, "row_count": row_count})
            except Exception:
                files.append({"name": f.stem, "filename": f.name})
    return {"files": files}


@router.post("/upload")
async def upload_data(body: dict):
    name = re.sub(r"[^a-zA-Z0-9_\-]", "_", body.get("name", "data"))
    content = body.get("content", "")
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / f"{name}.csv").write_text(content, encoding="utf-8")
    return {"ok": True, "name": name}


@router.delete("/{name}")
async def delete_data(name: str):
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
    f = DATA_DIR / f"{safe}.csv"
    if not f.exists():
        raise HTTPException(404)
    f.unlink()
    return Response(content=b'{"ok":true}', media_type="application/json")
