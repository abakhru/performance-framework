"""Environment profile CRUD routes."""

from fastapi import APIRouter, HTTPException

from core.storage import load_profiles, save_profiles

router = APIRouter(prefix="/profiles")


@router.get("")
async def list_profiles():
    return load_profiles()


@router.post("")
async def create_profile(body: dict):
    name = body.get("name", "")
    if not name:
        raise HTTPException(400, "name required")
    profiles = load_profiles()
    profiles[name] = body
    save_profiles(profiles)
    return body


@router.post("/{name}/activate")
async def activate_profile(name: str):
    profile = load_profiles().get(name)
    if profile is None:
        raise HTTPException(404)
    return {"ok": True, "profile": profile}


@router.put("/{name}")
async def update_profile(name: str, body: dict):
    profiles = load_profiles()
    profiles[name] = {**body, "name": name}
    save_profiles(profiles)
    return profiles[name]


@router.delete("/{name}")
async def delete_profile(name: str):
    profiles = load_profiles()
    if name not in profiles:
        raise HTTPException(404)
    del profiles[name]
    save_profiles(profiles)
    return {"ok": True}
