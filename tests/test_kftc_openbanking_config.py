import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import kftc_openbanking_config as cfg


class KftcOpenBankingConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "kftc_openbanking.json"

    def test_default_unconfigured_and_env_fallback(self):
        with patch.dict(
            os.environ,
            {
                "KFTC_OPENBANKING_CLIENT_ID": "env-id",
                "KFTC_OPENBANKING_CLIENT_SECRET": "env-secret",
                "KFTC_OPENBANKING_CLIENT_USE_CODE": "env-use-code",
                "KFTC_OPENBANKING_ENVIRONMENT": "production",
            },
            clear=False,
        ):
            eff = cfg.get_effective_kftc_config(path=self.path)
            self.assertEqual(eff["client_id"], "env-id")
            self.assertEqual(eff["client_secret"], "env-secret")
            self.assertEqual(eff["client_use_code"], "env-use-code")
            self.assertEqual(eff["environment"], "production")
            self.assertEqual(eff["sources"]["client_id"], "environment")

    def test_stored_wins_over_env(self):
        cfg.patch_kftc_config(
            {
                "enabled": True,
                "environment": "test",
                "client_id": "stored-id",
                "client_secret": "stored-secret",
                "client_use_code": "stored-code",
                "allowed_users": ["alice", "bob"],
            },
            path=self.path,
        )
        with patch.dict(
            os.environ,
            {
                "KFTC_OPENBANKING_CLIENT_ID": "env-id",
                "KFTC_OPENBANKING_CLIENT_SECRET": "env-secret",
            },
            clear=False,
        ):
            eff = cfg.get_effective_kftc_config(path=self.path)
            self.assertEqual(eff["client_id"], "stored-id")
            self.assertEqual(eff["client_secret"], "stored-secret")
            self.assertEqual(eff["sources"]["client_id"], "stored")
            self.assertTrue(eff["enabled"])
            self.assertEqual(eff["allowed_users"], ["alice", "bob"])

    def test_admin_status_masks_secret(self):
        cfg.patch_kftc_config(
            {
                "enabled": True,
                "environment": "test",
                "client_id": "my-id",
                "client_secret": "super-secret-key",
            },
            path=self.path,
        )
        status = cfg.get_kftc_admin_status(current_role="admin", path=self.path)
        self.assertTrue(status["enabled"])
        self.assertTrue(status["client_secret_configured"])
        self.assertNotIn("client_secret", status)
        self.assertNotIn("super-secret-key", str(status))

    def test_environment_and_host_isolation(self):
        self.assertEqual(cfg.get_kftc_host("production"), "https://openapi.openbanking.or.kr")
        self.assertEqual(cfg.get_kftc_host("test"), "https://testapi.openbanking.or.kr")
        with self.assertRaises(cfg.KftcConfigError):
            cfg.get_kftc_host("invalid_env")
        with self.assertRaises(cfg.KftcConfigError):
            cfg.get_kftc_host("http://attacker.com")

    def test_callback_url_from_public_base_url(self):
        cb = cfg.get_kftc_callback_url(public_base_url="https://wealth-sage.duckdns.org")
        self.assertEqual(cb, "https://wealth-sage.duckdns.org/api/kftc/openbanking/oauth/callback")

    def test_callback_url_fails_closed_without_public_base_url(self):
        with patch("app.services.kftc_openbanking_config.get_effective_system_settings", return_value={"public_base_url": None}):
            with self.assertRaises(cfg.KftcConfigError):
                cfg.get_kftc_callback_url(public_base_url=None)

    def test_allowed_users_filtering(self):
        cfg.patch_kftc_config(
            {"enabled": True, "allowed_users": ["alice"]},
            path=self.path,
        )
        self.assertTrue(cfg.is_user_allowed_kftc("alice", path=self.path))
        self.assertFalse(cfg.is_user_allowed_kftc("bob", path=self.path))

    def test_corrupt_file_fails_closed(self):
        self.path.write_text("{invalid json", encoding="utf-8")
        with self.assertRaises(cfg.KftcConfigError):
            cfg.load_kftc_config(path=self.path)


if __name__ == "__main__":
    unittest.main()
