from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import app.services.ipo.applications  # Ensure patch target module is loaded.
from app.services.ipo.store import get_ipo_calendar_events


ROOT = Path(__file__).resolve().parents[1]


def _run_ipo_date_js(expression: str) -> str:
    source = (ROOT / "app" / "static" / "wealth-ipo.js").read_text(encoding="utf-8")
    script = f"""
const fs = require('fs');
globalThis.window = {{ addEventListener: () => {{}}, dispatchEvent: () => {{}} }};
globalThis.document = {{ getElementById: () => null }};
globalThis.CustomEvent = function CustomEvent() {{}};
eval({json.dumps(source)});
process.stdout.write(String({expression}));
"""
    return subprocess.check_output(["node", "-e", script], cwd=ROOT, text=True, encoding="utf-8").strip()


class IpoPresentationTests(unittest.TestCase):
    def test_subscription_status_uses_canonical_dates_and_kst(self):
        ipo = {"subscription_start": "2026-09-19", "subscription_end": "2026-09-20", "status": "CLOSED"}
        for today, expected in (
            ("2026-09-18", "예정"),
            ("2026-09-19", "중"),
            ("2026-09-20", "중"),
            ("2026-09-21", "마감"),
        ):
            expression = f"window.WealthIpoDate.subscriptionStatus({json.dumps(ipo)}, '{today}')"
            self.assertEqual(_run_ipo_date_js(expression), expected)

    def test_subscription_status_kst_midnight_boundary_and_invalid_dates(self):
        ipo = {"subscription_start": "2026-09-19", "subscription_end": "2026-09-20"}
        expression = f"window.WealthIpoDate.subscriptionStatus({json.dumps(ipo)}, window.WealthIpoDate.todayKst(new Date('2026-09-18T15:00:00.000Z')))"
        self.assertEqual(_run_ipo_date_js(expression), "중")
        invalid = {"subscription_start": "2026-02-30", "subscription_end": "2026-03-01"}
        self.assertEqual(_run_ipo_date_js(f"window.WealthIpoDate.subscriptionStatus({json.dumps(invalid)}, '2026-02-28')"), "null")

    def test_score_labels_and_presentation_only_contract(self):
        source = (ROOT / "app" / "static" / "wealth-ipo.js").read_text(encoding="utf-8")
        self.assertIn("점수 산정중", source)
        self.assertIn("별도평가", source)
        self.assertIn("window.WealthIpoDate", source)
        self.assertNotIn("write_market_store", source)
        self.assertNotIn("/api/ipo/applications/", source.split("const subscriptionStatus", 1)[0])

    def test_subscription_period_projects_each_visible_day_and_owner_independent(self):
        market = {
            "schema_version": 1,
            "ipos": [{
                "ipo_id": "ipo-period",
                "company_name": "기간테스트",
                "subscription_start": "2026-09-18",
                "subscription_end": "2026-09-20",
                "listing_track": "spac",
            }],
        }
        with patch("app.services.ipo.store.read_market_store", return_value=market), \
             patch("app.services.ipo.applications.get_user_applications", return_value={"applications": {}}):
            events = get_ipo_calendar_events("user", "2026-09-18", "2026-09-20", "아빠")
        self.assertEqual(sorted(event["date"] for event in events if event["type"].startswith("ipo_subscription")), ["2026-09-18", "2026-09-19", "2026-09-20"])
        self.assertTrue(all(event["owner"] == "모두" for event in events))
        self.assertTrue(all(event["meta"]["company_name"] == "기간테스트" for event in events))

    def test_actual_listing_date_has_priority_and_expected_is_fallback(self):
        market = {"schema_version": 1, "ipos": [
            {"ipo_id": "actual", "company_name": "실제상장", "actual_listing_date": "2026-09-22", "expected_listing_date": "2026-09-20"},
            {"ipo_id": "expected", "company_name": "예정상장", "expected_listing_date": "2026-09-21"},
        ]}
        with patch("app.services.ipo.store.read_market_store", return_value=market):
            events = get_ipo_calendar_events(None, "2026-09-01", "2026-09-30")
        listings = {event["meta"]["ipo_id"]: event for event in events if event["type"] == "ipo_listing"}
        self.assertEqual(listings["actual"]["date"], "2026-09-22")
        self.assertEqual(listings["actual"]["meta"]["listing_status"], "actual")
        self.assertEqual(listings["expected"]["date"], "2026-09-21")
        self.assertEqual(listings["expected"]["meta"]["listing_status"], "expected")

    def test_calendar_rendering_has_name_overflow_and_timezone_contract(self):
        calendar = (ROOT / "app" / "static" / "wealth-calendar.js").read_text(encoding="utf-8")
        self.assertIn("names.slice(0, 3)", calendar)
        self.assertIn("cal-ipo-overflow", calendar)
        self.assertIn("timeZone: 'Asia/Seoul'", calendar)
        self.assertNotIn("new Date().toISOString().slice(0, 10)", calendar)

    def test_refresh_button_uses_wealth_action_style_and_restores_loading_state(self):
        index = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        ipo = (ROOT / "app" / "static" / "wealth-ipo.js").read_text(encoding="utf-8")
        self.assertIn('id="ipoRefreshBtn" class="button secondary compact"', index)
        self.assertIn("button.disabled = true;", ipo)
        self.assertIn("button.setAttribute('aria-busy', 'true');", ipo)
        self.assertIn("button.disabled = false;", ipo)
        self.assertIn("refreshInFlight = false;", ipo)
        self.assertIn("marketIpos = Array.isArray(data.market?.ipos) ? data.market.ipos : marketIpos", ipo)

    def test_calendar_detail_uses_canonical_ipo_event_labels_and_tooltips(self):
        calendar = (ROOT / "app" / "static" / "wealth-calendar.js").read_text(encoding="utf-8")
        for label in ("청약", "납입", "환불", "상장예정", "상장"):
            self.assertIn(label, calendar)
        self.assertIn('title="${escapeHtml(name)}"', calendar)

    def test_calendar_legend_and_compact_financial_labels(self):
        calendar = (ROOT / "app" / "static" / "wealth-calendar.js").read_text(encoding="utf-8")
        for label in ("청약", "상장", "수익", "손실", "배당", "수입", "지출"):
            self.assertIn(f">{label}<", calendar)
        for tone in ("tone-ipo-subscription", "tone-ipo-listing", "tone-profit", "tone-loss", "tone-dividend", "tone-income", "tone-expense"):
            self.assertIn(tone, calendar)
        self.assertIn("${label} ${sign}${formatMoney(pnlSum)}", calendar)
        self.assertIn("const cue = pnlSum > 0 ? '➕ ' : (pnlSum < 0 ? '➖ ' : '')", calendar)
        css = (ROOT / "app" / "static" / "wealth-layout.css").read_text(encoding="utf-8")
        for token in ("--calendar-subscription-fg", "--calendar-listing-fg", "--calendar-profit-fg", "--calendar-loss-fg", "--calendar-dividend-fg", "--calendar-income-fg", "--calendar-expense-fg"):
            self.assertIn(token, css)
        self.assertIn(".calendar-legend-item.tone-ipo-subscription", css)
        self.assertIn(".calendar-legend-item.tone-ipo-listing", css)

    def test_calendar_semantic_palette_contract(self):
        css = (ROOT / "app" / "static" / "wealth-layout.css").read_text(encoding="utf-8")
        expected = {
            "--calendar-loss-fg": "#448AFF",
            "--calendar-income-fg": "#FFAB40",
            "--calendar-expense-fg": "#4DF0FF",
            "--calendar-subscription-fg": "#69F0AE",
            "--calendar-listing-fg": "#B388FF",
            "--calendar-dividend-fg": "#FFE082",
        }
        for variable, value in expected.items():
            self.assertIn(f"{variable}: {value}", css)
        self.assertIn("--calendar-profit-fg: #f87171", css)
        for tone in ("tone-ipo-subscription", "tone-ipo-listing", "tone-profit", "tone-loss", "tone-dividend", "tone-income", "tone-expense"):
            self.assertIn(f".calendar-legend-item.{tone}", css)
            self.assertIn(f".cal-badge.{tone}", css)


if __name__ == "__main__":
    unittest.main()
