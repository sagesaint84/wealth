import re
import unittest
from pathlib import Path

from tests.test_request_state_user_id import _import_main_without_loading_real_env

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"


class ReleaseVersionTests(unittest.TestCase):
    def test_fastapi_app_version(self):
        main = _import_main_without_loading_real_env()
        self.assertEqual(getattr(main, "APP_VERSION", None), "2.1.3")
        self.assertEqual(main.app.version, "2.1.3")

    def test_index_html_version_metadata_and_cache_busting(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('<meta name="application-version" content="2.1.3" />', html)
        self.assertIn('<meta name="application-assets-revision" content="2.1.3-p0" />', html)
        self.assertIn('id="appVersionDisplay"', html)
        self.assertIn("앱 버전 v2.1.3", html)

        css_matches = re.findall(r'href="/static/([^"]+\.css)\?v=([^"]+)"', html)
        self.assertTrue(css_matches)
        for asset, version in css_matches:
            expected = {
                'wealth-financial-income-what-if.css': '2.1.0-b2',
                'wealth-ledger-ocr.css': '2.0.2-review1',
                "wealth-color-preferences.css": "10.9r6",
                "wealth-color-picker.css": "10.9r2",
                "wealth-layout.css": "2.1.3-home-tabs1",
                "wealth-savings-contributions.css": "10.9p",
                "wealth-dialog-system.css": "2.0.3-ai1",
                "wealth-ui-density.css": "2.1.3-uiux1",
                "wealth-national-pension.css": "2.0.2-r2",
                "wealth-overrides.css": "10.9h1",
            }.get(asset, "1.3.0")
            self.assertEqual(version, expected)

        js_matches = re.findall(r'src="/static/([^"]+\.js)\?v=([^"]+)"', html)
        self.assertTrue(js_matches)
        versions = {
            'wealth-ipo.js': '2.1.3-ipo-naver1',
            'wealth-ledger-ocr.js': '2.0.2-review2',
            'wealth-money-input.js': '2.1.3-ui-cleanup1',
            "wealth-financial-income-what-if.js": "2.1.3-p0",
            "wealth-dividend-source.js": "2.1.0-b2",
            "wealth-family-financial-income-risk.js": "2.1.3-p0",
            "wealth.js": "2.1.3-ui-icons-rate1", "wealth-layout.js": "2.1.3-home-tabs1",
            "wealth-national-pension.js": "2.0.2", "wealth-pension-import.js": "2.0.2",
            "wealth-transaction-defaults.js": "2.0.1",
            "wealth-color-preferences.js": "10.9r6", "wealth-planning.js": "2.1.3-home-tabs1",
            "wealth-calendar.js": "2.1.2-ipo-ui1", "wealth-color-picker.js": "10.9r5",
            "wealth-planning-model.js": "2.1.3-p0", "wealth-asset-category-state.js": "2.0.2",
            "wealth-settings-surface.js": "2.1.3-uiux1", "wealth-invest-tab-state.js": "10.9k1",
            "wealth-settings.js": "10.9h1", "wealth-family-financial-income-allocation.js": "2.1.3-p0",
        }
        for asset, version in js_matches:
            self.assertEqual(version, versions.get(asset, "1.3.0"))

    def test_service_worker_cache_name(self):
        sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
        self.assertIn('const CACHE_NAME = "wealth-cache-v2.1.3-p0";', sw)

    def test_documentation_version_sync(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("# Wealth 사용 설명서", readme)
        self.assertIn("## 1. 처음 시작하는 순서", readme)
        self.assertIn("## 7. 설정", readme)
        self.assertIn("issues/176", readme)
        self.assertNotIn("## 현재 운영 배포", readme)

        archived = (ROOT / "docs" / "README_OPERATIONS_ARCHIVE.md").read_text(encoding="utf-8")
        self.assertIn("2026-10-24 / Wealth v2.1.3", archived)
        self.assertIn("**Wealth v2.1.3**", archived)
        self.assertIn("**Wealth v2.1.2**", archived)
        self.assertIn("**Wealth v2.1.0**", archived)

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## 2026-10-22 — Wealth v2.1.3 P0 출시·Oracle 배포", changelog)
        self.assertIn("## Wealth v2.1.2", changelog)
        self.assertIn("## Wealth v2.1.0", changelog)
        self.assertIn("## Wealth v2.0.3", changelog)
        self.assertIn("## Wealth v2.0.2", changelog)
        self.assertIn("## Wealth v2.0.1 — Toss Account Layout and Insurance Display", changelog)
        self.assertIn("## Wealth v2.0.0 — UI Finish and ARM64 Toss Authentication — 2026-10-13", changelog)
        self.assertIn("## Wealth v1.3.0 \u2014 MoneyLog Calendar and Multi-Source IPO Integration \u2014 2026-09-19", changelog)
        self.assertIn("## Wealth v1.2.7 \u2014 Docker Build Security Hardening \u2014 2026-09-18", changelog)
        self.assertIn("## Wealth v1.2.6 \u2014 All-Owner Snapshot Coordination and Daily Close Automation \u2014 2026-09-18", changelog)
        self.assertIn("## Wealth v1.2.5 — Stock Record Accuracy and Performance Semantics — 2026-09-18", changelog)
        self.assertIn("## Wealth v1.2.4 \u2014 Strategy Bucket Color Clarity \u2014 2026-09-17", changelog)
        self.assertIn("## Wealth v1.2.3 — KB Empty Balance Compatibility — 2026-09-17", changelog)
        self.assertIn("## Wealth v1.2.2 — Broker Sync Reliability — 2026-09-17", changelog)


if __name__ == "__main__":
    unittest.main()
