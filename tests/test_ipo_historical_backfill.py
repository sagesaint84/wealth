"""KRX + OpenDART historical IPO backfill contracts."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.services.ipo.historical_backfill import Classification, HistoricalBackfillEngine, HistoricalBackfillError, parse_dart_subscription_schedule
from app.services.ipo.dart_client import DartRateLimitError
from app.services.ipo.presentation import derive_filter_group, derive_market_state
from app.services.ipo.score import calculate_wealth_ipo_score
from app.services.ipo.store import default_market_store, read_market_store, write_market_store


def krx_row(**extra):
    row = {"stock_code": "348370", "company_name": "엔켐", "market": "코스닥", "actual_listing_date": "2021-11-01", "final_offer_price": 42000.0}
    row.update(extra)
    return row


def dart_schedule(start="2021-10-21", end="2021-10-22", payment="2021-10-26"):
    return {"status": "000", "list": [{"sbd": f"{start} ~ {end}", "pymd": payment, "sband": "2021-10-20", "asand": "2021-10-25"}]}


class HistoricalBackfillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.market_file = Path(self.temp.name) / "market.json"
        self.store_patch = patch("app.services.ipo.store.get_market_file", return_value=self.market_file)
        self.engine_patch = patch("app.services.ipo.historical_backfill.get_market_file", return_value=self.market_file)
        self.store_patch.start(); self.engine_patch.start(); write_market_store(default_market_store())
        self.krx = MagicMock(); self.krx.fetch_new_listings.return_value = [krx_row()]
        self.dart = MagicMock(); self.dart.is_configured.return_value = True
        self.dart.get_corp_code_master.return_value = [{"corp_code": "00123456", "corp_name": "엔켐", "stock_code": "348370"}]
        self.dart.get_equity_registration_statements.return_value = dart_schedule()

    def tearDown(self):
        self.engine_patch.stop(); self.store_patch.stop(); self.temp.cleanup()

    def engine(self): return HistoricalBackfillEngine(krx_client=self.krx, dart_client=self.dart)

    def test_krx_candidate_is_hydrated_without_kind_and_preview_is_read_only(self):
        before = self.market_file.read_bytes(); preview = self.engine().generate_preview(2021, 2021)
        self.assertEqual(preview.items[0].classification, Classification.NEW.value)
        rec = preview.items[0].candidate_record
        self.assertEqual((rec["subscription_start"], rec["subscription_end"], rec["payment_date"]), ("2021-10-21", "2021-10-22", "2021-10-26"))
        self.assertEqual((rec["actual_listing_date"], rec["final_offer_price"]), ("2021-11-01", 42000.0))
        self.assertIn("krx_historical", rec["sources"]); self.assertIn("dart_schedule_historical", rec["sources"])
        self.assertEqual(before, self.market_file.read_bytes()); self.assertFalse(hasattr(self.engine(), "kind_client"))

    def test_krx_is_called_per_year_and_dart_schedule_parses_single_and_range(self):
        self.krx.fetch_new_listings.return_value = []
        self.engine().generate_preview(2020, 2021); self.assertEqual(self.krx.fetch_new_listings.call_count, 2)
        ranged = parse_dart_subscription_schedule({"general": [{"sbd": "2021년 10월 21일 ~ 2021년 10월 22일", "pymd": "2021.10.26"}]})
        self.assertEqual((ranged["subscription_start"], ranged["subscription_end"], ranged["payment_date"]), ("2021-10-21", "2021-10-22", "2021-10-26"))
        single = parse_dart_subscription_schedule({"general": [{"sbd": "20211021"}]})
        self.assertEqual((single["subscription_start"], single["subscription_end"]), ("2021-10-21", "2021-10-21"))

    def test_corp_resolution_is_exact_first_and_ambiguous_or_missing_schedule_reviewed(self):
        self.dart.get_corp_code_master.return_value = [{"corp_code": "wrong", "corp_name": "엔켐", "stock_code": ""}, {"corp_code": "right", "corp_name": "다른", "stock_code": "348370"}]
        self.assertEqual(self.engine().generate_preview(2021, 2021).items[0].candidate_record["corp_code"], "right")
        self.dart.get_corp_code_master.return_value = [{"corp_code": "a", "corp_name": "엔켐", "stock_code": "348370"}, {"corp_code": "b", "corp_name": "엔켐", "stock_code": "348370"}]
        self.assertEqual(self.engine().generate_preview(2021, 2021).items[0].classification, Classification.REVIEW_REQUIRED.value)
        self.dart.get_corp_code_master.return_value = [{"corp_code": "a", "corp_name": "엔켐", "stock_code": "348370"}]; self.dart.get_equity_registration_statements.return_value = {"status": "000", "list": []}
        self.assertEqual(self.engine().generate_preview(2021, 2021).items[0].classification, Classification.REVIEW_REQUIRED.value)

    def test_missing_dart_fails_closed_and_preview_digest_protects_commit(self):
        self.dart.is_configured.return_value = False
        with self.assertRaises(HistoricalBackfillError): self.engine().generate_preview(2021, 2021)
        self.dart.is_configured.return_value = True
        preview = self.engine().generate_preview(2021, 2021)
        changed = read_market_store(); changed["ipos"].append({"ipo_id": "other", "company_name": "other"}); write_market_store(changed)
        with self.assertRaises(HistoricalBackfillError): self.engine().commit_backfill(preview)

    def test_commit_duplicate_conflict_and_spac_contract(self):
        preview = self.engine().generate_preview(2021, 2021); self.assertEqual(self.engine().commit_backfill(preview)["applied_new"], 1)
        self.assertEqual(read_market_store()["ipos"][0]["actual_listing_date"], "2021-11-01")
        self.krx.fetch_new_listings.return_value = [krx_row(), krx_row(company_name="엔켐2")]
        self.assertIn(Classification.CONFLICT.value, [item.classification for item in self.engine().generate_preview(2021, 2021).items])
        self.krx.fetch_new_listings.return_value = [krx_row(company_name="한국제17호기업인수목적", stock_code="999999")]
        self.dart.get_corp_code_master.return_value = [{"corp_code": "spac", "corp_name": "한국제17호기업인수목적", "stock_code": "999999"}]
        self.assertEqual(self.engine().generate_preview(2021, 2021).items[0].candidate_record["listing_track"], "spac")

    def test_phase_b_keeps_point_in_time_filing_and_resume_contract(self):
        store = default_market_store(); store["ipos"] = [{"ipo_id": "ipo", "company_name": "엔켐", "corp_code": "00123456", "listing_track": "general", "subscription_start": "2021-10-21", "features": {}, "sources": {}}]; write_market_store(store)
        dart = MagicMock(); dart.is_configured.return_value = True
        dart.get_filing_list.return_value = {"list": [{"rcept_no": "future", "rcept_dt": "20211021", "report_nm": "증권신고서"}, {"rcept_no": "before", "rcept_dt": "20211020", "report_nm": "증권신고서"}]}; dart.download_document_zip.return_value = b"zip"
        with patch("app.services.ipo.historical_backfill.extract_document_text_from_zip", return_value="희망공모가액 15,000원 ~ 18,000원"):
            result = self.engine().enrich_dart(dart_client=dart, from_year=2021, to_year=2021)
        self.assertEqual(result["enriched"], 1); self.assertEqual(read_market_store()["ipos"][0]["sources"]["dart_historical"]["rcept_no"], "before")

    def test_from_year_before_2020_is_rejected(self):
        with self.assertRaises(HistoricalBackfillError): self.engine().generate_preview(2019, 2020)

    def test_to_year_after_current_kst_year_is_rejected(self):
        from app.services.ipo.historical_backfill import get_current_kst_date
        with self.assertRaises(HistoricalBackfillError): self.engine().generate_preview(2020, get_current_kst_date().year + 1)

    def test_inverted_year_range_is_rejected(self):
        with self.assertRaises(HistoricalBackfillError): self.engine().generate_preview(2021, 2020)

    def test_krx_fetch_failure_is_not_silently_accepted(self):
        from app.services.ipo.krx_client import KrxClientError
        self.krx.fetch_new_listings.side_effect = KrxClientError("partial")
        with self.assertRaises(HistoricalBackfillError): self.engine().generate_preview(2021, 2021)

    def test_normalized_company_name_unique_corp_match_is_used(self):
        self.krx.fetch_new_listings.return_value = [krx_row(stock_code="", company_name="엔 켐")]
        self.dart.get_corp_code_master.return_value = [{"corp_code": "name", "corp_name": "엔켐", "stock_code": ""}]
        self.assertEqual(self.engine().generate_preview(2021, 2021).items[0].candidate_record["corp_code"], "name")

    def test_unmatched_corp_code_is_review_required_without_guessing(self):
        self.dart.get_corp_code_master.return_value = []
        item = self.engine().generate_preview(2021, 2021).items[0]
        self.assertEqual(item.classification, Classification.REVIEW_REQUIRED.value)
        self.assertIn("not_found", item.reason)

    def test_iso_single_subscription_date_is_preserved(self):
        value = parse_dart_subscription_schedule({"general": [{"sbd": "2021-10-21"}]})
        self.assertEqual((value["subscription_start"], value["subscription_end"]), ("2021-10-21", "2021-10-21"))

    def test_korean_single_subscription_date_is_preserved(self):
        value = parse_dart_subscription_schedule({"general": [{"sbd": "2021년 10월 21일"}]})
        self.assertEqual((value["subscription_start"], value["subscription_end"]), ("2021-10-21", "2021-10-21"))

    def test_invalid_subscription_schedule_is_review_required(self):
        self.dart.get_equity_registration_statements.return_value = {"status": "000", "list": [{"sbd": "청약일 미정"}]}
        self.assertEqual(self.engine().generate_preview(2021, 2021).items[0].classification, Classification.REVIEW_REQUIRED.value)

    def test_inverted_subscription_dates_are_not_committed(self):
        self.dart.get_equity_registration_statements.return_value = dart_schedule("2021-10-22", "2021-10-21")
        self.assertEqual(self.engine().generate_preview(2021, 2021).items[0].classification, Classification.REVIEW_REQUIRED.value)

    def test_listing_date_is_not_used_as_subscription_date(self):
        self.dart.get_equity_registration_statements.return_value = {"status": "000", "list": []}
        item = self.engine().generate_preview(2021, 2021).items[0]
        self.assertIsNone(item.subscription_start)
        self.assertEqual(item.actual_listing_date, "2021-11-01")

    def test_refund_date_is_never_inferred(self):
        rec = self.engine().generate_preview(2021, 2021).items[0].candidate_record
        self.assertEqual(rec["payment_date"], "2021-10-26")
        self.assertIsNone(rec["refund_date"])

    def test_expected_listing_date_is_not_copied_from_actual(self):
        rec = self.engine().generate_preview(2021, 2021).items[0].candidate_record
        self.assertEqual(rec["actual_listing_date"], "2021-11-01")
        self.assertIsNone(rec["expected_listing_date"])

    def test_zero_final_offer_price_is_retained_without_substitution(self):
        self.krx.fetch_new_listings.return_value = [krx_row(final_offer_price=0.0)]
        self.assertEqual(self.engine().generate_preview(2021, 2021).items[0].candidate_record["final_offer_price"], 0.0)

    def test_new_classification_is_independent(self):
        self.assertEqual(self.engine().generate_preview(2021, 2021).items[0].classification, Classification.NEW.value)

    def test_already_present_classification_is_independent(self):
        preview = self.engine().generate_preview(2021, 2021); self.engine().commit_backfill(preview)
        self.assertEqual(self.engine().generate_preview(2021, 2021).items[0].classification, Classification.ALREADY_PRESENT.value)

    def test_enrichable_only_fills_existing_blank_fields(self):
        store = default_market_store(); store["ipos"] = [{"ipo_id": "ipo_old", "company_name": "엔켐", "stock_code": "348370", "corp_code": "00123456", "listing_track": "general", "subscription_start": "2021-10-21", "subscription_end": "2021-10-22", "market": None, "final_offer_price": None, "actual_listing_date": None, "expected_listing_date": None, "sources": {"keep": {"value": 1}}}]; write_market_store(store)
        item = self.engine().generate_preview(2021, 2021).items[0]
        self.assertEqual(item.classification, Classification.ENRICHABLE.value)
        self.engine().commit_backfill(self.engine().generate_preview(2021, 2021))
        saved = read_market_store()["ipos"][0]
        self.assertEqual(saved["market"], "KOSDAQ"); self.assertIn("keep", saved["sources"])

    def test_nonblank_mismatch_is_conflict_not_overwrite(self):
        store = default_market_store(); store["ipos"] = [{"ipo_id": "ipo_old", "company_name": "엔켐", "stock_code": "348370", "corp_code": "00123456", "listing_track": "general", "subscription_start": "2021-10-21", "subscription_end": "2021-10-22", "market": "KOSDAQ", "final_offer_price": 99999, "actual_listing_date": "2021-11-01", "expected_listing_date": None, "sources": {}}]; write_market_store(store)
        self.assertEqual(self.engine().generate_preview(2021, 2021).items[0].classification, Classification.CONFLICT.value)

    def test_historical_provenance_does_not_remove_existing_provenance(self):
        preview = self.engine().generate_preview(2021, 2021); self.engine().commit_backfill(preview)
        source = read_market_store()["ipos"][0]["sources"]
        self.assertIn("krx_historical", source); self.assertIn("dart_schedule_historical", source)

    def test_duplicate_preview_commit_is_idempotent(self):
        self.engine().commit_backfill(self.engine().generate_preview(2021, 2021))
        second = self.engine().generate_preview(2021, 2021)
        self.assertEqual(second.items[0].classification, Classification.ALREADY_PRESENT.value)
        self.assertEqual(self.engine().commit_backfill(second)["total_committed"], 0)

    def test_historical_record_presents_as_past(self):
        self.engine().commit_backfill(self.engine().generate_preview(2021, 2021))
        record = read_market_store()["ipos"][0]
        self.assertEqual(derive_filter_group(derive_market_state(record, today=__import__("datetime").date(2026, 9, 24)), "NOT_APPLIED"), "PAST")

    def test_spac_score_is_separate_evaluation(self):
        self.krx.fetch_new_listings.return_value = [krx_row(company_name="한국제17호기업인수목적", stock_code="999999")]
        self.dart.get_corp_code_master.return_value = [{"corp_code": "spac", "corp_name": "한국제17호기업인수목적", "stock_code": "999999"}]
        record = self.engine().generate_preview(2021, 2021).items[0].candidate_record
        score = calculate_wealth_ipo_score(record, [])
        self.assertEqual(score["score_label"], "별도평가")

    def test_phase_b_skips_canonical_and_legacy_named_spac(self):
        store = default_market_store(); store["ipos"] = [
            {"ipo_id": "spac", "company_name": "테스트스팩", "corp_code": "001", "listing_track": "spac", "subscription_start": "2021-10-21", "features": {}, "sources": {}},
            {"ipo_id": "legacy", "company_name": "케이비제34호기업인수목적", "corp_code": "002", "listing_track": "general", "subscription_start": "2021-10-21", "features": {}, "sources": {}},
        ]; write_market_store(store)
        dart = MagicMock(); dart.is_configured.return_value = True
        result = self.engine().enrich_dart(dart_client=dart, from_year=2021, to_year=2021)
        self.assertEqual(result["enriched"], 0); self.assertEqual(result["skipped"], 2); dart.get_filing_list.assert_not_called()

    def test_atomic_write_failure_preserves_existing_market(self):
        preview = self.engine().generate_preview(2021, 2021)
        before = self.market_file.read_bytes()
        with patch("app.services.ipo.historical_backfill.write_market_store", side_effect=OSError("write failed")):
            with self.assertRaises(OSError): self.engine().commit_backfill(preview)
        self.assertEqual(self.market_file.read_bytes(), before)

    def test_malformed_actual_listing_date_is_review_required(self):
        self.krx.fetch_new_listings.return_value = [krx_row(actual_listing_date="not-a-date")]
        item = self.engine().generate_preview(2021, 2021).items[0]
        self.assertEqual(item.classification, Classification.REVIEW_REQUIRED.value)

    def test_phase_b_completed_checkpoint_skips_second_run(self):
        store = default_market_store(); store["ipos"] = [{"ipo_id": "ipo", "company_name": "엔켐", "corp_code": "00123456", "listing_track": "general", "subscription_start": "2021-10-21", "features": {}, "sources": {}}]; write_market_store(store)
        first = MagicMock(); first.is_configured.return_value = True
        first.get_filing_list.return_value = {"list": [{"rcept_no": "before", "rcept_dt": "20211020", "report_nm": "증권신고서"}]}; first.download_document_zip.return_value = b"zip"
        with patch("app.services.ipo.historical_backfill.extract_document_text_from_zip", return_value="희망공모가액 15,000원 ~ 18,000원"):
            self.engine().enrich_dart(dart_client=first, from_year=2021, to_year=2021)
        dart = MagicMock(); dart.is_configured.return_value = True
        result = self.engine().enrich_dart(dart_client=dart, from_year=2021, to_year=2021)
        self.assertEqual(result["enriched"], 0); dart.get_filing_list.assert_not_called()

    def test_phase_b_rate_limit_preserves_prior_completed_record(self):
        store = default_market_store(); store["ipos"] = [
            {"ipo_id": "one", "company_name": "엔켐", "corp_code": "001", "listing_track": "general", "subscription_start": "2021-10-21", "features": {}, "sources": {}},
            {"ipo_id": "two", "company_name": "두", "corp_code": "002", "listing_track": "general", "subscription_start": "2021-10-21", "features": {}, "sources": {}},
        ]; write_market_store(store)
        dart = MagicMock(); dart.is_configured.return_value = True
        dart.get_filing_list.side_effect = [{"list": [{"rcept_no": "before", "rcept_dt": "20211020", "report_nm": "증권신고서"}]}, DartRateLimitError("DART_RATE_LIMIT")]; dart.download_document_zip.return_value = b"zip"
        with patch("app.services.ipo.historical_backfill.extract_document_text_from_zip", return_value="희망공모가액 15,000원 ~ 18,000원"):
            result = self.engine().enrich_dart(dart_client=dart, from_year=2021, to_year=2021)
        self.assertEqual(result["status"], "rate_limited")
        self.assertEqual(read_market_store()["ipos"][0]["sources"]["dart_historical"]["status"], "ok")


if __name__ == "__main__": unittest.main()
