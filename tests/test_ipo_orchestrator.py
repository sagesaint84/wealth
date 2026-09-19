import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import portfolio
from app.services.ipo.orchestrator import _kind_search_names_for_kis, run_ipo_daily_pipeline
from app.services.ipo.store import get_ipo_calendar_events, read_market_store, write_market_store


class IpoOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        self.portfolio_file = self.temp_path / "portfolio.json"
        self.portfolio_file.write_text(
            '{"settings": {"family_members": ["아빠", "엄마", "자녀"], "ipo": {"revision": 1, "applications": {}}}}',
            encoding="utf-8",
        )

        self.market_file = self.temp_path / "market.json"
        initial_market = {
            "schema_version": 1,
            "updated_at": "2026-09-18T00:00:00+09:00",
            "ipos": [
                {
                    "ipo_id": "test_closed_ipo",
                    "company_name": "종료기업",
                    "subscription_start": "2026-09-10",
                    "subscription_end": "2026-09-11",
                    "final_offer_price": 20000,
                },
                {
                    "ipo_id": "test_upcoming_ipo",
                    "company_name": "예정기업",
                    "subscription_start": "2026-09-25",
                    "subscription_end": "2026-09-26",
                    "final_offer_price": 30000,
                },
            ],
        }
        import json
        self.market_file.write_text(json.dumps(initial_market, ensure_ascii=False), encoding="utf-8")

        self.patch_pf = patch.object(portfolio, "_get_portfolio_file", return_value=self.portfolio_file)
        self.patch_market = patch("app.services.ipo.store.get_market_file", return_value=self.market_file)
        self.patch_pf.start()
        self.patch_market.start()

    def tearDown(self):
        self.patch_market.stop()
        self.patch_pf.stop()
        self.temp_dir.cleanup()

    def test_pipeline_preserves_market_and_reports_source_blockers(self):
        mock_notifier = MagicMock()
        mock_notifier.check_and_notify_events.return_value = ["test_key"]

        result = run_ipo_daily_pipeline(
            notifier=mock_notifier,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["dry_run"])
        # KIND, KRX, and NAVER are implemented but blocked by the test network policy.
        self.assertIn("external_network_disabled", result["sources"]["kind"])
        self.assertIn("external_network_disabled", result["sources"]["krx"])
        self.assertIn("external_network_disabled", result["sources"]["naver"])
        # Existing market store is preserved and not overwritten to empty
        self.assertEqual(result["total_ipos"], 2)

        # Closed IPO untouched application is frozen
        self.assertEqual(result["frozen_applications_count"], 1)

        saved = read_market_store()
        self.assertEqual(len(saved["ipos"]), 2)
        self.assertIsNotNone(saved["ipos"][0].get("score"))


    def test_kind_spac_search_aliases_are_local_and_preserve_numbering(self):
        kb_aliases = _kind_search_names_for_kis({
            "company_name": "케이비제34호기업인수목적", "listing_track": "spac"
        })
        self.assertIn("KB제34호스팩", kb_aliases)

        nh_aliases = _kind_search_names_for_kis({
            "company_name": "엔에이치스팩34호", "listing_track": "spac"
        })
        self.assertIn("NH스팩34호", nh_aliases)

    def test_kis_primary_schedule_syncs_spac_and_keeps_listing_as_evidence_only(self):
        mock_kis = MagicMock()
        mock_kis.configured = True
        mock_kis.fetch_ipo_subscription_schedule = AsyncMock(return_value=[
            {
                "company_name": "한국제17호기업인수목적",
                "stock_code": "0200G0",
                "listing_track": "spac",
                "subscription_start": "2026-09-10",
                "subscription_end": "2026-09-11",
                "payment_date": "2026-09-15",
                "refund_date": "2026-09-15",
                "expected_listing_date": None,
                "final_offer_price": 2000.0,
                "lead_managers": ["한국투자증권"],
                "sources": {"kis": {"schedule_source": "ksdinfo_pub_offer"}},
            }
        ])
        mock_kis.fetch_listing_schedule = AsyncMock(return_value=[
            {
                "company_name": "한국제17호기업인수목적",
                "stock_code": "0200G0",
                "listing_date": "2026-09-23",
                "stock_kind": "보통",
                "issue_type": "통일교체",
                "issue_stock_qty": 5000000.0,
                "total_issue_stock_qty": 5000000.0,
                "issue_price": 500.0,
            },
            {
                "company_name": "한국제17호기업인수목적",
                "stock_code": "0200G0",
                "listing_date": "2026-09-23",
                "stock_kind": "보통",
                "issue_type": "유상증자",
                "issue_stock_qty": 2000000.0,
                "total_issue_stock_qty": 5000000.0,
                "issue_price": 2000.0,
            },
            {
                "company_name": "다른회사",
                "stock_code": "0200G0",
                "listing_date": "2026-09-24",
                "issue_type": "유상증자",
            },
        ])
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.side_effect = lambda **kwargs: ([{
            "company_name": "한국제17호스팩",
            "filing_date": "2026-07-20",
            "subscription_start": "2026-09-10",
            "subscription_end": "2026-09-11",
            "payment_date": "2026-09-15",
            "final_offer_price": 2000.0,
            "expected_listing_date": "2026-09-22",
            "kind_bz_procs_no": "20260720001",
        }] if kwargs.get("corp_name") in {"한국제17호", "한국제17호스팩"} else [])

        result = run_ipo_daily_pipeline(
            kis_client=mock_kis,
            kind_client=mock_kind,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        self.assertIn("sync_ok", result["sources"]["kis"])
        self.assertEqual(result["sources"]["kind"], "fallback_not_used")
        mock_kind.fetch_pubofr_schedule_items.assert_not_called()
        mock_kis.fetch_ipo_subscription_schedule.assert_awaited_once_with("2026-09-01", "2026-10-31")
        mock_kis.fetch_listing_schedule.assert_awaited_once_with("2026-09-01", "2026-10-31")

        saved = read_market_store()
        spac = next(it for it in saved["ipos"] if it.get("stock_code") == "0200G0")
        self.assertEqual(spac["listing_track"], "spac")
        self.assertEqual(spac["subscription_start"], "2026-09-10")
        self.assertIsNone(spac.get("expected_listing_date"))
        self.assertIsNone(spac.get("actual_listing_date"))
        self.assertEqual(spac["sources"]["kis"]["schedule_source"], "ksdinfo_pub_offer")
        self.assertNotIn("kind", spac.get("sources", {}))
        self.assertEqual(len(spac["sources"]["kis"]["listing_events"]), 2)
        self.assertEqual(
            {event["issue_type"] for event in spac["sources"]["kis"]["listing_events"]},
            {"통일교체", "유상증자"},
        )

    def test_kis_success_empty_uses_kind_fallback_with_filing_window_and_schedule_filter(self):
        mock_kis = MagicMock()
        mock_kis.configured = True
        mock_kis.fetch_ipo_subscription_schedule = AsyncMock(return_value=[])
        mock_kis.fetch_listing_schedule = AsyncMock(return_value=[])

        mock_kind = MagicMock()
        kind_items = [
            {
                "company_name": "현재IPO",
                "subscription_start": "2026-09-20",
                "subscription_end": "2026-09-21",
                "expected_listing_date": "2026-10-01",
            },
            {
                "company_name": "과거IPO",
                "subscription_start": "2025-12-01",
                "subscription_end": "2025-12-02",
                "expected_listing_date": "2025-12-10",
            },
        ]

        mock_kind.fetch_pubofr_schedule_items.return_value = kind_items
        result = run_ipo_daily_pipeline(
            kis_client=mock_kis, kind_client=mock_kind,
            target_date_str="2026-09-18", dry_run=True,
        )

        mock_kind.fetch_pubofr_schedule_items.assert_called_once_with(
            from_date="2025-09-18", to_date="2026-09-18"
        )
        self.assertIn("relevant=1", result["sources"]["kind"])
        saved = read_market_store()
        self.assertTrue(any(it.get("company_name") == "현재IPO" for it in saved["ipos"]))
        self.assertFalse(any(it.get("company_name") == "과거IPO" for it in saved["ipos"]))

    def test_kis_nonblank_expected_listing_does_not_call_kind_enrichment(self):
        mock_kis = MagicMock()
        mock_kis.configured = True
        mock_kis.fetch_ipo_subscription_schedule = AsyncMock(return_value=[{
            "company_name": "네오사피엔스",
            "stock_code": "0161M0",
            "listing_track": "general",
            "subscription_start": "2026-09-10",
            "subscription_end": "2026-09-11",
            "payment_date": "2026-09-15",
            "refund_date": "2026-09-15",
            "expected_listing_date": "2026-09-21",
            "final_offer_price": 10000.0,
            "lead_managers": ["대신증권"],
            "sources": {"kis": {"schedule_source": "ksdinfo_pub_offer"}},
        }])
        mock_kis.fetch_listing_schedule = AsyncMock(return_value=[])
        mock_kind = MagicMock()

        result = run_ipo_daily_pipeline(
            kis_client=mock_kis, kind_client=mock_kind, target_date_str="2026-09-18", dry_run=True
        )

        self.assertEqual(result["sources"]["kind"], "fallback_not_used")
        mock_kind.fetch_pubofr_schedule_items.assert_not_called()
        saved = read_market_store()
        ipo = next(it for it in saved["ipos"] if it.get("stock_code") == "0161M0")
        self.assertEqual(ipo["expected_listing_date"], "2026-09-21")

    def test_kind_enrichment_ambiguous_match_leaves_expected_listing_blank(self):
        mock_kis = MagicMock()
        mock_kis.configured = True
        mock_kis.fetch_ipo_subscription_schedule = AsyncMock(return_value=[{
            "company_name": "브릴스",
            "stock_code": "468670",
            "listing_track": "general",
            "subscription_start": "2026-09-17",
            "subscription_end": "2026-09-18",
            "payment_date": "2026-09-22",
            "refund_date": "2026-09-22",
            "expected_listing_date": None,
            "final_offer_price": 19500.0,
            "lead_managers": ["아이비케이투자증권"],
            "sources": {"kis": {"schedule_source": "ksdinfo_pub_offer"}},
        }])
        mock_kis.fetch_listing_schedule = AsyncMock(return_value=[])
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = [
            {
                "company_name": "브릴스", "filing_date": "2026-07-13",
                "subscription_start": "2026-09-17", "subscription_end": "2026-09-18",
                "payment_date": "2026-09-22", "final_offer_price": 19500.0,
                "expected_listing_date": "2026-10-01", "kind_bz_procs_no": "A",
            },
            {
                "company_name": "브릴스", "filing_date": "2026-07-14",
                "subscription_start": "2026-09-17", "subscription_end": "2026-09-18",
                "payment_date": "2026-09-22", "final_offer_price": 19500.0,
                "expected_listing_date": "2026-10-02", "kind_bz_procs_no": "B",
            },
        ]

        result = run_ipo_daily_pipeline(
            kis_client=mock_kis, kind_client=mock_kind, target_date_str="2026-09-18", dry_run=True
        )

        self.assertEqual(result["sources"]["kind"], "fallback_not_used")
        mock_kind.fetch_pubofr_schedule_items.assert_not_called()
        saved = read_market_store()
        ipo = next(it for it in saved["ipos"] if it.get("stock_code") == "468670")
        self.assertIsNone(ipo.get("expected_listing_date"))
        self.assertNotIn("kind", ipo.get("sources", {}))

    def test_pipeline_dart_sync_ok_and_feature_preservation(self):
        import io, zipfile
        # Prepare sample zip bytes
        zf_buffer = io.BytesIO()
        with zipfile.ZipFile(zf_buffer, "w") as zf:
            zf.writestr("doc.xml", """
            <html><body>
            <h2>1. 수요예측 결과</h2>
            <p>기관투자자 경쟁률: 950.0 : 1</p>
            <table><caption>의무보유확약 신청현황</caption>
            <tbody><tr><td>6개월</td><td>100</td><td>5000000</td></tr>
            <tr><td>미확약</td><td>100</td><td>5000000</td></tr>
            <tr><td>합계</td><td>200</td><td>10000000</td></tr></tbody></table>
            <h2>2. 유통가능물량</h2>
            <p>유통가능 물량은 20.0%입니다.</p>
            </body></html>
            """)
        sample_zip = zf_buffer.getvalue()

        # Add candidate with corp_code to market store
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_dart_ipo",
            "company_name": "다트기업",
            "corp_code": "00123456",
            "subscription_start": "2026-09-25",
            "subscription_end": "2026-09-26",
            "final_offer_price": 25000,
            "offer_band_high": 25000,
        })
        write_market_store(market)

        mock_dart = MagicMock()
        mock_dart.is_configured.return_value = True
        mock_dart.get_filing_list.return_value = {
            "status": "000",
            "list": [{
                "rcept_no": "20260920000111",
                "report_nm": "증권신고서(지분증권)",
                "rcept_dt": "2026-09-20",
            }]
        }
        mock_dart.get_equity_registration_statements.return_value = {"status": "000", "list": []}
        mock_dart.download_document_zip.return_value = sample_zip

        result = run_ipo_daily_pipeline(
            dart_client=mock_dart,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        self.assertEqual(result["sources"]["dart"], "sync_ok")
        saved = read_market_store()
        dart_ipo = next(it for it in saved["ipos"] if it["ipo_id"] == "test_dart_ipo")
        self.assertIn("institutional_competition_ratio", dart_ipo["features"])
        self.assertEqual(dart_ipo["features"]["institutional_competition_ratio"]["value"], 950.0)
        self.assertEqual(dart_ipo["sources"]["dart"]["rcept_no"], "20260920000111")

    def test_stage5_1_naver_and_krx_exact_1_and_past_date_promotes_actual(self):
        # 1. NAVER LISTING exact 1 + KRX exact 1 + past lcalDate -> actual promotion
        # 8. NAVER KOSDAQ / KRX KSQ -> match
        # 11. expected_listing_date preserved
        # 12. sources.kis.schedule_source preserved
        # 14. sources.naver added
        # 15. sources.krx preserved/added
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_nh_spac34",
            "company_name": "엔에이치스팩34호",
            "stock_code": "0197V0",
            "listing_track": "spac",
            "subscription_start": "2026-09-01",
            "subscription_end": "2026-09-02",
            "expected_listing_date": "2026-09-10",
            "sources": {
                "kis": {"schedule_source": "ksdinfo_pub_offer"}
            },
        })
        write_market_store(market)

        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = [
            {
                "stock_code": "0197V0",
                "full_code": "KR70197V0000",
                "company_name": "엔에이치스팩34호",
                "market_code": "KSQ",
                "market_name": "코스닥",
                "market_eng_name": "KOSDAQ",
            }
        ]

        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = [
            {
                "stock_code": "0197V0",
                "raw_ipo_code": "A0197V0",
                "company_name": "엔에이치스팩34호",
                "market_type": "KOSDAQ",
                "listing_track": "spac",
                "actual_listing_date": "2026-09-10",
                "ipo_status": "상장",
                "gsr_class": "S",
            }
        ]

        result = run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        self.assertIn("confirmed=1", result["sources"]["naver"])
        saved = read_market_store()
        nh = next(it for it in saved["ipos"] if it.get("stock_code") == "0197V0")
        self.assertEqual(nh["actual_listing_date"], "2026-09-10")
        self.assertEqual(nh["expected_listing_date"], "2026-09-10")
        self.assertEqual(nh["sources"]["kis"]["schedule_source"], "ksdinfo_pub_offer")
        self.assertNotIn("stock_info", nh["sources"]["kis"])
        self.assertEqual(nh["sources"]["naver"]["listing_confirmation_source"], "ipo_progress_LISTING")
        self.assertEqual(nh["sources"]["naver"]["ipo_code"], "A0197V0")
        self.assertEqual(nh["sources"]["naver"]["ipo_status"], "상장")
        self.assertEqual(nh["sources"]["naver"]["actual_listing_date"], "2026-09-10")
        self.assertEqual(nh["sources"]["krx"]["listing_confirmation_source"], "finder_stkisu")
        self.assertEqual(nh["sources"]["krx"]["short_code"], "0197V0")

    def test_stage5_1_naver_completed_missing_and_krx_exact_no_actual(self):
        # 2. NAVER completed missing + KRX exact -> actual None
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_missing_naver",
            "company_name": "네이버누락종목",
            "stock_code": "123450",
            "expected_listing_date": "2026-09-10",
        })
        write_market_store(market)

        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = [
            {"stock_code": "123450", "company_name": "네이버누락종목", "market_code": "KSQ"}
        ]
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = []

        run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        saved = read_market_store()
        cand = next(it for it in saved["ipos"] if it.get("stock_code") == "123450")
        self.assertIsNone(cand.get("actual_listing_date"))

    def test_stage5_1_naver_listing_exact_and_krx_missing_no_actual(self):
        # 3. NAVER LISTING exact + KRX missing -> actual None
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_missing_krx",
            "company_name": "KRX누락종목",
            "stock_code": "234560",
            "expected_listing_date": "2026-09-10",
        })
        write_market_store(market)

        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = []
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = [
            {
                "stock_code": "234560",
                "raw_ipo_code": "A234560",
                "company_name": "KRX누락종목",
                "market_type": "KOSDAQ",
                "actual_listing_date": "2026-09-10",
                "ipo_status": "상장",
            }
        ]

        run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        saved = read_market_store()
        cand = next(it for it in saved["ipos"] if it.get("stock_code") == "234560")
        self.assertIsNone(cand.get("actual_listing_date"))

    def test_stage5_1_naver_ipo_status_not_listing_no_actual(self):
        # 4. NAVER ipoStatus != "상장" -> actual None
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_not_completed",
            "company_name": "청약완료종목",
            "stock_code": "345670",
        })
        write_market_store(market)

        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = [
            {"stock_code": "345670", "company_name": "청약완료종목", "market_code": "KSQ"}
        ]
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = [
            {
                "stock_code": "345670",
                "raw_ipo_code": "A345670",
                "company_name": "청약완료종목",
                "market_type": "KOSDAQ",
                "actual_listing_date": "2026-09-10",
                "ipo_status": "청약완료",
            }
        ]

        run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        saved = read_market_store()
        cand = next(it for it in saved["ipos"] if it.get("stock_code") == "345670")
        self.assertIsNone(cand.get("actual_listing_date"))

    def test_stage5_1_naver_lcal_date_future_no_actual(self):
        # 5. NAVER lcalDate future -> actual None
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_future",
            "company_name": "미래종목",
            "stock_code": "0161M0",
            "expected_listing_date": "2026-09-21",
        })
        write_market_store(market)

        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = [
            {"stock_code": "0161M0", "company_name": "미래종목", "market_code": "KSQ"}
        ]
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = [
            {
                "stock_code": "0161M0",
                "raw_ipo_code": "A0161M0",
                "company_name": "미래종목",
                "market_type": "KOSDAQ",
                "actual_listing_date": "2026-09-21",
                "ipo_status": "상장",
            }
        ]

        run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        saved = read_market_store()
        cand = next(it for it in saved["ipos"] if it.get("stock_code") == "0161M0")
        self.assertIsNone(cand.get("actual_listing_date"))
        self.assertEqual(cand.get("expected_listing_date"), "2026-09-21")

    def test_stage5_1_naver_duplicate_stock_code_no_actual(self):
        # 6. NAVER duplicate stock_code -> actual None
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_naver_dup",
            "company_name": "네이버중복종목",
            "stock_code": "456780",
        })
        write_market_store(market)

        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = [
            {"stock_code": "456780", "company_name": "네이버중복종목", "market_code": "KSQ"}
        ]
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = [
            {
                "stock_code": "456780",
                "raw_ipo_code": "A456780",
                "company_name": "중복1",
                "market_type": "KOSDAQ",
                "actual_listing_date": "2026-09-10",
                "ipo_status": "상장",
            },
            {
                "stock_code": "456780",
                "raw_ipo_code": "A456780",
                "company_name": "중복2",
                "market_type": "KOSDAQ",
                "actual_listing_date": "2026-09-10",
                "ipo_status": "상장",
            },
        ]

        run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        saved = read_market_store()
        cand = next(it for it in saved["ipos"] if it.get("stock_code") == "456780")
        self.assertIsNone(cand.get("actual_listing_date"))

    def test_stage5_1_krx_duplicate_stock_code_no_actual(self):
        # 7. KRX duplicate stock_code -> actual None
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_krx_dup",
            "company_name": "KRX중복종목",
            "stock_code": "567890",
        })
        write_market_store(market)

        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = [
            {"stock_code": "567890", "company_name": "중복1", "market_code": "KSQ"},
            {"stock_code": "567890", "company_name": "중복2", "market_code": "KSQ"},
        ]
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = [
            {
                "stock_code": "567890",
                "raw_ipo_code": "A567890",
                "company_name": "KRX중복종목",
                "market_type": "KOSDAQ",
                "actual_listing_date": "2026-09-10",
                "ipo_status": "상장",
            }
        ]

        run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        saved = read_market_store()
        cand = next(it for it in saved["ipos"] if it.get("stock_code") == "567890")
        self.assertIsNone(cand.get("actual_listing_date"))

    def test_stage5_1_market_mismatch_naver_kosdaq_vs_krx_stk_no_actual(self):
        # 9. NAVER KOSDAQ / KRX STK -> actual None
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_mismatch",
            "company_name": "불일치기업",
            "stock_code": "777770",
        })
        write_market_store(market)

        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = [
            {"stock_code": "777770", "company_name": "불일치기업", "market_code": "STK"}
        ]
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = [
            {
                "stock_code": "777770",
                "raw_ipo_code": "A777770",
                "company_name": "불일치기업",
                "market_type": "KOSDAQ",
                "actual_listing_date": "2026-09-10",
                "ipo_status": "상장",
            }
        ]

        run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        saved = read_market_store()
        cand = next(it for it in saved["ipos"] if it.get("stock_code") == "777770")
        self.assertIsNone(cand.get("actual_listing_date"))

    def test_stage5_1_existing_actual_updates_from_valid_confirmation(self):
        # A fresh, KRX-confirmed actual date may replace an older actual date.
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_existing",
            "company_name": "기상장사",
            "stock_code": "666660",
            "actual_listing_date": "2026-09-01",
        })
        write_market_store(market)

        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = [
            {"stock_code": "666660", "company_name": "기상장사", "market_code": "KSQ"}
        ]
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = [
            {
                "stock_code": "666660",
                "raw_ipo_code": "A666660",
                "company_name": "기상장사",
                "market_type": "KOSDAQ",
                "actual_listing_date": "2026-09-05",  # different date
                "ipo_status": "상장",
            }
        ]

        run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        saved = read_market_store()
        cand = next(it for it in saved["ipos"] if it.get("stock_code") == "666660")
        self.assertEqual(cand["actual_listing_date"], "2026-09-05")

    def test_stage5_1_sources_kind_preserved(self):
        # 13. sources.kind preserved
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_kind_pres",
            "company_name": "KIND보존종목",
            "stock_code": "888880",
            "expected_listing_date": "2026-09-10",
            "sources": {
                "kind": {
                    "schedule_source": "pubofrprogcom",
                    "expected_listing_date": "2026-09-10",
                }
            },
        })
        write_market_store(market)

        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = [
            {"stock_code": "888880", "company_name": "KIND보존종목", "market_code": "KSQ"}
        ]
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = [
            {
                "stock_code": "888880",
                "raw_ipo_code": "A888880",
                "company_name": "KIND보존종목",
                "market_type": "KOSDAQ",
                "actual_listing_date": "2026-09-10",
                "ipo_status": "상장",
            }
        ]

        run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        saved = read_market_store()
        cand = next(it for it in saved["ipos"] if it.get("stock_code") == "888880")
        self.assertEqual(cand["actual_listing_date"], "2026-09-10")
        self.assertEqual(cand["sources"]["kind"]["schedule_source"], "pubofrprogcom")

    def test_stage5_1_naver_fetch_failure_preserves_existing_market_data(self):
        # 16. NAVER fetch failure -> existing market data preserved
        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = [
            {"stock_code": "111110", "company_name": "후보1", "market_code": "KSQ"}
        ]
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.side_effect = RuntimeError("NAVER network timeout")

        result = run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        self.assertIn("source_error", result["sources"]["naver"])
        saved = read_market_store()
        self.assertEqual(len(saved["ipos"]), 2)

    def test_stage5_1_krx_fetch_failure_preserves_existing_market_data(self):
        # 17. KRX fetch failure -> existing market data preserved
        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.side_effect = RuntimeError("KRX connection timeout")
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = []

        result = run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        self.assertIn("source_error", result["sources"]["krx"])
        saved = read_market_store()
        self.assertEqual(len(saved["ipos"]), 2)

    def test_stage5_1_source_failure_before_apply_no_partial_mutation(self):
        # 18. Source failure before apply -> no partial actual mutation
        market = read_market_store()
        market["ipos"].extend([
            {
                "ipo_id": "test_cand_1",
                "company_name": "후보1",
                "stock_code": "111110",
            },
            {
                "ipo_id": "test_cand_2",
                "company_name": "후보2",
                "stock_code": "222220",
            },
        ])
        write_market_store(market)

        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = [
            {"stock_code": "111110", "company_name": "후보1", "market_code": "KSQ"},
            {"stock_code": "222220", "company_name": "후보2", "market_code": "KSQ"},
        ]
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.side_effect = RuntimeError("NAVER 500 error")

        result = run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        self.assertIn("source_error", result["sources"]["naver"])
        saved = read_market_store()
        c1 = next(it for it in saved["ipos"] if it.get("stock_code") == "111110")
        c2 = next(it for it in saved["ipos"] if it.get("stock_code") == "222220")
        self.assertIsNone(c1.get("actual_listing_date"))
        self.assertIsNone(c2.get("actual_listing_date"))

    def test_stage5_1_calendar_behavior_actual_suppresses_expected_listing_event(self):
        # 19. Calendar behavior: actual exists -> expected listing event suppressed, actual '신규상장' emitted
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_cal_actual",
            "company_name": "상장완료사",
            "stock_code": "333330",
            "expected_listing_date": "2026-09-10",
            "actual_listing_date": "2026-09-10",
        })
        write_market_store(market)

        events = get_ipo_calendar_events(None, "2026-09-01", "2026-09-30")
        listing_events = [e for e in events if e.get("source_id") == "test_cal_actual" and e.get("type") == "ipo_listing"]
        self.assertEqual(len(listing_events), 1)
        self.assertIn("신규상장", listing_events[0]["title"])
        self.assertEqual(listing_events[0]["meta"]["listing_status"], "actual")

    def test_stage5_1_krx_client_missing_fetch_listed_master_implementation_blocker(self):
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_nh_spac34",
            "company_name": "엔에이치스팩34호",
            "stock_code": "0197V0",
            "expected_listing_date": "2026-09-10",
        })
        write_market_store(market)

        class FakeKrxWithoutMethod:
            pass

        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = [
            {
                "stock_code": "0197V0",
                "raw_ipo_code": "A0197V0",
                "company_name": "엔에이치스팩34호",
                "market_type": "KOSDAQ",
                "actual_listing_date": "2026-09-10",
                "ipo_status": "상장",
            }
        ]

        result = run_ipo_daily_pipeline(
            krx_client=FakeKrxWithoutMethod(),
            naver_client=mock_naver,
            target_date_str="2026-09-18",
            dry_run=True,
        )

        self.assertEqual(result["sources"]["krx"], "implementation_blocker")
        saved = read_market_store()
        nh = next(it for it in saved["ipos"] if it.get("stock_code") == "0197V0")
        self.assertIsNone(nh.get("actual_listing_date"))

    def test_stage5_1_naver_client_missing_fetch_completed_listings_implementation_blocker(self):
        market = read_market_store()
        market["ipos"].append({
            "ipo_id": "test_nh_spac34",
            "company_name": "엔에이치스팩34호",
            "stock_code": "0197V0",
            "expected_listing_date": "2026-09-10",
        })
        write_market_store(market)

        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = [
            {"stock_code": "0197V0", "company_name": "엔에이치스팩34호", "market_code": "KSQ"}
        ]

        class FakeNaverWithoutMethod:
            pass

        result = run_ipo_daily_pipeline(
            krx_client=mock_krx,
            naver_client=FakeNaverWithoutMethod(),
            target_date_str="2026-09-18",
            dry_run=True,
        )

        self.assertEqual(result["sources"]["naver"], "implementation_blocker")
        saved = read_market_store()
        nh = next(it for it in saved["ipos"] if it.get("stock_code") == "0197V0")
        self.assertIsNone(nh.get("actual_listing_date"))
