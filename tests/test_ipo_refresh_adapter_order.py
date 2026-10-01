from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.ipo import refresh_adapter


class IpoRefreshAdapterOrderTests(unittest.TestCase):
    def test_full_refresh_runs_base_before_preferred_source_overlay(self):
        calls: list[str] = []

        def base(**_kwargs):
            calls.append("base")
            return {"status": "ok", "sources": {"kis": "sync_ok"}, "total_ipos": 10}

        def supplement(**_kwargs):
            calls.append("supplement")
            return (
                {"statuses": {"kind_discovery": "sync_ok"}, "total_ipos": 18},
                {"status": "ok", "enriched": 5},
            )

        with patch.object(refresh_adapter, "_BASE_REFRESH_ENRICHED", side_effect=base), \
             patch.object(refresh_adapter, "_run_supplement_and_targeted", side_effect=supplement):
            result = refresh_adapter.refresh_ipo_market_enriched(
                username="user",
                target_date_str="2026-10-01",
            )

        self.assertEqual(calls, ["base", "supplement"])
        self.assertEqual(result["total_ipos"], 18)
        self.assertEqual(result["targeted_dart"]["enriched"], 5)
        self.assertEqual(
            result["discovery_priority"],
            "DART/KIND + NAVER/Npay > Metalogos160 > KIS fallback",
        )

    def test_interactive_refresh_can_recover_from_preserved_kis_when_main_sources_sync(self):
        with patch.object(
            refresh_adapter,
            "_BASE_REFRESH_MARKET",
            return_value={"status": "preserved", "sources": {"kis": "source_error"}, "total_ipos": 10},
        ), patch.object(
            refresh_adapter,
            "_run_supplement_and_targeted",
            return_value=(
                {"statuses": {"npay": "sync_ok (relevant=18, review_required=0)"}, "total_ipos": 18},
                {"status": "ok", "enriched": 3},
            ),
        ):
            result = refresh_adapter.refresh_ipo_market(
                username="user",
                target_date_str="2026-10-01",
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["base_refresh_status"], "preserved")
        self.assertEqual(result["total_ipos"], 18)
        self.assertEqual(result["targeted_dart"]["enriched"], 3)

    def test_supplemental_160_alone_does_not_hide_main_source_failure(self):
        result = refresh_adapter._merge_refresh_result(
            {"status": "preserved", "sources": {"kis": "source_error"}},
            {"statuses": {"metalogos160": "sync_ok (relevant=7)"}, "total_ipos": 17},
            {"status": "ok"},
        )
        self.assertEqual(result["status"], "preserved")
        self.assertNotIn("base_refresh_status", result)


if __name__ == "__main__":
    unittest.main()
