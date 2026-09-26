from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"expected one match in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


root = Path(__file__).resolve().parents[1]
official = root / "app/services/dividend_official_sources.py"
replace_once(
    official,
    '''        row["annual_payout_krw"] = round(current_annual + delta)\n        current_orig = _money(row.get("annual_payout_orig")) or current_annual\n        row["annual_payout_orig"] = round(current_orig + delta, 2)\n        row["annual_div_per_share"] = round(row["annual_payout_orig"] / qty, 4)\n        source["numeric_source"] = "opendart_confirmed_disclosure"\n''',
    '''        row["annual_payout_krw"] = round(current_annual + delta)\n        current_orig = _money(row.get("annual_payout_orig")) or current_annual\n        row["annual_payout_orig"] = round(current_orig + delta, 2)\n        row["annual_div_per_share"] = round(row["annual_payout_orig"] / qty, 4)\n        holding = next(\n            (\n                item\n                for item in holdings\n                if isinstance(item, dict)\n                and _stock_code(item.get("code")) == code\n                and str(item.get("currency") or "KRW").upper() == "KRW"\n            ),\n            {},\n        )\n        price = _money(holding.get("current_price")) or _money(holding.get("purchase_price")) or 0.0\n        if price > 0:\n            row["div_yield"] = round((row["annual_div_per_share"] / price) * 100.0, 2)\n            existing["div_yield"] = row["div_yield"]\n        source["numeric_source"] = "opendart_confirmed_disclosure"\n''',
)
replace_once(
    official,
    '''    summary["total_annual_dividend_krw"] = round(total)\n    summary["monthly_avg_dividend_krw"] = round(total / 12.0)\n\n    total_eval = 0.0\n''',
    '''    summary["total_annual_dividend_krw"] = round(total)\n    summary["monthly_avg_dividend_krw"] = round(total / 12.0)\n    summary["dividend_paying_count"] = sum(\n        1\n        for row in rows\n        if isinstance(row, dict) and (_money(row.get("annual_payout_krw")) or 0.0) > 0\n    )\n\n    total_eval = 0.0\n''',
)

tests = root / "tests/test_dividend_confirmed_disclosures.py"
replace_once(
    tests,
    '''        row = result["holding_dividends"][0]\n        self.assertEqual(row["annual_payout_krw"], 6000)\n        self.assertEqual(result["monthly_schedule"][11]["total_krw"], 6000)\n        self.assertEqual(row["payout_months"], [12])\n        self.assertTrue(row["forecast_source"]["confirmed_numeric_override"])\n\n\nif __name__ == "__main__":\n''',
    '''        row = result["holding_dividends"][0]\n        self.assertEqual(row["annual_payout_krw"], 6000)\n        self.assertEqual(result["monthly_schedule"][11]["total_krw"], 6000)\n        self.assertEqual(row["payout_months"], [12])\n        self.assertEqual(result["dividend_paying_count"], 1)\n        self.assertTrue(row["forecast_source"]["confirmed_numeric_override"])\n\n    def test_latest_correction_filing_wins(self):\n        selected = official._latest_dividend_decision([\n            {\n                "report_nm": "현금ㆍ현물배당 결정",\n                "rcept_no": "20260313000100",\n                "rcept_dt": "20260313",\n            },\n            {\n                "report_nm": "[정정]현금ㆍ현물배당 결정",\n                "rcept_no": "20260420000276",\n                "rcept_dt": "20260420",\n            },\n        ])\n        self.assertIsNotNone(selected)\n        self.assertEqual(selected["receipt_no"], "20260420000276")\n        self.assertFalse(selected["confirmed_amount"])\n\n\nif __name__ == "__main__":\n''',
)
