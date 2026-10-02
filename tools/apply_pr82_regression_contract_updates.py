from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "tests" / "test_ipo_orchestrator.py"
PRESENTATION = ROOT / "tests" / "test_ipo_presentation.py"
ACTION_V2 = ROOT / "tests" / "test_ipo_subscription_reminders_action_v2.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_orchestrator_tests() -> None:
    text = ORCH.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''        # KIND, KRX, and NAVER are implemented but blocked by the test network policy.\n        self.assertIn("external_network_disabled", result["sources"]["kind"])\n        self.assertIn("external_network_disabled", result["sources"]["krx"])\n        self.assertIn("external_network_disabled", result["sources"]["naver"])\n''',
        '''        # KIND is still a live schedule fallback. Full KRX/NAVER history is explicit-only.\n        self.assertIn("external_network_disabled", result["sources"]["kind"])\n        self.assertEqual(result["sources"]["krx"], "not_requested (historical_sync_only)")\n        self.assertEqual(result["sources"]["naver"], "not_requested (historical_sync_only)")\n''',
        "pipeline source contract",
    )

    old = '''        self.assertIn("confirmed=1", result["sources"]["naver"])\n        saved = read_market_store()\n        nh = next(it for it in saved["ipos"] if it.get("stock_code") == "0197V0")\n        self.assertEqual(nh["actual_listing_date"], "2026-09-10")\n        self.assertEqual(nh["expected_listing_date"], "2026-09-10")\n        self.assertEqual(nh["sources"]["kis"]["schedule_source"], "ksdinfo_pub_offer")\n        self.assertNotIn("stock_info", nh["sources"]["kis"])\n        self.assertEqual(nh["sources"]["naver"]["listing_confirmation_source"], "ipo_progress_LISTING")\n        self.assertEqual(nh["sources"]["naver"]["ipo_code"], "A0197V0")\n        self.assertEqual(nh["sources"]["naver"]["ipo_status"], "상장")\n        self.assertEqual(nh["sources"]["naver"]["actual_listing_date"], "2026-09-10")\n        self.assertEqual(nh["sources"]["krx"]["listing_confirmation_source"], "finder_stkisu")\n        self.assertEqual(nh["sources"]["krx"]["short_code"], "0197V0")\n'''
    new = '''        self.assertEqual(result["sources"]["krx"], "not_requested (historical_sync_only)")\n        self.assertEqual(result["sources"]["naver"], "not_requested (historical_sync_only)")\n        mock_krx.fetch_listed_master.assert_not_called()\n        mock_naver.fetch_completed_listings.assert_not_called()\n        saved = read_market_store()\n        nh = next(it for it in saved["ipos"] if it.get("stock_code") == "0197V0")\n        self.assertIsNone(nh.get("actual_listing_date"))\n        self.assertEqual(nh["expected_listing_date"], "2026-09-10")\n        self.assertEqual(nh["sources"]["kis"]["schedule_source"], "ksdinfo_pub_offer")\n        self.assertNotIn("naver", nh["sources"])\n        self.assertNotIn("krx", nh["sources"])\n'''
    text = replace_once(text, old, new, "historical confirmation moved out of daily pipeline")

    text = replace_once(
        text,
        '        self.assertEqual(cand["actual_listing_date"], "2026-09-05")\n',
        '        self.assertEqual(cand["actual_listing_date"], "2026-09-01")\n        mock_krx.fetch_listed_master.assert_not_called()\n        mock_naver.fetch_completed_listings.assert_not_called()\n',
        "existing actual remains untouched",
    )

    text = replace_once(
        text,
        '''        self.assertEqual(cand["actual_listing_date"], "2026-09-10")\n        self.assertEqual(cand["sources"]["kind"]["schedule_source"], "pubofrprogcom")\n''',
        '''        self.assertIsNone(cand.get("actual_listing_date"))\n        self.assertEqual(cand["sources"]["kind"]["schedule_source"], "pubofrprogcom")\n        mock_krx.fetch_listed_master.assert_not_called()\n        mock_naver.fetch_completed_listings.assert_not_called()\n''',
        "kind source preserved without history scan",
    )

    text = replace_once(
        text,
        '''        self.assertIn("source_error", result["sources"]["naver"])\n        saved = read_market_store()\n        self.assertEqual(len(saved["ipos"]), 2)\n''',
        '''        self.assertEqual(result["sources"]["naver"], "not_requested (historical_sync_only)")\n        mock_naver.fetch_completed_listings.assert_not_called()\n        saved = read_market_store()\n        self.assertEqual(len(saved["ipos"]), 2)\n''',
        "naver failure path no longer entered",
    )

    text = replace_once(
        text,
        '''        self.assertIn("source_error", result["sources"]["krx"])\n        saved = read_market_store()\n        self.assertEqual(len(saved["ipos"]), 2)\n''',
        '''        self.assertEqual(result["sources"]["krx"], "not_requested (historical_sync_only)")\n        mock_krx.fetch_listed_master.assert_not_called()\n        saved = read_market_store()\n        self.assertEqual(len(saved["ipos"]), 2)\n''',
        "krx failure path no longer entered",
    )

    text = replace_once(
        text,
        '''        self.assertIn("source_error", result["sources"]["naver"])\n        saved = read_market_store()\n        c1 = next(it for it in saved["ipos"] if it.get("stock_code") == "111110")\n''',
        '''        self.assertEqual(result["sources"]["naver"], "not_requested (historical_sync_only)")\n        mock_krx.fetch_listed_master.assert_not_called()\n        mock_naver.fetch_completed_listings.assert_not_called()\n        saved = read_market_store()\n        c1 = next(it for it in saved["ipos"] if it.get("stock_code") == "111110")\n''',
        "historical source failure no longer part of daily pipeline",
    )

    text = replace_once(
        text,
        '        self.assertEqual(result["sources"]["krx"], "implementation_blocker")\n',
        '        self.assertEqual(result["sources"]["krx"], "not_requested (historical_sync_only)")\n',
        "krx missing method not relevant to routine refresh",
    )
    text = replace_once(
        text,
        '        self.assertEqual(result["sources"]["naver"], "implementation_blocker")\n',
        '        self.assertEqual(result["sources"]["naver"], "not_requested (historical_sync_only)")\n',
        "naver missing method not relevant to routine refresh",
    )

    ORCH.write_text(text, encoding="utf-8")


def patch_presentation_test() -> None:
    text = PRESENTATION.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    def test_subscription_period_projects_each_visible_day_and_owner_independent(self):\n',
        '    def test_subscription_period_projects_only_first_and_last_day_and_owner_independent(self):\n',
        "presentation test name",
    )
    text = replace_once(
        text,
        '        self.assertEqual(sorted(event["date"] for event in events if event["type"].startswith("ipo_subscription")), ["2026-09-18", "2026-09-19", "2026-09-20"])\n',
        '        subscription_events = [event for event in events if event["type"].startswith("ipo_subscription")]\n        self.assertEqual([event["date"] for event in subscription_events], ["2026-09-18", "2026-09-20"])\n        self.assertEqual([event["title"] for event in subscription_events], ["🎯 기간테스트 청약 첫째날", "🎯 기간테스트 청약 마지막날"])\n',
        "presentation boundary expectation",
    )
    PRESENTATION.write_text(text, encoding="utf-8")


def patch_action_v2_fixture() -> None:
    text = ACTION_V2.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    start_str = start or (cur - timedelta(days=1)).isoformat()\n    end_str = end or (cur + timedelta(days=2)).isoformat()\n',
        '    # Reminder integration tests run on the first canonical subscription day.\n    start_str = start or cur.isoformat()\n    end_str = end or (cur + timedelta(days=2)).isoformat()\n',
        "action-v2 reminder fixture boundary",
    )
    ACTION_V2.write_text(text, encoding="utf-8")


def main() -> None:
    patch_orchestrator_tests()
    patch_presentation_test()
    patch_action_v2_fixture()
    print("PR82_REGRESSION_CONTRACTS_UPDATED")


if __name__ == "__main__":
    main()
