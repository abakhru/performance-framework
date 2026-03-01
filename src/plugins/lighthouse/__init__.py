"""plugins/lighthouse — Google Lighthouse web audit plugin."""

from plugins.base import PluginMeta
from plugins.lighthouse.router import router

plugin = PluginMeta(
    name="lighthouse",
    description="Run Lighthouse audits against URLs; store and compare results.",
    router=router,
    tags=["Lighthouse"],
)
