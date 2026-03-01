"""UITestCase — WUIBase equivalent.

Base unittest.TestCase for browser-based dashboard tests.

Architecture (mirrors artemis_web BaseSetup):
  - setUpClass  : launches the FastAPI dashboard subprocess, then opens a
                  Playwright browser (Chromium, headless by default).
  - tearDownClass: closes browser, stops Playwright, terminates the server.
  - setUp       : creates a fresh BrowserContext + Page per test method.
  - tearDown    : closes the context.

Server lifecycle is class-scoped (one server per TestCase class) so the
expensive startup cost is paid only once per test file, matching the
artemis_web BaseSetup pattern.

Coverage is enabled by default via FastAPIHarness (PythonServerHarness),
which injects COVERAGE_PROCESS_START into the subprocess environment.
"""

from __future__ import annotations

import unittest

PORT_DEFAULT = 55656  # separate from the normal :5656 dev port to avoid conflicts


class UITestCase(unittest.TestCase):
    """Base UI test case — subclass and optionally override PORT / HEADLESS."""

    PORT: int = PORT_DEFAULT
    HEADLESS: bool = True

    # Class-level state — set in setUpClass, cleared in tearDownClass
    _harness = None
    _playwright = None
    _browser = None

    # ── Class lifecycle ───────────────────────────────────────────────────────

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise unittest.SkipTest("playwright not installed — run: just ui-install") from exc

        try:
            from api_tests.harness.fastapi import FastAPIHarness
        except ImportError as exc:
            raise unittest.SkipTest(f"api_tests not on PYTHONPATH: {exc}") from exc

        cls._harness = FastAPIHarness(test_case=None, port=cls.PORT, coverage=False)
        cls._harness.Launch()
        cls._harness.wait_for_ready(timeout=30.0)

        cls._playwright = sync_playwright().start()
        cls._browser = cls._playwright.chromium.launch(headless=cls.HEADLESS)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._browser:
            cls._browser.close()
            cls._browser = None
        if cls._playwright:
            cls._playwright.stop()
            cls._playwright = None
        if cls._harness:
            cls._harness.Terminate()
            cls._harness.Wait()
            cls._harness = None
        super().tearDownClass()

    # ── Per-test lifecycle ────────────────────────────────────────────────────

    def setUp(self) -> None:
        super().setUp()

        # Playwright not available → skip the test gracefully
        if self.__class__._browser is None:
            self.skipTest("Browser not available — check setUpClass errors")

        self._context = self.__class__._browser.new_context(
            viewport={"width": 1280, "height": 900},
            # Capture video/trace/screenshot on failure via pytest-playwright
            # when invoked through pytest (video: "retain-on-failure").
        )
        self.page = self._context.new_page()
        self.base_url = f"http://127.0.0.1:{self.__class__.PORT}"

    def tearDown(self) -> None:
        if hasattr(self, "_context") and self._context:
            self._context.close()
        super().tearDown()

    # ── Assertion helpers ─────────────────────────────────────────────────────

    def assertVisible(self, locator, msg: str = "") -> None:
        """Assert that a Playwright Locator is visible on the page."""
        self.assertTrue(locator.is_visible(), msg or f"Expected element to be visible: {locator}")

    def assertHidden(self, locator, msg: str = "") -> None:
        """Assert that a Playwright Locator is hidden/not visible."""
        self.assertFalse(locator.is_visible(), msg or f"Expected element to be hidden: {locator}")

    def assertTextContains(self, locator, expected: str, msg: str = "") -> None:
        """Assert that a Playwright Locator's text contains expected string."""
        actual = locator.inner_text().strip()
        self.assertIn(expected, actual, msg or f"Expected {expected!r} in {actual!r}")

    def assertClassContains(self, locator, css_class: str, msg: str = "") -> None:
        """Assert that a Playwright Locator's class attribute contains css_class."""
        cls_attr = locator.get_attribute("class") or ""
        self.assertIn(css_class, cls_attr, msg or f"Expected class {css_class!r} in {cls_attr!r}")
