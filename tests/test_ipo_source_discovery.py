from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.services.ipo.display import current_schedule, display_records, schedule_condition
from app.services.ipo.npay_client import parse_npay_ipo_html
from app.services.ipo.presentation import derive_market_state
from app.services.ipo.source_discovery import (
    _apply_observation,
    _record_npay_withdrawals,
    discover_and_merge_primary_sources,
)
from app.services.ipo.store import read_market_store


class NpayWithdrawalProjectionTests(unittest.TestCase):
    def test_same_period_requires_matching_code_for_withdrawn_state(self):
        observed = {
            "stock_code": "0103V0", "company_name": "Example IPO",
            "ipo_status": "공모철회", "subscription_start": "2026-11-24",
            "subscription_end": "2026-11-25",
        }
        today = date(2026, 11, 24)
        for code, expected in (("0103V0", "WITHDRAWN"), ("Z00459", "DATE_UNKNOWN")):
            with self.subTest(code=code):
                ipo = {
                    "ipo_id": "existing-ipo", "stock_code": code, "company_name": observed["company_name"],
                    "subscription_start": observed["subscription_start"],
                    "subscription_end": observed["subscription_end"],
                }
                _record_npay_withdrawals({"ipos": [ipo]}, [observed], today=today.isoformat(),
                                         observed_at="2026-11-24T10:00:00+09:00")
                displayed = current_schedule(display_records([ipo], today)[0], today)
                self.assertEqual(derive_market_state(displayed, today), expected)
                self.assertIsNone(displayed["subscription_start"])
                self.assertIsNone(displayed["subscription_end"])
                self.assertEqual(ipo["ipo_id"], "existing-ipo")
                self.assertEqual(ipo["stock_code"], code)
                self.assertEqual(ipo["subscription_start"], "2026-11-24")
                self.assertEqual(ipo["subscription_end"], "2026-11-25")

    def test_active_unlisted_row_with_same_code_and_close_date_keeps_withdrawal_under_review(self):
        today = date(2026, 11, 24)
        ipo = {"ipo_id": "existing-ipo", "stock_code": "0103V0", "company_name": "Example IPO",
               "subscription_start": "2026-11-24", "subscription_end": "2026-11-25"}
        withdrawn = {**ipo, "ipo_status": "공모철회"}
        positive = parse_npay_ipo_html(
            """다가오는 청약 종목 청약진행중 1 청약예정 0 진행중 11.25 마감 Example IPO 공모가 15,000원
            <script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"dehydratedState":{"queries":[{"queryKey":["upcomingStocks"],
            "state":{"data":{"toBeIPOList":[],"beingIPOList":[{"stockCode":"0103V0",
            "closedDate":"2026-11-25","stockName":"Example IPO"}]}}}]}}}}
            </script>""",
            target_date_str=today.isoformat(),
        )
        self.assertEqual(positive[0]["stock_code"], ipo["stock_code"])
        for observed_at, observations in (
            ("2026-11-24T10:00:00+09:00", positive),
            ("2026-11-24T11:00:00+09:00", []),
        ):
            _record_npay_withdrawals({"ipos": [ipo]}, [withdrawn], today=today.isoformat(),
                                     observed_at=observed_at, positive_observations=observations)
            viewed = current_schedule(display_records([ipo], today)[0], today)
            self.assertEqual(schedule_condition(viewed), "unverified")
            self.assertEqual(derive_market_state(viewed, today), "DATE_UNKNOWN")
            self.assertIsNone(viewed["subscription_end"])
            self.assertEqual(ipo["subscription_end"], "2026-11-25")
            self.assertEqual(ipo["ipo_id"], "existing-ipo")


    def test_official_filing_resolves_known_conflicts_without_changing_the_ipo_identity(self):
        for name, stored_code, reported_code, start, end, receipt in (
            ("케이엠에프", "0103V0", "0103V0", "2026-11-24", "2026-11-25", "20261123000066"),
            ("아델", "Z00459", "0181E0", "2026-11-23", "2026-11-24", "20261120000119"),
        ):
            with self.subTest(name=name):
                ipo = {"ipo_id": "existing-ipo", "stock_code": stored_code, "company_name": name,
                       "subscription_start": start}
                stopped = {**ipo, "stock_code": reported_code, "ipo_status": "공모철회", "subscription_end": end}
                market = {"ipos": [ipo]}
                reviews = _record_npay_withdrawals(
                    market, [stopped], today="2026-11-26", observed_at="2026-11-26T10:00:00+09:00",
                    unlisted_read_ok=False,
                )
                self.assertEqual(reviews, 0)
                self.assertEqual(ipo["sources"]["npay_offering_restriction"]["official_withdrawal"]["rcept_no"], receipt)
                view = current_schedule(display_records(market["ipos"])[0])
                self.assertEqual(schedule_condition(view), "withdrawn")
                self.assertIsNone(view["subscription_start"])
                self.assertEqual(ipo["subscription_start"], start)
                self.assertEqual(ipo["stock_code"], stored_code)
                self.assertEqual(ipo["ipo_id"], "existing-ipo")


class _DartOff:
    def is_configured(self):
        return False


class _DartOn:
    def is_configured(self):
        return True

    def _request_json(self, endpoint, params):
        self.endpoint = endpoint
        self.params = params
        return {
            "total_page": 1,
            "list": [{
                "corp_code": "01000001",
                "corp_name": "\uc9c4\ucf54\uc2a4\ud14d",
                "stock_code": "123456",
                "rcept_no": "20260930000123",
                "rcept_dt": "20260930",
                "report_nm": "[\ubc1c\ud589\uc870\uac74\ud655\uc815]\uc99d\uad8c\uc2e0\uace0\uc11c(\uc9c0\ubd84\uc99d\uad8c)",
            }],
        }

    def get_corp_code_master(self):
        return [{
            "corp_code": "01000001",
            "corp_name": "\uc9c4\ucf54\uc2a4\ud14d",
            "stock_code": "123456",
        }]

    def get_filing_list(self, **_kwargs):
        return {
            "list": [{
                "corp_code": "01000001",
                "corp_name": "\uc9c4\ucf54\uc2a4\ud14d",
                "stock_code": "123456",
                "rcept_no": "20260930000123",
                "rcept_dt": "20260930",
                "report_nm": "[\ubc1c\ud589\uc870\uac74\ud655\uc815]\uc99d\uad8c\uc2e0\uace0\uc11c(\uc9c0\ubd84\uc99d\uad8c)",
            }]
        }

    def get_equity_registration_statements(self, **_kwargs):
        return {
            "group": [
                {
                    "title": "general",
                    "list": [{
                        "rcept_no": "20260930000123",
                        "corp_code": "01000001",
                        "corp_name": "\uc9c4\ucf54\uc2a4\ud14d",
                        "corp_cls": "K",
                        "sbd": "2026.10.03 ~ 10.07",
                        "pymd": "2026.10.08",
                    }],
                },
                {
                    "title": "underwriters",
                    "list": [{
                        "rcept_no": "20260930000123",
                        "actnmn": "\uacf5\uc2dd\uc99d\uad8c",
                    }],
                },
                {
                    "title": "security classes",
                    "list": [{
                        "rcept_no": "20260930000123",
                        "slprc": "24,000",
                    }],
                },
            ]
        }


class _Kind:
    def fetch_pubofr_schedule_items(self, **_kwargs):
        return [{
            "company_name": "진코스텍",
            "kind_bz_procs_no": "KIND-1",
            "subscription_start": "2026-10-02",
            "subscription_end": "2026-10-06",
            "expected_listing_date": "2026-10-15",
            "final_offer_price": 23500.0,
            "market": "KOSDAQ",
            "lead_managers": ["하나증권"],
        }]


class _Naver:
    def fetch_ipo_progress_items(self):
        return [{
            "company_name": "진코스텍",
            "stock_code": "123456",
            "raw_ipo_code": "A123456",
            "expected_listing_date": "2026-10-15",
        }]


class _Npay:
    def fetch_upcoming_ipos(self, *, target_date_str):
        self.target_date_str = target_date_str
        return [{
            "company_name": "진코스텍",
            "subscription_start": "2026-10-02",
            "final_offer_price": 22000.0,
            "sources": {"npay": {"institutional_competition_ratio_reference": 1097.62}},
        }]


class _FailingKind:
    def fetch_pubofr_schedule_items(self, **_kwargs):
        raise RuntimeError("KIND unavailable")


class _FailingNpay:
    def fetch_upcoming_ipos(self, *, target_date_str):
        raise RuntimeError("Npay unavailable")


class _FailingNaver:
    def fetch_ipo_discovery_items(self):
        raise RuntimeError("NAVER unavailable")


class _Metalogos:
    def fetch_company_items(
        self,
        *,
        company_names,
        target_date_str,
    ):
        self.company_names = list(company_names)
        return self.fetch_calendar_items(
            target_date_str=target_date_str
        )

    def fetch_calendar_items(self, *, target_date_str):
        self.target_date_str = target_date_str
        return [{
            "company_name": "진코스텍",
            "stock_code": "123456",
            "subscription_start": "2026-10-02",
            "subscription_end": "2026-10-06",
            "expected_listing_date": "2026-10-15",
            "final_offer_price": 21000.0,
            "market": "KOSDAQ",
            "sources": {"metalogos160": {"attractiveness_score": 87}},
        }]


class IpoSourceDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.market_file = Path(self.temp.name) / "market.json"
        self.market_file.write_text(
            json.dumps({"schema_version": 1, "updated_at": "old", "ipos": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        self.patch = patch("app.services.ipo.store.get_market_file", return_value=self.market_file)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_only_npay_is_called_and_legacy_market_records_are_not_rewritten(self):
        kind, naver, metalogos, dart = _Kind(), _Naver(), _Metalogos(), _DartOn()
        npay = _Npay()
        with (
            patch.object(kind, "fetch_pubofr_schedule_items", wraps=kind.fetch_pubofr_schedule_items) as fetch_pubofr_schedule_items,
            patch.object(naver, "fetch_ipo_progress_items", wraps=naver.fetch_ipo_progress_items) as fetch_ipo_progress_items,
            patch.object(metalogos, "fetch_company_items", wraps=metalogos.fetch_company_items) as fetch_company_items,
            patch.object(dart, "is_configured", wraps=dart.is_configured) as is_configured,
        ):
            result = discover_and_merge_primary_sources(
                username="user",
                target_date_str="2026-10-01",
                kind_client=kind,
                naver_client=naver,
                npay_client=npay,
                metalogos_client=metalogos,
                dart_client=dart,
            )
        saved = read_market_store()["ipos"]
        self.assertEqual(len(saved), 1)
        ipo = saved[0]
        self.assertEqual(ipo["company_name"], "진코스텍")
        self.assertNotIn("stock_code", ipo)
        self.assertEqual(ipo["subscription_start"], "2026-10-02")
        self.assertNotIn("subscription_end", ipo)
        self.assertNotIn("expected_listing_date", ipo)
        self.assertEqual(ipo["final_offer_price"], 22000.0)
        self.assertIn("npay", ipo["sources"])
        self.assertNotIn("kind", ipo["sources"])
        self.assertNotIn("naver_progress", ipo["sources"])
        self.assertNotIn("metalogos160", ipo["sources"])
        fetch_pubofr_schedule_items.assert_not_called()
        fetch_ipo_progress_items.assert_not_called()
        fetch_company_items.assert_not_called()
        is_configured.assert_not_called()
        self.assertEqual(result["total_ipos"], 1)
        self.assertIn("sync_ok", result["statuses"]["npay"])

    def test_existing_dart_identity_and_score_are_preserved_without_outbound_refresh(self):
        existing = {
            "ipo_id": "legacy", "company_name": "진코스텍", "subscription_start": "2026-10-02",
            "corp_code": "01000001", "subscription_end": "2026-10-06", "final_offer_price": 22000,
            "sources": {"dart_schedule": {"board_reference": "retained"},
                        "schedule_fields": {"subscription_start": {"source": "npay", "value": "2026-10-02"}}},
            "score": {"score": 72, "status": "OK"},
        }
        market = {"schema_version": 1, "updated_at": "old", "ipos": [existing]}
        self.market_file.write_text(json.dumps(market, ensure_ascii=False), encoding="utf-8")
        dart = _DartOn()
        with (
            patch.object(dart, "get_corp_code_master", wraps=dart.get_corp_code_master) as get_corp_code_master,
            patch.object(dart, "get_filing_list", wraps=dart.get_filing_list) as get_filing_list,
        ):
            result = discover_and_merge_primary_sources(
                username="user",
                target_date_str="2026-10-01",
                kind_client=_Kind(),
                naver_client=_Naver(),
                npay_client=_Npay(),
                metalogos_client=_Metalogos(),
                dart_client=dart,
            )
        ipo = read_market_store()["ipos"][0]
        self.assertEqual(ipo["ipo_id"], "legacy")
        self.assertEqual(ipo["score"], {"score": 72, "status": "OK"})
        self.assertEqual(ipo["corp_code"], "01000001")
        self.assertEqual(ipo["subscription_start"], "2026-10-02")
        self.assertEqual(ipo["subscription_end"], "2026-10-06")
        self.assertEqual(ipo["final_offer_price"], 22000.0)
        self.assertEqual(ipo["sources"]["dart_schedule"]["board_reference"], "retained")
        get_corp_code_master.assert_not_called()
        get_filing_list.assert_not_called()
        self.assertEqual(result["statuses"]["dart_schedule"], "not_requested (npay_only_policy)")

    def _davio(self):
        return {
            "ipo_id": "ipo_davio_original",
            "company_name": "다비오",
            "stock_code": "0012G0",
            "corp_code": "12345678",
            "listing_track": "general",
            "subscription_start": "2026-11-10",
            "subscription_end": "2026-12-02",
            "offer_band_low": 12300,
            "offer_band_high": 16600,
            "application_record_ids": ["ipo_davio_original", "prior_alias"],
            "identity_alias_ids": ["prior_alias"],
            "sources": {
                "npay": {"url": "https://ustock.naver.com/service/ipo?schedule=toBeIPOList"},
                "schedule_fields": {
                    "subscription_start": {"source": "npay", "value": "2026-11-10", "observed_at": "2026-10-30T09:00:00+09:00"},
                    "subscription_end": {"source": "kind", "value": "2026-12-02", "observed_at": "2026-10-30T09:00:00+09:00"},
                },
            },
        }

    def _davio_npay_update(self):
        return {
            "company_name": "다비오",
            "listing_track": "general",
            "subscription_start": "2026-12-01",
            "offer_band_low": 12300,
            "offer_band_high": 16600,
            "sources": {"npay": {
                "url": "https://ustock.naver.com/service/ipo?schedule=toBeIPOList",
                "observed_at": "2026-11-10T12:00:00+09:00",
            }},
        }

    def test_npay_date_change_updates_same_ipo_and_preserves_identity_links(self):
        ipo = self._davio()
        store = {"ipos": [ipo]}
        target, review = _apply_observation(store, self._davio_npay_update(), source_name="npay")
        self.assertFalse(review)
        self.assertIs(target, ipo)
        self.assertEqual(len(store["ipos"]), 1)
        self.assertEqual(ipo["ipo_id"], "ipo_davio_original")
        self.assertEqual(ipo["application_record_ids"], ["ipo_davio_original", "prior_alias"])
        self.assertEqual(ipo["identity_alias_ids"], ["prior_alias"])
        self.assertEqual(ipo["subscription_start"], "2026-12-01")
        # Npay's public row confirms only the start date; it does not invent an end date.
        self.assertEqual(ipo["subscription_end"], "2026-12-02")
        start_evidence = ipo["sources"]["schedule_fields"]["subscription_start"]
        self.assertEqual(start_evidence["source"], "npay")
        self.assertEqual(start_evidence["value"], "2026-12-01")
        self.assertEqual(start_evidence["observed_at"], "2026-11-10T12:00:00+09:00")
        self.assertEqual(start_evidence["url"], "https://ustock.naver.com/service/ipo?schedule=toBeIPOList")
        self.assertEqual(ipo["sources"]["schedule_reconciliation"]["status"], "partial")
        self.assertEqual(schedule_condition(ipo), "unverified")

    def test_repeated_npay_schedule_refresh_is_idempotent(self):
        store = {"ipos": [self._davio()]}
        first, review = _apply_observation(store, self._davio_npay_update(), source_name="npay")
        self.assertFalse(review)
        second, review = _apply_observation(store, self._davio_npay_update(), source_name="npay")
        self.assertFalse(review)
        self.assertIs(first, second)
        self.assertEqual(len(store["ipos"]), 1)
        self.assertEqual(store["ipos"][0]["ipo_id"], "ipo_davio_original")

    def test_identity_or_offer_conflict_is_reviewed_without_merging_or_duplicate_ipo(self):
        ipo = self._davio()
        store = {"ipos": [ipo]}
        incoming = self._davio_npay_update()
        incoming["corp_code"] = "87654321"
        _, review = _apply_observation(store, incoming, source_name="npay")
        self.assertTrue(review)
        self.assertEqual(len(store["ipos"]), 1)
        self.assertEqual(ipo["subscription_start"], "2026-11-10")
        self.assertEqual(ipo["ipo_id"], "ipo_davio_original")
        self.assertEqual(len(store["schedule_reviews"]), 1)
        self.assertEqual(store["schedule_reviews"][0]["status"], "review_required")

    def test_start_after_retained_end_is_not_written_and_requires_schedule_review(self):
        ipo = self._davio()
        store = {"ipos": [ipo]}
        incoming = self._davio_npay_update()
        incoming["subscription_start"] = "2026-12-03"
        _, review = _apply_observation(store, incoming, source_name="npay")
        self.assertTrue(review)
        self.assertEqual(ipo["subscription_start"], "2026-11-10")
        self.assertEqual(ipo["subscription_end"], "2026-12-02")
        self.assertEqual(ipo["sources"]["schedule_reconciliation"]["status"], "review_required")

    def test_failed_source_attempt_preserves_schedule_evidence_and_is_not_a_successful_check(self):
        ipo = self._davio()
        original_fields = json.loads(json.dumps(ipo["sources"]["schedule_fields"]))
        state = {"schema_version": 1, "updated_at": "old", "ipos": [ipo]}

        def read():
            return json.loads(json.dumps(state))

        def write(market):
            state.clear()
            state.update(json.loads(json.dumps(market)))

        with patch("app.services.ipo.source_discovery.read_market_store", side_effect=read), \
             patch("app.services.ipo.source_discovery.write_market_store", side_effect=write):
            result = discover_and_merge_primary_sources(
                username="user", target_date_str="2026-11-10",
                kind_client=_FailingKind(), npay_client=_FailingNpay(),
                naver_client=_FailingNaver(), dart_client=_DartOff(),
            )
        saved = state["ipos"][0]
        self.assertEqual(saved["subscription_start"], "2026-11-10")
        self.assertEqual(saved["sources"]["schedule_fields"], original_fields)
        self.assertTrue(saved["sources"]["schedule_refresh_attempts"]["npay"]["outcome"].startswith("source_error"))
        self.assertIn("last_attempt_at", saved["sources"]["schedule_refresh_attempts"]["npay"])
        self.assertIn("source_error", result["statuses"]["npay"])

    def test_historical_record_is_not_rewritten_by_nonoverlapping_same_name_observation(self):
        ipo = self._davio()
        ipo.update({"subscription_start": "2025-11-10", "subscription_end": "2025-11-11",
                    "actual_listing_date": "2025-11-20"})
        store = {"ipos": [ipo]}
        incoming = self._davio_npay_update()
        _, review = _apply_observation(store, incoming, source_name="npay")
        self.assertTrue(review)
        self.assertEqual(len(store["ipos"]), 1)
        self.assertEqual(ipo["subscription_start"], "2025-11-10")
        self.assertEqual(ipo["actual_listing_date"], "2025-11-20")
        self.assertNotIn("schedule_reconciliation", ipo["sources"])
        self.assertEqual(store["schedule_reviews"][0]["status"], "review_required")


if __name__ == "__main__":
    unittest.main()
