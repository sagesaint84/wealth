from __future__ import annotations

import csv
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import openpyxl

from app.services import dividend_records, ledger, pnl_records


def csv_bytes(rows: list[dict[str, object]]) -> bytes:
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def xlsx_bytes(rows: list[dict[str, object]]) -> bytes:
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(key) for key in headers])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


class FileImportIdempotencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="wealth-file-import-")
        self.root = Path(self.temp.name)
        self.patches = [
            patch.object(pnl_records, "_get_user_dir", return_value=self.root / "pnl"),
            patch.object(dividend_records, "_get_user_dir", return_value=self.root / "dividend"),
            patch.object(ledger, "get_ledger_path", return_value=self.root / "ledger.json"),
            patch("app.services.stock_master.resolve_stock_info", side_effect=lambda code, name, currency: (code, name, currency or "KRW")),
            patch.object(dividend_records, "resolve_stock_info", side_effect=lambda code, name, currency: (code, name, currency or "KRW")),
            patch.object(pnl_records, "get_historical_fx_rate", return_value=1300.0),
            patch.object(dividend_records, "get_historical_fx_rate", return_value=1300.0),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    @staticmethod
    def pnl_row(day: str, code: str, pnl: object, quantity: object = "1", **extra: object) -> dict[str, object]:
        row = {
            "매도일": day,
            "종목코드": code,
            "종목명": f"Synthetic {code}",
            "통화": "KRW",
            "실현손익": pnl,
            "수량": quantity,
            "소유자": "synthetic-owner",
            "증권사": "synthetic-broker",
            "계좌명": "synthetic-account",
        }
        row.update(extra)
        return row

    @staticmethod
    def dividend_row(day: str, code: str, amount: object, currency: str = "KRW", **extra: object) -> dict[str, object]:
        row = {
            "입금일": day,
            "종목코드": code,
            "종목명": f"Synthetic {code}",
            "통화": currency,
            "실제 배당금": amount,
            "소유자": "synthetic-owner",
            "증권사": "synthetic-broker",
            "계좌명": "synthetic-account",
        }
        row.update(extra)
        return row

    @staticmethod
    def ledger_row(day: str, merchant: str, amount: object, kind: str = "지출", **extra: object) -> dict[str, object]:
        row = {"거래일": day, "내용": merchant, "금액": amount, "구분": kind, "소유자": "아빠"}
        row.update(extra)
        return row

    def test_pnl_same_renamed_reordered_overlap_and_one_additional_row(self) -> None:
        a = self.pnl_row("2026-01-02", "A", "100", "1")
        b = self.pnl_row("2026-01-03", "B", "-50", "2")
        c = self.pnl_row("2026-01-04", "C", "0", "3")
        self.assertEqual(len(pnl_records.import_pnl_file_data(csv_bytes([a, b]), "first.csv")), 2)
        self.assertEqual(len(pnl_records.import_pnl_file_data(xlsx_bytes([b, a]), "renamed.xlsx")), 0)
        self.assertEqual(len(pnl_records.import_pnl_file_data(csv_bytes([b, c]), "overlap.csv")), 1)
        self.assertEqual(len(pnl_records.read_pnl_records()), 3)

    def test_pnl_distinguishes_quantity_amount_fee_and_tax_and_preserves_missing(self) -> None:
        common = {"매수금액": "900", "매도금액": "1000", "수수료": "5", "세금": "10"}
        first = self.pnl_row("2026-02-01", "A", "85", "1", **common)
        second = self.pnl_row("2026-02-01", "A", "85", "2", **common)
        missing = self.pnl_row("2026-02-02", "A", "-25", "1")
        imported = pnl_records.import_pnl_file_data(csv_bytes([first, second, missing]), "pnl.csv")
        self.assertEqual(len(imported), 3)
        self.assertNotEqual(imported[0]["file_import_fingerprint"], imported[1]["file_import_fingerprint"])
        self.assertNotIn("fee", imported[2])
        self.assertNotIn("tax", imported[2])
        self.assertEqual(len(pnl_records.import_pnl_file_data(csv_bytes([second, first, missing]), "copy.xlsx.csv")), 0)

    def test_pnl_identical_rows_use_multiset_occurrences_and_do_not_cross_broker_api_identity(self) -> None:
        row = self.pnl_row("2026-03-01", "A", "10")
        first = pnl_records.import_pnl_file_data(csv_bytes([row, row]), "multi.csv")
        self.assertEqual([item["file_import_occurrence"] for item in first], [1, 2])
        self.assertEqual(len(pnl_records.import_pnl_file_data(csv_bytes([row, row]), "multi-copy.csv")), 0)
        self.assertEqual(len(pnl_records.import_pnl_file_data(csv_bytes([row, row, row]), "grown.csv")), 1)

        records = pnl_records.read_pnl_records()
        api_copy = dict(records[0], id="api", source="kiwoom", source_fingerprint="synthetic")
        api_copy.pop("file_import_fingerprint", None)
        api_copy.pop("file_import_occurrence", None)
        pnl_records.write_pnl_records([api_copy])
        self.assertEqual(len(pnl_records.import_pnl_file_data(csv_bytes([row]), "file.csv")), 1)

    def test_dividend_idempotency_overlap_dates_securities_and_foreign_currency(self) -> None:
        a = self.dividend_row("2026-01-10", "A", "100")
        b = self.dividend_row("2026-02-10", "A", "100")
        c = self.dividend_row("2026-02-10", "B", "100")
        usd = self.dividend_row("2026-03-10", "C", "1.25", "USD")
        self.assertEqual(len(dividend_records.import_dividend_file_data(csv_bytes([a, b, c]), "div.csv")), 3)
        self.assertEqual(len(dividend_records.import_dividend_file_data(xlsx_bytes([c, b, a]), "renamed.xlsx")), 0)
        self.assertEqual(len(dividend_records.import_dividend_file_data(csv_bytes([b, c, usd]), "overlap.csv")), 1)
        self.assertEqual(len(dividend_records.read_dividend_records()), 4)

    def test_dividend_optional_deductions_preserve_missing_and_affect_identity(self) -> None:
        missing = self.dividend_row("2026-04-01", "A", "80")
        detailed = self.dividend_row("2026-04-01", "A", "80", 세전배당금="100", 세금="20", 수수료="0")
        imported = dividend_records.import_dividend_file_data(csv_bytes([missing, detailed]), "details.csv")
        self.assertEqual(len(imported), 2)
        self.assertNotIn("tax", imported[0])
        self.assertEqual(imported[1]["tax"], 20.0)
        self.assertNotEqual(imported[0]["file_import_fingerprint"], imported[1]["file_import_fingerprint"])

    def test_dividend_identical_rows_preserve_multiset_cardinality(self) -> None:
        row = self.dividend_row("2026-05-01", "A", "25")
        self.assertEqual(len(dividend_records.import_dividend_file_data(csv_bytes([row, row]), "two.csv")), 2)
        self.assertEqual(len(dividend_records.import_dividend_file_data(csv_bytes([row, row]), "copy.csv")), 0)
        self.assertEqual(len(dividend_records.import_dividend_file_data(csv_bytes([row, row, row]), "three.csv")), 1)

    def test_dividend_import_fails_closed_on_malformed_existing_storage(self) -> None:
        path = dividend_records._get_dividend_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{malformed", encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaises(dividend_records.DividendRecordsStorageError):
            dividend_records.import_dividend_file_data(csv_bytes([self.dividend_row("2026-05-02", "A", "25")]), "new.csv")
        self.assertEqual(path.read_bytes(), before)

    def test_ledger_same_renamed_reordered_overlap_and_additional_row(self) -> None:
        a = self.ledger_row("2026-01-01", "Alpha", "100")
        b = self.ledger_row("2026-01-02", "Beta", "200")
        c = self.ledger_row("2026-01-03", "Gamma", "300")
        self.assertEqual(ledger.import_ledger_from_file_bytes(csv_bytes([a, b]), "first.csv"), 2)
        self.assertEqual(ledger.import_ledger_from_file_bytes(xlsx_bytes([b, a]), "renamed.xlsx"), 0)
        self.assertEqual(ledger.import_ledger_from_file_bytes(csv_bytes([b, c]), "overlap.csv"), 1)
        self.assertEqual(len(ledger.read_ledger()["transactions"]), 3)

    def test_ledger_distinguishes_memo_direction_time_balance_and_institution(self) -> None:
        base = self.ledger_row("2026-02-01", "Merchant", "100", 메모="first", 거래시간="10:00:00", 거래후잔액="900", 금융기관="A")
        different_memo = dict(base, 메모="second")
        different_time = dict(base, 거래시간="10:01:00")
        income = dict(base, 구분="입금")
        zero_balance = dict(base, 거래후잔액=0, 거래시간="10:02:00")
        no_optional = self.ledger_row("2026-02-02", "Merchant", "100")
        rows = [base, different_memo, different_time, income, zero_balance, no_optional]
        self.assertEqual(ledger.import_ledger_from_file_bytes(csv_bytes(rows), "ledger.csv"), 6)
        saved = ledger.read_ledger()["transactions"]
        self.assertNotIn("balance_after", saved[-1])
        self.assertEqual(saved[-2]["balance_after"], 0.0)
        self.assertEqual(len({item["file_import_fingerprint"] for item in saved}), 6)
        self.assertEqual(ledger.import_ledger_from_file_bytes(csv_bytes(list(reversed(rows))), "copy.csv"), 0)

    def test_ledger_legitimate_identical_rows_use_occurrence_multiset(self) -> None:
        row = self.ledger_row("2026-03-01", "Repeated", "777")
        self.assertEqual(ledger.import_ledger_from_file_bytes(csv_bytes([row, row]), "two.csv"), 2)
        self.assertEqual(ledger.import_ledger_from_file_bytes(csv_bytes([row, row]), "renamed.csv"), 0)
        self.assertEqual(ledger.import_ledger_from_file_bytes(csv_bytes([row, row, row]), "grown.csv"), 1)

    def test_ledger_import_fails_closed_on_malformed_existing_storage(self) -> None:
        path = ledger.get_ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{malformed", encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaises(ledger.LedgerImportStorageError):
            ledger.import_ledger_from_file_bytes(csv_bytes([self.ledger_row("2026-03-02", "New", "1")]), "new.csv")
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
