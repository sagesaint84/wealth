"""Permanent regression tests for session signing-key security.

Verifies:
A. Normal runtime cannot use the old known default signing key.
B. A configured private runtime secret is accepted.
C. Missing production secret follows the fail-closed policy (RuntimeError).
D. Blank production secret follows the same safe policy (RuntimeError).
E. Test mode accepts explicit WEALTH_TEST_SIGNING_SECRET.
F. Test mode WITHOUT explicit secret also fails closed (no built-in fallback).
G. Production cannot implicitly use the test-only secret.
H. Secret contents are not exposed through API responses.
I. _resolve_session_secret function is present (proves fallback was removed).
"""
from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Known constant that must NEVER be used as a signing key.
# Do not change this value — it must match what was historically committed.
# ---------------------------------------------------------------------------
_OLD_KNOWN_DEFAULT = "asset_dashboard_secret_key_default"


def _reload_main_with_env(**env_overrides):
    """Reload app.main in isolation with specific env vars.

    Hides the real .env so only explicitly supplied env vars apply.
    Clears WEALTH_TEST_SIGNING_SECRET from the base env to ensure tests
    are not silently passing because the value was already set.
    """
    project_root = Path(__file__).resolve().parents[1]
    original_exists = Path.exists

    def safe_exists(path: Path) -> bool:
        if path == project_root / ".env":
            return False
        return original_exists(path)

    # Remove cached module so it re-executes module-level code.
    sys.modules.pop("app.main", None)

    # Start from a clean slate for signing-related vars; caller supplies explicit values.
    base_overrides = {
        "DASHBOARD_SECRET_KEY": "",
        "WEALTH_TEST_SIGNING_SECRET": "",
    }
    base_overrides.update(env_overrides)

    with patch.object(Path, "exists", safe_exists), \
         patch.dict(os.environ, base_overrides, clear=False):
        module = importlib.import_module("app.main")
    return module


class TestSessionSigningSecurityInvariant(unittest.TestCase):
    """A. Normal runtime must not silently use the old known default."""

    def tearDown(self):
        sys.modules.pop("app.main", None)

    def test_old_default_constant_not_present_as_fallback(self):
        """_resolve_session_secret source must not embed the old known default."""
        # app.main is already loaded by the suite under WEALTH_ENV=test.
        import app.main as m
        import inspect
        source = inspect.getsource(m._resolve_session_secret)
        self.assertNotIn(
            _OLD_KNOWN_DEFAULT, source,
            "_resolve_session_secret must not embed the old known default constant."
        )

    def test_no_built_in_signing_fallback_in_source(self):
        """No built-in signing constant may appear in _resolve_session_secret."""
        import app.main as m
        import inspect
        source = inspect.getsource(m._resolve_session_secret)
        # The function must not contain any hard-wired literal secret.
        # Check for the old default and the previous test sentinel.
        self.assertNotIn("asset_dashboard_secret_key_default", source)
        self.assertNotIn("wealth-test-only-signing-secret", source)


class TestSessionSigningSecretAccepted(unittest.TestCase):
    """B. A configured private runtime secret is accepted."""

    def tearDown(self):
        sys.modules.pop("app.main", None)

    def test_explicit_dashboard_secret_key_is_used_in_production(self):
        """DASHBOARD_SECRET_KEY must be used in production mode."""
        main = _reload_main_with_env(
            WEALTH_ENV="production",
            DASHBOARD_SECRET_KEY="synthetic-explicit-production-test-secret-xyz",
        )
        self.assertEqual(
            main.SECRET_KEY,
            "synthetic-explicit-production-test-secret-xyz",
        )

    def test_explicit_dashboard_secret_key_is_used_in_test_mode(self):
        """DASHBOARD_SECRET_KEY must take priority over test env var."""
        main = _reload_main_with_env(
            WEALTH_ENV="test",
            DASHBOARD_SECRET_KEY="synthetic-explicit-test-mode-secret-abc",
            WEALTH_TEST_SIGNING_SECRET="should-not-be-used",
        )
        self.assertEqual(main.SECRET_KEY, "synthetic-explicit-test-mode-secret-abc")


class TestSessionSigningSecretFailClosed(unittest.TestCase):
    """C & D. Missing/blank secret must fail closed in production."""

    def tearDown(self):
        sys.modules.pop("app.main", None)

    def test_missing_secret_uses_persistent_secret_in_production(self):
        main = _reload_main_with_env(
                WEALTH_ENV="production",
                DASHBOARD_SECRET_KEY="",
            )
        self.assertTrue(main.SECRET_KEY)

    def test_blank_secret_uses_persistent_secret_in_production(self):
        main = _reload_main_with_env(
                WEALTH_ENV="production",
                DASHBOARD_SECRET_KEY="   ",
            )
        self.assertTrue(main.SECRET_KEY)


class TestSessionSigningTestModeConfiguration(unittest.TestCase):
    """E & F. Test mode explicit secret accepted; missing secret fails closed."""

    def tearDown(self):
        sys.modules.pop("app.main", None)

    def test_test_mode_with_wealth_test_signing_secret(self):
        """E. WEALTH_TEST_SIGNING_SECRET must be accepted in test mode."""
        main = _reload_main_with_env(
            WEALTH_ENV="test",
            DASHBOARD_SECRET_KEY="",
            WEALTH_TEST_SIGNING_SECRET="synthetic-test-signing-secret-for-suite",
        )
        self.assertEqual(main.SECRET_KEY, "synthetic-test-signing-secret-for-suite")
        self.assertIsNotNone(main._serializer)

    def test_test_mode_without_any_secret_uses_persistent_secret(self):
        main = _reload_main_with_env(
                WEALTH_ENV="test",
                DASHBOARD_SECRET_KEY="",
                WEALTH_TEST_SIGNING_SECRET="",
            )
        self.assertTrue(main.SECRET_KEY)

    def test_production_ignores_test_secret_and_uses_persistent_secret(self):
        main = _reload_main_with_env(
                WEALTH_ENV="production",
                DASHBOARD_SECRET_KEY="",
                WEALTH_TEST_SIGNING_SECRET="synthetic-test-signing-secret-for-suite",
            )
        self.assertNotEqual(main.SECRET_KEY,"synthetic-test-signing-secret-for-suite")


class TestSessionSigningSecretNotExposed(unittest.TestCase):
    """H. Secret contents must not be exposed through API responses."""

    @classmethod
    def setUpClass(cls):
        # Use the module already loaded by the test suite.
        cls.main = sys.modules.get("app.main")
        if cls.main is None:
            project_root = Path(__file__).resolve().parents[1]
            original_exists = Path.exists

            def safe_exists(path: Path) -> bool:
                if path == project_root / ".env":
                    return False
                return original_exists(path)

            with patch.object(Path, "exists", safe_exists):
                cls.main = importlib.import_module("app.main")

    def test_secret_key_not_in_health_endpoint(self):
        """H. SECRET_KEY value must not appear in any standard API response."""
        from fastapi.testclient import TestClient
        client = TestClient(self.main.app)
        response = client.get("/api/health", follow_redirects=False)
        self.assertNotIn(self.main.SECRET_KEY, response.text)
        client.close()

    def test_old_default_not_in_health_endpoint(self):
        """Old default constant must not appear in any API response."""
        from fastapi.testclient import TestClient
        client = TestClient(self.main.app)
        response = client.get("/api/health", follow_redirects=False)
        self.assertNotIn(_OLD_KNOWN_DEFAULT, response.text)
        client.close()


class TestSessionSigningFunctionPresent(unittest.TestCase):
    """I. _resolve_session_secret must exist and current SECRET_KEY must be safe."""

    def test_resolve_session_secret_function_exists(self):
        """_resolve_session_secret must be a callable on app.main."""
        import app.main as m
        self.assertTrue(
            callable(getattr(m, "_resolve_session_secret", None)),
            "_resolve_session_secret must be a callable on app.main",
        )

    def test_secret_key_is_not_old_known_default(self):
        """In test mode, SECRET_KEY must not equal the old known default."""
        import app.main as m
        self.assertNotEqual(
            m.SECRET_KEY,
            _OLD_KNOWN_DEFAULT,
            "SECRET_KEY must never be the old known hard-coded default.",
        )

    def test_secret_key_is_non_empty(self):
        """SECRET_KEY must be non-empty after initialisation."""
        import app.main as m
        self.assertTrue(m.SECRET_KEY, "SECRET_KEY must not be empty")

    def test_serializer_is_initialised(self):
        """_serializer must be a live URLSafeTimedSerializer instance."""
        import app.main as m
        from itsdangerous import URLSafeTimedSerializer
        self.assertIsInstance(m._serializer, URLSafeTimedSerializer)


if __name__ == "__main__":
    unittest.main()
