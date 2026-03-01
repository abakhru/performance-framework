"""
UI regression tests — Endpoints pane.

Feature: Endpoints pane operation metrics table — bd-ui-endpoints
Covers:
  - Endpoints tab navigates to the correct pane
  - Operations table is visible
  - Table has expected column headers
  - Group filter bar is visible with at least an 'All' button
  - 'All' filter is active by default
  - Waiting placeholder shown when no k6 run has produced data

Run with:
    just test-ui
    uv run pytest tests/ui/regression/test_endpoints.py -v -m regression
"""

from __future__ import annotations

import pytest

from tests.ui.base.ui_test_case import UITestCase
from tests.ui.page_objects.dashboard.endpoints import Endpoints

EXPECTED_COLUMNS = ["Operation", "Reqs", "Errors", "Err%", "Avg ms", "p95"]


class EndpointsPaneRegression(UITestCase):
    """bd-ui-endpoints: Endpoints pane structure in idle state."""

    def setUp(self) -> None:
        super().setUp()
        self.ep = Endpoints(page=self.page, base_url=self.base_url)
        self.ep.navigate()

    # ── Pane structure ────────────────────────────────────────────────────────

    @pytest.mark.regression
    def test_endpoints_pane_visible(self) -> None:
        """bd-ui-endpoints: Endpoints pane is visible after clicking the tab."""
        self.assertTrue(self.ep.pane().is_visible(), "#pane-endpoints should be visible")

    @pytest.mark.regression
    def test_operations_table_visible(self) -> None:
        """bd-ui-endpoints: Operations table is visible inside the pane."""
        self.assertTrue(self.ep.table_visible(), "Operations table should be visible")

    # ── Column headers ────────────────────────────────────────────────────────

    @pytest.mark.regression
    def test_column_headers_present(self) -> None:
        """bd-ui-endpoints: All expected column headers are in the table."""
        headers = self.ep.column_headers()
        for col in EXPECTED_COLUMNS:
            self.assertTrue(
                any(col in h for h in headers),
                f"Column '{col}' not found in headers: {headers}",
            )

    # ── Group filter ──────────────────────────────────────────────────────────

    @pytest.mark.regression
    def test_group_filter_bar_visible(self) -> None:
        """bd-ui-endpoints: Group filter bar is visible."""
        self.assertVisible(self.ep.group_filter())

    @pytest.mark.regression
    def test_all_filter_button_present(self) -> None:
        """bd-ui-endpoints: 'All' filter button is present."""
        self.assertVisible(self.ep.filter_all_btn())

    @pytest.mark.regression
    def test_all_filter_active_by_default(self) -> None:
        """bd-ui-endpoints: 'All' group filter is active when the pane first opens."""
        active = self.ep.active_filter()
        self.assertIn("All", active, f"Expected 'All' to be active filter, got: {active!r}")

    # ── Idle / waiting state ──────────────────────────────────────────────────

    @pytest.mark.regression
    def test_waiting_placeholder_shown_when_no_data(self) -> None:
        """bd-ui-endpoints: 'Waiting for k6…' placeholder shown when no run has data."""
        # This will be True for a fresh server with no InfluxDB data.
        # If data exists from a previous run the table will have real rows instead.
        is_waiting = self.ep.is_waiting()
        row_count = self.ep.row_count()
        # Either waiting placeholder is shown OR there are real rows — never neither
        self.assertTrue(
            is_waiting or row_count > 0,
            "Expected either a waiting placeholder or data rows in the operations table",
        )

    @pytest.mark.regression
    def test_ops_body_exists(self) -> None:
        """bd-ui-endpoints: The tbody#opsBody element is present in the DOM."""
        self.assertEqual(self.ep.ops_body().count(), 1, "Expected exactly one #opsBody element")
