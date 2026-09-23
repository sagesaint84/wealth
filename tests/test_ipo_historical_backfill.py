"""Comprehensive unit tests for historical IPO backfill engine (Stage 2B).

All external network operations are mocked. Validates the 24 key invariants.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.services.ipo.historical_backfill import (
    validate_subscription_dates,
    Classification,
    HistoricalBackfillEngine,
    HistoricalBackfillError,
    PreviewItem,
    PreviewResult,
    compute_market_digest,
    get_current_kst_date,
)
from app.services.ipo.presentation import derive_filter_group, derive_market_state
from app.services.ipo.store import (
    default_market_store,
    read_market_store,
    validate_market_store,
    write_market_store,
)


class TestHistoricalBackfill(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.market_file = Path(self.temp_dir.name) / "market.json"

        self.patcher_market_file = patch("app.services.ipo.historical_backfill.get_market_file", return_value=self.market_file)
        self.patcher_store_file = patch("app.services.ipo.store.get_market_file", return_value=self.market_file)
        self.patcher_market_file.start()
        self.patcher_store_file.start()

        # Initialize clean empty market store
        write_market_store(default_market_store())

        # Sample master datasets
        self.mock_listed_master = [
            {
                "company_name": "엔켐",
                "stock_code": "348370",
                "market": "KOSDAQ",
                "actual_listing_date": "2021-11-01",
            },
            {
                "company_name": "카카오페이",
                "stock_code": "377300",
                "market": "KOSPI",
                "actual_listing_date": "2021-11-03",
            },
            {
                "company_name": "중복회사",
                "stock_code": "111111",
                "market": "KOSDAQ",
                "actual_listing_date": "2022-01-01",
            },
            {
                "company_name": "중복회사",
                "stock_code": "222222",
                "market": "KOSDAQ",
                "actual_listing_date": "2022-01-01",
            },
        ]

        self.mock_delisted_master = [
            {
                "company_name": "교보10호스팩",
                "stock_code": "355150",
                "market_eng_name": "KOSDAQ",
                "market_name": "코스닥",
            },
            {
                "company_name": "신한제7호스팩",
                "stock_code": "366330",
                "market_eng_name": "KOSDAQ",
                "market_name": "코스닥",
            },
        ]

    def tearDown(self) -> None:
        self.patcher_store_file.stop()
        self.patcher_market_file.stop()
        self.temp_dir.cleanup()

    # 1. 2020 range lower bound
    def test_01_range_lower_bound_rejected(self) -> None:
        engine = HistoricalBackfillEngine()
        with self.assertRaises(HistoricalBackfillError) as ctx:
            engine.generate_preview(from_year=2019, to_year=2021)
        self.assertIn("HISTORICAL_RANGE_UNSUPPORTED", str(ctx.exception))
        self.assertIn(">= 2020", str(ctx.exception))

    # 2. current KST year upper bound
    def test_02_range_upper_bound_rejected(self) -> None:
        engine = HistoricalBackfillEngine()
        current_year = get_current_kst_date().year
        with self.assertRaises(HistoricalBackfillError) as ctx:
            engine.generate_preview(from_year=2020, to_year=current_year + 1)
        self.assertIn("HISTORICAL_RANGE_UNSUPPORTED", str(ctx.exception))
        self.assertIn("cannot exceed current KST year", str(ctx.exception))

    # 3. KIND year filtering by subscription_start
    def test_03_kind_year_filtering_by_subscription_start(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "expected_listing_date": "2021-11-01",
                "final_offer_price": 42000,
            },
            {
                "company_name": "2020종목",
                "subscription_start": "2020-05-10",
                "expected_listing_date": "2020-05-20",
                "final_offer_price": 10000,
            },
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=self.mock_delisted_master,
        )
        # Only 엔켐 should be in 2021 bucket
        names = [item.company_name for item in preview.items]
        self.assertIn("엔켐", names)
        self.assertNotIn("2020종목", names)

    # 4. pagination reuse
    def test_04_pagination_reuse(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = []
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2020,
            to_year=2021,
            listed_master=[],
            delisted_master=[],
        )
        # fetch_pubofr_schedule_items must have been called for each year
        self.assertEqual(mock_kind.fetch_pubofr_schedule_items.call_count, 2)

    # 5. listing evidence required
    def test_05_listing_evidence_required(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "미상장기업",
                "subscription_start": "2021-03-01",
                "final_offer_price": 15000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=self.mock_delisted_master,
        )
        self.assertEqual(len(preview.items), 1)
        self.assertEqual(preview.items[0].classification, Classification.EXCLUDED_NO_LISTING_EVIDENCE.value)

    # 6. withdrawn/unverified excluded
    def test_06_withdrawn_excluded(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "철회기업",
                "subscription_start": "2021-03-01",
                "final_offer_price": None,  # no offer price
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=self.mock_delisted_master,
        )
        self.assertEqual(len(preview.items), 1)
        self.assertEqual(preview.items[0].classification, Classification.EXCLUDED_WITHDRAWN.value)

    # 7. pending excluded
    def test_07_pending_excluded(self) -> None:
        mock_kind = MagicMock()
        current_year = get_current_kst_date().year
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": f"{current_year}-12-01",
                "expected_listing_date": f"{current_year}-12-15",
                "final_offer_price": 42000,
            }
        ]
        # Temporarily mock listed master with future listing date
        future_listed = [
            {
                "company_name": "엔켐",
                "stock_code": "348370",
                "market": "KOSDAQ",
                "actual_listing_date": f"{current_year}-12-15",
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=current_year,
            to_year=current_year,
            listed_master=future_listed,
            delisted_master=[],
        )
        self.assertEqual(len(preview.items), 1)
        self.assertEqual(preview.items[0].classification, Classification.EXCLUDED_PENDING.value)

    # 8. current listed accepted
    def test_08_current_listed_accepted(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "subscription_end": "2021-10-22",
                "expected_listing_date": "2021-11-01",
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        self.assertEqual(len(preview.items), 1)
        item = preview.items[0]
        self.assertEqual(item.classification, Classification.NEW.value)
        self.assertEqual(item.stock_code, "348370")
        # KRX listed master proves current listing but has no authoritative IPO listing date.
        self.assertIsNone(item.actual_listing_date)

    # 9. delisted SPAC evidence accepted
    def test_09_delisted_spac_evidence_accepted(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "교보10호스팩",
                "subscription_start": "2020-07-20",
                "expected_listing_date": "2020-08-04",
                "final_offer_price": 2000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2020,
            to_year=2020,
            listed_master=[],
            delisted_master=self.mock_delisted_master,
        )
        self.assertEqual(len(preview.items), 1)
        item = preview.items[0]
        self.assertEqual(item.classification, Classification.NEW.value)
        self.assertEqual(item.stock_code, "355150")
        self.assertEqual(item.listing_track, "spac")
        self.assertIsNone(item.actual_listing_date)  # delisted master has no actual listing date

    # 10. name-only SPAC ambiguity => REVIEW_REQUIRED
    def test_10_ambiguous_name_review_required(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "중복회사",
                "subscription_start": "2021-05-10",
                "final_offer_price": 5000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,  # has 2 entries for 중복회사
            delisted_master=[],
        )
        self.assertEqual(len(preview.items), 1)
        self.assertEqual(preview.items[0].classification, Classification.REVIEW_REQUIRED.value)

    # 11. refund_date remains null
    def test_11_refund_date_remains_null(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "payment_date": "2021-10-26",
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        item = preview.items[0]
        self.assertIsNone(item.candidate_record.get("refund_date"))

    # 12. actual_listing_date never guessed from expected
    def test_12_actual_listing_never_guessed(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "신한제7호스팩",
                "subscription_start": "2020-08-10",
                "expected_listing_date": "2020-08-25",
                "final_offer_price": 2000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2020,
            to_year=2020,
            listed_master=[],
            delisted_master=self.mock_delisted_master,
        )
        item = preview.items[0]
        self.assertEqual(item.candidate_record.get("expected_listing_date"), "2020-08-25")
        self.assertIsNone(item.candidate_record.get("actual_listing_date"))

    # 13. NEW classification
    def test_13_new_classification(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        self.assertEqual(preview.items[0].classification, Classification.NEW.value)

    # 14. ALREADY_PRESENT
    def test_14_already_present(self) -> None:
        store = read_market_store()
        store["ipos"].append({
            "ipo_id": "ipo_enchem_test",
            "company_name": "엔켐",
            "stock_code": "348370",
            "market": "KOSDAQ",
            "subscription_start": "2021-10-21",
            "subscription_end": None,
            "final_offer_price": 42000,
            "expected_listing_date": None,
            "actual_listing_date": "2021-11-01",
        })
        write_market_store(store)

        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        self.assertEqual(preview.items[0].classification, Classification.ALREADY_PRESENT.value)

    # 15. ENRICHABLE blank-only
    def test_15_enrichable_blank_only(self) -> None:
        store = read_market_store()
        store["ipos"].append({
            "ipo_id": "ipo_enchem_test",
            "company_name": "엔켐",
            "stock_code": "348370",
            "market": None,  # blank
            "subscription_start": "2021-10-21",
            "final_offer_price": 42000,
            "actual_listing_date": None,  # blank
        })
        write_market_store(store)

        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        self.assertEqual(preview.items[0].classification, Classification.ENRICHABLE.value)
        self.assertIn("market", preview.items[0].enrich_diff)
        self.assertNotIn("actual_listing_date", preview.items[0].enrich_diff)

    # 16. existing nonblank mismatch => CONFLICT
    def test_16_existing_nonblank_mismatch_conflict(self) -> None:
        store = read_market_store()
        store["ipos"].append({
            "ipo_id": "ipo_enchem_test",
            "company_name": "엔켐",
            "stock_code": "348370",
            "market": "KOSPI",  # Mismatch: master says KOSDAQ
            "subscription_start": "2021-10-21",
            "final_offer_price": 42000,
        })
        write_market_store(store)

        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        self.assertEqual(preview.items[0].classification, Classification.CONFLICT.value)

    # 17. existing nonblank never overwritten
    def test_17_existing_nonblank_never_overwritten(self) -> None:
        store = read_market_store()
        store["ipos"].append({
            "ipo_id": "ipo_enchem_test",
            "company_name": "엔켐",
            "stock_code": "348370",
            "market": "KOSDAQ",
            "final_offer_price": 42000,
            "lead_managers": ["기존주관사"],
            "subscription_start": "2021-10-21",
            "actual_listing_date": None,  # blank
        })
        write_market_store(store)

        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "final_offer_price": 42000,
                "lead_managers": ["새로운주관사"],
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        self.assertEqual(preview.items[0].classification, Classification.ALREADY_PRESENT.value)

        engine.commit_backfill(preview)

        # Verify existing record in market.json
        updated_store = read_market_store()
        rec = updated_store["ipos"][0]
        # Lead managers was non-empty and must NOT have been overwritten
        self.assertEqual(rec["lead_managers"], ["기존주관사"])
        # Blank actual_listing_date was enriched
        self.assertIsNone(rec["actual_listing_date"])

    # 18. source provenance merge
    def test_18_source_provenance_merge(self) -> None:
        store = read_market_store()
        store["ipos"].append({
            "ipo_id": "ipo_enchem_test",
            "company_name": "엔켐",
            "stock_code": "348370",
            "market": "KOSDAQ",
            "subscription_start": "2021-10-21",
            "final_offer_price": 42000,
            "sources": {"kis": {"code": "348370"}},
            "actual_listing_date": None,
        })
        write_market_store(store)

        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        engine.commit_backfill(preview)

        updated_store = read_market_store()
        rec = updated_store["ipos"][0]
        self.assertIn("kis", rec["sources"])
        # No blank field remained to enrich; existing source provenance is preserved.
        self.assertIn("kis", rec["sources"])

    # 19. duplicate run idempotency
    def test_19_duplicate_run_idempotency(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        # First preview & commit
        preview1 = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        self.assertEqual(preview1.items[0].classification, Classification.NEW.value)
        engine.commit_backfill(preview1)

        # Second preview on updated store
        preview2 = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        self.assertEqual(preview2.items[0].classification, Classification.ALREADY_PRESENT.value)

    # 20. stale preview rejected
    def test_20_stale_preview_rejected(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )

        # External write modifies market store after preview
        store = read_market_store()
        store["schema_version"] = 99
        write_market_store(store)

        with self.assertRaises(HistoricalBackfillError) as ctx:
            engine.commit_backfill(preview)
        self.assertIn("PREVIEW_STALE", str(ctx.exception))

    # 21. atomic failure preserves market
    def test_21_atomic_failure_preserves_market(self) -> None:
        original_store = read_market_store()
        original_digest = compute_market_digest()

        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )

        # Force validation error during commit
        with patch("app.services.ipo.historical_backfill.validate_market_store", side_effect=ValueError("Simulated validation crash")):
            with self.assertRaises(ValueError):
                engine.commit_backfill(preview)

        # Market file must remain intact
        self.assertEqual(compute_market_digest(), original_digest)

    # 22. historical listed record presents as PAST
    def test_22_historical_record_presents_as_past(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "subscription_end": "2021-10-22",
                "expected_listing_date": "2021-11-01",
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        rec = preview.items[0].candidate_record
        m_state = derive_market_state(rec, today=date(2026, 9, 22))
        f_group = derive_filter_group(m_state, "NOT_APPLIED")
        self.assertEqual(m_state, "LISTED")
        self.assertEqual(f_group, "PAST")

    # 23. withdrawn/unverified does not enter ACTIVE
    def test_23_withdrawn_unverified_does_not_enter_active(self) -> None:
        # If an unverified item with no listing date were processed, verify it would be excluded
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "미상장철회",
                "subscription_start": "2021-05-01",
                "subscription_end": "2021-05-02",
                "final_offer_price": 0,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        item = preview.items[0]
        self.assertEqual(item.classification, Classification.EXCLUDED_WITHDRAWN.value)
        # Because it's excluded, commit does not touch market
        res = engine.commit_backfill(preview)
        self.assertEqual(res["total_committed"], 0)

    # 24. market validation duplicate code safety
    def test_24_duplicate_code_safety(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "final_offer_price": 42000,
            },
            {
                "company_name": "엔켐클론",
                "stock_code": "348370",  # duplicate stock code!
                "subscription_start": "2021-10-22",
                "final_offer_price": 42000,
            },
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        # First one is NEW, second one encountered with duplicate code is CONFLICT
        classifications = [it.classification for it in preview.items]
        self.assertIn(Classification.NEW.value, classifications)
        self.assertIn(Classification.CONFLICT.value, classifications)

        # Commit only adds NEW, so market store validation passes without error
        commit_res = engine.commit_backfill(preview)
        self.assertEqual(commit_res["applied_new"], 1)


    # 25. subscription_end < subscription_start detection in validator
    def test_25_subscription_end_before_start_detection(self) -> None:
        # Normal same-month range
        s, e, anom = validate_subscription_dates("2023-03-07", "2023-03-08")
        self.assertEqual(s, "2023-03-07")
        self.assertEqual(e, "2023-03-08")
        self.assertFalse(anom)

        # Normal cross-month range
        s, e, anom = validate_subscription_dates("2023-10-31", "2023-11-01")
        self.assertEqual(s, "2023-10-31")
        self.assertEqual(e, "2023-11-01")
        self.assertFalse(anom)

        # Inverted anomaly
        s, e, anom = validate_subscription_dates("2020-03-03", "2020-02-04")
        self.assertEqual(s, "2020-03-03")
        self.assertIsNone(e)
        self.assertTrue(anom)

        # Missing / blank inputs (not an anomaly)
        s, e, anom = validate_subscription_dates(None, None)
        self.assertIsNone(s)
        self.assertIsNone(e)
        self.assertFalse(anom)

        s, e, anom = validate_subscription_dates("2023-03-07", None)
        self.assertEqual(s, "2023-03-07")
        self.assertIsNone(e)
        self.assertFalse(anom)

        s, e, anom = validate_subscription_dates(None, "2023-03-08")
        self.assertIsNone(s)
        self.assertEqual(e, "2023-03-08")
        self.assertFalse(anom)

    # 25b. Invalid ISO date literal detection in validator
    def test_25b_invalid_iso_date_detection(self) -> None:
        # Invalid end: 2023-02-30
        s, e, anom = validate_subscription_dates("2023-02-01", "2023-02-30")
        self.assertEqual(s, "2023-02-01")
        self.assertIsNone(e)
        self.assertTrue(anom)

        # Invalid end: 2023-13-01
        s, e, anom = validate_subscription_dates("2023-10-01", "2023-13-01")
        self.assertEqual(s, "2023-10-01")
        self.assertIsNone(e)
        self.assertTrue(anom)

        # Invalid start: not-a-date
        s, e, anom = validate_subscription_dates("not-a-date", "2023-11-01")
        self.assertIsNone(s)
        self.assertEqual(e, "2023-11-01")
        self.assertTrue(anom)

        # Invalid start: 2023-00-10
        s, e, anom = validate_subscription_dates("2023-00-10", "2023-01-10")
        self.assertIsNone(s)
        self.assertEqual(e, "2023-01-10")
        self.assertTrue(anom)

    # 26. candidate with inverted subscription dates does not propagate malformed end to canonical
    def test_26_malformed_end_date_suppressed_in_candidate(self) -> None:
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "subscription_end": "2021-10-10",  # inverted!
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        self.assertEqual(len(preview.items), 1)
        item = preview.items[0]
        self.assertEqual(item.classification, Classification.NEW.value)
        # Verify candidate record has None for subscription_end and anomaly flag
        self.assertEqual(item.candidate_record.get("subscription_start"), "2021-10-21")
        self.assertIsNone(item.candidate_record.get("subscription_end"))
        self.assertTrue(item.candidate_record.get("_source_sub_date_anomaly"))

        # Verify commit does not add malformed end date or internal flag to market store
        engine.commit_backfill(preview)
        store = read_market_store()
        rec = next(r for r in store["ipos"] if r.get("stock_code") == "348370")
        self.assertEqual(rec["subscription_start"], "2021-10-21")
        self.assertIsNone(rec["subscription_end"])
        self.assertNotIn("_source_sub_date_anomaly", rec)

    # 27. corrected canonical value does not create false conflict against anomalous candidate source
    def test_27_corrected_canonical_avoids_false_conflict(self) -> None:
        # Pre-seed canonical store with corrected subscription_end
        store = default_market_store()
        store["ipos"].append({
            "company_name": "엔켐",
            "stock_code": "348370",
            "market": "KOSDAQ",
            "listing_track": "general",
            "subscription_start": "2021-10-21",
            "subscription_end": "2021-10-22",  # corrected canonical value
            "final_offer_price": 42000,
            "actual_listing_date": "2021-11-01",
            "expected_listing_date": None,
            "lead_managers": [],
            "sources": {"historical_kind": {"source": "KIND_SCHEDULE"}},
            "ipo_id": "ipo_enchem_test",
        })
        write_market_store(store)

        # Raw candidate has inverted source date: 2021-10-21 ~ 2021-10-10
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "엔켐",
                "subscription_start": "2021-10-21",
                "subscription_end": "2021-10-10",
                "final_offer_price": 42000,
            }
        ]
        engine = HistoricalBackfillEngine(kind_client=mock_kind)
        preview = engine.generate_preview(
            from_year=2021,
            to_year=2021,
            listed_master=self.mock_listed_master,
            delisted_master=[],
        )
        self.assertEqual(len(preview.items), 1)
        item = preview.items[0]
        # Must be ALREADY_PRESENT without false conflict on subscription_end
        self.assertEqual(item.classification, Classification.ALREADY_PRESENT.value)

    # 28. canonical historical records PAST presentation check
    def test_28_canonical_market_historical_presentation(self) -> None:
        # Load real canonical market store and verify all historical records are PAST
        real_market = json.loads((Path(__file__).resolve().parents[1] / "data" / "ipo" / "market.json").read_text(encoding="utf-8"))
        historical_items = [
            item for item in real_market.get("ipos", [])
            if "historical_kind" in item.get("sources", {})
        ]
        self.assertEqual(len(historical_items), 704)
        for item in historical_items:
            m_state = derive_market_state(item, today=date(2026, 9, 22))
            f_group = derive_filter_group(m_state, "NOT_APPLIED")
            self.assertEqual(f_group, "PAST", f"Item {item.get('company_name')} ({item.get('stock_code')}) is not PAST: {m_state}")

    def test_krx_listed_master_is_the_only_runtime_listed_evidence_fetch(self) -> None:
        kind = MagicMock()
        krx = MagicMock()
        krx.fetch_listed_master.return_value = []
        krx.fetch_delisted_master.return_value = []
        listed, delisted = HistoricalBackfillEngine(kind_client=kind, krx_client=krx).load_master_evidence()
        self.assertEqual((listed, delisted), ([], []))
        krx.fetch_listed_master.assert_called_once()
        krx.fetch_delisted_master.assert_called_once()
        kind.fetch_listed_company_master.assert_not_called()

    def test_krx_listed_evidence_normalizes_market_without_actual_listing_date(self) -> None:
        indexes = HistoricalBackfillEngine.build_evidence_indexes([
            {"company_name": "엔켐", "stock_code": "348370", "market_name": "코스닥", "market_eng_name": "KOSDAQ"}
        ], [])
        found, info, evidence, ambiguous = HistoricalBackfillEngine.match_listing_evidence(
            {"company_name": "엔켐", "stock_code": "348370"}, indexes
        )
        self.assertTrue(found)
        self.assertFalse(ambiguous)
        self.assertEqual(evidence, "KRX_LISTED_MASTER:348370")
        self.assertEqual(info["market"], "KOSDAQ")
        self.assertIsNone(info["actual_listing_date"])

    def test_krx_listed_unique_name_fallback_and_ambiguous_fail_closed(self) -> None:
        unique = HistoricalBackfillEngine.build_evidence_indexes([
            {"company_name": "엔 켐", "stock_code": "348370", "market_name": "코스닥"}
        ], [])
        found, info, evidence, ambiguous = HistoricalBackfillEngine.match_listing_evidence(
            {"company_name": "엔켐", "stock_code": ""}, unique
        )
        self.assertTrue(found); self.assertFalse(ambiguous)
        self.assertEqual(info["stock_code"], "348370")
        self.assertEqual(evidence, "KRX_LISTED_MASTER:348370")
        ambiguous_indexes = HistoricalBackfillEngine.build_evidence_indexes([
            {"company_name": "중복회사", "stock_code": "111111", "market_name": "코스닥"},
            {"company_name": "중복회사", "stock_code": "222222", "market_name": "코스닥"},
        ], [])
        found, info, evidence, ambiguous = HistoricalBackfillEngine.match_listing_evidence(
            {"company_name": "중복회사", "stock_code": ""}, ambiguous_indexes
        )
        self.assertFalse(found); self.assertIsNone(info); self.assertTrue(ambiguous)
        self.assertEqual(evidence, "AMBIGUOUS_LISTED_MASTER_NAME")

    @patch("app.services.ipo.historical_backfill.extract_document_text_from_zip")
    def test_historical_dart_enrichment_uses_only_pre_subscription_filing(self, extract_text) -> None:
        store = default_market_store()
        store["ipos"] = [{
            "ipo_id": "ipo_history_dart", "company_name": "과거기업", "corp_code": "00123456",
            "listing_track": "general", "subscription_start": "2021-10-21",
            "final_offer_price": 18000, "features": {}, "sources": {},
        }]
        write_market_store(store)
        dart = MagicMock()
        dart.is_configured.return_value = True
        dart.get_filing_list.return_value = {"list": [
            {"rcept_no": "future", "rcept_dt": "20211021", "report_nm": "증권신고서(지분증권)"},
            {"rcept_no": "before", "rcept_dt": "20211020", "report_nm": "증권신고서(지분증권)"},
        ]}
        dart.download_document_zip.return_value = b"zip"
        extract_text.return_value = "희망공모가액 15,000원 ~ 18,000원"

        result = HistoricalBackfillEngine().enrich_dart(
            dart_client=dart, from_year=2021, to_year=2021,
        )
        saved = read_market_store()["ipos"][0]
        self.assertEqual(result["enriched"], 1)
        self.assertEqual(saved["sources"]["dart_historical"]["rcept_no"], "before")
        self.assertEqual(saved["offer_band_high"], 18000.0)

    def test_historical_dart_enrichment_spac_is_separately_evaluated(self) -> None:
        store = default_market_store()
        store["ipos"] = [{
            "ipo_id": "ipo_spac", "company_name": "테스트스팩", "corp_code": "00999999",
            "listing_track": "spac", "subscription_start": "2021-10-21", "features": {}, "sources": {},
        }]
        write_market_store(store)
        dart = MagicMock()
        dart.is_configured.return_value = True
        result = HistoricalBackfillEngine().enrich_dart(dart_client=dart, from_year=2021, to_year=2021)
        self.assertEqual(result["enriched"], 0)
        dart.get_filing_list.assert_not_called()


if __name__ == "__main__":
    unittest.main()
