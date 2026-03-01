"""
UI regression tests — Discover pane.

Feature: Discovery wizard — bd-ui-discover
Covers:
  - Discover tab navigates to the correct pane
  - Wizard container is visible
  - Wizard shows 6 step indicator pills
  - Step 1 is active by default
  - URL scan source card is selected by default
  - URL input field is present and accepts text
  - Auth token input is present
  - 'Next' button is initially disabled (no URL entered)
  - 'Next' button becomes enabled after typing a URL

Run with:
    just test-ui
    uv run pytest tests/ui/regression/test_discover.py -v -m regression
"""

from __future__ import annotations

import pytest

from tests.ui.base.ui_test_case import UITestCase
from tests.ui.page_objects.dashboard.discover import Discover


class DiscoverPaneRegression(UITestCase):
    """bd-ui-discover: Discovery wizard structure and initial state."""

    def setUp(self) -> None:
        super().setUp()
        self.disc = Discover(page=self.page, base_url=self.base_url)
        self.disc.navigate()

    # ── Pane / wizard structure ───────────────────────────────────────────────

    @pytest.mark.regression
    def test_discover_pane_visible(self) -> None:
        """bd-ui-discover: Discover pane is visible after clicking the tab."""
        self.assertTrue(self.disc.pane().is_visible(), "#pane-discover should be visible")

    @pytest.mark.regression
    def test_wizard_container_visible(self) -> None:
        """bd-ui-discover: Wizard container is visible inside the pane."""
        self.assertTrue(self.disc.wizard_visible(), "#wizContainer should be visible")

    @pytest.mark.regression
    def test_wizard_has_six_steps(self) -> None:
        """bd-ui-discover: Wizard shows exactly 6 step indicator pills."""
        count = self.disc.step_count()
        self.assertEqual(count, 6, f"Expected 6 wizard steps, got {count}")

    @pytest.mark.regression
    def test_step_1_active_by_default(self) -> None:
        """bd-ui-discover: Step 1 (Source) is active on pane open."""
        self.assertTrue(self.disc.step_1_active(), "Wizard step 1 should be active by default")

    # ── Source selection ──────────────────────────────────────────────────────

    @pytest.mark.regression
    def test_url_scan_source_selected_by_default(self) -> None:
        """bd-ui-discover: URL Scan source card is selected by default."""
        self.assertTrue(self.disc.src_url_selected(), "URL scan source card should be selected by default")

    @pytest.mark.regression
    def test_url_input_visible(self) -> None:
        """bd-ui-discover: URL input field is visible in step 1."""
        self.assertVisible(self.disc.url_input())

    @pytest.mark.regression
    def test_token_input_visible(self) -> None:
        """bd-ui-discover: Auth token input field is visible in step 1."""
        self.assertVisible(self.disc.token_input())

    # ── Next button state ─────────────────────────────────────────────────────

    @pytest.mark.regression
    def test_next_button_disabled_initially(self) -> None:
        """bd-ui-discover: 'Next →' button is disabled before a URL is entered."""
        self.assertFalse(
            self.disc.next_btn_enabled(),
            "Next button should be disabled when no URL is entered",
        )

    @pytest.mark.regression
    def test_next_button_enabled_after_url_entry(self) -> None:
        """bd-ui-discover: 'Next →' button becomes enabled after typing a valid URL."""
        self.disc.fill_url("https://api.example.com")
        # Trigger any input event the JS may be listening to
        self.disc.url_input().dispatch_event("input")
        # Small wait for the JS to react
        self.page.wait_for_timeout(300)
        self.assertTrue(
            self.disc.next_btn_enabled(),
            "Next button should be enabled after entering a URL",
        )

    @pytest.mark.regression
    def test_url_input_accepts_text(self) -> None:
        """bd-ui-discover: URL input field correctly stores typed text."""
        test_url = "https://test.example.com"
        self.disc.fill_url(test_url)
        self.assertEqual(self.disc.url_value(), test_url)
