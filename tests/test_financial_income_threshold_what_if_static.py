from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / "app" / "static" / "wealth-financial-income-what-if.js"
CSS_PATH = ROOT / "app" / "static" / "wealth-financial-income-what-if.css"


class FinancialIncomeThresholdWhatIfStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS_PATH.read_text(encoding="utf-8")
        cls.css = CSS_PATH.read_text(encoding="utf-8")

    def test_quick_dividend_presets_remain_100_500_1000_manwon(self):
        self.assertIn("const DIVIDEND_PRESETS = [1e6, 5e6, 10e6];", self.js)
        self.assertIn("data-dividend-preset", self.js)

    def test_threshold_states_are_server_driven(self):
        self.assertIn("scenarioState.exceeded === true", self.js)
        self.assertIn("scenarioState.at_or_above === true", self.js)
        self.assertIn("watchState.at_or_above === true", self.js)
        self.assertNotIn("20_000_000", self.js)

    def test_exact_threshold_has_distinct_reached_state(self):
        self.assertIn("className: 'reached'", self.js)
        self.assertIn("fi-decision-note reached", self.js)
        self.assertIn("추가 배당 후 2천만원 기준에 도달합니다.", self.js)
        reached = self.js.index("additionalDividend > 0 && scenarioState.at_or_above === true")
        safe = self.js.index("additionalDividend > 0 && scenarioState.exceeded === false")
        self.assertLess(reached, safe)

    def test_watch_threshold_has_distinct_approach_state(self):
        self.assertIn("className: 'approach'", self.js)
        self.assertIn("fi-decision-note approach", self.js)
        self.assertIn("2천만원 기준에 가까워지고 있습니다.", self.js)

    def test_threshold_state_styles_exist(self):
        self.assertIn(".fi-result-card.approach", self.css)
        self.assertIn(".fi-result-card.reached", self.css)
        self.assertIn(".fi-decision-note.approach", self.css)
        self.assertIn(".fi-decision-note.reached", self.css)

    def test_no_client_persistence_added(self):
        self.assertNotIn("localStorage", self.js)
        self.assertNotIn("sessionStorage", self.js)


if __name__ == "__main__":
    unittest.main()
