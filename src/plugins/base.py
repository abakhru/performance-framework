"""
plugins/base.py — Plugin base class and metadata.

Every plugin module must expose a top-level ``plugin`` object that is an
instance of :class:`PluginMeta`.  The plugin registry in
``plugins/__init__.py`` auto-discovers these via ``pkgutil``.

Minimal plugin example::

    # src/plugins/my_feature/__init__.py
    from fastapi import APIRouter
    from plugins.base import PluginMeta

    router = APIRouter(prefix="/my-feature", tags=["My Feature"])

    @router.get("/ping")
    async def ping():
        return {"ok": True}

    plugin = PluginMeta(
        name="my_feature",
        description="Does something useful.",
        router=router,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter


@dataclass
class PluginMeta:
    """Metadata + FastAPI router for a single plugin."""

    name: str
    """Unique snake_case identifier (e.g. ``"performance"``)."""

    description: str
    """One-line human-readable description shown in logs / docs."""

    router: APIRouter | None = None
    """FastAPI router to mount on the main app.  ``None`` for CLI-only plugins."""

    tags: list[str] = field(default_factory=list)
    """OpenAPI tag names for this plugin's routes."""

    version: str = "1.0.0"
    """Semver string — informational only."""

    cli_module: str | None = None
    """Dotted module path of a Click/Typer CLI entry-point, if any."""

    def __repr__(self) -> str:
        has_router = self.router is not None
        return (
            f"PluginMeta(name={self.name!r}, version={self.version!r}, "
            f"router={'yes' if has_router else 'no'})"
        )
