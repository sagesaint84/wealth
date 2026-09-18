import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.ipo.store import (
    IpoStorageError,
    get_market_file,
    read_market_store,
    upsert_ipo_record,
    write_market_store,
)


class IpoStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.market_file = Path(self.tmp_dir.name) / "market.json"
        self.patcher = patch("app.services.ipo.store.get_market_file", return_value=self.market_file)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.tmp_dir.cleanup)

    def test_corrupt_market_store_raises(self):
        self.market_file.write_text("{invalid json corrupt", encoding="utf-8")
        with self.assertRaises(IpoStorageError):
            read_market_store()

    def test_failed_feature_refresh_preserves_previous_ok_value(self):
        # Initial record with good features
        initial = {
            "ipo_id": "ipo_test_feat",
            "company_name": "특성기업",
            "stock_code": "123450",
            "features": {
                "tradable_share_ratio": {"value": 25.5, "status": "ok"},
                "lockup_commitment_ratio": {"value": 40.0, "status": "ok"},
            }
        }
        upsert_ipo_record(initial)

        # Incoming refresh has parse_error on tradable_share_ratio
        incoming_refresh = {
            "ipo_id": "ipo_test_feat",
            "stock_code": "123450",
            "features": {
                "tradable_share_ratio": {"value": None, "status": "parse_error", "source_status": "table_mismatch"},
                "lockup_commitment_ratio": {"value": 42.0, "status": "ok"},
            }
        }
        saved, review = upsert_ipo_record(incoming_refresh)
        self.assertFalse(review)
        feats = saved["features"]

        # tradable_share_ratio must preserve the original 25.5 and 'ok' status!
        self.assertEqual(feats["tradable_share_ratio"]["value"], 25.5)
        self.assertEqual(feats["tradable_share_ratio"]["status"], "ok")
        self.assertEqual(feats["tradable_share_ratio"].get("source_status"), "table_mismatch")

        # lockup_commitment_ratio updated to 42.0
        self.assertEqual(feats["lockup_commitment_ratio"]["value"], 42.0)

    def test_zero_feature_is_not_treated_as_missing(self):
        record = {
            "ipo_id": "ipo_test_zero",
            "company_name": "제로기업",
            "stock_code": "987650",
            "features": {
                "secondary_sale_ratio": {"value": 0.0, "status": "ok"},
            }
        }
        saved, _ = upsert_ipo_record(record)
        self.assertEqual(saved["features"]["secondary_sale_ratio"]["value"], 0.0)
        self.assertEqual(saved["features"]["secondary_sale_ratio"]["status"], "ok")

        # Refresh with an error should preserve 0.0
        refresh = {
            "ipo_id": "ipo_test_zero",
            "stock_code": "987650",
            "features": {
                "secondary_sale_ratio": {"value": None, "status": "source_error"},
            }
        }
        saved2, _ = upsert_ipo_record(refresh)
        self.assertEqual(saved2["features"]["secondary_sale_ratio"]["value"], 0.0)
        self.assertEqual(saved2["features"]["secondary_sale_ratio"]["status"], "ok")

    def test_atomic_upsert_concurrent_threads(self):
        # Concurrently upsert records to verify thread safety
        errors = []

        def worker(idx):
            try:
                rec = {
                    "ipo_id": f"ipo_thread_{idx}",
                    "company_name": f"스레드기업_{idx}",
                    "stock_code": f"{idx:06d}",
                }
                upsert_ipo_record(rec)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        store = read_market_store()
        self.assertEqual(len(store["ipos"]), 15)


if __name__ == "__main__":
    unittest.main()
