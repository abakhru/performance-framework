"""
test_influx.py — Unit tests for dashboard/influx.py

Issue: Modularization of server.py
Tests verify line-protocol escaping, CSV parsing, and helper functions.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

import influx

# ── lp_tag escaping ────────────────────────────────────────────────────────────


class TestLpTag:
    def test_lp_escape_commas(self):
        """Commas in tag values must be backslash-escaped."""
        assert influx.lp_tag("hello,world") == r"hello\,world"

    def test_lp_escape_spaces(self):
        """Spaces in tag values must be backslash-escaped."""
        assert influx.lp_tag("hello world") == r"hello\ world"

    def test_lp_escape_equals(self):
        """Equals signs in tag values must be backslash-escaped."""
        assert influx.lp_tag("a=b") == r"a\=b"

    def test_lp_escape_plain_string(self):
        """Plain strings without special chars pass through unchanged."""
        assert influx.lp_tag("my-run-id") == "my-run-id"

    def test_lp_escape_multiple_chars(self):
        """Multiple special chars are all escaped correctly."""
        result = influx.lp_tag("a,b c=d")
        assert result == r"a\,b\ c\=d"


# ── lp_str quoting ─────────────────────────────────────────────────────────────


class TestLpStr:
    def test_lp_str_wraps_in_quotes(self):
        assert influx.lp_str("hello") == '"hello"'

    def test_lp_str_escapes_inner_quotes(self):
        assert influx.lp_str('say "hi"') == r'"say \"hi\""'

    def test_lp_str_escapes_backslash(self):
        assert influx.lp_str("back\\slash") == '"back\\\\slash"'


# ── parse_influx_csv ───────────────────────────────────────────────────────────


class TestParseInfluxCsv:
    def test_parse_empty_string(self):
        """Empty input returns an empty list."""
        assert influx.parse_influx_csv("") == []

    def test_parse_only_comments(self):
        """Lines starting with '#' are skipped entirely."""
        text = "#datatype,string,long\n#group,false,false\n#default,,,\n"
        assert influx.parse_influx_csv(text) == []

    def test_parse_valid_annotated_csv(self):
        """Valid annotated CSV is parsed into a list of dicts."""
        text = (
            "#datatype,string,long,dateTime:RFC3339,string,double\n"
            "#group,false,false,false,true,false\n"
            "#default,_result,,,,\n"
            ",result,table,_time,run_id,_value\n"
            ",_result,0,2024-01-01T00:00:00Z,abc-123,42.5\n"
        )
        rows = influx.parse_influx_csv(text)
        assert len(rows) == 1
        assert rows[0]["run_id"] == "abc-123"
        assert rows[0]["_value"] == "42.5"
        # Skipped columns should not appear
        assert "result" not in rows[0]
        assert "table" not in rows[0]

    def test_parse_skips_empty_lines_between_tables(self):
        """Empty lines (table separators) reset the header."""
        text = (
            ",result,table,_time,run_id,_value\n"
            ",_result,0,2024-01-01T00:00:00Z,run1,10\n"
            "\n"
            ",result,table,_time,run_id,_value\n"
            ",_result,1,2024-01-02T00:00:00Z,run2,20\n"
        )
        rows = influx.parse_influx_csv(text)
        assert len(rows) == 2
        assert rows[0]["run_id"] == "run1"
        assert rows[1]["run_id"] == "run2"

    def test_parse_skips_mismatched_rows(self):
        """Rows with different column count than header are silently skipped."""
        text = (
            ",result,table,_time,run_id,_value\n"
            ",_result,0,2024-01-01T00:00:00Z\n"  # only 4 cols, header has 6
        )
        rows = influx.parse_influx_csv(text)
        assert rows == []


# ── now_ns / now ──────────────────────────────────────────────────────────────


class TestTimeHelpers:
    def test_now_ns_is_int(self):
        ts = influx.now_ns()
        assert isinstance(ts, int)
        assert ts > 0

    def test_now_returns_iso_string(self):
        s = influx.now()
        # Should contain 'T' and '+' or 'Z' (ISO 8601)
        assert "T" in s
        assert len(s) >= 19
