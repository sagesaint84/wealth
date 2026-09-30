from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.services.ipo.source_discovery import discover_and_merge_primary_sources
from app.services.ipo.store import read_market_store


class _DartOff:
    def is_configured(self):
        return False


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


class _Metalogos:
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

    def test_kind_remains_canonical_while_naver_npay_and_160_enrich_same_record(self):
        result = discover_and_merge_primary_sources(
            username="user",
            target_date_str="2026-10-01",
            kind_client=_Kind(),
            naver_client=_Naver(),
            npay_client=_Npay(),
            metalogos_client=_Metalogos(),
            dart_client=_DartOff(),
        )
        saved = read_market_store()["ipos"]
        self.assertEqual(len(saved), 1)
        ipo = saved[0]
        self.assertEqual(ipo["company_name"], "진코스텍")
        self.assertEqual(ipo["stock_code"], "123456")
        self.assertEqual(ipo["subscription_start"], "2026-10-02")
        self.assertEqual(ipo["subscription_end"], "2026-10-06")
        self.assertEqual(ipo["expected_listing_date"], "2026-10-15")
        self.assertEqual(ipo["final_offer_price"], 23500.0)
        self.assertEqual(ipo["lead_managers"], ["하나증권"])
        self.assertIn("kind", ipo["sources"])
        self.assertIn("naver_progress", ipo["sources"])
        self.assertIn("npay", ipo["sources"])
        self.assertIn("metalogos160", ipo["sources"])
        self.assertEqual(result["total_ipos"], 1)
        self.assertIn("sync_ok", result["statuses"]["kind_discovery"])


if __name__ == "__main__":
    unittest.main()
