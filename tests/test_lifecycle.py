"""
test_lifecycle.py — Unit tests for dashboard/lifecycle.py

Issue: Modularization of server.py
Tests cover SLO checks, badge generation, and webhook HMAC signing.
"""

import hashlib
import hmac
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

import lifecycle

# ── compute_slo_checks ─────────────────────────────────────────────────────────


class TestComputeSloChecks:
    def test_all_pass_when_within_thresholds(self):
        """All SLO metrics within threshold → all pass=True."""
        slos = {"p95_ms": 500.0, "error_rate": 0.01}
        fields = {"p95_ms": 200.0, "error_rate": 0.005}
        result = lifecycle.compute_slo_checks(slos, fields)
        assert result["p95_ms"]["pass"] is True
        assert result["error_rate"]["pass"] is True

    def test_one_fail_when_exceeds_threshold(self):
        """One metric exceeding its threshold → that metric has pass=False."""
        slos = {"p95_ms": 200.0, "error_rate": 0.01}
        fields = {"p95_ms": 500.0, "error_rate": 0.005}
        result = lifecycle.compute_slo_checks(slos, fields)
        assert result["p95_ms"]["pass"] is False
        assert result["error_rate"]["pass"] is True

    def test_higher_is_better_metrics_pass_when_above_threshold(self):
        """checks_rate and apdex_score pass when >= threshold."""
        slos = {"checks_rate": 0.99, "apdex_score": 0.9}
        fields = {"checks_rate": 1.0, "apdex_score": 0.95}
        result = lifecycle.compute_slo_checks(slos, fields)
        assert result["checks_rate"]["pass"] is True
        assert result["apdex_score"]["pass"] is True

    def test_higher_is_better_fails_when_below_threshold(self):
        """checks_rate and apdex_score fail when < threshold."""
        slos = {"checks_rate": 0.99, "apdex_score": 0.9}
        fields = {"checks_rate": 0.80, "apdex_score": 0.75}
        result = lifecycle.compute_slo_checks(slos, fields)
        assert result["checks_rate"]["pass"] is False
        assert result["apdex_score"]["pass"] is False

    def test_empty_slos_returns_empty_dict(self):
        """No SLO definitions → empty result (caller treats as 'unknown')."""
        result = lifecycle.compute_slo_checks({}, {"p95_ms": 100.0})
        assert result == {}

    def test_missing_field_is_skipped(self):
        """SLO metric not present in fields dict is simply skipped."""
        slos = {"p95_ms": 500.0, "p99_ms": 1000.0}
        fields = {"p95_ms": 200.0}  # p99_ms missing
        result = lifecycle.compute_slo_checks(slos, fields)
        assert "p95_ms" in result
        assert "p99_ms" not in result

    def test_result_contains_value_and_threshold(self):
        """Each check result includes the actual value and threshold."""
        slos = {"p95_ms": 300.0}
        fields = {"p95_ms": 150.0}
        result = lifecycle.compute_slo_checks(slos, fields)
        assert result["p95_ms"]["value"] == 150.0
        assert result["p95_ms"]["threshold"] == 300.0


# ── make_badge_svg ─────────────────────────────────────────────────────────────


class TestMakeBadgeSvg:
    def test_pass_badge_contains_green(self):
        """Verdict 'pass' → SVG contains green fill color."""
        svg = lifecycle.make_badge_svg("pass")
        assert "#2da44e" in svg

    def test_fail_badge_contains_red(self):
        """Verdict 'fail' → SVG contains red fill color."""
        svg = lifecycle.make_badge_svg("fail")
        assert "#cf222e" in svg

    def test_pass_badge_text(self):
        """Pass badge label says 'PERF PASS'."""
        svg = lifecycle.make_badge_svg("pass")
        assert "PERF PASS" in svg

    def test_fail_badge_text(self):
        """Fail badge label says 'PERF FAIL'."""
        svg = lifecycle.make_badge_svg("fail")
        assert "PERF FAIL" in svg

    def test_unknown_verdict_defaults_to_fail_colour(self):
        """Any verdict other than 'pass' uses the fail (red) colour."""
        svg = lifecycle.make_badge_svg("unknown")
        assert "#cf222e" in svg

    def test_badge_is_valid_svg(self):
        """SVG output is wrapped in an <svg> tag."""
        svg = lifecycle.make_badge_svg("pass")
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")


# ── _send_webhook HMAC header ──────────────────────────────────────────────────


class TestSendWebhookHmac:
    def test_hmac_header_present_when_secret_set(self):
        """Webhook POST includes valid X-Perf-Signature when secret is configured."""
        hook = {"url": "http://example.com/hook", "secret": "mysecret", "events": ["run.finished"]}
        payload = {"event": "run.finished", "run_id": "test-run"}
        captured = {}

        def fake_urlopen(req, timeout=10):
            captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
            resp = MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            resp.status = 200
            resp.read = lambda: b""
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            lifecycle._send_webhook(hook, payload)

        assert "x-perf-signature" in captured["headers"]
        sig_header = captured["headers"]["x-perf-signature"]
        assert sig_header.startswith("sha256=")

        # Verify the signature is correct
        body = json.dumps(payload).encode()
        expected_sig = hmac.new(b"mysecret", body, hashlib.sha256).hexdigest()
        assert sig_header == f"sha256={expected_sig}"

    def test_no_hmac_header_when_no_secret(self):
        """Webhook POST omits X-Perf-Signature when no secret is configured."""
        hook = {"url": "http://example.com/hook", "secret": "", "events": ["run.finished"]}
        payload = {"event": "run.finished"}
        captured = {}

        def fake_urlopen(req, timeout=10):
            captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
            resp = MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            resp.status = 200
            resp.read = lambda: b""
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            lifecycle._send_webhook(hook, payload)

        assert "x-perf-signature" not in captured["headers"]

    def test_send_webhook_skips_empty_url(self):
        """_send_webhook returns early without making any HTTP call when url is empty."""
        hook = {"url": "", "secret": "", "events": ["run.finished"]}
        payload = {"event": "run.finished"}

        with patch("urllib.request.urlopen") as mock_open:
            lifecycle._send_webhook(hook, payload)
            mock_open.assert_not_called()
