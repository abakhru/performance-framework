"""SSE live-reload endpoint and background file watcher."""

import asyncio
import threading
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.storage import SCRIPT_DIR

router = APIRouter()

_reload_queues: list[asyncio.Queue] = []
_reload_lock = threading.Lock()


def broadcast_reload() -> None:
    with _reload_lock:
        queues = list(_reload_queues)
    for q in queues:
        try:
            q.put_nowait("reload")
        except Exception:
            pass


def start_file_watcher() -> None:
    threading.Thread(target=_watch_files, daemon=True, name="file-watcher").start()


def _watch_files() -> None:
    watched_exts = (".py", ".html")

    def _scan() -> dict:
        result = {}
        for ext in watched_exts:
            for p in SCRIPT_DIR.glob(f"*{ext}"):
                try:
                    result[str(p)] = p.stat().st_mtime
                except OSError:
                    pass
        return result

    mtimes = _scan()
    while True:
        time.sleep(1)
        current = _scan()
        if current != mtimes:
            mtimes = current
            broadcast_reload()


@router.get("/livereload")
async def livereload():
    q: asyncio.Queue = asyncio.Queue()
    with _reload_lock:
        _reload_queues.append(q)

    async def event_stream():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"event: {msg}\ndata: {{}}\n\n"
                except TimeoutError:
                    yield ": ping\n\n"
        finally:
            with _reload_lock:
                try:
                    _reload_queues.remove(q)
                except ValueError:
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
