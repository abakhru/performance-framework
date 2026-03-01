"""plugins/visual_qa — 31 AI-powered visual QA agent plugin."""

from plugins.base import PluginMeta
from plugins.visual_qa.router import router

plugin = PluginMeta(
    name="visual_qa",
    description="Run 31 AI tester personas against any page via Claude Vision API.",
    router=router,
    tags=["Visual QA"],
    cli_module="plugins.visual_qa.cli",
)
