from __future__ import annotations

import json
from pathlib import Path
import unittest
from decimal import Decimal

from app.services.broker_realized_import import (
    BrokerRealizedImportError,
    canonicalize_realized_date,
)
from app.services.nh_feed import project_nh_row
from app.services.nh_realized import classify_nh_rows, nh_fingerprint, NEW, ALREADY_IMPORTED, POSSIBLE_DUPLICATE, INVALID
from app.services.kiwoom_feed import project_kiwoom_row
from app.services.kiwoom_realized import classify_kiwoom_rows, kiwoom_fingerprint
from app.services.kb_feed import project_kb_domestic_row
from app.services.kb_realized import classify_kb_rows, kb_fingerprint
from app.services import pnl_records
from tests.regression_support import IsolatedDataTestCase


class RealizedDateCanonicalizationTests(unittest.TestCase):
    def test_canonicalize_iso_valid(self):
        self.assertEqual(canonicalize_realized_date("2026-09-23"), "2026-09-23")
        self.assertEqual(canonicalize_realized_date("2024-02-29"), "2024-02-29")
        self.assertEqual(canonicalize_realized_date("1999-12-31"), "1999-12-31")

    def test_canonicalize_compact_valid(self):
        self.assertEqual(canonicalize_realized_date("20260923"), "2026-09-23")
        self.assertEqual(canonicalize_realized_date("20240229"), "2024-02-29")
        self.assertEqual(canonicalize_realized_date("19991231"), "1999-12-31")

    def test_canonicalize_rejects_invalid_calendar_dates(self):
        # Non-existent leap day
        with self.assertRaises((ValueError, BrokerRealizedImportError)):
            canonicalize_realized_date("20230229")
        with self.assertRaises((ValueError, BrokerRealizedImportError)):
            canonicalize_realized_date("2023-02-29")
        # Day 30 in February
        with self.assertRaises((ValueError, BrokerRealizedImportError)):
            canonicalize_realized_date("20260230")
        with self.assertRaises((ValueError, BrokerRealizedImportError)):
            canonicalize_realized_date("2026-02-30")
        # Month 13
        with self.assertRaises((ValueError, BrokerRealizedImportError)):
            canonicalize_realized_date("20261301")
        # Month 00 or Day 00
        with self.assertRaises((ValueError, BrokerRealizedImportError)):
            canonicalize_realized_date("20260001")
        with self.assertRaises((ValueError, BrokerRealizedImportError)):
            canonicalize_realized_date("20260100")

    def test_canonicalize_rejects_malformed_empty_and_types(self):
        for invalid in ("", "   ", None, True, False, 12345, "2026-9-1", "2026/09/01", "random"):
            with self.assertRaises((ValueError, BrokerRealizedImportError)):
                canonicalize_realized_date(invalid)


class NHRealizedDateCanonicalizationTests(unittest.TestCase):
    def test_nh_domestic_projection_keeps_compact_feed_date_but_candidate_is_iso(self):
        raw = {
            "_wealth_date_context": "20260901",
            "iem_cd": "005930",
            "iem_nm": "삼성전자",
            "sll_qty": "10",
            "byn_uit_pr": "60000",
            "byn_amt": "600000",
            "sll_uit_pr": "70000",
            "sll_amt": "700000",
            "pls_amt": "100000",
            "pft_rt": "16.6",
            "fee_sum": "500",
            "tax_sum": "1500",
        }
        feed_row = project_nh_row(raw, "kr")
        # Feed row date remains compact YYYYMMDD for row signing and stable hash
        self.assertEqual(feed_row["date"], "20260901")

        result = classify_nh_rows([feed_row], [], "key-nh-1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], NEW)
        # Candidate date must be canonical YYYY-MM-DD
        self.assertEqual(result[0]["candidate"]["date"], "2026-09-01")

    def test_nh_fingerprint_preservation_and_already_imported_match(self):
        raw = {
            "_wealth_date_context": "20260901",
            "iem_cd": "005930",
            "iem_nm": "삼성전자",
            "sll_qty": "10",
            "byn_uit_pr": "60000",
            "byn_amt": "600000",
            "sll_uit_pr": "70000",
            "sll_amt": "700000",
            "pls_amt": "100000",
            "pft_rt": "16.6",
            "fee_sum": "500",
            "tax_sum": "1500",
        }
        feed_row = project_nh_row(raw, "kr")
        expected_fp = nh_fingerprint(feed_row, "key-nh-1", 0)

        # Existing record stored with canonical YYYY-MM-DD date and stored source_fingerprint
        existing_record_iso = {
            "source": "nh",
            "source_fingerprint": expected_fp,
            "date": "2026-09-01",
            "code": "005930",
            "pnl": "100000",
        }
        result = classify_nh_rows([feed_row], [existing_record_iso], "key-nh-1")
        self.assertEqual(result[0]["status"], ALREADY_IMPORTED)
        self.assertEqual(result[0]["fingerprint"], expected_fp)

        # Existing record stored with legacy YYYYMMDD date also matches
        existing_record_compact = {
            "source": "nh",
            "source_fingerprint": expected_fp,
            "date": "20260901",
            "code": "005930",
            "pnl": "100000",
        }
        result2 = classify_nh_rows([feed_row], [existing_record_compact], "key-nh-1")
        self.assertEqual(result2[0]["status"], ALREADY_IMPORTED)

    def test_nh_manual_duplicate_match_across_date_formats(self):
        raw = {
            "_wealth_date_context": "20260901",
            "iem_cd": "005930",
            "iem_nm": "삼성전자",
            "sll_qty": "10",
            "byn_uit_pr": "60000",
            "byn_amt": "600000",
            "sll_uit_pr": "70000",
            "sll_amt": "700000",
            "pls_amt": "100000",
            "pft_rt": "16.6",
            "fee_sum": "500",
            "tax_sum": "1500",
        }
        feed_row = project_nh_row(raw, "kr")

        # Manual record with ISO date YYYY-MM-DD
        manual_record_iso = {
            "source": "manual",
            "date": "2026-09-01",
            "code": "005930",
            "pnl": "100000",
        }
        result = classify_nh_rows([feed_row], [manual_record_iso], "key-nh-1")
        self.assertEqual(result[0]["status"], POSSIBLE_DUPLICATE)

        # Manual record with compact date YYYYMMDD
        manual_record_compact = {
            "source": "manual",
            "date": "20260901",
            "code": "005930",
            "pnl": "100000",
        }
        result2 = classify_nh_rows([feed_row], [manual_record_compact], "key-nh-1")
        self.assertEqual(result2[0]["status"], POSSIBLE_DUPLICATE)


class KiwoomRealizedDateCanonicalizationTests(unittest.TestCase):
    def test_kiwoom_projection_keeps_compact_feed_date_but_candidate_is_iso(self):
        raw = {
            "dt": "20260901", "stk_cd": "A005930", "stk_nm": "Samsung",
            "cntr_qty": "2", "buy_uv": "10", "cntr_pric": "20",
            "tdy_sel_pl": "20", "pl_rt": "100", "tdy_trde_cmsn": "1",
            "tdy_trde_tax": "2",
        }
        feed_row = project_kiwoom_row(raw, "kr")
        self.assertEqual(feed_row["date"], "20260901")

        result = classify_kiwoom_rows([dict(feed_row, source_occurrence=1)], [], "key-kw-1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], NEW)
        self.assertEqual(result[0]["candidate"]["date"], "2026-09-01")

    def test_kiwoom_already_imported_and_manual_duplicate_across_date_formats(self):
        raw = {
            "dt": "20260901", "stk_cd": "A005930", "stk_nm": "Samsung",
            "cntr_qty": "2", "buy_uv": "10", "cntr_pric": "20",
            "tdy_sel_pl": "20", "pl_rt": "100", "tdy_trde_cmsn": "1",
            "tdy_trde_tax": "2",
        }
        feed_row = project_kiwoom_row(raw, "kr")
        fp = kiwoom_fingerprint(feed_row, "key-kw-1", 1)

        # ALREADY_IMPORTED with ISO date in existing
        existing_iso = {"source": "kiwoom", "source_fingerprint": fp, "date": "2026-09-01"}
        res = classify_kiwoom_rows([dict(feed_row, source_occurrence=1)], [existing_iso], "key-kw-1")
        self.assertEqual(res[0]["status"], ALREADY_IMPORTED)

        # POSSIBLE_DUPLICATE with manual ISO record
        manual_iso = {"source": "manual", "date": "2026-09-01", "code": "005930", "pnl": "20"}
        res_m1 = classify_kiwoom_rows([dict(feed_row, source_occurrence=1)], [manual_iso], "key-kw-1")
        self.assertEqual(res_m1[0]["status"], POSSIBLE_DUPLICATE)

        # POSSIBLE_DUPLICATE with manual compact record
        manual_compact = {"source": "manual", "date": "20260901", "code": "005930", "pnl": "20"}
        res_m2 = classify_kiwoom_rows([dict(feed_row, source_occurrence=1)], [manual_compact], "key-kw-1")
        self.assertEqual(res_m2[0]["status"], POSSIBLE_DUPLICATE)


class KBRealizedDateCanonicalizationTests(unittest.TestCase):
    def test_kb_projection_keeps_compact_feed_date_but_candidate_is_iso(self):
        raw = {
            "trd_dt": "20260901", "stnd_is_cd": "KR7005930003", "shrt_is_cd": "A005930",
            "is_nm": "삼성전자", "trd_dl_ccd": "01", "crdt_typ_cd": "00", "ccls_q": "2",
            "dtls_ccls_q": "2", "dcml_dl_f": "0", "ccls_uprc": "70000", "b_uprc": "60000",
            "s_amt": "140000", "b_amt": "120000", "fee": "100", "svrl_tx": "300",
            "rlztn_pl": "19600", "yld": "16.33",
        }
        feed_row = project_kb_domestic_row(raw)
        self.assertEqual(feed_row["date"], "20260901")

        result = classify_kb_rows([dict(feed_row, source_occurrence=1)], [], "key-kb-1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], NEW)
        self.assertEqual(result[0]["candidate"]["date"], "2026-09-01")

    def test_kb_already_imported_and_manual_duplicate_across_date_formats(self):
        raw = {
            "trd_dt": "20260901", "stnd_is_cd": "KR7005930003", "shrt_is_cd": "A005930",
            "is_nm": "삼성전자", "trd_dl_ccd": "01", "crdt_typ_cd": "00", "ccls_q": "2",
            "dtls_ccls_q": "2", "dcml_dl_f": "0", "ccls_uprc": "70000", "b_uprc": "60000",
            "s_amt": "140000", "b_amt": "120000", "fee": "100", "svrl_tx": "300",
            "rlztn_pl": "19600", "yld": "16.33",
        }
        feed_row = project_kb_domestic_row(raw)
        fp = kb_fingerprint(feed_row, "key-kb-1", 1)

        # ALREADY_IMPORTED
        existing = {"source": "kb", "source_fingerprint": fp, "date": "2026-09-01"}
        res = classify_kb_rows([dict(feed_row, source_occurrence=1)], [existing], "key-kb-1")
        self.assertEqual(res[0]["status"], ALREADY_IMPORTED)

        # POSSIBLE_DUPLICATE with manual ISO record
        manual_iso = {"source": "manual", "date": "2026-09-01", "code": "005930", "pnl": "19600"}
        res_m1 = classify_kb_rows([dict(feed_row, source_occurrence=1)], [manual_iso], "key-kb-1")
        self.assertEqual(res_m1[0]["status"], POSSIBLE_DUPLICATE)

        # POSSIBLE_DUPLICATE with manual compact record
        manual_compact = {"source": "manual", "date": "20260901", "code": "005930", "pnl": "19600"}
        res_m2 = classify_kb_rows([dict(feed_row, source_occurrence=1)], [manual_compact], "key-kb-1")
        self.assertEqual(res_m2[0]["status"], POSSIBLE_DUPLICATE)


class PnlRecordsStorageAndValidationTests(IsolatedDataTestCase):
    def test_legacy_compact_date_canonicalized_in_memory_on_read(self):
        username = "test-user-date"
        pnl_file = pnl_records._get_pnl_file(username)
        pnl_file.parent.mkdir(parents=True, exist_ok=True)
        # Write legacy record with YYYYMMDD date directly to file
        legacy_data = {
            "records": [
                {
                    "id": "rec-1",
                    "date": "20260901",
                    "code": "005930",
                    "name": "삼성전자",
                    "currency": "KRW",
                    "pnl": 10000.0,
                    "pnl_krw": 10000.0,
                    "source": "nh",
                    "source_fingerprint": "nh-realized:v1:legacy-hash",
                }
            ],
            "updated_at": "2026-09-23T00:00:00Z",
        }
        with open(pnl_file, "w", encoding="utf-8") as fp:
            json.dump(legacy_data, fp)

        # read_pnl_records canonicalizes to YYYY-MM-DD
        records = pnl_records.read_pnl_records(username)
        self.assertEqual(records[0]["date"], "2026-09-01")
        # Fingerprint is untouched
        self.assertEqual(records[0]["source_fingerprint"], "nh-realized:v1:legacy-hash")

    def test_create_and_update_pnl_record_date_validation(self):
        username = "test-user-validation"
        # 1. Broker record requires date
        with self.assertRaises(ValueError):
            pnl_records.create_pnl_record({
                "source": "nh",
                "code": "005930",
                "pnl": 1000,
            }, username=username)

        # 2. Broker record rejects invalid calendar date
        with self.assertRaises(ValueError):
            pnl_records.create_pnl_record({
                "source": "nh",
                "date": "20260230",
                "code": "005930",
                "pnl": 1000,
            }, username=username)

        # 3. Broker record canonicalizes valid compact date to ISO
        rec = pnl_records.create_pnl_record({
            "source": "nh",
            "date": "20260901",
            "code": "005930",
            "pnl": 1000,
        }, username=username)
        self.assertEqual(rec["date"], "2026-09-01")

        # 4. Update with compact date canonicalizes to ISO
        updated = pnl_records.update_pnl_record(rec["id"], {
            "date": "20260902",
        }, username=username)
        self.assertEqual(updated["date"], "2026-09-02")

    def test_open_pnl_record_dialog_normalizes_compact_date_frontend(self):
        js = (Path(__file__).resolve().parents[1] / "app" / "static" / "wealth.js").read_text(encoding="utf-8")
        self.assertIn("/^\\d{8}$/.test(targetDate.trim())", js)
        self.assertIn("targetDate = `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6)}`", js)
