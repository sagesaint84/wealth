from pathlib import Path
import unittest


class InvestmentNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "app/static/wealth-planning.js").read_text(encoding="utf-8")
        cls.css = (root / "app/static/wealth-layout.css").read_text(encoding="utf-8")

    def test_flat_top_level_tabs_are_in_required_order(self):
        expected = ["overview", "heatmap", "records", "buckets", "tax_accounts", "holdings"]
        start = self.js.index("nav.innerHTML = '")
        markup = self.js[start:self.js.index("';", start)]
        positions = [markup.index(f'data-invest="{tab}"') for tab in expected]
        self.assertEqual(positions, sorted(positions))
        for label in ("포트폴리오", "히트맵", "주식기록", "전략 버킷", "절세계좌", "보유종목"):
            self.assertIn(label, markup)

    def test_nested_record_switch_is_hidden_and_panels_are_individually_selected(self):
        self.assertIn("#recordViewTabs { display: none !important; }", self.css)
        self.assertIn("tab === 'heatmap'", self.js)
        self.assertIn("tab === 'tax_accounts'", self.js)
        self.assertIn("tab === 'holdings'", self.js)


if __name__ == "__main__":
    unittest.main()
