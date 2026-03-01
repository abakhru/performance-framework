"""
test_visual_qa.py — Unit tests for dashboard/visual_qa.py

Covers: profile loading, data class construction, bug JSON parsing,
run storage round-trip, agent resolution, and _format_a11y_snapshot.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import plugins.visual_qa.agents as vqa

# ── Profile loading ────────────────────────────────────────────────────────────


class TestLoadProfiles(unittest.TestCase):
    """Verify all 31 agent profiles are present and well-formed."""

    def setUp(self) -> None:
        self.profiles = vqa.load_profiles()

    def test_returns_31_profiles(self) -> None:
        """load_profiles() returns exactly 31 agents."""
        self.assertEqual(len(self.profiles), 31)

    def test_all_expected_ids_present(self) -> None:
        """All known agent ids are present in the profile dict."""
        expected_ids = {
            "marcus", "jason", "mia", "sophia", "tariq", "fatima", "sharon",
            "pete", "hiroshi", "zanele", "mei", "alejandro", "diego", "leila",
            "kwame", "zara", "priya", "yara", "hassan", "amara", "yuki",
            "mateo", "anika", "zoe", "zachary", "sundar", "samantha", "richard",
            "ravi", "rajesh", "olivia",
        }
        self.assertEqual(set(self.profiles.keys()), expected_ids)

    def test_each_profile_has_required_keys(self) -> None:
        """Every profile contains id, name, specialty, check_types, group, prompt."""
        required = {"id", "name", "specialty", "check_types", "group", "prompt"}
        for agent_id, profile in self.profiles.items():
            with self.subTest(agent=agent_id):
                self.assertEqual(required, required & profile.keys(), f"{agent_id} missing keys")

    def test_check_types_are_non_empty_lists(self) -> None:
        """check_types must be a non-empty list of strings."""
        for agent_id, p in self.profiles.items():
            with self.subTest(agent=agent_id):
                self.assertIsInstance(p["check_types"], list)
                self.assertTrue(len(p["check_types"]) >= 1)

    def test_get_profile_returns_none_for_unknown(self) -> None:
        self.assertIsNone(vqa.get_profile("nonexistent_agent"))

    def test_get_profile_returns_correct_profile(self) -> None:
        p = vqa.get_profile("marcus")
        self.assertIsNotNone(p)
        self.assertEqual(p["name"], "Marcus")
        self.assertEqual(p["specialty"], "Networking & Connectivity")

    def test_list_agent_ids_count(self) -> None:
        ids = vqa.list_agent_ids()
        self.assertEqual(len(ids), 31)
        self.assertIn("marcus", ids)
        self.assertIn("olivia", ids)


# ── Data classes ───────────────────────────────────────────────────────────────


class TestPageState(unittest.TestCase):
    """PageState dataclass construction and serialisation."""

    def test_basic_construction(self) -> None:
        ps = vqa.PageState(url="https://example.com", screenshot_b64="abc123", a11y_tree="[webarea]")
        self.assertEqual(ps.url, "https://example.com")
        self.assertEqual(ps.console_logs, [])

    def test_with_console_logs(self) -> None:
        ps = vqa.PageState(
            url="https://example.com",
            screenshot_b64="x",
            a11y_tree="y",
            console_logs=["[ERROR] TypeError: foo is not a function"],
        )
        self.assertEqual(len(ps.console_logs), 1)


class TestBugReport(unittest.TestCase):
    """BugReport dataclass construction and round-trip via dict."""

    def _make_bug(self) -> vqa.BugReport:
        return vqa.BugReport(
            bug_title="Missing alt text on hero image",
            bug_type=["Accessibility", "WCAG"],
            bug_priority=8,
            bug_confidence=9,
            bug_reasoning_why_a_bug="Screen readers cannot describe the image to users",
            suggested_fix="Add alt attribute to <img> tag",
            fix_prompt="Add descriptive alt text: <img src='hero.jpg' alt='Team collaboration'>",
        )

    def test_construction(self) -> None:
        bug = self._make_bug()
        self.assertEqual(bug.bug_priority, 8)
        self.assertEqual(bug.bug_type, ["Accessibility", "WCAG"])

    def test_asdict_round_trip(self) -> None:
        bug = self._make_bug()
        d = asdict(bug)
        self.assertEqual(d["bug_title"], bug.bug_title)
        self.assertEqual(d["bug_priority"], 8)


class TestAgentResult(unittest.TestCase):
    def test_no_bugs_default(self) -> None:
        r = vqa.AgentResult(agent_id="sophia", agent_name="Sophia", specialty="Accessibility")
        self.assertEqual(r.bugs, [])
        self.assertIsNone(r.error)

    def test_with_error(self) -> None:
        r = vqa.AgentResult(agent_id="marcus", agent_name="Marcus", specialty="Networking", error="API key missing")
        self.assertEqual(r.error, "API key missing")


class TestVQARun(unittest.TestCase):
    def test_default_status_and_created_at(self) -> None:
        run = vqa.VQARun(run_id="r1", url="https://example.com", agents=["marcus"], status="running")
        self.assertEqual(run.status, "running")
        self.assertIsNotNone(run.created_at)
        self.assertIsNone(run.completed_at)


# ── Bug JSON parsing ───────────────────────────────────────────────────────────


class TestParseBugs(unittest.TestCase):
    """_parse_bugs handles various AI response formats gracefully."""

    def test_clean_json_array(self) -> None:
        raw = json.dumps([
            {
                "bug_title": "Low contrast text",
                "bug_type": ["Accessibility"],
                "bug_priority": 7,
                "bug_confidence": 9,
                "bug_reasoning_why_a_bug": "Fails WCAG 1.4.3",
                "suggested_fix": "Darken text color",
                "fix_prompt": "Change color from #999 to #555",
            }
        ])
        bugs = vqa._parse_bugs(raw)
        self.assertEqual(len(bugs), 1)
        self.assertEqual(bugs[0].bug_title, "Low contrast text")
        self.assertEqual(bugs[0].bug_priority, 7)

    def test_markdown_fenced_json(self) -> None:
        raw = "Here are the bugs:\n```json\n[{\"bug_title\":\"X\",\"bug_type\":[\"UI\"],\"bug_priority\":5,\"bug_confidence\":8,\"bug_reasoning_why_a_bug\":\"r\",\"suggested_fix\":\"f\",\"fix_prompt\":\"p\"}]\n```"
        bugs = vqa._parse_bugs(raw)
        self.assertEqual(len(bugs), 1)
        self.assertEqual(bugs[0].bug_title, "X")

    def test_empty_array(self) -> None:
        bugs = vqa._parse_bugs("[]")
        self.assertEqual(bugs, [])

    def test_invalid_json_returns_empty(self) -> None:
        bugs = vqa._parse_bugs("This page looks great! No issues found.")
        self.assertEqual(bugs, [])

    def test_missing_optional_fields_get_defaults(self) -> None:
        raw = json.dumps([{
            "bug_title": "Broken link",
            "bug_type": ["Content"],
            "bug_priority": 4,
            "bug_confidence": 7,
            "bug_reasoning_why_a_bug": "Link 404s",
            "suggested_fix": "",
            "fix_prompt": "",
        }])
        bugs = vqa._parse_bugs(raw)
        self.assertEqual(len(bugs), 1)
        self.assertEqual(bugs[0].suggested_fix, "")

    def test_multiple_bugs_all_parsed(self) -> None:
        items = [
            {"bug_title": f"Bug {i}", "bug_type": ["UI"], "bug_priority": i,
             "bug_confidence": 5, "bug_reasoning_why_a_bug": "r", "suggested_fix": "s", "fix_prompt": "p"}
            for i in range(1, 6)
        ]
        bugs = vqa._parse_bugs(json.dumps(items))
        self.assertEqual(len(bugs), 5)


# ── A11y snapshot formatter ────────────────────────────────────────────────────


class TestFormatA11ySnapshot(unittest.TestCase):
    def test_simple_node(self) -> None:
        node = {"role": "button", "name": "Submit"}
        result = vqa._format_a11y_snapshot(node)
        self.assertIn("[button]", result)
        self.assertIn('"Submit"', result)

    def test_nested_node(self) -> None:
        node = {
            "role": "main",
            "name": "",
            "children": [
                {"role": "heading", "name": "Welcome", "children": []},
                {"role": "button", "name": "Login", "children": []},
            ],
        }
        result = vqa._format_a11y_snapshot(node)
        self.assertIn("[main]", result)
        self.assertIn("[heading]", result)
        self.assertIn('"Welcome"', result)
        self.assertIn("[button]", result)

    def test_empty_node(self) -> None:
        result = vqa._format_a11y_snapshot({})
        self.assertIsInstance(result, str)


# ── Agent resolution ───────────────────────────────────────────────────────────


class TestResolveAgentIds(unittest.TestCase):
    def test_all_keyword_returns_all_31(self) -> None:
        resolved = vqa._resolve_agent_ids(["all"])
        self.assertEqual(len(resolved), 31)

    def test_empty_list_returns_all_31(self) -> None:
        resolved = vqa._resolve_agent_ids([])
        self.assertEqual(len(resolved), 31)

    def test_specific_agents_preserved(self) -> None:
        resolved = vqa._resolve_agent_ids(["marcus", "mia", "sophia"])
        self.assertEqual(resolved, ["marcus", "mia", "sophia"])

    def test_unknown_agents_skipped(self) -> None:
        resolved = vqa._resolve_agent_ids(["marcus", "unknown_agent"])
        self.assertEqual(resolved, ["marcus"])

    def test_all_unknown_falls_back_to_all(self) -> None:
        resolved = vqa._resolve_agent_ids(["nonexistent"])
        self.assertEqual(len(resolved), 31)


# ── Storage round-trip ────────────────────────────────────────────────────────


class TestRunStorage(unittest.TestCase):
    """store_run / get_run / list_runs using a temporary directory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_dir = vqa.VQA_DATA_DIR
        vqa.VQA_DATA_DIR = Path(self._tmp.name)

        # Clear in-memory cache
        vqa._runs.clear()

    def tearDown(self) -> None:
        vqa.VQA_DATA_DIR = self._orig_dir
        vqa._runs.clear()
        self._tmp.cleanup()

    def _make_run(self, run_id: str = "test-run-1") -> vqa.VQARun:
        bug = vqa.BugReport(
            bug_title="Missing alt text",
            bug_type=["Accessibility"],
            bug_priority=8,
            bug_confidence=9,
            bug_reasoning_why_a_bug="Reason",
            suggested_fix="Add alt",
            fix_prompt="<img alt='...'>",
        )
        result = vqa.AgentResult(
            agent_id="sophia",
            agent_name="Sophia",
            specialty="Accessibility",
            bugs=[bug],
        )
        return vqa.VQARun(
            run_id=run_id,
            url="https://example.com",
            agents=["sophia"],
            status="done",
            results=[result],
            completed_at="2026-01-01T00:00:00+00:00",
        )

    def test_store_and_get_round_trip(self) -> None:
        """A stored run can be retrieved with identical contents."""
        run = self._make_run()
        vqa.store_run(run)

        loaded = vqa.get_run("test-run-1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.run_id, "test-run-1")
        self.assertEqual(loaded.url, "https://example.com")
        self.assertEqual(loaded.status, "done")
        self.assertEqual(len(loaded.results), 1)
        self.assertEqual(len(loaded.results[0].bugs), 1)
        self.assertEqual(loaded.results[0].bugs[0].bug_title, "Missing alt text")

    def test_get_run_returns_none_for_unknown(self) -> None:
        result = vqa.get_run("does-not-exist")
        self.assertIsNone(result)

    def test_list_runs_returns_stored_runs(self) -> None:
        for i in range(3):
            vqa.store_run(self._make_run(f"run-{i}"))
        runs = vqa.list_runs(limit=10)
        self.assertEqual(len(runs), 3)

    def test_list_runs_respects_limit(self) -> None:
        for i in range(5):
            vqa.store_run(self._make_run(f"run-{i}"))
        runs = vqa.list_runs(limit=2)
        self.assertEqual(len(runs), 2)

    def test_stored_file_is_valid_json(self) -> None:
        run = self._make_run()
        vqa.store_run(run)
        path = Path(self._tmp.name) / "test-run-1.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text())
        self.assertEqual(data["run_id"], "test-run-1")
        self.assertEqual(len(data["results"]), 1)

    def test_get_run_loads_from_disk_bypassing_cache(self) -> None:
        """get_run falls back to disk when run is not in the in-memory cache."""
        run = self._make_run()
        vqa.store_run(run)
        # Clear in-memory cache to force disk read
        vqa._runs.clear()
        loaded = vqa.get_run("test-run-1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.url, "https://example.com")


# ── run_agent with missing API key ────────────────────────────────────────────


class TestRunAgentWithoutApiKey(unittest.TestCase):
    def test_missing_api_key_returns_error_result(self) -> None:
        """run_agent returns AgentResult with error when VISUAL_QA_AI_KEY is not set."""
        page_state = vqa.PageState(
            url="https://example.com",
            screenshot_b64="fake",
            a11y_tree="[webarea]",
        )
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("VISUAL_QA_AI_KEY", None)
            result = vqa.run_agent("marcus", page_state)
        self.assertIsNotNone(result.error)
        self.assertIn("VISUAL_QA_AI_KEY", result.error)

    def test_unknown_agent_id_returns_error_result(self) -> None:
        page_state = vqa.PageState(url="https://example.com", screenshot_b64="x", a11y_tree="y")
        result = vqa.run_agent("nonexistent_agent", page_state)
        self.assertIsNotNone(result.error)
        self.assertIn("Unknown agent id", result.error)


if __name__ == "__main__":
    unittest.main()
