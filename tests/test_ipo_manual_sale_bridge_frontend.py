from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_JS = ROOT / "app" / "static" / "wealth-ipo-sale-bridge.js"


class IpoManualSaleBridgeFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = BRIDGE_JS.read_text(encoding="utf-8")

    def test_bridge_records_into_existing_realized_pnl_ledger(self) -> None:
        self.assertIn("jsonFetch('/api/realized-pnl'", self.source)
        self.assertIn("asset_type: 'ipo'", self.source)
        self.assertIn("is_ipo: true", self.source)
        self.assertIn("account_id: text(account.id)", self.source)
        self.assertIn("quantity,", self.source)
        self.assertIn("provider_realized_pnl: pnlKrw", self.source)
        self.assertIn("ipo_subscription_fee_krw: ipoSubscriptionFeeKrw", self.source)
        self.assertIn("pnl_krw: finalWealthPnlKrw", self.source)

    def test_bridge_does_not_invent_realized_pnl_or_tax_formula(self) -> None:
        self.assertIn("증권사에서 확인한 실제 매도 실현손익", self.source)
        self.assertIn("Wealth가 매도 손익이나 세금을 임의 계산하지 않습니다", self.source)
        self.assertIn("const pnlKrw = Number(form.elements.pnl_krw.value)", self.source)
        self.assertNotIn("offer_price * quantity", self.source)
        self.assertNotIn("sell_amount -", self.source)

    def test_bridge_uses_exact_connected_account_metadata(self) -> None:
        self.assertIn("/api/accounts?group=All&owner=모두", self.source)
        self.assertIn("context.accountId", self.source)
        self.assertIn("broker: text(account.broker)", self.source)
        self.assertIn("account_name: text(account.name || account.account_name)", self.source)

    def test_bridge_respects_listing_date_and_remaining_allocation(self) -> None:
        self.assertIn("/allocation`", self.source)
        self.assertIn("remaining_quantity", self.source)
        self.assertIn("today < listingDate", self.source)
        self.assertIn("quantity > context.remainingQuantity", self.source)
        self.assertIn("form.elements.date.min = listingDate || ''", self.source)
        self.assertIn("form.elements.date.max = today", self.source)
        self.assertIn("listingDate && date < listingDate", self.source)
        self.assertIn("date > today", self.source)

    def test_saved_record_is_refetched_through_canonical_sale_candidate_endpoint(self) -> None:
        self.assertIn("allocation/sale-candidates", self.source)
        self.assertIn("refreshSaleCandidates(context, recordId, quantity)", self.source)
        self.assertIn("매도 연결", self.source)
        self.assertNotIn("allocation/links',", self.source)

    def test_bridge_observer_is_scoped_to_ipo_wrapper(self) -> None:
        self.assertIn("document.getElementById('ipoListWrapper')", self.source)
        self.assertIn("observer.observe(wrapper", self.source)
        self.assertNotIn("observer.observe(document.body", self.source)

    def test_bridge_collects_optional_provider_reported_sale_fields_without_recalculation(self) -> None:
        for marker in ("sell_amount", "fee", "tax"):
            self.assertIn(marker, self.source)
        self.assertIn("if (raw !== '') payload[field] = Number(raw)", self.source)

    def test_bridge_exposes_and_deducts_ipo_subscription_fee_once(self) -> None:
        self.assertIn("공모청약비", self.source)
        self.assertIn('name="ipo_subscription_fee_krw"', self.source)
        self.assertIn('value="2000"', self.source)
        self.assertIn("const ipoSubscriptionFeeKrw = Number(form.elements.ipo_subscription_fee_krw.value)", self.source)
        self.assertIn("Number.isInteger(ipoSubscriptionFeeKrw)", self.source)
        self.assertIn("const finalWealthPnlKrw = pnlKrw - ipoSubscriptionFeeKrw", self.source)
        self.assertIn("provider_realized_pnl: pnlKrw", self.source)
        self.assertIn("ipo_subscription_fee_krw: ipoSubscriptionFeeKrw", self.source)
        self.assertIn("pnl: finalWealthPnlKrw", self.source)
        self.assertIn("pnl_krw: finalWealthPnlKrw", self.source)
        self.assertIn("공모수수료", self.source)

    def test_bridge_injects_explicit_manual_sale_action(self) -> None:
        self.assertIn("ipo-manual-sale-create", self.source)
        self.assertIn("➕ 매도 기록 추가", self.source)
        self.assertIn("매도 후보가 없으면 실제 실현손익 기록을 먼저 추가하세요", self.source)


if __name__ == "__main__":
    unittest.main()
