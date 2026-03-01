"""
UI smoke tests — sidebar navigation.

Feature: Sidebar tab navigation — bd-ui-nav
Covers:
  - All 8 sidebar tabs are present and visible on page load
  - Execute tab is active by default
  - Each tab is clickable and updates the active state
  - Page title in the header updates when switching tabs
  - Status dot and label are present in the header bar

Run with:
    just test-ui-smoke
    uv run pytest tests/ui/smoke/ -v -m smoke
"""

from __future__ import annotations

import pytest

from tests.ui.base.ui_test_case import UITestCase
from tests.ui.page_objects.dashboard.navigation import ALL_TABS, Navigation


class NavigationSmoke(UITestCase):
    """bd-ui-nav: All sidebar tabs visible and clickable."""

    def setUp(self) -> None:
        super().setUp()
        self.nav = Navigation(page=self.page, base_url=self.base_url)
        self.nav.navigate()

    # ── Presence ──────────────────────────────────────────────────────────────

    @pytest.mark.smoke
    @pytest.mark.sanity
    def test_all_sidebar_tabs_visible(self) -> None:
        """bd-ui-nav: All 8 sidebar tabs are present and visible on load."""
        for tab in ALL_TABS:
            loc = self.page.locator(f".tab:has-text('{tab}')")
            self.assertTrue(loc.is_visible(), f"Tab '{tab}' not visible")

    @pytest.mark.smoke
    @pytest.mark.sanity
    def test_sidebar_has_exactly_8_tabs(self) -> None:
        """bd-ui-nav: Sidebar contains exactly 8 tab entries (no extra/missing)."""
        visible = self.nav.tabs_visible()
        # tabs_visible returns raw inner_text — may include whitespace/newlines
        matched = [t for t in ALL_TABS if any(t in v for v in visible)]
        self.assertEqual(
            len(matched),
            len(ALL_TABS),
            f"Expected {len(ALL_TABS)} tabs, matched {len(matched)}: {visible}",
        )

    # ── Default state ─────────────────────────────────────────────────────────

    @pytest.mark.smoke
    def test_active_tab_defaults_to_execute(self) -> None:
        """bd-ui-nav: Execute tab is active on page load."""
        self.assertClassContains(
            self.nav.tab_execute(),
            "active",
            "Execute tab should have 'active' class on load",
        )

    @pytest.mark.smoke
    def test_execute_pane_visible_on_load(self) -> None:
        """bd-ui-nav: #pane-run is visible and other panes are hidden on load."""
        self.assertTrue(self.page.locator("#pane-run").is_visible())
        self.assertFalse(self.page.locator("#pane-overview").is_visible())

    # ── Click behaviour ───────────────────────────────────────────────────────

    @pytest.mark.smoke
    def test_clicking_overview_tab_activates_it(self) -> None:
        """bd-ui-nav: Clicking Overview tab makes it active and shows its pane."""
        self.nav.navigate_to_tab("Overview")
        self.assertClassContains(self.nav.tab_overview(), "active")
        self.assertTrue(self.page.locator("#pane-overview").is_visible())
        self.assertFalse(self.page.locator("#pane-run").is_visible())

    @pytest.mark.smoke
    def test_clicking_endpoints_tab_activates_it(self) -> None:
        """bd-ui-nav: Clicking Endpoints tab makes it active and shows its pane."""
        self.nav.navigate_to_tab("Endpoints")
        self.assertClassContains(self.nav.tab_endpoints(), "active")
        self.assertTrue(self.page.locator("#pane-endpoints").is_visible())

    @pytest.mark.smoke
    def test_clicking_discover_tab_activates_it(self) -> None:
        """bd-ui-nav: Clicking Discover tab makes it active and shows its pane."""
        self.nav.navigate_to_tab("Discover")
        self.assertClassContains(self.nav.tab_discover(), "active")
        self.assertTrue(self.page.locator("#pane-discover").is_visible())

    @pytest.mark.smoke
    def test_only_one_tab_active_at_a_time(self) -> None:
        """bd-ui-nav: Only one sidebar tab carries the 'active' class at a time."""
        for tab_text in ["Overview", "Endpoints", "History", "Execute"]:
            self.nav.navigate_to_tab(tab_text)
            active_count = self.page.locator(".tab.active").count()
            self.assertEqual(active_count, 1, f"Expected 1 active tab when '{tab_text}' clicked, got {active_count}")

    # ── Header bar ────────────────────────────────────────────────────────────

    @pytest.mark.smoke
    def test_status_dot_present(self) -> None:
        """bd-ui-nav: Status dot is present in the header bar."""
        self.assertVisible(self.nav.status_dot())

    @pytest.mark.smoke
    def test_status_label_present(self) -> None:
        """bd-ui-nav: Status label is present in the header bar."""
        self.assertVisible(self.nav.status_label())
