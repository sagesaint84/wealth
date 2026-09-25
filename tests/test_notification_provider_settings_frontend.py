from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/wealth-settings.js").read_text(encoding="utf-8")


class NotificationProviderSettingsFrontendTests(unittest.TestCase):
    def test_discord_secret_controls_are_wired(self):
        for control_id in (
            "settingsDiscordWebhookStatus",
            "settingsDiscordWebhookUrl",
            "settingsClearDiscordWebhook",
            "settingsDiscordTest",
            "settingsSaveDiscord",
            "settingsDiscordError",
        ):
            self.assertIn(f'id="{control_id}"', HTML)
        for endpoint in (
            "/api/settings/discord",
            "/api/settings/discord/secrets",
            "/api/settings/discord/test",
        ):
            self.assertIn(endpoint, JS)

    def test_kakao_app_secret_controls_are_wired(self):
        for control_id in (
            "settingsKakaoRestApiKeyStatus",
            "settingsKakaoRestApiKey",
            "settingsClearKakaoRestApiKey",
            "settingsKakaoClientSecretStatus",
            "settingsKakaoClientSecret",
            "settingsClearKakaoClientSecret",
            "settingsSaveKakaoSecrets",
        ):
            self.assertIn(f'id="{control_id}"', HTML)
        self.assertIn("/api/settings/kakao/secrets", JS)

    def test_new_provider_secret_values_are_never_rendered_or_persisted_client_side(self):
        self.assertNotIn(".value = data.rest_api_key", JS)
        self.assertNotIn(".value = data.client_secret", JS)
        self.assertNotIn(".value = data.webhook_url", JS)
        self.assertNotIn("localStorage", JS)
        self.assertNotIn("sessionStorage", JS)
        self.assertIn("autocomplete=\"new-password\"", HTML)
        self.assertIn("Wealth에 저장됨", JS)

    def test_notification_dialog_mentions_all_three_providers(self):
        self.assertIn("Telegram·Discord·카카오 알림", HTML)


if __name__ == "__main__":
    unittest.main()
