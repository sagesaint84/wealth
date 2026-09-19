import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.services.ipo.calendar import build_moneylog_calendar_events
from app.services.pnl_records import write_pnl_records
from app.services.dividend_records import write_dividend_records
from app.services.ledger import write_ledger, default_ledger_data, get_ledger_path


class MoneylogCalendarTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.data_dir = Path(self.tmp_dir.name)
        self.username = "testuser"

        self.patches = [
            patch("app.services.user_manager.get_user_data_dir", return_value=self.data_dir),
            patch("app.services.ledger.get_user_data_dir", return_value=self.data_dir),
            patch("app.services.pnl_records._get_user_dir", return_value=self.data_dir),
            patch("app.services.dividend_records._get_user_dir", return_value=self.data_dir),
            # Calendar unit tests own their event fixtures; do not depend on a
            # live, process-shared IPO market snapshot.
            patch("app.services.ipo.store.read_market_store", return_value={"schema_version": 1, "ipos": []}),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

        # Seed test data
        self.pnl_records = [
            {
                "id": "pnl-1",
                "date": "2026-09-18",
                "code": "005930",
                "name": "삼성전자",
                "asset_type": "stock",
                "currency": "KRW",
                "pnl": 3133660.0,
                "pnl_krw": 3133660.0,
                "owner": "아빠",
            },
            {
                "id": "pnl-2",
                "date": "2026-09-10",
                "code": "REAL_ESTATE",
                "name": "마포 아파트",
                "asset_type": "real_estate",
                "currency": "KRW",
                "pnl": 50000000.0,
                "pnl_krw": 50000000.0,
                "owner": "엄마",
            },
            {
                "id": "pnl-3",
                "date": "2026-08-01",  # out of date range
                "code": "035420",
                "name": "NAVER",
                "asset_type": "stock",
                "currency": "KRW",
                "pnl": -50000.0,
                "pnl_krw": -50000.0,
                "owner": "아빠",
            },
        ]
        write_pnl_records(self.pnl_records, username=self.username)

        self.dividend_records = [
            {
                "id": "div-1",
                "date": "2026-09-18",
                "code": "005930",
                "name": "삼성전자",
                "currency": "KRW",
                "amount": 84000.0,
                "amount_krw": 84000.0,
                "owner": "아빠",
            },
            {
                "id": "div-2",
                "date": "2026-09-15",
                "code": "INTEREST_KRW",
                "name": "원화이자",
                "currency": "KRW",
                "amount": 12500.0,
                "amount_krw": 12500.0,
                "owner": "모두",
            },
            {
                "id": "div-3",
                "date": "2026-09-16",
                "code": "000660",
                "name": "SK하이닉스",
                "currency": "KRW",
                "amount": 40000.0,
                "amount_krw": 40000.0,
                "owner": "엄마",
            },
        ]
        write_dividend_records(self.dividend_records, username=self.username)

        ledger_payload = default_ledger_data()
        ledger_payload["transactions"] = [
            {
                "id": "tx-1",
                "date": "2026-09-18",
                "type": "expense",
                "amount": 120000.0,
                "category": "식비/외식",
                "owner": "아빠",
                "merchant": "식당",
            },
            {
                "id": "tx-2",
                "date": "2026-09-14",
                "type": "income",
                "amount": 3500000.0,
                "category": "급여/상여",
                "owner": "엄마",
                "merchant": "회사",
            },
        ]
        write_ledger(ledger_payload, username=self.username)

    def test_calendar_events_all_owners(self):
        events = build_moneylog_calendar_events(
            self.username,
            from_date="2026-09-01",
            to_date="2026-09-30",
            owner="모두",
        )
        # Should include pnl-1, pnl-2, div-1, div-2, div-3, tx-1, tx-2 (pnl-3 is in August)
        self.assertEqual(len(events), 7)

        # Check realized_pnl event
        pnl_ev = next(e for e in events if e["id"] == "realized:pnl-1")
        self.assertEqual(pnl_ev["type"], "realized_pnl")
        self.assertEqual(pnl_ev["subtype"], "stock")
        self.assertEqual(pnl_ev["amount_krw"], 3133660.0)
        self.assertEqual(pnl_ev["owner"], "아빠")
        self.assertEqual(pnl_ev["date"], "2026-09-18")
        self.assertEqual(pnl_ev["source_id"], "pnl-1")

        # Check dividend event
        div_ev = next(e for e in events if e["id"] == "dividend:div-1")
        self.assertEqual(div_ev["type"], "dividend")
        self.assertEqual(div_ev["subtype"], "dividend")
        self.assertEqual(div_ev["amount_krw"], 84000.0)
        self.assertIn("삼성전자 배당", div_ev["title"])

        # Check interest event
        int_ev = next(e for e in events if e["id"] == "interest:div-2")
        self.assertEqual(int_ev["type"], "interest")
        self.assertEqual(int_ev["subtype"], "interest")
        self.assertEqual(int_ev["amount_krw"], 12500.0)

        # Check ledger expense event
        exp_ev = next(e for e in events if e["id"] == "ledger:tx-1")
        self.assertEqual(exp_ev["type"], "ledger_expense")
        self.assertEqual(exp_ev["subtype"], "식비/외식")
        self.assertEqual(exp_ev["amount_krw"], -120000.0)

        # Check ledger income event
        inc_ev = next(e for e in events if e["id"] == "ledger:tx-2")
        self.assertEqual(inc_ev["type"], "ledger_income")
        self.assertEqual(inc_ev["amount_krw"], 3500000.0)

    def test_calendar_events_owner_filter(self):
        events = build_moneylog_calendar_events(
            self.username,
            from_date="2026-09-01",
            to_date="2026-09-30",
            owner="아빠",
        )
        # Should include pnl-1 (아빠), div-1 (아빠), div-2 (모두), tx-1 (아빠)
        # Should exclude pnl-2 (엄마), div-3 (엄마), tx-2 (엄마)
        event_ids = {e["id"] for e in events}
        self.assertIn("realized:pnl-1", event_ids)
        self.assertIn("dividend:div-1", event_ids)
        self.assertIn("interest:div-2", event_ids)  # owner: 모두 is included
        self.assertIn("ledger:tx-1", event_ids)
        self.assertNotIn("realized:pnl-2", event_ids)
        self.assertNotIn("dividend:div-3", event_ids)
        self.assertNotIn("ledger:tx-2", event_ids)

    def test_date_range_filtering(self):
        events = build_moneylog_calendar_events(
            self.username,
            from_date="2026-09-17",
            to_date="2026-09-18",
            owner="모두",
        )
        # Only events on 2026-09-18
        for e in events:
            self.assertEqual(e["date"], "2026-09-18")

    def test_invalid_date_formats(self):
        with self.assertRaises(ValueError):
            build_moneylog_calendar_events(self.username, "2026-09-32", "2026-09-30")
        with self.assertRaises(ValueError):
            build_moneylog_calendar_events(self.username, "invalid", "2026-09-30")
        with self.assertRaises(ValueError):
            build_moneylog_calendar_events(self.username, "2026-09-30", "2026-09-01")

    def test_source_records_are_not_mutated(self):
        pnl_file = self.data_dir / "realized_pnl_records.json"
        before_pnl = pnl_file.read_bytes()
        div_file = self.data_dir / "dividend_records.json"
        before_div = div_file.read_bytes()
        ledger_file = self.data_dir / "ledger.json"
        before_ledger = ledger_file.read_bytes()

        build_moneylog_calendar_events(
            self.username,
            from_date="2026-09-01",
            to_date="2026-09-30",
            owner="모두",
        )

        self.assertEqual(pnl_file.read_bytes(), before_pnl)
        self.assertEqual(div_file.read_bytes(), before_div)
        self.assertEqual(ledger_file.read_bytes(), before_ledger)

    def test_calendar_api_endpoint(self):
        client = TestClient(main.app)
        token = main._serializer.dumps({"user": self.username, "role": "user"})
        headers = {"Cookie": f"{main.COOKIE_NAME}={token}"}
        fake_user = {"username": self.username, "role": "user"}

        with patch("app.services.user_manager.get_user_by_name", return_value=fake_user):
            resp = client.get("/api/moneylog/calendar?from=2026-09-01&to=2026-09-30&owner=모두", headers=headers)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["from"], "2026-09-01")
            self.assertEqual(data["to"], "2026-09-30")
            self.assertEqual(data["owner"], "모두")
            self.assertIn("events", data)
            self.assertIsInstance(data["events"], list)
            self.assertGreater(len(data["events"]), 0)

            # Invalid date check via API
            resp_bad = client.get("/api/moneylog/calendar?from=bad-date&to=2026-09-30", headers=headers)
            self.assertEqual(resp_bad.status_code, 400)

            # from > to check via API
            resp_inverted = client.get("/api/moneylog/calendar?from=2026-09-30&to=2026-09-01", headers=headers)
            self.assertEqual(resp_inverted.status_code, 400)

    def test_calendar_corrupt_market_does_not_swallow(self):
        from app.services.ipo.store import IpoStorageError
        with patch("app.services.ipo.store.read_market_store", side_effect=IpoStorageError("Corrupt market json")):
            with self.assertRaises(IpoStorageError):
                build_moneylog_calendar_events(self.username, "2026-09-01", "2026-09-30", "모두")

    def test_calendar_listing_actual_suppresses_expected(self):
        fake_market = {
            "schema_version": 1,
            "ipos": [{
                "ipo_id": "ipo-dual-listing",
                "company_name": "상장테스트",
                "expected_listing_date": "2026-09-20",
                "actual_listing_date": "2026-09-22",
                "final_offer_price": 20000,
            }]
        }
        with patch("app.services.ipo.store.read_market_store", return_value=fake_market):
            evs = build_moneylog_calendar_events(self.username, "2026-09-01", "2026-09-30", "모두")
            listing_evs = [e for e in evs if e["type"] == "ipo_listing"]
            # Exactly one listing event should be projected, with actual date 2026-09-22
            self.assertEqual(len(listing_evs), 1)
            self.assertEqual(listing_evs[0]["date"], "2026-09-22")
            self.assertEqual(listing_evs[0]["meta"]["listing_status"], "actual")

    def test_calendar_ipo_projection_excludes_payment_and_refund(self):
        fake_market = {
            "schema_version": 1,
            "ipos": [{
                "ipo_id": "ipo-schedule",
                "company_name": "일정테스트",
                "subscription_start": "2026-09-15",
                "subscription_end": "2026-09-16",
                "payment_date": "2026-09-18",
                "refund_date": "2026-09-18",
                "expected_listing_date": "2026-09-29",
            }],
        }
        with patch("app.services.ipo.store.read_market_store", return_value=fake_market):
            events = build_moneylog_calendar_events(self.username, "2026-09-01", "2026-09-30", "모두")
        self.assertEqual(
            [(event["date"], event["type"]) for event in events if event.get("source_id") == "ipo-schedule"],
            [("2026-09-15", "ipo_subscription"), ("2026-09-16", "ipo_subscription"), ("2026-09-29", "ipo_listing")],
        )
        self.assertFalse(any(event["type"] in {"ipo_payment", "ipo_refund"} for event in events))

    def test_calendar_owner_all_requires_all_applied(self):
        fake_market = {
            "schema_version": 1,
            "ipos": [{
                "ipo_id": "ipo-app-check",
                "company_name": "신청테스트",
                "subscription_start": "2026-09-15",
                "subscription_end": "2026-09-16",
            }]
        }
        # Partial application (only 아빠 applied, not all)
        partial_apps = {
            "applications": {
                "ipo-app-check": {
                    "applied_owners": ["아빠"],
                    "target_owners": ["아빠", "엄마"],
                    "all_applied": False,
                }
            }
        }
        with patch("app.services.ipo.store.read_market_store", return_value=fake_market):
            with patch("app.services.ipo.applications.get_user_applications", return_value=partial_apps):
                evs_modu = build_moneylog_calendar_events(self.username, "2026-09-01", "2026-09-30", "모두")
                sub_ev = next(e for e in evs_modu if e["type"] == "ipo_subscription")
                self.assertFalse(sub_ev["meta"]["is_applied_by_owner"])

                # Direct query for 아빠 should be True
                evs_appa = build_moneylog_calendar_events(self.username, "2026-09-01", "2026-09-30", "아빠")
                sub_ev_appa = next(e for e in evs_appa if e["type"] == "ipo_subscription")
                self.assertTrue(sub_ev_appa["meta"]["is_applied_by_owner"])


if __name__ == "__main__":
    unittest.main()
