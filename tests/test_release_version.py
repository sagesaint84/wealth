import re
import unittest
from pathlib import Path

from tests.test_request_state_user_id import _import_main_without_loading_real_env

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"


class ReleaseVersionTests(unittest.TestCase):
    def test_fastapi_app_version(self):
        main = _import_main_without_loading_real_env()
        self.assertEqual(getattr(main, "APP_VERSION", None), "2.1.17")
        self.assertEqual(main.app.version, "2.1.17")

    def test_index_html_version_metadata_and_cache_busting(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('<meta name="application-version" content="2.1.17" />', html)
        self.assertIn('id="appVersionDisplay"', html)
        self.assertIn("앱 버전 v2.1.17", html)

        main = _import_main_without_loading_real_env()
        self.assertIn(f'<meta name="application-version" content="{main.APP_VERSION}" />', html)
        self.assertIn(f'앱 버전 v{main.APP_VERSION}', html)
        revision = re.search(r'<meta name="application-assets-revision" content="([^"]+)"', html)
        self.assertIsNotNone(revision)
        self.assertRegex(revision.group(1), r"^[0-9]+(?:\.[0-9]+)+(?:[-A-Za-z0-9._]*)$")
        for attribute, extension in (("href", "css"), ("src", "js")):
            assets = re.findall(rf'{attribute}="(/static/[^"?]+\.{extension})(?:\?([^"#]*))?"', html)
            self.assertTrue(assets)
            for url, query in assets:
                from urllib.parse import parse_qs
                versions = parse_qs(query).get("v", [])
                self.assertEqual(len(versions), 1, url)
                self.assertRegex(versions[0], r"^[0-9]+(?:\.[0-9]+)+(?:[-A-Za-z0-9._]*)$")
                path = (STATIC_DIR / url.removeprefix("/static/")).resolve()
                self.assertTrue(path.is_relative_to(STATIC_DIR.resolve()), url)
                self.assertTrue(path.is_file(), url)

    def test_dynamic_chart_asset_revision(self):
        loader = (STATIC_DIR / "wealth-planning-model.js").read_text(encoding="utf-8")
        matches = re.findall(r"/static/(wealth-timeseries-unified\.js)\?v=([A-Za-z0-9._-]+)", loader)
        self.assertTrue(matches)
        for asset, revision in matches:
            self.assertTrue((STATIC_DIR / asset).is_file())
            self.assertRegex(revision, r"^[0-9]+(?:\.[0-9]+)+(?:[-A-Za-z0-9._]*)$")

    def test_service_worker_cache_name(self):
        sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
        self.assertIn('const CACHE_NAME = "wealth-cache-v2.1.3-p0";', sw)

    def test_documentation_version_sync(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("마지막으로 운영 확인된 버전은 v2.1.9", readme)
        self.assertIn("최신 개발 후보는 **v2.1.17**", readme)
        self.assertIn("Wealth v2.1.9 후보", readme)
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
        self.assertIn("## Wealth v2.1.17 —", changelog)
        self.assertIn("## Wealth v2.1.16 —", changelog)
        self.assertIn("## Wealth v2.1.15 —", changelog)
        self.assertIn("## Wealth v2.1.14 —", changelog)
        self.assertIn("## Wealth v2.1.13 —", changelog)
        self.assertIn("## Wealth v2.1.12 —", changelog)
        self.assertIn("## Wealth v2.1.11 —", changelog)
        self.assertIn("## Wealth v2.1.10 —", changelog)
        self.assertIn("## Wealth v2.1.9 —", changelog)
        for name in ("ROADMAP.md", "PROJECT_STATE.md"):
            current = (ROOT / "docs" / name).read_text(encoding="utf-8")
            self.assertIn("v2.1.17 개발 후보", current)
            self.assertIn("## v2.1.16 —", current)
            self.assertIn("## v2.1.15 —", current)
            self.assertIn("## v2.1.14 —", current)
            self.assertIn("## v2.1.13 —", current)
            self.assertIn("## v2.1.12 —", current)
            self.assertIn("## v2.1.11 —", current)
            self.assertIn("d6987cb22c9ab097a4478ffb2738a0c8efba19cb", current)
            self.assertIn("45538636442", current)
            self.assertIn("## v2.1.10 —", current)
            self.assertIn("e0e93deec1ad9ca2b8316cd768d82dbe468041fe", current)
            self.assertIn("45479870999", current)
            self.assertIn("v2.1.9 개발 후보", current)
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
