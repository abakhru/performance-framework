"""DashboardPage — WUIPage equivalent.

Base page object for the Luna / k6 dashboard.  Each feature-specific page
object subclasses this and provides its own locator config module.

Pattern mirrors artemis_web WUIPage exactly:
  - Constructor binds every element name in locator_config.elements as a
    method that returns the live Playwright Locator for that selector.
  - navigate() loads the config's startUrl relative to base_url.
  - wait_for_load() waits for the #app container to be visible.
"""

from __future__ import annotations

import types
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


class DashboardPage:
    """Base page object.  Subclasses pass a locator config module.

    Usage::

        class Navigation(DashboardPage):
            def __init__(self, page, base_url):
                import tests.ui.page_objects.dashboard.locators.navigation_config as cfg
                super().__init__(page, base_url, cfg)

        nav = Navigation(page, "http://127.0.0.1:55656")
        nav.navigate()
        assert nav.tab_execute().is_visible()
    """

    def __init__(self, page: Page, base_url: str, locator_config: types.ModuleType) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/")
        self._config = locator_config

        # Bind every element from the config as a method → Locator
        for name, (strategy, selector) in locator_config.elements.items():
            if strategy == "css":
                setattr(self, name, self._make_css_locator(selector))
            elif strategy == "text":
                setattr(self, name, self._make_text_locator(selector))
            elif strategy == "xpath":
                setattr(self, name, self._make_xpath_locator(selector))
            else:
                # Fallback: treat as CSS
                setattr(self, name, self._make_css_locator(selector))

    # ── Locator factories ─────────────────────────────────────────────────────

    def _make_css_locator(self, selector: str):
        def _loc() -> Locator:
            return self.page.locator(selector)

        return _loc

    def _make_text_locator(self, text: str):
        def _loc() -> Locator:
            return self.page.get_by_text(text)

        return _loc

    def _make_xpath_locator(self, xpath: str):
        def _loc() -> Locator:
            return self.page.locator(f"xpath={xpath}")

        return _loc

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate(self) -> None:
        """Load startUrl relative to base_url and wait for the app to mount."""
        url = f"{self.base_url}{self._config.startUrl}"
        self.page.goto(url, wait_until="domcontentloaded")
        self.wait_for_load()

    def wait_for_load(self, timeout: float = 15_000) -> None:
        """Wait for the #app container to be visible — cheap app-ready gate."""
        self.page.locator("#app").wait_for(state="visible", timeout=timeout)

    # ── Convenience helpers ───────────────────────────────────────────────────

    def click_tab(self, tab_text: str) -> None:
        """Click a sidebar tab by its visible text."""
        self.page.locator(f".tab:has-text('{tab_text}')").click()
        self.page.wait_for_load_state("domcontentloaded")

    def active_tab_text(self) -> str:
        """Return the text content of the currently active sidebar tab."""
        return self.page.locator(".tab.active").inner_text().strip()

    def pane_visible(self, pane_id: str) -> bool:
        """Return True if a pane element (e.g. '#pane-run') is visible."""
        return self.page.locator(pane_id).is_visible()
