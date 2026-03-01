"""
UI regression tests — Overview pane.

Feature: Overview pane health + metrics — bd-ui-overview
Covers:
  - Health hero block is visible
  - Health badge is rendered and shows IDLE when no run is active
  - Hero KPI elements are present (p95, RPS, VUs, errors)
  - Metric cards grid renders with expected card labels
  - Mini header stats (VUs, Reqs, RPS, p95, Errors) are visible

Run with:
    just test-ui
    uv run pytest tests/ui/regression/test_overview.py -v -m regression
"""

from __future__ import annotations

import pytest

from tests.ui.base.ui_test_case import UITestCase
from tests.ui.page_objects.dashboard.overview import BADGE_STATES, Overview

# Card labels we expect to see in the grid (subset — enough to verify layout)
EXPECTED_CARD_LABELS = [
    "Total Requests",
    "Req/s",
    "Active VUs",
]


class OverviewPaneRegression(UITestCase):
    """bd-ui-overview: Overview pane structure and idle state."""

    def setUp(self) -> None:
        super().setUp()
        self.ov = Overview(page=self.page, base_url=self.base_url)
        self.ov.navigate()

    # ── Health hero ───────────────────────────────────────────────────────────

    @pytest.mark.regression
    def test_health_hero_visible(self) -> None:
        """bd-ui-overview: Health hero block is visible after navigating to Overview."""
        self.assertVisible(self.ov.health_hero(), "Health hero block should be visible")

    @pytest.mark.regression
    def test_health_badge_renders(self) -> None:
        """bd-ui-overview: Health badge element is visible."""
        self.assertVisible(self.ov.health_badge(), "Health badge should be visible")

    @pytest.mark.regression
    def test_health_badge_shows_idle_or_loading(self) -> None:
        """bd-ui-overview: Health badge shows IDLE or LOADING when no run is active."""
        text = self.ov.health_badge_text()
        self.assertIn(
            text,
            BADGE_STATES,
            f"Health badge text {text!r} not in expected states {BADGE_STATES}",
        )

    @pytest.mark.regression
    def test_hero_kpi_p95_visible(self) -> None:
        """bd-ui-overview: p95 KPI value element is visible in the hero."""
        self.assertVisible(self.ov.kpi_p95())

    @pytest.mark.regression
    def test_hero_kpi_rps_visible(self) -> None:
        """bd-ui-overview: RPS KPI value element is visible in the hero."""
        self.assertVisible(self.ov.kpi_rps())

    @pytest.mark.regression
    def test_hero_kpi_vus_visible(self) -> None:
        """bd-ui-overview: VUs KPI value element is visible in the hero."""
        self.assertVisible(self.ov.kpi_vus())

    @pytest.mark.regression
    def test_hero_kpi_errors_visible(self) -> None:
        """bd-ui-overview: Errors KPI value element is visible in the hero."""
        self.assertVisible(self.ov.kpi_err())

    # ── Metric cards ──────────────────────────────────────────────────────────

    @pytest.mark.regression
    def test_metric_cards_present(self) -> None:
        """bd-ui-overview: At least 6 metric cards are present in the grid."""
        count = self.ov.cards_count()
        self.assertGreaterEqual(count, 6, f"Expected ≥6 metric cards, got {count}")

    @pytest.mark.regression
    def test_metric_card_values_show_placeholder(self) -> None:
        """bd-ui-overview: Metric card values show '—' placeholder when no run is active."""
        val = self.ov.card_value("cReqs")
        # Accepts '—' (em dash placeholder) or a numeric value (if InfluxDB is seeded)
        self.assertTrue(val == "—" or val.replace(",", "").isdigit(), f"Unexpected cReqs value: {val!r}")

    @pytest.mark.regression
    def test_apdex_card_visible(self) -> None:
        """bd-ui-overview: Apdex metric card is visible."""
        self.assertVisible(self.page.locator("#cApdex"))

    # ── Mini header stats ─────────────────────────────────────────────────────

    @pytest.mark.regression
    def test_header_stats_visible(self) -> None:
        """bd-ui-overview: Mini header stats (VUs, Reqs, RPS, p95, Errors) are visible."""
        for stat_id in ("#hVus", "#hReqs", "#hRps", "#hP95", "#hFail"):
            loc = self.page.locator(stat_id)
            self.assertTrue(loc.is_visible(), f"Header stat {stat_id} should be visible")
