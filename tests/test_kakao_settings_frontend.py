from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "app" / "static" / "index.html"
SETTINGS_JS = ROOT / "app" / "static" / "wealth-settings.js"


class KakaoSettingsFrontendTests(unittest.TestCase):
    def test_settings_dialog_contains_kakao_controls(self):
        html = INDEX.read_text(encoding="utf-8")
        for control_id in (
            "settingsKakaoAppStatus",
            "settingsKakaoConnectionStatus",
            "settingsKakaoRedirectUri",
            "settingsKakaoConnect",
            "settingsKakaoTest",
            "settingsKakaoDisconnect",
            "settingsKakaoError",
        ):
            self.assertIn(f'id="{control_id}"', html)

    def test_settings_js_uses_same_origin_oauth_popup_message(self):
        js = SETTINGS_JS.read_text(encoding="utf-8")
        self.assertIn("/api/settings/kakao/oauth/start", js)
        self.assertIn("/api/settings/kakao/test", js)
        self.assertIn("/api/settings/kakao/disconnect", js)
        self.assertIn("event.origin !== window.location.origin", js)
        self.assertIn("wealth:kakao-oauth", js)

    def test_settings_asset_cache_key_was_bumped(self):
        html = INDEX.read_text(encoding="utf-8")
        self.assertIn('/static/wealth-settings.js?v=1.3.0', html)


if __name__ == "__main__":
    unittest.main()
