"""Navigation page object — sidebar tabs.

Provides methods for:
  - navigating to a specific tab
  - reading the active tab name
  - asserting all expected tabs are visible
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.ui.base.page import DashboardPage
from tests.ui.page_objects.dashboard.locators import navigation_config

if TYPE_CHECKING:
    from playwright.sync_api import Page

ALL_TABS = [
    "Execute",
    "Overview",
    "Endpoints",
    "HTTP Metrics",
    "Log",
    "History",
    "Discover",
    "Lighthouse",
]


class Navigation(DashboardPage):
    """Sidebar navigation page object.

    Feature: Sidebar tab navigation — bd-ui-nav
    Covers: all tabs visible, tabs clickable, active state updates correctly.
    """

    def __init__(self, page: Page, base_url: str) -> None:
        super().__init__(page, base_url, navigation_config)

    # ── Actions ───────────────────────────────────────────────────────────────

    def navigate_to_tab(self, tab_text: str) -> None:
        """Click the sidebar tab with the given label and wait for pane update."""
        self.page.locator(f".tab:has-text('{tab_text}')").click()
        self.page.wait_for_load_state("domcontentloaded")

    # ── Queries ───────────────────────────────────────────────────────────────

    def active_tab(self) -> str:
        """Return the text of the currently active tab."""
        return self.active_tab_text()

    def tabs_visible(self) -> list[str]:
        """Return text of every visible sidebar tab."""
        tabs = self.page.locator(".tab").all()
        return [t.inner_text().strip() for t in tabs if t.is_visible()]

    def is_tab_active(self, tab_text: str) -> bool:
        """Return True if the given tab currently has the 'active' class."""
        loc = self.page.locator(f".tab:has-text('{tab_text}')")
        cls = loc.get_attribute("class") or ""
        return "active" in cls

    def all_tabs_present(self) -> bool:
        """Return True if all 8 expected tabs are visible."""
        visible = self.tabs_visible()
        return all(any(tab in v for v in visible) for tab in ALL_TABS)

    def status_dot_class(self) -> str:
        """Return the CSS classes of the status dot (idle/running/waiting)."""
        return self.status_dot().get_attribute("class") or ""

    def status_label_text(self) -> str:
        """Return the current status label text (CONNECTING / IDLE / RUNNING…)."""
        return self.status_label().inner_text().strip()
