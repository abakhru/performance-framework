"""plugins/discovery — API endpoint auto-discovery plugin."""

from plugins.base import PluginMeta
from plugins.discovery.router import router

plugin = PluginMeta(
    name="discovery",
    description="Auto-discover API endpoints from URLs, Postman, HAR, WSDL, and more.",
    router=router,
    tags=["Discovery"],
)
