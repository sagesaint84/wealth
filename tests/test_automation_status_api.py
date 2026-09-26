from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app


class AutomationStatusApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = TestClient(app)
        self.user = patch(
            "app.services.user_manager.get_user_by_name",
            return_value={"username": "alice", "id": "a", "role": "user"},
        )
        self.user.start()
        self.addCleanup(self.user.stop)
        self.data_dir = patch(
            "app.services.settings.get_user_data_dir",
            return_value=Path(self.temp.name),
        )
        self.data_dir.start()
        self.addCleanup(self.data_dir.stop)
        self.client.cookies.set(
            main.COOKIE_NAME,
            main._serializer.dumps({"user": "alice", "role": "user"}),
        )

    def test_get_automation_includes_read_only_operational_status(self):
        status = {
            "version": 1,
            "timezone": "Asia/Seoul",
            "counts": {"enabled": 2, "success": 1, "warning": 0, "running": 0},
            "jobs": [{"job": "daily_close", "health": "success"}],
            "recent": [],
        }
        with patch(
            "app.services.automation.status.build_automation_status",
            return_value=status,
        ):
            response = self.client.get("/api/settings/automation")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["automation"]["_status"], status)

    def test_status_failure_is_non_fatal_and_secret_safe(self):
        with patch(
            "app.services.automation.status.build_automation_status",
            side_effect=RuntimeError("SECRET_TOKEN /private/path"),
        ):
            response = self.client.get("/api/settings/automation")
        self.assertEqual(response.status_code, 200)
        status = response.json()["automation"]["_status"]
        self.assertTrue(status["unavailable"])
        self.assertEqual(status["code"], "AUTOMATION_STATUS_UNAVAILABLE")
        self.assertNotIn("SECRET_TOKEN", response.text)
        self.assertNotIn("/private/path", response.text)

    def test_patch_response_may_include_status_but_never_persists_it(self):
        with patch(
            "app.services.automation.status.build_automation_status",
            return_value={"version": 1, "jobs": [], "recent": []},
        ):
            response = self.client.patch(
                "/api/settings/automation",
                json={"daily_close": {"time": "20:31"}},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("_status", response.json()["automation"])
        stored = (Path(self.temp.name) / "settings.json").read_text(encoding="utf-8")
        self.assertNotIn('"_status"', stored)

    def test_status_api_requires_existing_settings_authentication(self):
        self.client.cookies.clear()
        self.assertEqual(
            self.client.get("/api/settings/automation").status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()
