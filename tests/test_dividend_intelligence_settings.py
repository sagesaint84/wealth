from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.services.settings import (
    SettingsValidationError,
    default_settings,
    get_effective_settings,
    patch_settings,
)


class DividendIntelligenceSettingsTests(unittest.TestCase):
    def test_default_alert_setting_is_disabled(self) -> None:
        settings = default_settings()
        self.assertEqual(
            settings["automation"]["dividend_intelligence_alerts"],
            {"enabled": False},
        )

    def test_legacy_settings_are_normalized_with_alert_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            legacy = default_settings()
            del legacy["automation"]["dividend_intelligence_alerts"]
            path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

            result = get_effective_settings(
                "tester", path=path, include_automation_status=False
            )
            self.assertEqual(
                result["automation"]["dividend_intelligence_alerts"],
                {"enabled": False},
            )

    def test_partial_patch_can_enable_alerts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            result = patch_settings(
                "tester",
                {"automation": {"dividend_intelligence_alerts": {"enabled": True}}},
                path=path,
            )
            self.assertTrue(
                result["automation"]["dividend_intelligence_alerts"]["enabled"]
            )

    def test_alert_enabled_must_be_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            with self.assertRaises(SettingsValidationError):
                patch_settings(
                    "tester",
                    {
                        "automation": {
                            "dividend_intelligence_alerts": {"enabled": "yes"}
                        }
                    },
                    path=path,
                )


if __name__ == "__main__":
    unittest.main()
