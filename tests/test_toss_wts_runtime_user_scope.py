from __future__ import annotations

import inspect
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.services.toss_wts_feed_auth import WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID
from app.services.toss_wts_feed_runtime import (
    CONFIRMED,
    RUNTIME_GENERATION_CHANGED,
    check_wts_feed_runtime_confirmation_for_username,
    clear_wts_feed_runtime_confirmation,
    confirm_wts_feed_runtime_session,
    confirm_wts_feed_runtime_session_for_username,
)
from app.services.user_identity import generate_user_id


class TossWtsRuntimeUserScopeTests(unittest.TestCase):
    def setUp(self):
        clear_wts_feed_runtime_confirmation()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(clear_wts_feed_runtime_confirmation)

        root = Path(self.temp.name)
        self.exe = root / "tossctl"
        self.exe.write_text("synthetic", encoding="utf-8")

        self.global_config = root / "global-config"
        self.global_config.mkdir()
        self.global_session = self.global_config / "session.json"
        self.global_session.write_text("global", encoding="utf-8")

        self.user_config = root / "toss-wts" / "users" / "alice" / "config"
        self.user_config.mkdir(parents=True)
        self.user_session = self.user_config / "session.json"
        self.user_session.write_text("alice-v1", encoding="utf-8")

        self.user_id = generate_user_id()
        self.env = {
            WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: self.user_id,
            "WEALTH_TOSS_WTS_ENABLED": "1",
            "WEALTH_TOSSCTL_PATH": str(self.exe),
            "WEALTH_TOSSCTL_CONFIG_DIR": str(self.global_config),
            "WEALTH_DATA_DIR": str(root),
        }

    def test_legacy_signature_is_preserved(self):
        self.assertEqual(
            list(inspect.signature(confirm_wts_feed_runtime_session).parameters),
            ["user_id"],
        )

    def test_scoped_confirmation_tracks_user_session_not_global_session(self):
        with patch.dict(os.environ, self.env, clear=False):
            confirmed = confirm_wts_feed_runtime_session_for_username(
                self.user_id, "alice"
            )
            self.assertTrue(confirmed.confirmed)
            self.assertEqual(confirmed.code, CONFIRMED)

            self.global_session.write_text("global-changed", encoding="utf-8")
            still_confirmed = check_wts_feed_runtime_confirmation_for_username(
                self.user_id, "alice"
            )
            self.assertTrue(still_confirmed.confirmed)

            self.user_session.write_text("alice-v2-longer", encoding="utf-8")
            changed = check_wts_feed_runtime_confirmation_for_username(
                self.user_id, "alice"
            )
            self.assertFalse(changed.confirmed)
            self.assertEqual(changed.code, RUNTIME_GENERATION_CHANGED)


if __name__ == "__main__":
    unittest.main()
