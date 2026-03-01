"""plugins/test_generator — Auto-generate and execute multi-type test suites."""

from plugins.base import PluginMeta

# The router lives inside discovery (generate/execute routes are under /discover)
# but codegen logic is here; discovery plugin's router imports from this package.
plugin = PluginMeta(
    name="test_generator",
    description="Generate API, UI, k6 performance, and Lighthouse test suites from discovered endpoints.",
    tags=["Test Generator"],
)
