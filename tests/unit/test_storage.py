"""
test_storage.py — Unit tests for dashboard/storage.py

Issue: Modularization of server.py
Tests cover file round-trips, type coercions, and endpoint config loading.
"""

import json

import pytest

import core.storage as storage

# ── load_state / save_state ────────────────────────────────────────────────────


class TestStatePersistence:
    def test_save_and_load_state_round_trip(self, tmp_path, monkeypatch):
        """State saved to disk can be loaded back with identical contents."""
        state_file = tmp_path / "state.json"
        monkeypatch.setattr(storage, "DASHBOARD_STATE", state_file)

        state = {"baseline_run_id": "abc-123", "some_key": [1, 2, 3]}
        storage.save_state(state)

        loaded = storage.load_state()
        assert loaded == state

    def test_load_state_returns_empty_dict_when_missing(self, tmp_path, monkeypatch):
        """load_state returns {} when the state file does not exist."""
        monkeypatch.setattr(storage, "DASHBOARD_STATE", tmp_path / "nonexistent.json")
        assert storage.load_state() == {}

    def test_load_state_returns_empty_dict_on_corrupt_json(self, tmp_path, monkeypatch):
        """load_state returns {} on malformed JSON."""
        state_file = tmp_path / "state.json"
        state_file.write_text("not valid json}")
        monkeypatch.setattr(storage, "DASHBOARD_STATE", state_file)
        assert storage.load_state() == {}


# ── load_profiles / save_profiles ─────────────────────────────────────────────


class TestProfilesPersistence:
    def test_save_and_load_profiles_round_trip(self, tmp_path, monkeypatch):
        """Profiles saved to disk can be loaded back with identical contents."""
        profiles_file = tmp_path / "profiles.json"
        monkeypatch.setattr(storage, "PROFILES_FILE", profiles_file)

        profiles = {
            "staging": {"name": "staging", "base_url": "https://staging.example.com"},
        }
        storage.save_profiles(profiles)
        loaded = storage.load_profiles()
        assert loaded == profiles

    def test_load_profiles_returns_empty_dict_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "PROFILES_FILE", tmp_path / "none.json")
        assert storage.load_profiles() == {}


# ── load_webhooks / save_webhooks ──────────────────────────────────────────────


class TestWebhooksPersistence:
    def test_save_and_load_webhooks_round_trip(self, tmp_path, monkeypatch):
        """Webhooks list saved to disk can be loaded back identically."""
        hooks_file = tmp_path / "webhooks.json"
        monkeypatch.setattr(storage, "WEBHOOKS_FILE", hooks_file)

        hooks = [{"id": "1", "url": "https://example.com/hook", "events": ["run.finished"]}]
        storage.save_webhooks(hooks)
        loaded = storage.load_webhooks()
        assert loaded == hooks

    def test_load_webhooks_returns_empty_list_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "WEBHOOKS_FILE", tmp_path / "none.json")
        assert storage.load_webhooks() == []


# ── load_endpoint_config ───────────────────────────────────────────────────────


class TestLoadEndpointConfig:
    def test_load_endpoint_config_missing_file(self, tmp_path, monkeypatch):
        """Missing endpoints.json returns the default empty structure."""
        monkeypatch.setattr(storage, "_ENDPOINTS_JSON", tmp_path / "nonexistent.json")
        cfg = storage.load_endpoint_config()
        assert "endpoints" in cfg
        assert "setup" in cfg
        assert "teardown" in cfg
        assert cfg["endpoints"] == []

    def test_load_endpoint_config_valid_file(self, tmp_path, monkeypatch, sample_endpoints):
        """Valid endpoints.json is loaded correctly."""
        ep_file = tmp_path / "endpoints.json"
        ep_file.write_text(json.dumps(sample_endpoints))
        monkeypatch.setattr(storage, "_ENDPOINTS_JSON", ep_file)

        cfg = storage.load_endpoint_config()
        assert cfg["service"] == "Test"
        assert len(cfg["endpoints"]) == 1
        assert cfg["endpoints"][0]["name"] == "Foo"


# ── save_endpoints_json ────────────────────────────────────────────────────────


class TestSaveEndpointsJson:
    def test_save_endpoints_json_writes_file(self, tmp_path, monkeypatch, sample_endpoints):
        """save_endpoints_json writes the config to disk."""
        ep_file = tmp_path / "endpoints.json"
        monkeypatch.setattr(storage, "_ENDPOINTS_JSON", ep_file)

        storage.save_endpoints_json(sample_endpoints)
        assert ep_file.exists()

        written = json.loads(ep_file.read_text())
        assert written == sample_endpoints

    def test_save_endpoints_json_updates_globals_ref(self, tmp_path, monkeypatch, sample_endpoints):
        """save_endpoints_json updates the caller's mutable globals dict."""
        ep_file = tmp_path / "endpoints.json"
        monkeypatch.setattr(storage, "_ENDPOINTS_JSON", ep_file)

        globals_ref = {"_endpoint_config": {}, "OP_GROUP": {}}
        storage.save_endpoints_json(sample_endpoints, globals_ref)

        assert globals_ref["_endpoint_config"] == sample_endpoints
        assert "Foo" in globals_ref["OP_GROUP"]


# ── build_op_group ─────────────────────────────────────────────────────────────


class TestBuildOpGroup:
    def test_build_op_group_maps_endpoints(self, sample_endpoints):
        """build_op_group maps each endpoint name to its group."""
        result = storage.build_op_group(sample_endpoints)
        assert result["Foo"] == "g1"

    def test_build_op_group_includes_setup_and_teardown(self):
        """setup and teardown sections are also included in the mapping."""
        cfg = {
            "endpoints": [{"name": "main", "group": "g1"}],
            "setup": [{"name": "login", "group": "auth"}],
            "teardown": [{"name": "logout", "group": "auth"}],
        }
        result = storage.build_op_group(cfg)
        assert result["main"] == "g1"
        assert result["login"] == "auth"
        assert result["logout"] == "auth"

    def test_build_op_group_uses_name_as_default_group(self):
        """Endpoint without 'group' key uses its name as the group."""
        cfg = {"endpoints": [{"name": "myop"}], "setup": [], "teardown": []}
        result = storage.build_op_group(cfg)
        assert result["myop"] == "myop"


# ── coerce_int ─────────────────────────────────────────────────────────────────


class TestCoerceInt:
    def test_coerce_int_valid_string(self):
        """String '42' coerces to int 42."""
        assert storage.coerce_int("42") == 42

    def test_coerce_int_float_string(self):
        """String '3.9' coerces to int 3 (truncated)."""
        assert storage.coerce_int("3.9") == 3

    def test_coerce_int_invalid_returns_default(self):
        """Non-numeric string returns default value."""
        assert storage.coerce_int("abc") is None
        assert storage.coerce_int("abc", default=0) == 0

    def test_coerce_int_none_returns_default(self):
        assert storage.coerce_int(None) is None
        assert storage.coerce_int(None, default=-1) == -1

    def test_coerce_int_empty_string_returns_default(self):
        assert storage.coerce_int("", default=99) == 99


# ── coerce_float ───────────────────────────────────────────────────────────────


class TestCoerceFloat:
    def test_coerce_float_valid_string(self):
        """String '3.14' coerces to float 3.14."""
        assert storage.coerce_float("3.14") == pytest.approx(3.14)

    def test_coerce_float_int_string(self):
        """String '10' coerces to float 10.0."""
        assert storage.coerce_float("10") == 10.0

    def test_coerce_float_invalid_returns_default(self):
        """Non-numeric string returns default value."""
        assert storage.coerce_float("bad") is None
        assert storage.coerce_float("bad", default=0.0) == 0.0

    def test_coerce_float_none_returns_default(self):
        assert storage.coerce_float(None) is None

    def test_coerce_float_empty_string_returns_default(self):
        assert storage.coerce_float("", default=1.5) == 1.5
