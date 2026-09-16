from pathlib import Path
import unittest


class StrategyBucketBatch3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.ui = (root / "app/static/wealth-planning.js").read_text(encoding="utf-8")
        cls.model = (root / "app/static/wealth-planning-model.js").read_text(encoding="utf-8")
        cls.css = (root / "app/static/wealth-layout.css").read_text(encoding="utf-8")
        cls.backend = (root / "app/services/planning.py").read_text(encoding="utf-8")
        cls.layout = (root / "app/static/wealth-layout.js").read_text(encoding="utf-8")

    def test_target_persistence_and_validation_reuse_existing_contract(self):
        self.assertIn('"target": target', self.backend)
        self.assertIn('sum(b["target"] for b in clean) > 100.000001', self.backend)
        self.assertIn('name="target" type="number" min="0" max="100" step="0.1"', self.ui)
        self.assertIn("targetValidation=renderDraftTargetStatus()", self.ui)
        self.assertIn("100% 이하로 조정해주세요", self.ui)

    def test_all_recommended_presets_and_custom_creation_are_available(self):
        for name in ("코어", "성장", "배당", "섹터", "테마", "전술", "방어", "현금"):
            self.assertIn(name, self.ui)
        self.assertIn("+ 사용자 정의 버킷", self.ui)
        self.assertIn("buckets.some(bucket=>bucket.name.trim()===name)", self.ui)
        self.assertIn("버킷이 이미 있습니다", self.ui)

    def test_target_and_current_donuts_have_distinct_empty_states(self):
        self.assertIn("목표 비중이 아직 설정되지 않았습니다.", self.ui)
        self.assertIn("표시할 현재 증권 자산이 없습니다.", self.ui)
        self.assertIn("bucketAllocationComparison", self.ui)
        self.assertIn("wealth-bucket-comparison", self.ui)
        self.assertIn("grid-template-columns:repeat(2,minmax(0,1fr))", self.css)
        self.assertIn(".wealth-bucket-comparison { grid-template-columns:1fr; }", self.css)
        for selector in (
            ".wealth-bucket-comparison > section",
            ".wealth-bucket-donut::after",
            ".wealth-bucket-legend-row::before",
            ".wealth-bucket-empty",
            ".wealth-bucket-presets",
            ".wealth-bucket-preset.active",
            ".wealth-bucket-target-status.invalid",
        ):
            self.assertIn(selector, self.css)

    def test_unallocated_and_unclassified_are_not_merged(self):
        self.assertIn("id: '__unallocated__', name: '미배정'", self.model)
        self.assertIn("id: '__unclassified__'", self.model)
        self.assertIn("name: '미분류'", self.model)
        self.assertIn("totals.get('')", self.model)
        self.assertIn("current.push", self.model)

    def test_current_denominator_keeps_existing_bucket_totals(self):
        self.assertIn("const { totals, total } = bucketTotals(state, view)", self.model)
        self.assertIn("bucket.value / total * 100", self.model)
        self.assertIn("amount(a.cash_krw) + (usd ? usd * fx : 0)", self.model)
        self.assertIn("add(id, h.market_value_krw)", self.model)

    def test_same_bucket_color_is_keyed_by_identity_not_array_order(self):
        self.assertIn("function bucketColor(id)", self.ui)
        self.assertIn("bucketColor(item.id)", self.ui)
        self.assertIn("BUCKET_COLORS[hash%BUCKET_COLORS.length]", self.ui)
        self.assertIn("wealth-bucket-legend-row", self.ui)

    def test_owner_and_assignment_semantics_remain_explicit(self):
        self.assertIn("portfolioView.owner", self.ui)
        self.assertIn("목표는 사용자 공통 설정이며 현재 비중은 선택한 가족 범위 기준", self.ui)
        self.assertIn("Object.hasOwn(state.holdings, h.id) ? state.holdings[h.id] : state.accounts[h.account_id]", self.model)
        self.assertIn("계좌 기본값 사용", self.ui)
        self.assertIn("명시적 미분류", self.ui)

    def test_no_trading_and_batches_one_two_contracts_remain_present(self):
        self.assertIn("매매 주문은 실행하지 않습니다.", self.ui)
        for label in ("홈", "주식 투자", "종합 자산", "머니 로그", "설정"):
            self.assertIn(label, self.layout)
        self.assertIn('class="wealth-history-main"', self.ui)
        self.assertIn("left = pad, right = width - pad", self.ui)


if __name__ == "__main__":
    unittest.main()
