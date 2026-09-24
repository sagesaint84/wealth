import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import kftc_openbanking_config as cfg
from app.services import kftc_openbanking_crypto as crypto


class KftcOpenBankingConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path_alice = Path(self.tmp.name) / "alice_config.json"
        self.path_bob = Path(self.tmp.name) / "bob_config.json"

    def test_default_unconfigured(self):
        eff = cfg.get_effective_kftc_config("alice", path=self.path_alice)
        self.assertFalse(eff["enabled"])
        self.assertEqual(eff["client_id"], "")
        self.assertEqual(eff["client_secret"], "")
        self.assertEqual(eff["environment"], "test")
        self.assertFalse(eff["configured"])

    def test_patch_and_get_user_config(self):
        # Alice patches her config
        res = cfg.patch_user_kftc_config(
            "alice",
            {
                "enabled": True,
                "environment": "test",
                "client_id": "alice-id",
                "client_secret": "alice-super-secret",
                "client_use_code": "B123456789",
            },
            path=self.path_alice,
        )
        # Safe status metadata returned
        self.assertTrue(res["enabled"])
        self.assertTrue(res["client_id_configured"])
        self.assertTrue(res["client_secret_configured"])
        self.assertTrue(res["client_use_code_configured"])
        self.assertNotIn("client_secret", res)
        self.assertNotIn("alice-super-secret", str(res))

        # Check raw JSON on disk - secret MUST be encrypted
        raw_json = json.loads(self.path_alice.read_text(encoding="utf-8"))
        self.assertNotIn("alice-super-secret", str(raw_json))
        self.assertIn("client_secret_encrypted", raw_json)
        self.assertTrue(raw_json["client_secret_encrypted"])

        # Effective config internal resolution decrypts secret for service use
        eff = cfg.get_effective_kftc_config("alice", path=self.path_alice)
        self.assertEqual(eff["client_id"], "alice-id")
        self.assertEqual(eff["client_secret"], "alice-super-secret")
        self.assertEqual(eff["client_use_code"], "B123456789")
        self.assertTrue(eff["configured"])

    def test_blank_secret_and_use_code_preserves_existing(self):
        cfg.patch_user_kftc_config(
            "alice",
            {
                "enabled": True,
                "client_id": "orig-id",
                "client_secret": "orig-secret",
                "client_use_code": "B123456789",
            },
            path=self.path_alice,
        )
        # Patch with empty secret and empty use_code
        cfg.patch_user_kftc_config(
            "alice",
            {
                "client_id": "updated-id",
                "client_secret": "",
                "client_use_code": "",
            },
            path=self.path_alice,
        )
        eff = cfg.get_effective_kftc_config("alice", path=self.path_alice)
        self.assertEqual(eff["client_id"], "updated-id")
        self.assertEqual(eff["client_secret"], "orig-secret")
        self.assertEqual(eff["client_use_code"], "B123456789")

    def test_user_isolation_alice_and_bob(self):
        # Alice configures her credentials
        cfg.patch_user_kftc_config(
            "alice",
            {"enabled": True, "client_id": "alice-id", "client_secret": "alice-secret"},
            path=self.path_alice,
        )
        # Bob configures nothing
        eff_bob = cfg.get_effective_kftc_config("bob", path=self.path_bob)
        self.assertFalse(eff_bob["enabled"])
        self.assertEqual(eff_bob["client_id"], "")
        self.assertEqual(eff_bob["client_secret"], "")

        # Alice cannot access Bob's, and vice versa
        self.assertTrue(cfg.is_user_allowed_kftc("alice", path=self.path_alice))
        self.assertFalse(cfg.is_user_allowed_kftc("bob", path=self.path_bob))

    def test_same_plaintext_secret_different_users(self):
        # Both alice and bob set the identical plaintext secret
        shared_plaintext = "same-shared-secret-12345"
        cfg.patch_user_kftc_config(
            "alice",
            {"enabled": True, "client_id": "alice-id", "client_secret": shared_plaintext},
            path=self.path_alice,
        )
        cfg.patch_user_kftc_config(
            "bob",
            {"enabled": True, "client_id": "bob-id", "client_secret": shared_plaintext},
            path=self.path_bob,
        )

        eff_alice = cfg.get_effective_kftc_config("alice", path=self.path_alice)
        eff_bob = cfg.get_effective_kftc_config("bob", path=self.path_bob)

        # Both load successfully and independently
        self.assertEqual(eff_alice["client_secret"], shared_plaintext)
        self.assertEqual(eff_bob["client_secret"], shared_plaintext)

    def test_user_a_file_copied_to_user_b_fails_decryption(self):
        # Alice's config copied maliciously or erroneously to Bob's path
        cfg.patch_user_kftc_config(
            "alice",
            {"enabled": True, "client_id": "alice-id", "client_secret": "alice-secret"},
            path=self.path_alice,
        )
        # Copy alice's config directly to bob's config path
        self.path_bob.write_text(self.path_alice.read_text(encoding="utf-8"), encoding="utf-8")

        # Bob's attempt to load Alice's ciphertext fails closed because context is bound to "bob"
        with self.assertRaises(cfg.KftcConfigError) as ctx:
            cfg.get_effective_kftc_config("bob", path=self.path_bob)
        self.assertEqual(str(ctx.exception), "KFTC_CLIENT_SECRET_DECRYPT_FAILED")

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

    def test_corrupt_file_fails_closed(self):
        self.path_alice.write_text("{invalid json", encoding="utf-8")
        with self.assertRaises(cfg.KftcConfigError):
            cfg.load_user_kftc_config("alice", path=self.path_alice)


if __name__ == "__main__":
    unittest.main()
