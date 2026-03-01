"""Execute page object — run controls.

Provides methods for:
  - selecting a load profile
  - starting and stopping a run
  - reading the run status banner
  - reading/setting the target URL
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.ui.base.page import DashboardPage
from tests.ui.page_objects.dashboard.locators import execute_config

if TYPE_CHECKING:
    from playwright.sync_api import Page

PROFILES = ("smoke", "ramp", "soak", "stress", "spike")


class Execute(DashboardPage):
    """Execute (run control) pane page object.

    Feature: Run control — bd-ui-execute
    Covers: profile picker renders, start/stop buttons visible, status banner.
    """

    def __init__(self, page: Page, base_url: str) -> None:
        super().__init__(page, base_url, execute_config)

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate(self) -> None:
        """Load the page — Execute is the default active tab."""
        super().navigate()
        # Execute is already active on load; click it to be explicit
        self.click_tab("Execute")

    # ── Profile picker ────────────────────────────────────────────────────────

    def select_profile(self, profile: str) -> None:
        """Click the profile button for the given profile name."""
        self.page.locator(f"#profileBtn{profile.capitalize()}").click()

    def active_profile_text(self) -> str:
        """Return the text of the currently active profile button."""
        return self.active_profile().inner_text().strip().split("\n")[0].strip()

    def profile_selector(self, profile: str):
        """Return the Locator for a specific profile button."""
        return self.page.locator(f"#profileBtn{profile.capitalize()}")

    def all_profile_buttons(self) -> list:
        """Return Locators for all profile picker buttons."""
        return self.page.locator(".profile-picker .profile-btn").all()

    # ── Run control ───────────────────────────────────────────────────────────

    def start_run(self) -> None:
        """Click the START RUN button."""
        self.start_btn().click()

    def stop_run(self) -> None:
        """Click the STOP button."""
        self.stop_btn().click()

    def start_btn_enabled(self) -> bool:
        """Return True if the START RUN button is not disabled."""
        return not self.start_btn().is_disabled()

    def stop_btn_enabled(self) -> bool:
        """Return True if the STOP button is not disabled."""
        return not self.stop_btn().is_disabled()

    # ── Status banner ─────────────────────────────────────────────────────────

    def banner_text(self) -> str:
        """Return the current run status banner text."""
        return self.run_banner_text().inner_text().strip()

    def banner_class(self) -> str:
        """Return the CSS classes of the run status banner."""
        return self.run_banner().get_attribute("class") or ""

    def banner_state(self) -> str:
        """Return the semantic run state from the banner class (idle/running…)."""
        cls = self.banner_class()
        for state in ("running", "starting", "stopping", "finished"):
            if state in cls:
                return state
        return "idle"

    # ── Target input ──────────────────────────────────────────────────────────

    def set_base_url(self, url: str) -> None:
        """Fill the base URL input field."""
        self.base_url_input().fill(url)

    def get_base_url(self) -> str:
        """Return the current value of the base URL input."""
        return self.base_url_input().input_value()
