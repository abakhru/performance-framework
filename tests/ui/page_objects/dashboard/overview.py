"""Overview page object — health hero and metric cards.

Provides methods for:
  - reading the health badge status
  - reading hero KPI values (p95, RPS, VUs, errors)
  - enumerating metric card names and values
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.ui.base.page import DashboardPage
from tests.ui.page_objects.dashboard.locators import overview_config

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Badge text values we expect to see
BADGE_STATES = {"IDLE", "NOMINAL", "DEGRADED", "CRITICAL", "LOADING"}


class Overview(DashboardPage):
    """Overview pane page object.

    Feature: Overview pane — bd-ui-overview
    Covers: health badge idle state, metric cards rendered, KPI values visible.
    """

    def __init__(self, page: Page, base_url: str) -> None:
        super().__init__(page, base_url, overview_config)

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate(self) -> None:
        """Load the page and switch to the Overview tab."""
        super().navigate()
        self.click_tab("Overview")

    # ── Health hero ───────────────────────────────────────────────────────────

    def health_badge_text(self) -> str:
        """Return the text shown inside the health badge (e.g. 'IDLE')."""
        return self.health_badge().inner_text().strip().upper()

    def health_badge_class(self) -> str:
        """Return the CSS class string of the health badge."""
        return self.health_badge().get_attribute("class") or ""

    def health_badge_state(self) -> str:
        """Return the semantic state: nominal | degraded | critical | idle."""
        cls = self.health_badge_class()
        for state in ("nominal", "degraded", "critical", "loading"):
            if state in cls:
                return state
        return "idle"

    def kpi_values(self) -> dict[str, str]:
        """Return a dict of {name: text} for the four hero KPIs."""
        return {
            "p95":    self.kpi_p95().inner_text().strip(),
            "rps":    self.kpi_rps().inner_text().strip(),
            "vus":    self.kpi_vus().inner_text().strip(),
            "errors": self.kpi_err().inner_text().strip(),
        }

    # ── Metric cards ──────────────────────────────────────────────────────────

    def card_labels(self) -> list[str]:
        """Return the text of every metric card label in the grid."""
        return [el.inner_text().strip() for el in self.all_card_labels().all()]

    def card_value(self, card_id: str) -> str:
        """Return the value text of a card by element ID (e.g. 'cReqs')."""
        return self.page.locator(f"#{card_id}").inner_text().strip()

    def cards_count(self) -> int:
        """Return the total number of visible metric cards."""
        return self.all_cards().count()
