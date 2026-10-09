import re
import unittest
from pathlib import Path

from tests.test_request_state_user_id import _import_main_without_loading_real_env

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"


class ReleaseVersionTests(unittest.TestCase):
    def test_fastapi_app_version(self):
        main = _import_main_without_loading_real_env()
        self.assertEqual(getattr(main, "APP_VERSION", None), "1.3.0")
        self.assertEqual(main.app.version, "1.3.0")

    def test_index_html_version_metadata_and_cache_busting(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('<meta name="application-version" content="1.3.0" />', html)
        self.assertIn('id="appVersionDisplay"', html)
        self.assertIn("v1.3.0", html)

        css_matches = re.findall(r'href="/static/([^"]+\.css)\?v=([^"]+)"', html)
        self.assertTrue(css_matches)
        for asset, version in css_matches:
            expected = "10.9m1" if asset == "wealth-layout.css" else "10.9h1" if asset == "wealth-overrides.css" else "1.3.0"
            self.assertEqual(version, expected)

        js_matches = re.findall(r'src="/static/([^"]+\.js)\?v=([^"]+)"', html)
        self.assertTrue(js_matches)
        hotfix_assets = {"wealth-family-financial-income-allocation.js", "wealth-planning-model.js"}
        settings_assets = {"wealth-settings-surface.js", "wealth-settings.js", "wealth-layout.js", "wealth.js"}
        invest_hotfix_assets = {"wealth-invest-tab-state.js", "wealth.js", "wealth-planning.js"}
        ui_detail_assets = {"wealth-layout.js", "wealth-settings-surface.js"}
        for asset, version in js_matches:
            expected = "10.9n1" if asset in {"wealth.js", "wealth-transaction-defaults.js"} else "10.9m1" if asset in ui_detail_assets else "10.9k1" if asset in invest_hotfix_assets else "10.9h1" if asset in settings_assets else "10.7g1" if asset in hotfix_assets else "1.3.0"
            self.assertEqual(version, expected)

    def test_service_worker_cache_name(self):
        sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
        self.assertIn('const CACHE_NAME = "wealth-cache-v1.3.0";', sw)

    def test_documentation_version_sync(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("**Wealth v1.3.0**", readme)

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## Wealth v1.3.0 \u2014 MoneyLog Calendar and Multi-Source IPO Integration \u2014 2026-09-19", changelog)
        self.assertIn("## Wealth v1.2.7 \u2014 Docker Build Security Hardening \u2014 2026-09-18", changelog)
        self.assertIn("## Wealth v1.2.6 \u2014 All-Owner Snapshot Coordination and Daily Close Automation \u2014 2026-09-18", changelog)
        self.assertIn("## Wealth v1.2.5 — Stock Record Accuracy and Performance Semantics — 2026-09-18", changelog)
        self.assertIn("## Wealth v1.2.4 \u2014 Strategy Bucket Color Clarity \u2014 2026-09-17", changelog)
        self.assertIn("## Wealth v1.2.3 — KB Empty Balance Compatibility — 2026-09-17", changelog)
        self.assertIn("## Wealth v1.2.2 — Broker Sync Reliability — 2026-09-17", changelog)


if __name__ == "__main__":
    unittest.main()
