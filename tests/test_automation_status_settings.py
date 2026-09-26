from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import settings


class AutomationStatusSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "settings.json"

    def test_effective_settings_exposes_read_only_status_by_default(self):
        status = {
            "version": 1,
            "counts": {"enabled": 3},
            "jobs": [],
            "recent": [],
        }
        with patch(
            "app.services.automation.status.build_automation_status",
            return_value=status,
        ) as build:
            result = settings.get_effective_settings("alice", path=self.path)

        self.assertEqual(result["automation"]["_status"], status)
        build.assert_called_once()
        self.assertEqual(build.call_args.args[0], "alice")
        self.assertIs(build.call_args.kwargs["settings"], result)
        self.assertFalse(self.path.exists())

    def test_internal_callers_can_skip_operational_status(self):
        with patch(
            "app.services.automation.status.build_automation_status"
        ) as build:
            result = settings.get_effective_settings(
                "alice",
                path=self.path,
                include_automation_status=False,
            )
        build.assert_not_called()
        self.assertNotIn("_status", result["automation"])

    def test_status_failure_never_breaks_settings(self):
        with patch(
            "app.services.automation.status.build_automation_status",
            side_effect=RuntimeError("SECRET path/token failure"),
        ):
            result = settings.get_effective_settings("alice", path=self.path)
        self.assertEqual(
            result["automation"]["_status"]["code"],
            "AUTOMATION_STATUS_UNAVAILABLE",
        )
        self.assertTrue(result["automation"]["_status"]["unavailable"])
        self.assertNotIn("SECRET", json.dumps(result))

    def test_status_projection_is_never_persisted(self):
        with patch(
            "app.services.automation.status.build_automation_status",
            return_value={"version": 1, "jobs": [], "recent": []},
        ):
            settings.patch_settings(
                "alice",
                {"automation": {"daily_close": {"time": "20:31"}}},
                path=self.path,
            )
        raw = self.path.read_text(encoding="utf-8")
        self.assertNotIn('"_status"', raw)
        self.assertEqual(
            json.loads(raw)["automation"]["daily_close"]["time"],
            "20:31",
        )


if __name__ == "__main__":
    unittest.main()
