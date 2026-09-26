from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_JS = (ROOT / "app" / "static" / "wealth-automation-status.js").read_text(
    encoding="utf-8"
)
LAYOUT_JS = (ROOT / "app" / "static" / "wealth-layout.js").read_text(
    encoding="utf-8"
)


class AutomationStatusFrontendTests(unittest.TestCase):
    def test_layout_loads_status_module_without_changing_app_version(self):
        self.assertIn(
            "import('/static/wealth-automation-status.js?v=1.3.0')",
            LAYOUT_JS,
        )

    def test_status_panel_covers_all_operational_health_states(self):
        for label in (
            "정상",
            "실패",
            "실행 중",
            "멈춤 의심",
            "실행 누락",
            "실행 이력 없음",
            "사용 안 함",
            "미설정",
            "확인 필요",
        ):
            self.assertIn(label, STATUS_JS)
        self.assertIn("자동화 실행 상태", STATUS_JS)
        self.assertIn("최근 실행 기록", STATUS_JS)
        self.assertIn("다음 예정", STATUS_JS)
        self.assertIn("시도 횟수", STATUS_JS)

    def test_status_refresh_uses_authenticated_same_origin_settings_endpoint(self):
        self.assertIn("getJson('/api/settings/automation')", STATUS_JS)
        self.assertIn("credentials: 'same-origin'", STATUS_JS)
        self.assertNotIn("window.api", STATUS_JS)
        self.assertIn("settingsAutomationStatusRefresh", STATUS_JS)
        self.assertIn("automation._status", STATUS_JS)

    def test_server_values_are_rendered_as_text_not_html(self):
        render_job = STATUS_JS.split("function renderJob(job)", 1)[1].split(
            "function renderRecent", 1
        )[0]
        render_recent = STATUS_JS.split("function renderRecent(items)", 1)[1].split(
            "function renderStatus", 1
        )[0]
        render_status = STATUS_JS.split("function renderStatus(status)", 1)[1].split(
            "async function refreshStatus", 1
        )[0]
        for section in (render_job, render_recent, render_status):
            self.assertNotIn("innerHTML", section)
            self.assertIn("textContent", section)

    def test_status_module_is_non_fatal_and_mobile_responsive(self):
        self.assertIn(".catch(() => {})", LAYOUT_JS)
        self.assertIn("@media(max-width:620px)", STATUS_JS)
        self.assertIn("grid-template-columns:1fr", STATUS_JS)
        self.assertIn("AUTOMATION_STATUS_UNAVAILABLE", STATUS_JS)


if __name__ == "__main__":
    unittest.main()
