from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "wealth-settings.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "wealth-overrides.css").read_text(encoding="utf-8")


class NotificationHistoryFrontendTests(unittest.TestCase):
    def test_history_section_has_refresh_clear_summary_and_list(self):
        for element_id in (
            "notificationHistoryTitle",
            "settingsNotificationHistoryRefresh",
            "settingsNotificationHistoryClear",
            "settingsNotificationHistorySummary",
            "settingsNotificationHistoryList",
            "settingsNotificationHistoryError",
        ):
            self.assertIn(f'id="{element_id}"', HTML)
        self.assertIn("메시지 본문과 비밀정보는 저장하지 않습니다.", HTML)

    def test_settings_reload_treats_history_as_non_fatal(self):
        self.assertIn(
            "api('/api/settings/notifications/history?limit=20').catch(",
            JS,
        )
        self.assertIn("renderNotificationHistory(history);", JS)
        self.assertIn("unavailable: true", JS)

    def test_history_rendering_uses_text_content_not_server_html(self):
        self.assertIn("function renderNotificationHistory(data)", JS)
        self.assertIn("title.textContent =", JS)
        self.assertIn("pill.textContent =", JS)
        history_render = JS.split(
            "function renderNotificationHistory(data)", 1
        )[1].split("async function reloadNotificationHistory()", 1)[0]
        self.assertNotIn("innerHTML", history_render)

    def test_history_refresh_and_clear_api_contract(self):
        self.assertIn(
            "api('/api/settings/notifications/history?limit=20')",
            JS,
        )
        self.assertIn(
            "api('/api/settings/notifications/history', {method: 'DELETE'})",
            JS,
        )
        self.assertIn(
            "settingsNotificationHistoryRefresh",
            JS,
        )
        self.assertIn(
            "settingsNotificationHistoryClear",
            JS,
        )

    def test_history_styles_cover_status_and_mobile_safe_layout(self):
        for css_class in (
            ".settings-history-list",
            ".settings-history-item",
            ".settings-history-badge",
            ".settings-history-providers",
            ".settings-history-provider",
        ):
            self.assertIn(css_class, CSS)


if __name__ == "__main__":
    unittest.main()
