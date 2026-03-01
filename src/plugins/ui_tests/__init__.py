"""plugins/ui_tests — Playwright-based UI test execution plugin."""

from plugins.base import PluginMeta
from plugins.ui_tests.router import router

plugin = PluginMeta(
    name="ui_tests",
    description="Execute Playwright UI tests and stream results to the dashboard.",
    router=router,
    tags=["UI Tests"],
)
