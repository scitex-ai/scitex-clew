#!/usr/bin/env python3
# Timestamp: "2026-03-14 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-clew/tests/test__registry.py
"""Tests for scitex_clew._registry module (ClewRegistry)."""

from __future__ import annotations

import contextlib
import json
import os
import urllib.request

import pytest

import scitex_clew._db as _db_module
from scitex_clew._db import set_db
from scitex_clew._registry import ClewRegistry, DEFAULT_REGISTRY_URL, get_registry


# ---------------------------------------------------------------------------
# Helpers (mock-free)
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _swap_attr(obj, name, value):
    """Temporarily swap an attribute on an object, restoring it on exit."""
    saved = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, saved)


@contextlib.contextmanager
def _set_env(name, value):
    """Temporarily set an environment variable, restoring its prior state."""
    sentinel = object()
    prior = os.environ.get(name, sentinel)
    os.environ[name] = value
    try:
        yield
    finally:
        if prior is sentinel:
            os.environ.pop(name, None)
        else:
            os.environ[name] = prior


@contextlib.contextmanager
def _del_env(name):
    """Temporarily delete an environment variable, restoring it on exit."""
    sentinel = object()
    prior = os.environ.get(name, sentinel)
    os.environ.pop(name, None)
    try:
        yield
    finally:
        if prior is not sentinel:
            os.environ[name] = prior


class _FakeResponse:
    """Minimal stand-in for an HTTP response context manager."""

    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_return_value_urlopen(response):
    """Build a fake urlopen that ignores args and returns a fixed response."""

    def fake_urlopen(req, timeout=None):
        return response

    return fake_urlopen


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
        # Arrange
        # Act
        reg = ClewRegistry()
        # Assert
        assert reg.base_url == DEFAULT_REGISTRY_URL.rstrip("/")

    def test_explicit_base_url(self):
        """Explicit base_url overrides default."""
        # Arrange
        # Act
        reg = ClewRegistry(base_url="https://custom.example.com/")
        # Assert
        assert reg.base_url == "https://custom.example.com"

    def test_explicit_base_url_strips_trailing_slash(self):
        """Trailing slash is stripped from base_url."""
        # Arrange
        # Act
        reg = ClewRegistry(base_url="https://example.com///")
        # Assert
        assert not reg.base_url.endswith("/")

    def test_base_url_from_env(self):
        """SCITEX_REGISTRY_URL environment variable sets base_url."""
        # Arrange
        with _set_env("SCITEX_REGISTRY_URL", "https://env.example.com"):
            # Act
            reg = ClewRegistry()
        # Assert
        assert reg.base_url == "https://env.example.com"

    def test_explicit_base_url_overrides_env(self):
        """Explicit base_url takes precedence over env variable."""
        # Arrange
        with _set_env("SCITEX_REGISTRY_URL", "https://env.example.com"):
            # Act
            reg = ClewRegistry(base_url="https://explicit.example.com")
        # Assert
        assert reg.base_url == "https://explicit.example.com"

    def test_api_key_none_by_default(self):
        """api_key is None when not set and env var not present."""
        # Arrange
        with _del_env("SCITEX_API_KEY"):
            # Act
            reg = ClewRegistry()
        # Assert
        assert reg.api_key is None

    def test_explicit_api_key(self):
        """Explicit api_key is stored."""
        # Arrange
        # Act
        reg = ClewRegistry(api_key="my-secret-key")
        # Assert
        assert reg.api_key == "my-secret-key"

    def test_api_key_from_env(self):
        """SCITEX_API_KEY environment variable sets api_key."""
        # Arrange
        with _set_env("SCITEX_API_KEY", "env-api-key-xyz"):
            # Act
            reg = ClewRegistry()
        # Assert
        assert reg.api_key == "env-api-key-xyz"

    def test_explicit_api_key_overrides_env(self):
        """Explicit api_key takes precedence over env variable."""
        # Arrange
        with _set_env("SCITEX_API_KEY", "env-api-key"):
            # Act
            reg = ClewRegistry(api_key="explicit-key")
        # Assert
        assert reg.api_key == "explicit-key"

    def test_default_registry_url_constant(self):
        """DEFAULT_REGISTRY_URL should be the expected value."""
        # Arrange
        # Act
        # Assert
        assert DEFAULT_REGISTRY_URL == "https://scitex.ai"


# ---------------------------------------------------------------------------
# register() — HTTP failure paths (no real server)
# ---------------------------------------------------------------------------


class TestClewRegistryRegister:
    def test_register_returns_dict(self, registry):
        """register() returns a dict even when the server is unreachable."""
        # Arrange
        # Act
        result = registry.register("abc123hash")
        # Assert
        assert isinstance(result, dict)

    def test_register_failure_returns_success_false(self, registry):
        """When server is unreachable, success is False."""
        # Arrange
        # Act
        result = registry.register("abc123hash")
        # Assert
        assert result.get("success") is False

    def test_register_failure_has_error_key(self, registry):
        """Error result contains an 'error' key."""
        # Arrange
        # Act
        result = registry.register("abc123hash")
        # Assert
        assert "error" in result

    def test_register_uses_bearer_auth_header_auth_is_not_none(self, registry_with_key):
        # Arrange
        # Arrange
        # Arrange
        captured_headers = {}
        def fake_urlopen(req, timeout=None):
            captured_headers.update(req.headers)
            raise ConnectionError("not a real server")
        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry_with_key.register("somehash")
        # Act
        # Act
        auth = captured_headers.get("Authorization") or captured_headers.get(
            "authorization"
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert auth is not None

    def test_register_uses_bearer_auth_header_test_api_key_abc_in_auth(self, registry_with_key):
        # Arrange
        # Arrange
        # Arrange
        captured_headers = {}
        def fake_urlopen(req, timeout=None):
            captured_headers.update(req.headers)
            raise ConnectionError("not a real server")
        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry_with_key.register("somehash")
        # Act
        # Act
        auth = captured_headers.get("Authorization") or captured_headers.get(
            "authorization"
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert "test-api-key-abc" in auth


    def test_register_no_auth_header_without_key(self):
        """When no api_key, no Authorization header is sent."""
        # Arrange
        captured_headers = {}

        def fake_urlopen(req, timeout=None):
            captured_headers.update(req.headers)
            raise ConnectionError("not a real server")

        reg = ClewRegistry(
            base_url="http://localhost:9999",
            api_key=None,
        )
        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            reg.register("somehash")

        # Authorization header should not be present
        # Act
        auth = captured_headers.get("Authorization") or captured_headers.get(
            "authorization"
        )
        # Assert
        assert auth is None

    def test_register_posts_to_correct_url_len_captured_urls_is_1(self, registry):
        # Arrange
        # Arrange
        # Arrange
        captured_urls = []
        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            raise ConnectionError("not a real server")
        # Act
        # Act
        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry.register("myhash")
        # Act
        # Assert
        # Assert
        # Assert
        assert len(captured_urls) == 1

    def test_register_posts_to_correct_url_captured_urls_0_endswith_clew_register(self, registry):
        # Arrange
        # Arrange
        # Arrange
        captured_urls = []
        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            raise ConnectionError("not a real server")
        # Act
        # Act
        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry.register("myhash")
        # Act
        # Assert
        # Assert
        # Assert
        assert captured_urls[0].endswith("/clew/register/")


    def test_register_sends_hash_in_payload_len_captured_bodies_is_1(self, registry):
        # Arrange
        # Arrange
        # Arrange
        captured_bodies = []
        def fake_urlopen(req, timeout=None):
            captured_bodies.append(req.data)
            raise ConnectionError("not a real server")
        # Act
        # Act
        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry.register("deadbeef1234")
        # Act
        # Assert
        # Assert
        # Assert
        assert len(captured_bodies) == 1

    def test_register_sends_hash_in_payload_payload_hash_deadbeef1234_len_captured_bodies_is_1(self, registry):
        # Arrange
        # Arrange
        captured_bodies = []
        def fake_urlopen(req, timeout=None):
            captured_bodies.append(req.data)
            raise ConnectionError("not a real server")
        # Act
        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry.register("deadbeef1234")
        # Act
        # Assert
        # Assert
        assert len(captured_bodies) == 1

    def test_register_sends_hash_in_payload_payload_hash_deadbeef1234_payload_hash_deadbeef1234(self, registry):
        # Arrange
        captured_bodies = []
        def fake_urlopen(req, timeout=None):
            captured_bodies.append(req.data)
            raise ConnectionError("not a real server")
        # Act
        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry.register("deadbeef1234")
        payload = json.loads(captured_bodies[0].decode()) if captured_bodies else {}
        # Assert
        assert payload.get("hash") == "deadbeef1234"



    def test_register_sends_source_type(self, registry):
        """register() includes source_type in the payload."""
        # Arrange
        captured_bodies = []

        def fake_urlopen(req, timeout=None):
            captured_bodies.append(req.data)
            raise ConnectionError("not a real server")

        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry.register("abc", source_type="file")

        # Act
        payload = json.loads(captured_bodies[0].decode())
        # Assert
        assert payload["source_type"] == "file"

    def test_register_sends_session_id(self, registry):
        """register() includes session_id in the payload."""
        # Arrange
        captured_bodies = []

        def fake_urlopen(req, timeout=None):
            captured_bodies.append(req.data)
            raise ConnectionError("not a real server")

        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry.register("abc", session_id="sess_001")

        # Act
        payload = json.loads(captured_bodies[0].decode())
        # Assert
        assert payload["session_id"] == "sess_001"

    def test_register_sends_metadata(self, registry):
        """register() includes metadata in the payload."""
        # Arrange
        captured_bodies = []

        def fake_urlopen(req, timeout=None):
            captured_bodies.append(req.data)
            raise ConnectionError("not a real server")

        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry.register("abc", metadata={"foo": "bar"})

        # Act
        payload = json.loads(captured_bodies[0].decode())
        # Assert
        assert payload["metadata"]["foo"] == "bar"

    def test_register_uses_post_method(self, registry):
        """register() sends a POST request."""
        # Arrange
        captured_methods = []

        def fake_urlopen(req, timeout=None):
            captured_methods.append(req.method)
            raise ConnectionError("not a real server")

        # Act
        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry.register("abc")

        # Assert
        assert captured_methods[0] == "POST"

    def test_register_success_parses_response_result_success_is_true(self, registry):
        # Arrange
        # Arrange
        # Arrange
        fake_response = _FakeResponse(
            json.dumps(
                {"success": True, "registered_at": "2026-03-14T12:00:00Z"}
            ).encode()
        )
        # Act
        # Act
        with _swap_attr(
            urllib.request, "urlopen", _make_return_value_urlopen(fake_response)
        ):
            result = registry.register("abc123")
        # Act
        # Assert
        # Assert
        # Assert
        assert result["success"] is True

    def test_register_success_parses_response_registered_at_in_result(self, registry):
        # Arrange
        # Arrange
        # Arrange
        fake_response = _FakeResponse(
            json.dumps(
                {"success": True, "registered_at": "2026-03-14T12:00:00Z"}
            ).encode()
        )
        # Act
        # Act
        with _swap_attr(
            urllib.request, "urlopen", _make_return_value_urlopen(fake_response)
        ):
            result = registry.register("abc123")
        # Act
        # Assert
        # Assert
        # Assert
        assert "registered_at" in result



# ---------------------------------------------------------------------------
# verify() — HTTP failure paths
# ---------------------------------------------------------------------------


class TestClewRegistryVerify:
    def test_verify_returns_dict(self, registry):
        """verify() returns a dict even when server is unreachable."""
        # Arrange
        # Act
        result = registry.verify("abc123hash")
        # Assert
        assert isinstance(result, dict)

    def test_verify_failure_has_registered_false(self, registry):
        """When server is unreachable, registered is False."""
        # Arrange
        # Act
        result = registry.verify("abc123hash")
        # Assert
        assert result.get("registered") is False

    def test_verify_failure_has_error_key(self, registry):
        """Error result contains an 'error' key."""
        # Arrange
        # Act
        result = registry.verify("abc123hash")
        # Assert
        assert "error" in result

    def test_verify_requests_correct_url_len_captured_urls_is_1(self, registry):
        # Arrange
        # Arrange
        # Arrange
        captured_urls = []
        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            raise ConnectionError("not a real server")
        # Act
        # Act
        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry.verify("deadbeef")
        # Act
        # Assert
        # Assert
        # Assert
        assert len(captured_urls) == 1

    def test_verify_requests_correct_url_clew_verify_deadbeef_in_captured_urls_0(self, registry):
        # Arrange
        # Arrange
        # Arrange
        captured_urls = []
        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            raise ConnectionError("not a real server")
        # Act
        # Act
        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry.verify("deadbeef")
        # Act
        # Assert
        # Assert
        # Assert
        assert "/clew/verify/deadbeef/" in captured_urls[0]


    def test_verify_uses_get_method(self, registry):
        """verify() sends a GET request."""
        # Arrange
        captured_methods = []

        def fake_urlopen(req, timeout=None):
            captured_methods.append(req.method)
            raise ConnectionError("not a real server")

        # Act
        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry.verify("abc")

        # Assert
        assert captured_methods[0] == "GET"

    def test_verify_sends_auth_header_with_key(self, registry_with_key):
        """verify() sends Authorization header when api_key is set."""
        # Arrange
        captured_headers = {}

        def fake_urlopen(req, timeout=None):
            captured_headers.update(req.headers)
            raise ConnectionError("not a real server")

        with _swap_attr(urllib.request, "urlopen", fake_urlopen):
            registry_with_key.verify("somehash")

        # Act
        auth = captured_headers.get("Authorization") or captured_headers.get(
            "authorization"
        )
        # Assert
        assert auth is not None

    def test_verify_success_parses_response_result_registered_is_true(self, registry):
        # Arrange
        # Arrange
        # Arrange
        fake_response = _FakeResponse(
            json.dumps(
                {"registered": True, "registrations": [{"registered_at": "2026-03-14"}]}
            ).encode()
        )
        # Act
        # Act
        with _swap_attr(
            urllib.request, "urlopen", _make_return_value_urlopen(fake_response)
        ):
            result = registry.verify("abc123")
        # Act
        # Assert
        # Assert
        # Assert
        assert result["registered"] is True

    def test_verify_success_parses_response_isinstance_result_registrations_list(self, registry):
        # Arrange
        # Arrange
        # Arrange
        fake_response = _FakeResponse(
            json.dumps(
                {"registered": True, "registrations": [{"registered_at": "2026-03-14"}]}
            ).encode()
        )
        # Act
        # Act
        with _swap_attr(
            urllib.request, "urlopen", _make_return_value_urlopen(fake_response)
        ):
            result = registry.verify("abc123")
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result["registrations"], list)



# ---------------------------------------------------------------------------
# register_session() — uses local DB
# ---------------------------------------------------------------------------


class TestClewRegistryRegisterSession:
    def test_register_session_empty_returns_empty_list(self, registry, tmp_path):
        """A session with no hashes returns empty list (no combined_hash)."""
        # Arrange
        db = _db_module.get_db()
        db.add_run("sess_empty", "/path/script.py")

        # Patch register to avoid real HTTP, count calls
        called_with = []

        def fake_register(
            hash_value, source_type="manual", session_id="", metadata=None
        ):
            called_with.append(hash_value)
            return {"success": False, "error": "no server"}

        # Act
        with _swap_attr(registry, "register", fake_register):
            results = registry.register_session("sess_empty")

        # No combined_hash set, no file hashes → zero registrations
        # Assert
        assert len(results) == 0

    def test_register_session_combined_hash_registered_combined_abc123_in_hash_types(self, registry, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        db = _db_module.get_db()
        db.add_run("sess_combo", "/path/script.py")
        db.finish_run("sess_combo", status="success", combined_hash="combined_abc123")
        called_with = []
        def fake_register(
            hash_value, source_type="manual", session_id="", metadata=None
        ):
            called_with.append((hash_value, source_type))
            return {"success": True}
        with _swap_attr(registry, "register", fake_register):
            results = registry.register_session("sess_combo")
        # At least the combined hash should be registered
        # Act
        # Act
        hash_types = dict(called_with)
        # Act
        # Assert
        # Assert
        # Assert
        assert "combined_abc123" in hash_types

    def test_register_session_combined_hash_registered_hash_types_combined_abc123_session(self, registry, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        db = _db_module.get_db()
        db.add_run("sess_combo", "/path/script.py")
        db.finish_run("sess_combo", status="success", combined_hash="combined_abc123")
        called_with = []
        def fake_register(
            hash_value, source_type="manual", session_id="", metadata=None
        ):
            called_with.append((hash_value, source_type))
            return {"success": True}
        with _swap_attr(registry, "register", fake_register):
            results = registry.register_session("sess_combo")
        # At least the combined hash should be registered
        # Act
        # Act
        hash_types = dict(called_with)
        # Act
        # Assert
        # Assert
        # Assert
        assert hash_types["combined_abc123"] == "session"


    def test_register_session_nonexistent_session(self, registry):
        """A nonexistent session results in zero registrations."""
        # Arrange
        called_with = []

        def fake_register(
            hash_value, source_type="manual", session_id="", metadata=None
        ):
            called_with.append(hash_value)
            return {"success": False}

        # Act
        with _swap_attr(registry, "register", fake_register):
            results = registry.register_session("nonexistent_session_xyz")

        # No run_info → nothing to register
        # Assert
        assert results == []

    def test_register_session_returns_list(self, registry):
        """register_session always returns a list."""
        # Arrange
        db = _db_module.get_db()
        db.add_run("sess_list_check", "/script.py")

        def fake_register(*args, **kwargs):
            return {"success": False, "error": "no server"}

        # Act
        with _swap_attr(registry, "register", fake_register):
            results = registry.register_session("sess_list_check")

        # Assert
        assert isinstance(results, list)

    def test_register_session_passes_session_id(self, registry):
        """register_session passes the session_id to each register call."""
        # Arrange
        db = _db_module.get_db()
        db.add_run("sess_id_check", "/script.py")
        db.finish_run("sess_id_check", combined_hash="hashABC")

        captured_session_ids = []

        def fake_register(
            hash_value, source_type="manual", session_id="", metadata=None
        ):
            captured_session_ids.append(session_id)
            return {"success": True}

        # Act
        with _swap_attr(registry, "register", fake_register):
            registry.register_session("sess_id_check")

        # Assert
        assert all(sid == "sess_id_check" for sid in captured_session_ids)


# ---------------------------------------------------------------------------
# get_registry() — singleton factory
# ---------------------------------------------------------------------------


class TestGetRegistry:
    def test_get_registry_returns_clew_registry(self):
        """get_registry() returns a ClewRegistry instance."""
        # Arrange
        # Act
        result = get_registry()
        # Assert
        assert isinstance(result, ClewRegistry)

    def test_get_registry_singleton(self):
        """get_registry() returns the same instance on repeated calls
        when no arguments are provided."""
        # Arrange
        r1 = get_registry()
        # Act
        r2 = get_registry()
        # Assert
        assert r1 is r2

    def test_get_registry_new_instance_with_base_url(self):
        """Passing base_url creates a new registry instance."""
        # Arrange
        r1 = get_registry()
        # Act
        r2 = get_registry(base_url="https://other.example.com")
        # Assert
        assert r1 is not r2

    def test_get_registry_new_instance_with_api_key(self):
        """Passing api_key creates a new registry instance."""
        # Arrange
        r1 = get_registry()
        # Act
        r2 = get_registry(api_key="some-key")
        # Assert
        assert r1 is not r2

    def test_get_registry_custom_base_url(self):
        """Custom base_url is reflected in the returned instance."""
        # Arrange
        # Act
        reg = get_registry(base_url="https://custom.registry.io")
        # Assert
        assert "custom.registry.io" in reg.base_url

    def test_get_registry_custom_api_key(self):
        """Custom api_key is reflected in the returned instance."""
        # Arrange
        # Act
        reg = get_registry(api_key="my-custom-key")
        # Assert
        assert reg.api_key == "my-custom-key"


# ---------------------------------------------------------------------------
# Module-level __all__
# ---------------------------------------------------------------------------


class TestRegistryModuleAll:
    def test_all_exports_set_all_clewregistry_get_registry(self):
        """Module exports exactly ClewRegistry and get_registry."""
        # Arrange
        # Act
        from scitex_clew._registry import __all__

        # Assert
        assert set(__all__) == {"ClewRegistry", "get_registry"}


# EOF
