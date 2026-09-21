import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import user_openapi


class UserOpenApiPermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.users = Path(self.temp.name) / "users"
        self.patch = patch.object(user_openapi, "USERS_DIR", self.users)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.config_patch = patch.object(
            user_openapi,
            "get_user_openapi_config",
            return_value={
                "toss": {"app_key": "", "app_secret": ""},
                "kb": {"app_key": "", "app_secret": "", "gnl_ac_no": "", "gds_no": ""},
                "nh": {"app_key": "", "app_secret": ""},
                "kis": {"app_key": "", "app_secret": "", "account_no": ""},
                "kiwoom": {"app_key": "", "app_secret": "", "account_no": ""},
            },
        )
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)

    def test_save_is_atomic_and_posix_mode_is_restrictive(self):
        user_openapi.save_user_openapi_config("testuser", {
            "kis": {"app_key": "fixture-key", "app_secret": "fixture-secret", "account_no": ""}
        })
        target = self.users / "testuser" / "openapi_config.json"
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["kis"]["app_key"], "fixture-key")
        self.assertFalse(list(target.parent.glob(".openapi_config.json.*.tmp")))
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_replace_failure_preserves_existing_file(self):
        user_openapi.save_user_openapi_config("testuser", {
            "toss": {"app_key": "old-key", "app_secret": "old-secret"}
        })
        target = self.users / "testuser" / "openapi_config.json"
        before = target.read_bytes()
        with patch("app.services.secure_files.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                user_openapi.save_user_openapi_config("testuser", {
                    "toss": {"app_key": "new-key", "app_secret": "new-secret"}
                })
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(list(target.parent.glob(".openapi_config.json.*.tmp")))

    def test_delete_update_path_keeps_private_mode(self):
        user_openapi.save_user_openapi_config("testuser", {
            "kb": {"app_key": "fixture-key", "app_secret": "fixture-secret", "account_no": ""}
        })
        user_openapi.delete_user_broker_openapi("testuser", "kb")
        target = self.users / "testuser" / "openapi_config.json"
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["kb"]["app_secret"], "")
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
