import unittest
from app.services.kis_realized import (
    map_kis_domestic_profit_row,
    map_kis_overseas_profit_row,
    build_kis_realized_fingerprint,
    KIS_BROKER,
)
from app.services.kis_openapi import compute_kis_account_key


class TestKISRealizedMapper(unittest.TestCase):
    def setUp(self):
        self.account_key = compute_kis_account_key("12345678", "01")
        self.masked_label = "1234****-01"

    def test_domestic_row_mapping(self):
        row = {
            "trad_dt": "20240410",
            "pdno": "005930",
            "prdt_name": "삼성전자",
            "sll_qty": "20",
            "sll_amt": "1680000",
            "buy_amt": "1400000",
            "pchs_amt": "1400000",
            "rlzt_pfls": "280000",
            "pfls_rt": "20.00",
            "fee": "250",
            "tl_tax": "3360",
        }
        cand = map_kis_domestic_profit_row(
            row,
            account_name="한투종합",
            source_account_key=self.account_key,
            source_account_label=self.masked_label,
            owner="김철수",
            fetched_at="2024-04-10T15:30:00Z",
        )
        self.assertEqual(cand["date"], "2024-04-10")
        self.assertEqual(cand["code"], "005930")
        self.assertEqual(cand["name"], "삼성전자")
        self.assertEqual(cand["asset_type"], "stock")
        self.assertEqual(cand["currency"], "KRW")
        self.assertEqual(cand["pnl"], 280000.0)
        self.assertIsNone(cand["fx_rate"])
        self.assertIsNone(cand["fx_pnl_krw"])
        self.assertEqual(cand["pnl_krw"], 280000.0)
        self.assertFalse(cand["is_ipo"])
        self.assertEqual(cand["owner"], "김철수")
        self.assertEqual(cand["broker"], KIS_BROKER)
        self.assertEqual(cand["account_name"], "한투종합")
        self.assertEqual(cand["source"], "kis")
        self.assertEqual(cand["source_account_key"], self.account_key)
        self.assertEqual(cand["source_account_label"], self.masked_label)
        self.assertTrue(cand["source_scope_verified"])
        self.assertEqual(cand["source_meta"]["quantity"], 20.0)
        self.assertEqual(cand["source_meta"]["buy_amount"], 1400000.0)
        self.assertEqual(cand["source_meta"]["sell_amount"], 1680000.0)
        self.assertEqual(cand["source_meta"]["fee"], 250.0)
        self.assertEqual(cand["source_meta"]["tax"], 3360.0)
        self.assertNotIn("raw", cand["source_meta"])

    def test_domestic_buy_amt_priority_over_pchs_amt(self):
        row = {
            "trad_dt": "20240410",
            "pdno": "005930",
            "prdt_name": "삼성전자",
            "sll_qty": "20",
            "sll_amt": "1680000",
            "buy_amt": "1400000",
            "pchs_amt": "0",  # Provider bug: pchs_amt returns "0"
            "rlzt_pfls": "280000",
            "pfls_rt": "20.00",
        }
        cand = map_kis_domestic_profit_row(
            row,
            account_name="한투종합",
            source_account_key=self.account_key,
            source_account_label=self.masked_label,
            owner="김철수",
            fetched_at="2024-04-10T15:30:00Z",
        )
        self.assertEqual(cand["source_meta"]["buy_amount"], 1400000.0)

    def test_overseas_row_mapping_with_fx(self):
        row = {
            "trad_day": "20240325",
            "ovrs_pdno": "AAPL",
            "ovrs_item_name": "애플",
            "slcl_qty": "10",
            "frcr_sll_amt_smtl1": "1750.00",
            "frcr_pchs_amt1": "1500.00",
            "ovrs_rlzt_pfls_amt": "250.00",
            "pftrt": "16.67",
            "bass_exrt": "1350.00",
            "crcy_cd": "USD",
            "stck_sll_amt_smtl": "2362500",
            "stck_buy_amt_smtl": "2025000",
            "ovrs_excg_cd": "NASD",
        }
        cand = map_kis_overseas_profit_row(
            row,
            account_name="한투해외",
            source_account_key=self.account_key,
            source_account_label=self.masked_label,
            owner="이영희",
            fetched_at="2024-03-25T18:00:00Z",
        )
        self.assertEqual(cand["date"], "2024-03-25")
        self.assertEqual(cand["code"], "AAPL")
        self.assertEqual(cand["name"], "애플")
        self.assertEqual(cand["currency"], "USD")
        self.assertEqual(cand["pnl"], 250.0)
        self.assertEqual(cand["fx_rate"], 1350.0)
        self.assertEqual(cand["pnl_krw"], 337500.0)
        self.assertEqual(cand["source"], "kis")
        self.assertEqual(cand["source_account_key"], self.account_key)
        self.assertEqual(cand["source_account_label"], self.masked_label)
        self.assertEqual(cand["source_meta"]["market_type"], "us")
        self.assertEqual(cand["source_meta"]["exchange_code"], "NASD")
        self.assertNotIn("raw", cand["source_meta"])

    def test_overseas_row_mapping_without_fx_yields_none_pnl_krw(self):
        # When FX conversion is unavailable, pnl_krw MUST be None, never foreign_pnl
        row = {
            "trad_day": "20240325",
            "ovrs_pdno": "AAPL",
            "ovrs_item_name": "애플",
            "slcl_qty": "10",
            "frcr_sll_amt_smtl1": "1750.00",
            "frcr_pchs_amt1": "1500.00",
            "ovrs_rlzt_pfls_amt": "250.00",
            "pftrt": "16.67",
            "crcy_cd": "USD",
        }
        cand = map_kis_overseas_profit_row(
            row,
            account_name="한투해외",
            source_account_key=self.account_key,
            source_account_label=self.masked_label,
            owner="이영희",
            fetched_at="2024-03-25T18:00:00Z",
        )
        self.assertEqual(cand["currency"], "USD")
        self.assertEqual(cand["pnl"], 250.0)
        self.assertIsNone(cand["fx_rate"])
        self.assertIsNone(cand["pnl_krw"])  # MUST be None, NEVER 250.0 KRW!
        self.assertNotIn("raw", cand["source_meta"])

    def test_fingerprint_deterministic_and_sensitive(self):
        row1 = {
            "trad_dt": "20240410",
            "pdno": "005930",
            "prdt_name": "삼성전자",
            "sll_qty": "20",
            "sll_amt": "1680000",
            "pchs_amt": "1400000",
            "rlzt_pfls": "280000",
        }
        cand1 = map_kis_domestic_profit_row(
            row1, account_name="한투", source_account_key=self.account_key, owner="홍길동", fetched_at="2024-04-10"
        )
        cand2 = map_kis_domestic_profit_row(
            row1, account_name="다른이름", source_account_key=self.account_key, owner="다른소유자", fetched_at="2024-04-10"
        )
        fp1 = build_kis_realized_fingerprint(cand1)
        fp2 = build_kis_realized_fingerprint(cand2)
        # Account display name and owner do not alter financial identity fingerprint
        self.assertEqual(fp1, fp2)

        # Different quantity -> different fingerprint
        row_diff = dict(row1, sll_qty="25")
        cand_diff = map_kis_domestic_profit_row(
            row_diff, account_name="한투", source_account_key=self.account_key, owner="홍길동", fetched_at="2024-04-10"
        )
        self.assertNotEqual(fp1, build_kis_realized_fingerprint(cand_diff))

        # Different account key -> different fingerprint
        other_key = compute_kis_account_key("99999999", "01")
        cand_diff_account = map_kis_domestic_profit_row(
            row1, account_name="한투", source_account_key=other_key, owner="홍길동", fetched_at="2024-04-10"
        )
        self.assertNotEqual(fp1, build_kis_realized_fingerprint(cand_diff_account))

    def test_invalid_mapping_inputs_raise(self):
        with self.assertRaises(ValueError):
            map_kis_domestic_profit_row(
                {}, account_name="한투", source_account_key="k1", owner="홍", fetched_at="2024-01-01"
            )
        with self.assertRaises(ValueError):
            map_kis_domestic_profit_row(
                {"trad_dt": "invalid"}, account_name="한투", source_account_key="k1", owner="홍", fetched_at="2024-01-01"
            )


if __name__ == "__main__":
    unittest.main()
