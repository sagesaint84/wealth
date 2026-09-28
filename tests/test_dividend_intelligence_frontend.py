from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app" / "static" / "wealth-dividend-source.js"
OFFICIAL = ROOT / "app" / "services" / "dividend_official_sources.py"
SNAPSHOTS = ROOT / "app" / "services" / "dividend_forecast_snapshots.py"


class DividendIntelligenceFrontendStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = JS.read_text(encoding="utf-8")
        cls.official = OFFICIAL.read_text(encoding="utf-8")
        cls.snapshots = SNAPSHOTS.read_text(encoding="utf-8")

    def test_dashboard_keeps_existing_c5_panel_contract(self) -> None:
        self.assertIn("portfolioAfterTaxDividendPanel", self.js)
        self.assertIn("Dividend Intelligence", self.js)
        self.assertIn("원천징수·알려진 세금 기준 screening", self.js)
        self.assertIn("전체 계산 보류", self.js)

    def test_trust_evidence_and_official_link_are_rendered(self) -> None:
        self.assertIn("배당 예상 근거", self.js)
        self.assertIn("공식 근거", self.js)
        self.assertIn("이력·시장 추정", self.js)
        self.assertIn("미귀속 residual", self.js)
        self.assertIn("원문 ↗", self.js)
        self.assertIn("evidence_url", self.js)

    def test_instrument_and_account_contribution_are_explicitly_estimated(self) -> None:
        self.assertIn("종목·계좌별 근거와 공식 자격 보기", self.js)
        self.assertIn("gross_portfolio_contribution_pct", self.js)
        self.assertIn("calculable_after_known_tax_contribution_pct", self.js)
        self.assertIn("현재 보유수량", self.js)
        self.assertIn("entitlement", self.js)
        self.assertIn("임의 배분", self.js)

    def test_accuracy_ui_is_point_in_time_and_accumulating_safe(self) -> None:
        self.assertIn("예측 정확도 · 과거 point-in-time", self.js)
        self.assertIn("예측 정확도 · 데이터 누적 중", self.js)
        self.assertIn("MAE", self.js)
        self.assertIn("WAPE", self.js)
        self.assertIn("현재 월 제외", self.js)
        self.assertIn("과거 snapshot 재생성 없음", self.js)

    def test_alert_setting_is_opt_in_and_uses_existing_settings_api(self) -> None:
        self.assertIn("dividendIntelligenceAlertsEnabled", self.js)
        self.assertIn("dividend_intelligence_alerts", self.js)
        self.assertIn("/api/settings/automation", self.js)
        self.assertIn("method: 'PATCH'", self.js)
        self.assertIn("기본 OFF", self.js)
        self.assertIn("개인별 금융소득 상태만", self.js)

    def test_frontend_does_not_add_tax_rate_constants(self) -> None:
        for forbidden in ("0.154", "15.4%", "0.15"):
            self.assertNotIn(forbidden, self.js)

    def test_official_enrichment_attaches_c5_before_intelligence(self) -> None:
        self.assertIn("def _attach_dividend_intelligence", self.official)
        c5 = self.official.rfind("_attach_portfolio_after_tax(summary, holdings)")
        intelligence = self.official.rfind("_attach_dividend_intelligence(summary, holdings")
        self.assertGreater(c5, -1)
        self.assertGreater(intelligence, c5)

    def test_scheduled_snapshot_dispatch_remains_nonfatal(self) -> None:
        self.assertIn("dispatch_scheduled_dividend_intelligence_alerts", self.snapshots)
        self.assertIn('str(saved.get("trigger") or "") == "scheduled"', self.snapshots)
        self.assertIn("except Exception", self.snapshots)


if __name__ == "__main__":
    unittest.main()
