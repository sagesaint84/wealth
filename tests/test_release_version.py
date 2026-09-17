import re
import unittest
from pathlib import Path

from tests.test_request_state_user_id import _import_main_without_loading_real_env

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"


class ReleaseVersionTests(unittest.TestCase):
    def test_fastapi_app_version(self):
        main = _import_main_without_loading_real_env()
        self.assertEqual(getattr(main, "APP_VERSION", None), "1.2.4")
        self.assertEqual(main.app.version, "1.2.4")

    def test_index_html_version_metadata_and_cache_busting(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('<meta name="application-version" content="1.2.4" />', html)
        self.assertIn('id="appVersionDisplay"', html)
        self.assertIn("v1.2.4", html)

        css_matches = re.findall(r'href="/static/[^"]+\.css\?v=([^"]+)"', html)
        self.assertTrue(css_matches)
        for version in css_matches:
            self.assertEqual(version, "1.2.4")

        js_matches = re.findall(r'src="/static/[^"]+\.js\?v=([^"]+)"', html)
        self.assertTrue(js_matches)
        for version in js_matches:
            self.assertEqual(version, "1.2.4")

    def test_service_worker_cache_name(self):
        sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
        self.assertIn('const CACHE_NAME = "wealth-cache-v1.2.4";', sw)

    def test_documentation_version_sync(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("**Wealth v1.2.4**", readme)

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## Wealth v1.2.4 — Strategy Bucket Color Clarity — 2026-09-17", changelog)
        self.assertIn("## Wealth v1.2.3 — KB Empty Balance Compatibility — 2026-09-17", changelog)
        self.assertIn("## Wealth v1.2.2 — Broker Sync Reliability — 2026-09-17", changelog)


if __name__ == "__main__":
    unittest.main()
