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

    def test_settings_help_text_uses_muted_compact_typography(self):
        for text in (
            "Kakao Developers에 아래 Redirect URI를 등록하고",
            "남은 세션 시간이 기준값 이내이면 Wealth가 Toss 세션 연장을 요청합니다.",
            "세션이 없거나 만료된 경우 내 Toss WTS 계정을 QR 코드로 인증하거나 재인증할 수 있습니다.",
        ):
            self.assertIn(text, HTML)
        self.assertIn(".settings-dialog .settings-help", CSS)
        self.assertIn("font-size:12px!important", CSS)
        self.assertIn("font-weight:400!important", CSS)
        self.assertIn("line-height:1.6!important", CSS)
        self.assertIn("color:var(--muted,#91a0c1)", CSS)
        self.assertIn(
            '[data-theme="white"] .settings-dialog .settings-help{color:#64748b}',
            CSS,
        )

    def test_notification_dialog_mentions_all_three_providers(self):
        self.assertIn("Telegram·Discord·카카오 알림", HTML)


if __name__ == "__main__":
    unittest.main()
