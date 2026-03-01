"""Endpoints page object — operation metrics table.

Provides methods for:
  - reading endpoint/operation count from the table body
  - reading group filter buttons
  - clicking a group filter
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.ui.base.page import DashboardPage
from tests.ui.page_objects.dashboard.locators import endpoints_config

if TYPE_CHECKING:
    from playwright.sync_api import Page


class Endpoints(DashboardPage):
    """Endpoints pane page object.

    Feature: Endpoints pane — bd-ui-endpoints
    Covers: table renders, group filter buttons, waiting state shown idle.
    """

    def __init__(self, page: Page, base_url: str) -> None:
        super().__init__(page, base_url, endpoints_config)

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate(self) -> None:
        """Load the page and navigate to the Endpoints tab."""
        super().navigate()
        self.click_tab("Endpoints")

    # ── Table ─────────────────────────────────────────────────────────────────

    def row_count(self) -> int:
        """Return number of data rows in the operations tbody."""
        return self.ops_rows().count()

    def is_waiting(self) -> bool:
        """Return True if the table shows the 'Waiting for k6…' placeholder."""
        wc = self.waiting_cell()
        if wc.count() == 0:
            return False
        return wc.is_visible()

    def column_headers(self) -> list[str]:
        """Return text of all thead column headers."""
        return [h.inner_text().strip() for h in self.page.locator("#pane-endpoints thead th").all()]

    # ── Group filter ──────────────────────────────────────────────────────────

    def filter_groups(self) -> list[str]:
        """Return text of all group filter buttons."""
        return [b.inner_text().strip() for b in self.all_filter_btns().all()]

    def active_filter(self) -> str:
        """Return the text of the currently active group filter."""
        btn = self.page.locator("#groupFilter .filter-btn.active")
        return btn.inner_text().strip() if btn.count() > 0 else ""

    def click_filter(self, group: str) -> None:
        """Click a group filter button by its text."""
        self.page.locator(f"#groupFilter .filter-btn:has-text('{group}')").click()

    def table_visible(self) -> bool:
        """Return True if the operations table is visible."""
        return self.ops_table().is_visible()
