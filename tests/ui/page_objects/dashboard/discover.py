"""Discover page object — endpoint discovery wizard.

Provides methods for:
  - typing a URL into the discovery input
  - submitting the discovery (clicking Next)
  - reading discovered endpoint count
  - checking wizard step visibility
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.ui.base.page import DashboardPage
from tests.ui.page_objects.dashboard.locators import discover_config

if TYPE_CHECKING:
    from playwright.sync_api import Page


class Discover(DashboardPage):
    """Discover pane page object.

    Feature: Discovery wizard — bd-ui-discover
    Covers: wizard renders, URL input works, step indicator visible.
    """

    def __init__(self, page: Page, base_url: str) -> None:
        super().__init__(page, base_url, discover_config)

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate(self) -> None:
        """Load the page and navigate to the Discover tab."""
        super().navigate()
        self.click_tab("Discover")

    # ── URL input ─────────────────────────────────────────────────────────────

    def discover_url_input(self):
        """Return the Locator for the URL input field."""
        return self.url_input()

    def fill_url(self, url: str) -> None:
        """Type a URL into the discovery input."""
        self.url_input().fill(url)

    def url_value(self) -> str:
        """Return the current value of the URL input."""
        return self.url_input().input_value()

    def submit(self) -> None:
        """Click the 'Next →' button to start discovery."""
        self.next_btn().click()

    def next_btn_enabled(self) -> bool:
        """Return True if the Next button is enabled (URL entered)."""
        return not self.next_btn().is_disabled()

    # ── Wizard state ──────────────────────────────────────────────────────────

    def wizard_visible(self) -> bool:
        """Return True if the wizard container is visible."""
        return self.wiz_container().is_visible()

    def step_count(self) -> int:
        """Return the number of wizard step indicator pills."""
        return self.all_wiz_steps().count()

    def step_1_active(self) -> bool:
        """Return True if wizard step 1 is active (contains 'active' class)."""
        cls = self.wiz_step_1().get_attribute("class") or ""
        return "active" in cls

    def src_url_selected(self) -> bool:
        """Return True if the URL scan source card is selected."""
        cls = self.src_url_card().get_attribute("class") or ""
        return "selected" in cls

    # ── Results ───────────────────────────────────────────────────────────────

    def result_count_text(self) -> str:
        """Return the disc-count text after discovery (e.g. '12 endpoints')."""
        count_el = self.disc_count()
        if count_el.count() == 0:
            return ""
        return count_el.inner_text().strip()
