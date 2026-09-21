from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import app.main as main
from app.services import portfolio
from app.services.ipo.orchestrator import IpoRefreshAlreadyRunning, refresh_ipo_market, run_ipo_daily_pipeline
from app.services.ipo.store import read_market_store


class IpoMarketRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.market_file = root / "market.json"
        self.portfolio_file = root / "portfolio.json"
        self.username = "ipo-refresh-user"
        self.market_file.write_text(json.dumps({"schema_version": 1, "updated_at": "old", "ipos": [{"ipo_id": "existing", "company_name": "기존일정"}]}, ensure_ascii=False), encoding="utf-8")
        self.portfolio_file.write_text(json.dumps({"settings": {"family_members": ["아빠", "엄마", "자녀"], "ipo": {"revision": 7, "applications": {"existing": {"applied_owners": ["아빠"], "target_owners": ["아빠", "엄마", "자녀"]}}}}}, ensure_ascii=False), encoding="utf-8")
        self.market_patch = patch("app.services.ipo.store.get_market_file", return_value=self.market_file)
        self.portfolio_patch = patch.object(portfolio, "_get_portfolio_file", return_value=self.portfolio_file)
        self.ipo_dir_patch = patch("app.services.ipo.store.get_ipo_data_dir", return_value=root)
        def _get_user_dir(u=None):
            p = root / "users" / (u or "fixture_default").strip()
            p.mkdir(parents=True, exist_ok=True)
            return p
        self.user_dir_patch = patch("app.services.user_manager.get_user_data_dir", side_effect=_get_user_dir)
        self.market_patch.start(); self.portfolio_patch.start(); self.ipo_dir_patch.start(); self.user_dir_patch.start()
        self.addCleanup(self.market_patch.stop); self.addCleanup(self.portfolio_patch.stop); self.addCleanup(self.ipo_dir_patch.stop); self.addCleanup(self.user_dir_patch.stop)

    def test_market_only_pipeline_never_notifies_or_mutates_applications(self):
        notifier = MagicMock()
        before = self.portfolio_file.read_bytes()
        result = run_ipo_daily_pipeline(
            notifier=notifier, target_date_str="2026-09-18", market_only=True,
        )
        self.assertTrue(result["market_only"])
        self.assertEqual(result["frozen_applications_count"], 0)
        self.assertEqual(result["notifications_sent"], [])
        notifier.check_and_notify_events.assert_not_called()
        self.assertEqual(self.portfolio_file.read_bytes(), before)

    def test_market_only_failure_preserves_existing_store(self):
        before = self.market_file.read_bytes()
        broken_kis = MagicMock(); broken_kis.configured = True
        broken_kis.fetch_ipo_subscription_schedule.side_effect = RuntimeError("provider down")
        broken_kis.fetch_listing_schedule.side_effect = RuntimeError("provider down")
        result = run_ipo_daily_pipeline(kis_client=broken_kis, target_date_str="2026-09-18", market_only=True)
        self.assertEqual(result["status"], "preserved")
        self.assertIn("source_error", result["sources"]["kis"])
        self.assertEqual(self.market_file.read_bytes(), before)

    def test_market_only_malformed_primary_response_preserves_existing_store(self):
        before = self.market_file.read_bytes()
        malformed_kis = MagicMock(); malformed_kis.configured = True
        malformed_kis.fetch_ipo_subscription_schedule = MagicMock()
        async def malformed_subscriptions(*_args):
            return None
        async def empty_listings(*_args):
            return []
        malformed_kis.fetch_ipo_subscription_schedule.side_effect = malformed_subscriptions
        malformed_kis.fetch_listing_schedule.side_effect = empty_listings
        result = run_ipo_daily_pipeline(kis_client=malformed_kis, target_date_str="2026-09-18", market_only=True)
        self.assertEqual(result["status"], "preserved")
        self.assertIn("source_error", result["sources"]["kis"])
        self.assertEqual(self.market_file.read_bytes(), before)

    def test_market_only_empty_primary_and_failed_fallback_preserve_existing_store(self):
        before = self.market_file.read_bytes()
        empty_kis = MagicMock(); empty_kis.configured = True
        async def empty_schedule(*_args):
            return []
        empty_kis.fetch_ipo_subscription_schedule.side_effect = empty_schedule
        empty_kis.fetch_listing_schedule.side_effect = empty_schedule
        broken_kind = MagicMock()
        result = run_ipo_daily_pipeline(
            kis_client=empty_kis, kind_client=broken_kind,
            target_date_str="2026-09-18", market_only=True,
        )
        self.assertEqual(result["status"], "preserved")
        self.assertIn("sync_ok", result["sources"]["kis"])
        self.assertEqual(result["sources"]["kind"], "not_requested (market_only)")
        broken_kind.fetch_pubofr_schedule_items.assert_not_called()
        self.assertEqual(self.market_file.read_bytes(), before)

    def test_empty_store_bootstraps_spac_from_primary_schedule(self):
        self.market_file.unlink()
        kis = MagicMock(); kis.configured = True
        async def subscriptions(*_args):
            return [{
                "company_name": "신규스팩", "stock_code": "0123A0", "listing_track": "spac",
                "subscription_start": "2026-09-20", "subscription_end": "2026-09-21",
                "final_offer_price": 2000.0, "lead_managers": ["테스트증권"],
            }]
        async def listings(*_args):
            return []
        kis.fetch_ipo_subscription_schedule.side_effect = subscriptions
        kis.fetch_listing_schedule.side_effect = listings
        krx = MagicMock(); krx.fetch_listed_master.return_value = []
        naver = MagicMock(); naver.fetch_completed_listings.return_value = []
        result = run_ipo_daily_pipeline(
            kis_client=kis, krx_client=krx, naver_client=naver,
            target_date_str="2026-09-18", market_only=True,
        )
        saved = read_market_store()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(saved["ipos"][0]["listing_track"], "spac")
        self.assertEqual(saved["ipos"][0]["company_name"], "신규스팩")

    def test_empty_store_primary_failure_is_not_reported_as_success(self):
        self.market_file.unlink()
        broken_kis = MagicMock(); broken_kis.configured = True
        broken_kis.fetch_ipo_subscription_schedule.side_effect = RuntimeError("provider down")
        broken_kis.fetch_listing_schedule.side_effect = RuntimeError("provider down")
        broken_kind = MagicMock()
        broken_kind.fetch_pubofr_schedule_items.side_effect = RuntimeError("KIND down")
        result = run_ipo_daily_pipeline(
            kis_client=broken_kis, kind_client=broken_kind,
            target_date_str="2026-09-18", market_only=True,
        )
        self.assertEqual(result["status"], "preserved")
        self.assertTrue(self.market_file.exists())
        self.assertEqual(read_market_store()["ipos"], [])

    def test_secondary_confirmation_failures_preserve_store_when_schedule_sources_fail(self):
        before = self.market_file.read_bytes()
        for client_name, method_name in (("krx_client", "fetch_listed_master"), ("naver_client", "fetch_completed_listings")):
            with self.subTest(client=client_name):
                client = MagicMock()
                getattr(client, method_name).side_effect = RuntimeError("secondary source down")
                kwargs = {client_name: client}
                run_ipo_daily_pipeline(target_date_str="2026-09-18", market_only=True, **kwargs)
                self.assertEqual(self.market_file.read_bytes(), before)

    def test_refresh_wrapper_uses_market_only_mode(self):
        with patch("app.services.ipo.orchestrator.run_ipo_daily_pipeline", return_value={"status": "ok"}) as pipeline:
            refresh_ipo_market(username=self.username)
        self.assertTrue(pipeline.call_args.kwargs["market_only"])
        self.assertEqual(pipeline.call_args.kwargs["username"], self.username)

    def test_refresh_api_requires_authentication(self):
        response = TestClient(main.app).post("/api/ipo/market/refresh")
        self.assertEqual(response.status_code, 401)

    def test_refresh_api_failure_is_not_cacheable(self):
        token = main._serializer.dumps({"user": self.username, "role": "user"})
        with patch("app.services.ipo.orchestrator.refresh_ipo_market", side_effect=RuntimeError("source down")), \
             patch("app.services.user_manager.get_user_by_name", return_value={"username": self.username, "role": "user"}):
            response = TestClient(main.app).post("/api/ipo/market/refresh", headers={"Cookie": f"{main.COOKIE_NAME}={token}"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json()["detail"]["code"], "IPO_MARKET_REFRESH_FAILED")
        self.assertEqual(response.json()["detail"]["message"], "공모주 일정 동기화에 실패했습니다. 기존 데이터를 유지합니다.")

    def test_refresh_api_lock_conflict_is_409_and_not_cacheable(self):
        token = main._serializer.dumps({"user": self.username, "role": "user"})
        with patch("app.services.ipo.orchestrator.refresh_ipo_market", side_effect=IpoRefreshAlreadyRunning()), \
             patch("app.services.user_manager.get_user_by_name", return_value={"username": self.username, "role": "user"}):
            response = TestClient(main.app).post("/api/ipo/market/refresh", headers={"Cookie": f"{main.COOKIE_NAME}={token}"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json()["detail"]["code"], "IPO_REFRESH_ALREADY_RUNNING")

    def test_refresh_api_preserved_primary_failure_returns_502_without_changing_store(self):
        token = main._serializer.dumps({"user": self.username, "role": "user"})
        before = self.market_file.read_bytes()
        with patch("app.services.ipo.orchestrator.refresh_ipo_market", return_value={"status": "preserved", "market_only": True}), \
             patch("app.services.user_manager.get_user_by_name", return_value={"username": self.username, "role": "user"}):
            response = TestClient(main.app).post("/api/ipo/market/refresh", headers={"Cookie": f"{main.COOKIE_NAME}={token}"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json()["detail"]["code"], "IPO_MARKET_REFRESH_FAILED")
        self.assertEqual(self.market_file.read_bytes(), before)

    def test_refresh_api_calls_sync_and_returns_spac_without_application_change(self):
        market = {"schema_version": 1, "updated_at": "new", "ipos": [{"ipo_id": "spac", "company_name": "테스트스팩", "listing_track": "spac"}]}
        token = main._serializer.dumps({"user": self.username, "role": "user"})
        before = self.portfolio_file.read_bytes()
        with patch("app.services.ipo.orchestrator.refresh_ipo_market", return_value={"status": "ok", "market_only": True, "sources": {"krx": "source_error"}}) as refresh, \
             patch("app.services.ipo.store.read_market_store", return_value=copy.deepcopy(market)), \
             patch("app.services.user_manager.get_user_by_name", return_value={"username": self.username, "role": "user"}):
            response = TestClient(main.app).post("/api/ipo/market/refresh", headers={"Cookie": f"{main.COOKIE_NAME}={token}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["market"]["ipos"][0]["listing_track"], "spac")
        refresh.assert_called_once_with(username=self.username)
        self.assertEqual(self.portfolio_file.read_bytes(), before)

    def test_primary_success_with_secondary_failures_updates_market(self):
        async def subscriptions(*_args):
            return [{
                "company_name": "신규일정", "stock_code": "0123B0", "listing_track": "general",
                "subscription_start": "2026-09-20", "subscription_end": "2026-09-21",
                "final_offer_price": 2000.0, "lead_managers": ["테스트증권"],
            }]
        async def listings(*_args):
            return []

        for client_name, method_name in (("krx_client", "fetch_listed_master"), ("naver_client", "fetch_completed_listings")):
            with self.subTest(client=client_name):
                kis = MagicMock(); kis.configured = True
                kis.fetch_ipo_subscription_schedule.side_effect = subscriptions
                kis.fetch_listing_schedule.side_effect = listings
                client = MagicMock()
                getattr(client, method_name).side_effect = RuntimeError("secondary source down")
                kwargs = {client_name: client}
                result = run_ipo_daily_pipeline(
                    kis_client=kis, target_date_str="2026-09-18", market_only=True, **kwargs,
                )
                self.assertEqual(result["status"], "ok")
                self.assertIn("source_error", result["sources"][client_name.removesuffix("_client")])
                self.assertTrue(any(ipo.get("company_name") == "신규일정" for ipo in read_market_store()["ipos"]))

    def test_naver_progress_enriches_only_blank_kis_listing_dates(self):
        kis = MagicMock(); kis.configured = True
        kis.fetch_ipo_subscription_schedule = AsyncMock(return_value=[
            {"company_name": "빅웨이브로보틱스", "stock_code": "111111", "expected_listing_date": None},
            {"company_name": "브릴스", "stock_code": "468670", "expected_listing_date": "2026-09-30"},
        ])
        kis.fetch_listing_schedule = AsyncMock(return_value=[])
        naver = MagicMock()
        naver.fetch_ipo_progress_items.return_value = [
            {"stock_code": "111111", "raw_ipo_code": "A111111", "expected_listing_date": "2026-09-29"},
            {"stock_code": "468670", "raw_ipo_code": "A468670", "expected_listing_date": "2026-10-01"},
        ]
        naver.fetch_completed_listings.return_value = []
        kind = MagicMock()
        result = run_ipo_daily_pipeline(kis_client=kis, naver_client=naver, kind_client=kind, target_date_str="2026-09-18", market_only=True)
        saved = {ipo["stock_code"]: ipo for ipo in read_market_store()["ipos"] if ipo.get("stock_code")}
        self.assertEqual(saved["111111"]["expected_listing_date"], "2026-09-29")
        self.assertEqual(saved["468670"]["expected_listing_date"], "2026-09-30")
        self.assertIn("filled=1", result["sources"]["naver_progress"])
        kind.fetch_pubofr_schedule_items.assert_not_called()

    def test_naver_progress_failure_preserves_existing_expected_date(self):
        self.market_file.write_text(json.dumps({"schema_version": 1, "ipos": [{"ipo_id": "existing", "company_name": "기존", "stock_code": "222222", "expected_listing_date": "2026-09-29"}]}), encoding="utf-8")
        kis = MagicMock(); kis.configured = True
        kis.fetch_ipo_subscription_schedule = AsyncMock(return_value=[{"company_name": "기존", "stock_code": "222222", "expected_listing_date": None}])
        kis.fetch_listing_schedule = AsyncMock(return_value=[])
        naver = MagicMock(); naver.fetch_ipo_progress_items.side_effect = RuntimeError("NAVER down"); naver.fetch_completed_listings.return_value = []
        run_ipo_daily_pipeline(kis_client=kis, naver_client=naver, target_date_str="2026-09-18", market_only=True)
        self.assertEqual(read_market_store()["ipos"][0]["expected_listing_date"], "2026-09-29")

    def test_blank_naver_progress_value_preserves_existing_expected_date(self):
        self.market_file.write_text(json.dumps({"schema_version": 1, "ipos": [{"ipo_id": "existing", "company_name": "기존", "stock_code": "222222", "expected_listing_date": "2026-09-29"}]}), encoding="utf-8")
        kis = MagicMock(); kis.configured = True
        kis.fetch_ipo_subscription_schedule = AsyncMock(return_value=[{"company_name": "기존", "stock_code": "222222", "expected_listing_date": None}])
        kis.fetch_listing_schedule = AsyncMock(return_value=[])
        naver = MagicMock(); naver.fetch_ipo_progress_items.return_value = []; naver.fetch_completed_listings.return_value = []
        run_ipo_daily_pipeline(kis_client=kis, naver_client=naver, target_date_str="2026-09-18", market_only=True)
        self.assertEqual(read_market_store()["ipos"][0]["expected_listing_date"], "2026-09-29")

    def test_progress_identity_mismatch_does_not_enrich_and_registry_retains_missing_records(self):
        self.market_file.write_text(json.dumps({"schema_version": 1, "ipos": [
            {"ipo_id": code, "company_name": code, "stock_code": code, "expected_listing_date": "2026-09-29"}
            for code in ("111111", "222222", "333333")
        ]}), encoding="utf-8")
        kis = MagicMock(); kis.configured = True
        fresh = [
            {"company_name": code, "stock_code": code, "expected_listing_date": "2026-10-01"}
            for code in ("111111", "333333", "444444")
        ]
        kis.fetch_ipo_subscription_schedule = AsyncMock(return_value=fresh)
        kis.fetch_listing_schedule = AsyncMock(return_value=[])
        naver = MagicMock()
        naver.fetch_ipo_progress_items.return_value = [{"stock_code": "999999", "expected_listing_date": "2026-10-15"}]
        naver.fetch_completed_listings.return_value = []
        for _ in range(2):
            run_ipo_daily_pipeline(kis_client=kis, naver_client=naver, target_date_str="2026-09-18", market_only=True)
        saved = read_market_store()["ipos"]
        self.assertEqual({item.get("stock_code") for item in saved if item.get("stock_code")}, {"111111", "222222", "333333", "444444"})
        self.assertEqual(len([item for item in saved if item.get("stock_code") == "444444"]), 1)
        self.assertEqual(next(item for item in saved if item.get("stock_code") == "222222")["expected_listing_date"], "2026-09-29")

    def test_market_get_remains_read_only(self):
        token = main._serializer.dumps({"user": self.username, "role": "user"})
        before = self.market_file.read_bytes()
        with patch("app.services.user_manager.get_user_by_name", return_value={"username": self.username, "role": "user"}):
            response = TestClient(main.app).get("/api/ipo/market", headers={"Cookie": f"{main.COOKIE_NAME}={token}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.market_file.read_bytes(), before)

    def test_frontend_refresh_uses_post_and_keeps_existing_rows_on_failure(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "static" / "wealth-ipo.js").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/ipo/market/refresh', { method: 'POST' })", source)
        self.assertIn("marketIpos = Array.isArray(data.market?.ipos) ? data.market.ipos : marketIpos", source)
        self.assertIn("공모주 일정 동기화에 실패했습니다. 기존 데이터를 유지합니다.", source)
        self.assertIn("button.disabled = false;", source)
        self.assertIn("refreshInFlight = false;", source)


if __name__ == "__main__":
    unittest.main()
