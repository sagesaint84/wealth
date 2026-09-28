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
        self.assertIn("포트폴리오 세후 배당수익률", self.js)
        self.assertIn("원천징수·알려진 세금 기준 screening", self.js)
        self.assertIn("전체 계산 보류", self.js)

    def test_trust_evidence_and_official_link_are_rendered(self) -> None:
        self.assertIn("Dividend Intelligence", self.js)
        self.assertIn("공식 근거 확인", self.js)
        self.assertIn("이력/시장/휴리스틱 추정", self.js)
        self.assertIn("종목 미귀속 residual", self.js)
        self.assertIn("원문 ↗", self.js)
        self.assertIn("evidence_url", self.js)

    def test_instrument_and_account_contribution_are_explicitly_estimated(self) -> None:
        self.assertIn("종목·계좌별 계산 근거 보기", self.js)
        self.assertIn("gross_portfolio_contribution_pct", self.js)
        self.assertIn("calculable_after_known_tax_contribution_pct", self.js)
        self.assertIn("현재 보유수량", self.js)
        self.assertIn("entitlement", self.js)
        self.assertIn("종목/계좌에 임의 배분하지 않음", self.js)

    def test_accuracy_ui_is_point_in_time_and_accumulating_safe(self) -> None:
        self.assertIn("과거 point-in-time 예측 평가", self.js)
        self.assertIn("측정 데이터 누적 중", self.js)
        self.assertIn("MAE", self.js)
        self.assertIn("WAPE", self.js)
        self.assertIn("진행 중인 현재 월은 제외", self.js)
        self.assertIn("과거 snapshot을 현재 holdings/source로 재생성하지 않습니다", self.js)

    def test_alert_setting_is_opt_in_and_uses_existing_settings_api(self) -> None:
        self.assertIn("dividendIntelligenceAlertsEnabled", self.js)
        self.assertIn("dividend_intelligence_alerts", self.js)
        self.assertIn("/api/settings/automation", self.js)
        self.assertIn("method: 'PATCH'", self.js)
        self.assertIn("기본 OFF", self.js)
        self.assertIn("가족 합계에는 법정 기준을 적용하지 않습니다", self.js)

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
