from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app" / "static" / "wealth-money-input.js"


class MoneyInputUsdPreviewStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = JS.read_text(encoding="utf-8")

    def test_cash_usd_and_opt_in_attribute_are_supported(self) -> None:
        self.assertIn("cash_usd", self.js)
        self.assertIn("data-auto-usd-preview", self.js)
        self.assertIn("isUsdMoneyInput", self.js)

    def test_preview_uses_live_usdkrw_portfolio_rate(self) -> None:
        self.assertIn("wealth:portfolio", self.js)
        self.assertIn("fxRates?.USDKRW", self.js)
        self.assertIn("setUsdKrwRate", self.js)
        self.assertIn("원화 환산 대기", self.js)
        self.assertIn("약 ₩", self.js)

    def test_preview_formats_usd_without_mutating_input_value(self) -> None:
        self.assertIn("formatUsdDigits", self.js)
        self.assertIn("toLocaleString('en-US'", self.js)
        self.assertNotIn("input.value =", self.js)
        self.assertNotIn("target.value =", self.js)

    def test_no_hardcoded_fx_rate_is_added(self) -> None:
        for forbidden in ("1300", "1350", "1400", "1450", "1500"):
            self.assertNotIn(forbidden, self.js)


if __name__ == "__main__":
    unittest.main()
