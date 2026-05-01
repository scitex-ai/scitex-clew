#!/usr/bin/env python3
# Timestamp: "2026-03-14 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-clew/tests/test__registry.py
"""Tests for scitex_clew._registry module (ClewRegistry)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import scitex_clew._db as _db_module
from scitex_clew._db import set_db
from scitex_clew._registry import ClewRegistry, DEFAULT_REGISTRY_URL, get_registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Inject a fresh temp DB and reset global state after each test."""
    db_path = tmp_path / "registry_test.db"
    set_db(db_path)
    yield
    _db_module._DB_INSTANCE = None


@pytest.fixture(autouse=True)
def reset_registry_singleton():
    """Reset the module-level registry singleton between tests."""
    import scitex_clew._registry as _reg_module

    original = _reg_module._registry_instance
    yield
    _reg_module._registry_instance = original


@pytest.fixture
def registry():
    """Return a ClewRegistry pointed at a local non-existent base URL."""
    return ClewRegistry(base_url="http://localhost:9999", api_key=None)


@pytest.fixture
def registry_with_key():
    """Return a ClewRegistry with an API key set."""
    return ClewRegistry(base_url="http://localhost:9999", api_key="test-api-key-abc")


# ---------------------------------------------------------------------------
# ClewRegistry construction
# ---------------------------------------------------------------------------


class TestClewRegistryInit:
    def test_default_base_url(self):
        """Default base URL should be https://scitex.ai (no trailing slash)."""
        reg = ClewRegistry()
        assert reg.base_url == DEFAULT_REGISTRY_URL.rstrip("/")

    def test_explicit_base_url(self):
        """Explicit base_url overrides default."""
        reg = ClewRegistry(base_url="https://custom.example.com/")
        assert reg.base_url == "https://custom.example.com"

    def test_explicit_base_url_strips_trailing_slash(self):
        """Trailing slash is stripped from base_url."""
        reg = ClewRegistry(base_url="https://example.com///")
        assert not reg.base_url.endswith("/")

    def test_base_url_from_env(self, monkeypatch):
        """SCITEX_REGISTRY_URL environment variable sets base_url."""
        monkeypatch.setenv("SCITEX_REGISTRY_URL", "https://env.example.com")
        reg = ClewRegistry()
        assert reg.base_url == "https://env.example.com"

    def test_explicit_base_url_overrides_env(self, monkeypatch):
        """Explicit base_url takes precedence over env variable."""
        monkeypatch.setenv("SCITEX_REGISTRY_URL", "https://env.example.com")
        reg = ClewRegistry(base_url="https://explicit.example.com")
        assert reg.base_url == "https://explicit.example.com"

    def test_api_key_none_by_default(self, monkeypatch):
        """api_key is None when not set and env var not present."""
        monkeypatch.delenv("SCITEX_API_KEY", raising=False)
        reg = ClewRegistry()
        assert reg.api_key is None

    def test_explicit_api_key(self):
        """Explicit api_key is stored."""
        reg = ClewRegistry(api_key="my-secret-key")
        assert reg.api_key == "my-secret-key"

    def test_api_key_from_env(self, monkeypatch):
        """SCITEX_API_KEY environment variable sets api_key."""
        monkeypatch.setenv("SCITEX_API_KEY", "env-api-key-xyz")
        reg = ClewRegistry()
        assert reg.api_key == "env-api-key-xyz"

    def test_explicit_api_key_overrides_env(self, monkeypatch):
        """Explicit api_key takes precedence over env variable."""
        monkeypatch.setenv("SCITEX_API_KEY", "env-api-key")
        reg = ClewRegistry(api_key="explicit-key")
        assert reg.api_key == "explicit-key"

    def test_default_registry_url_constant(self):
        """DEFAULT_REGISTRY_URL should be the expected value."""
        assert DEFAULT_REGISTRY_URL == "https://scitex.ai"


# ---------------------------------------------------------------------------
# register() — HTTP failure paths (no real server)
# ---------------------------------------------------------------------------


class TestClewRegistryRegister:
    def test_register_returns_dict(self, registry):
        """register() returns a dict even when the server is unreachable."""
        result = registry.register("abc123hash")
        assert isinstance(result, dict)

    def test_register_failure_returns_success_false(self, registry):
        """When server is unreachable, success is False."""
        result = registry.register("abc123hash")
        assert result.get("success") is False

    def test_register_failure_has_error_key(self, registry):
        """Error result contains an 'error' key."""
        result = registry.register("abc123hash")
        assert "error" in result

    def test_register_uses_bearer_auth_header(self, registry_with_key):
        """When api_key is set, Authorization header is sent."""
        captured_headers = {}

        def fake_urlopen(req, timeout=None):
            captured_headers.update(req.headers)
            raise ConnectionError("not a real server")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            registry_with_key.register("somehash")

        auth = captured_headers.get("Authorization") or captured_headers.get(
            "authorization"
        )
        assert auth is not None
        assert "test-api-key-abc" in auth

    def test_register_no_auth_header_without_key(self):
        """When no api_key, no Authorization header is sent."""
        captured_headers = {}

        def fake_urlopen(req, timeout=None):
            captured_headers.update(req.headers)
            raise ConnectionError("not a real server")

        reg = ClewRegistry(
            base_url="http://localhost:9999",
            api_key=None,
        )
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            reg.register("somehash")

        # Authorization header should not be present
        auth = captured_headers.get("Authorization") or captured_headers.get(
            "authorization"
        )
        assert auth is None

    def test_register_posts_to_correct_url(self, registry):
        """register() targets <base_url>/clew/register/."""
        captured_urls = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            raise ConnectionError("not a real server")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            registry.register("myhash")

        assert len(captured_urls) == 1
        assert captured_urls[0].endswith("/clew/register/")

    def test_register_sends_hash_in_payload(self, registry):
        """register() sends the hash value in the POST body."""
        captured_bodies = []

        def fake_urlopen(req, timeout=None):
            captured_bodies.append(req.data)
            raise ConnectionError("not a real server")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            registry.register("deadbeef1234")

        assert len(captured_bodies) == 1
        payload = json.loads(captured_bodies[0].decode())
        assert payload["hash"] == "deadbeef1234"

    def test_register_sends_source_type(self, registry):
        """register() includes source_type in the payload."""
        captured_bodies = []

        def fake_urlopen(req, timeout=None):
            captured_bodies.append(req.data)
            raise ConnectionError("not a real server")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            registry.register("abc", source_type="file")

        payload = json.loads(captured_bodies[0].decode())
        assert payload["source_type"] == "file"

    def test_register_sends_session_id(self, registry):
        """register() includes session_id in the payload."""
        captured_bodies = []

        def fake_urlopen(req, timeout=None):
            captured_bodies.append(req.data)
            raise ConnectionError("not a real server")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            registry.register("abc", session_id="sess_001")

        payload = json.loads(captured_bodies[0].decode())
        assert payload["session_id"] == "sess_001"

    def test_register_sends_metadata(self, registry):
        """register() includes metadata in the payload."""
        captured_bodies = []

        def fake_urlopen(req, timeout=None):
            captured_bodies.append(req.data)
            raise ConnectionError("not a real server")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            registry.register("abc", metadata={"foo": "bar"})

        payload = json.loads(captured_bodies[0].decode())
        assert payload["metadata"]["foo"] == "bar"

    def test_register_uses_post_method(self, registry):
        """register() sends a POST request."""
        captured_methods = []

        def fake_urlopen(req, timeout=None):
            captured_methods.append(req.method)
            raise ConnectionError("not a real server")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            registry.register("abc")

        assert captured_methods[0] == "POST"

    def test_register_success_parses_response(self, registry):
        """When server returns valid JSON, register() returns parsed dict."""
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(
            {"success": True, "registered_at": "2026-03-14T12:00:00Z"}
        ).encode()
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            result = registry.register("abc123")

        assert result["success"] is True
        assert "registered_at" in result


# ---------------------------------------------------------------------------
# verify() — HTTP failure paths
# ---------------------------------------------------------------------------


class TestClewRegistryVerify:
    def test_verify_returns_dict(self, registry):
        """verify() returns a dict even when server is unreachable."""
        result = registry.verify("abc123hash")
        assert isinstance(result, dict)

    def test_verify_failure_has_registered_false(self, registry):
        """When server is unreachable, registered is False."""
        result = registry.verify("abc123hash")
        assert result.get("registered") is False

    def test_verify_failure_has_error_key(self, registry):
        """Error result contains an 'error' key."""
        result = registry.verify("abc123hash")
        assert "error" in result

    def test_verify_requests_correct_url(self, registry):
        """verify() targets <base_url>/clew/verify/<hash>/."""
        captured_urls = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            raise ConnectionError("not a real server")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            registry.verify("deadbeef")

        assert len(captured_urls) == 1
        assert "/clew/verify/deadbeef/" in captured_urls[0]

    def test_verify_uses_get_method(self, registry):
        """verify() sends a GET request."""
        captured_methods = []

        def fake_urlopen(req, timeout=None):
            captured_methods.append(req.method)
            raise ConnectionError("not a real server")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            registry.verify("abc")

        assert captured_methods[0] == "GET"

    def test_verify_sends_auth_header_with_key(self, registry_with_key):
        """verify() sends Authorization header when api_key is set."""
        captured_headers = {}

        def fake_urlopen(req, timeout=None):
            captured_headers.update(req.headers)
            raise ConnectionError("not a real server")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            registry_with_key.verify("somehash")

        auth = captured_headers.get("Authorization") or captured_headers.get(
            "authorization"
        )
        assert auth is not None

    def test_verify_success_parses_response(self, registry):
        """When server returns valid JSON, verify() returns parsed dict."""
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(
            {"registered": True, "registrations": [{"registered_at": "2026-03-14"}]}
        ).encode()
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            result = registry.verify("abc123")

        assert result["registered"] is True
        assert isinstance(result["registrations"], list)


# ---------------------------------------------------------------------------
# register_session() — uses local DB
# ---------------------------------------------------------------------------


class TestClewRegistryRegisterSession:
    def test_register_session_empty_returns_empty_list(self, registry, tmp_path):
        """A session with no hashes returns empty list (no combined_hash)."""
        db = _db_module.get_db()
        db.add_run("sess_empty", "/path/script.py")

        # Patch register to avoid real HTTP, count calls
        called_with = []

        def fake_register(
            hash_value, source_type="manual", session_id="", metadata=None
        ):
            called_with.append(hash_value)
            return {"success": False, "error": "no server"}

        with patch.object(registry, "register", side_effect=fake_register):
            results = registry.register_session("sess_empty")

        # No combined_hash set, no file hashes → zero registrations
        assert len(results) == 0

    def test_register_session_combined_hash_registered(self, registry, tmp_path):
        """Combined hash is registered when present on the run record."""
        db = _db_module.get_db()
        db.add_run("sess_combo", "/path/script.py")
        db.finish_run("sess_combo", status="success", combined_hash="combined_abc123")

        called_with = []

        def fake_register(
            hash_value, source_type="manual", session_id="", metadata=None
        ):
            called_with.append((hash_value, source_type))
            return {"success": True}

        with patch.object(registry, "register", side_effect=fake_register):
            results = registry.register_session("sess_combo")

        # At least the combined hash should be registered
        hash_types = dict(called_with)
        assert "combined_abc123" in hash_types
        assert hash_types["combined_abc123"] == "session"

    def test_register_session_nonexistent_session(self, registry):
        """A nonexistent session results in zero registrations."""
        called_with = []

        def fake_register(
            hash_value, source_type="manual", session_id="", metadata=None
        ):
            called_with.append(hash_value)
            return {"success": False}

        with patch.object(registry, "register", side_effect=fake_register):
            results = registry.register_session("nonexistent_session_xyz")

        # No run_info → nothing to register
        assert results == []

    def test_register_session_returns_list(self, registry):
        """register_session always returns a list."""
        db = _db_module.get_db()
        db.add_run("sess_list_check", "/script.py")

        with patch.object(
            registry, "register", return_value={"success": False, "error": "no server"}
        ):
            results = registry.register_session("sess_list_check")

        assert isinstance(results, list)

    def test_register_session_passes_session_id(self, registry):
        """register_session passes the session_id to each register call."""
        db = _db_module.get_db()
        db.add_run("sess_id_check", "/script.py")
        db.finish_run("sess_id_check", combined_hash="hashABC")

        captured_session_ids = []

        def fake_register(
            hash_value, source_type="manual", session_id="", metadata=None
        ):
            captured_session_ids.append(session_id)
            return {"success": True}

        with patch.object(registry, "register", side_effect=fake_register):
            registry.register_session("sess_id_check")

        assert all(sid == "sess_id_check" for sid in captured_session_ids)


# ---------------------------------------------------------------------------
# get_registry() — singleton factory
# ---------------------------------------------------------------------------


class TestGetRegistry:
    def test_get_registry_returns_clew_registry(self):
        """get_registry() returns a ClewRegistry instance."""
        result = get_registry()
        assert isinstance(result, ClewRegistry)

    def test_get_registry_singleton(self):
        """get_registry() returns the same instance on repeated calls
        when no arguments are provided."""
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_get_registry_new_instance_with_base_url(self):
        """Passing base_url creates a new registry instance."""
        r1 = get_registry()
        r2 = get_registry(base_url="https://other.example.com")
        assert r1 is not r2

    def test_get_registry_new_instance_with_api_key(self):
        """Passing api_key creates a new registry instance."""
        r1 = get_registry()
        r2 = get_registry(api_key="some-key")
        assert r1 is not r2

    def test_get_registry_custom_base_url(self):
        """Custom base_url is reflected in the returned instance."""
        reg = get_registry(base_url="https://custom.registry.io")
        assert "custom.registry.io" in reg.base_url

    def test_get_registry_custom_api_key(self):
        """Custom api_key is reflected in the returned instance."""
        reg = get_registry(api_key="my-custom-key")
        assert reg.api_key == "my-custom-key"


# ---------------------------------------------------------------------------
# Module-level __all__
# ---------------------------------------------------------------------------


class TestRegistryModuleAll:
    def test_all_exports(self):
        """Module exports exactly ClewRegistry and get_registry."""
        from scitex_clew._registry import __all__

        assert set(__all__) == {"ClewRegistry", "get_registry"}


# EOF
