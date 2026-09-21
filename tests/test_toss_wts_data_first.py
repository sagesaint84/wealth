import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import system_settings
from app.services.toss_wts_adapter import TossWtsConfig
from app.services.toss_wts_feed_auth import (
    AUTHORIZED,
    INVALID_CONFIGURATION,
    NOT_CONFIGURED,
    check_wts_feed_static_authorization,
)


class TossWtsDataFirstTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = self.root / "system" / "settings.json"
        self.user_id = "123e4567-e89b-42d3-a456-426614174000"
        self.env = {
            "WEALTH_DATA_DIR": str(self.root),
            "WEALTH_TOSS_WTS_ENABLED": "1",
            "WEALTH_TOSSCTL_PATH": str(self.root / "env-tossctl"),
            "WEALTH_TOSSCTL_CONFIG_DIR": str(self.root / "env-config"),
            "WEALTH_TOSSCTL_EXPECTED_VERSION": "v9.9.9",
            "WEALTH_TOSSCTL_TIMEOUT_SECONDS": "33",
            "WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID": "123e4567-e89b-42d3-a456-426614174001",
        }

    def test_stored_values_drive_adapter_and_authorization(self):
        executable = self.root / "stored-tossctl"
        config_dir = self.root / "stored-config"
        system_settings.patch_system_settings({"toss_wts": {
            "enabled": True,
            "executable": str(executable),
            "config_dir": str(config_dir),
            "expected_version": "v0.50.3",
            "timeout_seconds": 9,
            "allowed_user_id": self.user_id,
        }}, path=self.settings)
        with patch.dict(os.environ, self.env, clear=False):
            config = TossWtsConfig.from_environment()
            decision = check_wts_feed_static_authorization(self.user_id)
        self.assertEqual(config.executable, executable)
        self.assertEqual(config.config_dir, config_dir)
        self.assertEqual(config.timeout_seconds, 9)
        self.assertTrue(decision.authorized)
        self.assertEqual(decision.code, AUTHORIZED)

    def test_env_fallback_and_fail_closed_authorization(self):
        with patch.dict(os.environ, self.env, clear=False):
            config = TossWtsConfig.from_environment()
        self.assertTrue(config.enabled)
        self.assertEqual(config.executable, self.root / "env-tossctl")
        no_allowed = {**self.env, "WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID": ""}
        with patch.dict(os.environ, no_allowed, clear=False):
            self.assertEqual(check_wts_feed_static_authorization(self.user_id).code, NOT_CONFIGURED)
        invalid = {**self.env, "WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID": "invalid"}
        with patch.dict(os.environ, invalid, clear=False):
            self.assertEqual(check_wts_feed_static_authorization(self.user_id).code, INVALID_CONFIGURATION)

    def test_malformed_persisted_settings_disable_adapter_and_auth(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{bad', encoding='utf-8')
        with patch.dict(os.environ, {"WEALTH_DATA_DIR": str(self.root)}, clear=False):
            self.assertFalse(TossWtsConfig.from_environment().enabled)
            self.assertEqual(check_wts_feed_static_authorization(self.user_id).code, INVALID_CONFIGURATION)
        self.assertEqual(self.settings.read_text(encoding='utf-8'), '{bad')


if __name__ == "__main__":
    unittest.main()
