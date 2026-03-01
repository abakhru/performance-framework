"""Webhook registration, testing, and deletion routes."""

import threading
import uuid

from fastapi import APIRouter, HTTPException

from core.influx import now as _now
from core.storage import load_webhooks, save_webhooks
from plugins.performance.runner import _send_webhook

router = APIRouter(prefix="/webhooks")


@router.get("")
async def list_webhooks():
    return load_webhooks()


@router.post("")
async def create_webhook(body: dict):
    new_hook = {**body, "id": str(uuid.uuid4())}
    hooks = load_webhooks()
    hooks.append(new_hook)
    save_webhooks(hooks)
    return new_hook


@router.post("/{hook_id}/test")
async def test_webhook(hook_id: str):
    hook = next((h for h in load_webhooks() if h.get("id") == hook_id), None)
    if hook is None:
        raise HTTPException(404)
    payload = {
        "event": "test",
        "run_id": str(uuid.uuid4()),
        "message": "This is a test webhook payload",
        "timestamp": _now(),
    }
    threading.Thread(target=_send_webhook, args=(hook, payload), daemon=True).start()
    return {"ok": True, "message": "Test webhook fired"}


@router.delete("/{hook_id}")
async def delete_webhook(hook_id: str):
    hooks = load_webhooks()
    new_hooks = [h for h in hooks if h.get("id") != hook_id]
    if len(new_hooks) == len(hooks):
        raise HTTPException(404)
    save_webhooks(new_hooks)
    return {"ok": True}
