from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.services.toss_wts_adapter import TossWtsAdapter, TossWtsAdapterError, TossWtsConfig
from app.services.toss_wts_income import (
    build_toss_wts_income_fingerprint,
    classify_toss_wts_income_row,
    map_toss_wts_income_row,
    map_toss_wts_income_rows,
)


def ledger_row(*, market="kr", currency="KRW", summary_no="1104", trade_name="배당금입금", stock_code="005930", stock_name="테스트주식", amount=10000, adjusted=8460, tax=1540, no=7):
    return {
        "market": market, "category": "cash", "currency": currency,
        "datetime": "2026-09-01T12:00:00+09:00", "display_type": "13",
        "stock_name": stock_name, "amount": amount, "adjusted_amount": adjusted,
        "source_meta": {
            "summary_no": summary_no, "trade_type_name": trade_name,
            "transaction_type_code": "1", "transaction_type_name": "입금",
            "display_type": "13", "stock_code": stock_code, "stock_name": stock_name,
            "product_name": stock_name, "quantity": 0,
            "provider_amount": amount, "provider_adjusted_amount": adjusted,
            "provider_tax_amount": tax,
            "composite_key": {"date": "20260901", "no": no},
        },
    }


class TossWtsIncomeMappingTests(unittest.TestCase):
    def test_verified_kr_categories(self):
        self.assertEqual(classify_toss_wts_income_row(ledger_row()), "dividend")
        self.assertEqual(classify_toss_wts_income_row(ledger_row(summary_no="1117", trade_name="결산분배금입금", stock_code="069500")), "distribution")
        self.assertEqual(classify_toss_wts_income_row(ledger_row(summary_no="1017", trade_name="이자입금", stock_code="", stock_name="")), "account_interest")

    def test_verified_us_categories(self):
        self.assertEqual(classify_toss_wts_income_row(ledger_row(market="us", currency="USD", summary_no="1207", trade_name="", stock_code="US0378331005", amount=12.5, adjusted=12.5, tax=0)), "dividend")
        self.assertEqual(classify_toss_wts_income_row(ledger_row(market="us", currency="USD", summary_no="1204", trade_name="", stock_code="", stock_name="", amount=1.25, adjusted=1.25, tax=0)), "account_interest")

    def test_unknown_and_tax_rows_fail_closed(self):
        for row in (
            ledger_row(summary_no="1114", trade_name="배당단주대금입금"),
            ledger_row(summary_no="2123", trade_name="배당세출금"),
            ledger_row(summary_no="1374", trade_name="캐시백입금", stock_code=""),
        ):
            self.assertIsNone(classify_toss_wts_income_row(row))

    def test_kr_net_gross_tax_mapping_and_us_net_only(self):
        mapped = map_toss_wts_income_row(ledger_row())
        self.assertEqual(mapped["amount"], 8460)
        self.assertEqual(mapped["gross_amount"], 10000)
        self.assertEqual(mapped["tax"], 1540)
        us = map_toss_wts_income_row(ledger_row(market="us", currency="USD", summary_no="1207", trade_name="", stock_code="US0378331005", amount=12.5, adjusted=12.5, tax=0))
        self.assertNotIn("gross_amount", us)
        self.assertNotIn("tax", us)

    def test_fingerprint_deterministic_and_composite_sensitive(self):
        first = build_toss_wts_income_fingerprint(ledger_row())
        self.assertEqual(first, build_toss_wts_income_fingerprint(ledger_row()))
        self.assertNotEqual(first, build_toss_wts_income_fingerprint(ledger_row(no=8)))

    def test_batch_counts_ignored(self):
        result = map_toss_wts_income_rows([ledger_row(), ledger_row(summary_no="1374", trade_name="캐시백입금", stock_code="")])
        self.assertEqual((result["fetched"], result["eligible"], result["ignored"], result["invalid"]), (2, 1, 1, 0))


class TossWtsTransactionAdapterTests(unittest.TestCase):
    def configured(self, root: Path) -> TossWtsConfig:
        exe = root / "tossctl"; exe.write_text("fake", encoding="utf-8")
        cfg = root / "config"; cfg.mkdir()
        (cfg / "session.json").write_text("fake", encoding="utf-8")
        return TossWtsConfig(True, exe, cfg, "v0.50.3", 3)

    @staticmethod
    def provider_row():
        return {
            "type": "2", "category": "cash", "code": "1", "display_name": "배당",
            "display_type": "13", "summary": "배당금", "market": "kr", "currency": "KRW",
            "stock_name": "테스트주식", "amount": 10000, "adjusted_amount": 8460,
            "balance_amount": 100000, "datetime": "2026-09-01T12:00:00+09:00", "sort_key": "x",
            "raw": {
                "type": "2", "transactionType": {"code": "1", "displayName": "입금"},
                "displayType": "13", "summary": "배당금", "stockCode": "005930",
                "stockName": "테스트주식", "productName": "테스트주식",
                "productNameFromOrdered": "", "quantity": 0.0, "amount": 10000.0,
                "adjustedAmount": 8460.0, "commissionAmount": 0.0,
                "totalTaxAmount": 1540.0, "loanOrderId": None, "balanceAmount": 100000.0,
                "cancelTradeYn": False, "summaryNo": "1104", "tradeTypeName": "배당금입금",
                "rightHistory": None, "transferDelay": False,
                "dateTime": "2026-09-01T12:00:00+09:00", "executionDate": None,
                "refund": None, "exchange": None, "dividend": None, "bond": None,
                "referenceType": None, "referenceId": None,
                "opponentAccountInfo": {"account": "SHOULD_NOT_LEAK"},
                "isTaxable": None, "compositeKey": {"date": "20260901", "no": 7},
            },
        }

    def test_transactions_safe_argv_and_raw_sanitized(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = TossWtsAdapter(self.configured(Path(temp)))
            completed = Mock(returncode=0, stdout=json.dumps([self.provider_row()]), stderr="")
            with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch("app.services.toss_wts_adapter.subprocess.run", return_value=completed) as run:
                rows = adapter.get_transactions_list("2026-03-09", "2026-09-24", market="kr")
        self.assertEqual(len(rows), 1)
        self.assertNotIn("raw", rows[0])
        self.assertNotIn("SHOULD_NOT_LEAK", repr(rows[0]))
        self.assertEqual(rows[0]["source_meta"]["summary_no"], "1104")
        argv = run.call_args.args[0]
        self.assertIn("transactions", argv)
        self.assertIn("list", argv)
        self.assertEqual(argv[-2:], ["--size", "50"])
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_query_over_200_days_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = TossWtsAdapter(self.configured(Path(temp)))
            with patch("app.services.toss_wts_adapter.subprocess.run") as run:
                with self.assertRaisesRegex(TossWtsAdapterError, "^INVALID_SCHEMA$"):
                    adapter.get_transactions_list("2026-01-01", "2026-09-24", market="kr")
            run.assert_not_called()

    def test_long_range_is_split_and_both_markets_queried(self):
        adapter = Mock(spec=TossWtsAdapter)
        adapter.get_transactions_list.side_effect = [[{"market": "kr"}], [{"market": "us"}], [{"market": "kr"}], [{"market": "us"}]]
        result = TossWtsAdapter.get_income_transactions(adapter, "2026-01-01", "2026-09-24")
        self.assertEqual(len(result["windows"]), 2)
        self.assertEqual(len(result["rows"]), 4)
        self.assertEqual(adapter.get_transactions_list.call_count, 4)

    def test_user_scoped_config_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exe = root / "tossctl"; exe.write_text("fake", encoding="utf-8")
            cfg = root / "toss-wts" / "users" / "alice" / "config"
            cfg.mkdir(parents=True)
            (cfg / "session.json").write_text("fake", encoding="utf-8")
            settings = {"enabled": True, "executable": str(exe), "config_dir": "/wrong/global", "expected_version": "v0.50.3", "timeout_seconds": 3}
            with patch.dict(os.environ, {"WEALTH_DATA_DIR": str(root)}), patch("app.services.toss_wts_adapter.resolve_toss_wts_settings", return_value=settings):
                adapter = TossWtsAdapter(username="alice")
                status = adapter.get_local_status()
            self.assertTrue(status["adapter_ready"])
            self.assertEqual(adapter._config.config_dir, cfg)


if __name__ == "__main__":
    unittest.main()
