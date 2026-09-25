from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "wealth-settings.js").read_text(encoding="utf-8")


class NotificationProviderEnabledFrontendTests(unittest.TestCase):
    def test_all_three_provider_sections_have_usage_switches(self):
        for control_id in (
            "settingsTelegramEnabled",
            "settingsDiscordEnabled",
            "settingsKakaoEnabled",
        ):
            self.assertIn(f'id="{control_id}"', HTML)
        self.assertGreaterEqual(HTML.count("<span>사용</span>"), 3)

    def test_provider_switches_are_rendered_from_notification_settings(self):
        self.assertIn(
            "byId('settingsDiscordEnabled').checked = data.discord?.enabled === true;",
            JS,
        )
        self.assertIn(
            "byId('settingsKakaoEnabled').checked = data.kakao?.enabled === true;",
            JS,
        )

    def test_discord_save_persists_enabled_state_without_deleting_secret(self):
        self.assertIn(
            "JSON.stringify({discord: {enabled: byId('settingsDiscordEnabled').checked}})",
            JS,
        )
        self.assertIn("/api/settings/discord/secrets", JS)

    def test_kakao_save_persists_enabled_state_without_deleting_credentials(self):
        self.assertIn(
            "JSON.stringify({kakao: {enabled: byId('settingsKakaoEnabled').checked}})",
            JS,
        )
        self.assertIn("/api/settings/kakao/secrets", JS)


if __name__ == "__main__":
    unittest.main()
