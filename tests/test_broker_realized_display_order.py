from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.kis_feed import build_kis_realized_feed_response, verify_kis_feed_row_token
from app.services.kis_realized import preview_kis_realized_selection


ROOT = Path(__file__).resolve().parents[1]


class BrokerRealizedDisplayOrderTests(unittest.TestCase):
    def run_sort(self, rows: list[dict], tokens: list[str]) -> dict:
        if not shutil.which("node"):
            self.skipTest("node runtime is not available")
        script = r'''
const fs = require("fs");
const source = fs.readFileSync("app/static/wealth.js", "utf8");
const match = source.match(/function brokerRealizedDateKey\(value\) \{[\s\S]*?\r?\n\/\/ Wealth-side/);
if (!match) process.exit(2);
eval(match[0].replace(/\r?\n\r?\n\/\/ Wealth-side$/, ""));
const input = JSON.parse(process.argv[1]);
process.stdout.write(JSON.stringify(sortBrokerRealizedFeedRows(input.rows, input.tokens)));
'''
        completed = subprocess.run(
            ["node", "-e", script, json.dumps({"rows": rows, "tokens": tokens})],
            cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8",
        )
        return json.loads(completed.stdout)

    def test_hyphenated_compact_and_mixed_dates_sort_newest_first(self) -> None:
        rows = [
            {"date": "2026-01-01", "code": "OLD"},
            {"date": "20260303", "code": "NEW"},
            {"date": "2026-02-02", "code": "MID"},
        ]
        result = self.run_sort(rows, ["old-token", "new-token", "mid-token"])
        self.assertEqual([row["code"] for row in result["rows"]], ["NEW", "MID", "OLD"])
        self.assertEqual(result["selectionTokens"], ["new-token", "mid-token", "old-token"])

    def test_same_date_is_deterministic_and_identical_rows_are_preserved(self) -> None:
        duplicate = {
            "date": "20260303", "code": "B", "name": "Same",
            "canonical_hash": "hash-b", "source_occurrence": 1,
        }
        rows = [
            duplicate.copy(),
            {"date": "2026-03-03", "code": "A", "name": "Same", "canonical_hash": "hash-a", "source_occurrence": 1},
            duplicate.copy(),
        ]
        result = self.run_sort(rows, ["token-b1", "token-a", "token-b2"])
        self.assertEqual(len(result["rows"]), 3)
        self.assertEqual([row["code"] for row in result["rows"]], ["A", "B", "B"])
        self.assertCountEqual(result["selectionTokens"], ["token-a", "token-b1", "token-b2"])

    def test_sorting_changes_only_presentation_order_not_identity_fields(self) -> None:
        rows = [
            {"date": "20260101", "code": "A", "canonical_hash": "hash-a", "source_occurrence": 2, "source_fingerprint": "fp-a", "status": "NEW"},
            {"date": "2026-04-01", "code": "B", "canonical_hash": "hash-b", "source_occurrence": 1, "source_fingerprint": "fp-b", "status": "ALREADY_IMPORTED"},
        ]
        before = json.loads(json.dumps(rows))
        result = self.run_sort(rows, ["signed-a", "signed-b"])
        self.assertCountEqual(
            [(row["canonical_hash"], row["source_occurrence"], row["source_fingerprint"], row["status"]) for row in result["rows"]],
            [(row["canonical_hash"], row["source_occurrence"], row["source_fingerprint"], row["status"]) for row in before],
        )
        self.assertEqual(rows, before)
        self.assertEqual(result["selectionTokens"], ["signed-b", "signed-a"])

    def test_real_signed_rows_and_duplicate_classification_survive_sorting(self) -> None:
        raw_rows = [
            {"trad_dt": "20260101", "pdno": "SYN-A", "prdt_name": "Older", "sll_qty": "1", "sll_amt": "20", "buy_amt": "10", "rlzt_pfls": "10", "pfls_rt": "100"},
            {"trad_dt": "20260401", "pdno": "SYN-B", "prdt_name": "Newer", "sll_qty": "1", "sll_amt": "30", "buy_amt": "10", "rlzt_pfls": "20", "pfls_rt": "200"},
        ]
        source_key = "synthetic-source-key"
        user_id = "synthetic-user-id"
        with patch.dict(os.environ, {"WEALTH_ENV": "test", "WEALTH_TEST_SIGNING_SECRET": "synthetic-display-sort-secret"}, clear=False):
            feed = build_kis_realized_feed_response(
                market="kr", from_date="2026-01-01", to_date="2026-04-01",
                rows_raw=raw_rows, source_account_key=source_key,
                source_account_label="masked", user_id=user_id,
            )
            sorted_feed = self.run_sort(feed["rows"], feed["selection_tokens"])
            for row, token in zip(sorted_feed["rows"], sorted_feed["selectionTokens"]):
                valid, reason = verify_kis_feed_row_token(
                    row, token, user_id=user_id, expected_account_key=source_key,
                )
                self.assertTrue(valid, reason)

            destination = {"id": "synthetic-destination", "account_name": "Synthetic", "broker": "Synthetic", "owner": "모두"}
            before = preview_kis_realized_selection(
                [{"row": row, "selection_token": token} for row, token in zip(feed["rows"], feed["selection_tokens"])],
                destination, [], user_id=user_id, source_account_key=source_key, market="kr",
            )
            after = preview_kis_realized_selection(
                [{"row": row, "selection_token": token} for row, token in zip(sorted_feed["rows"], sorted_feed["selectionTokens"])],
                destination, [], user_id=user_id, source_account_key=source_key, market="kr",
            )
        self.assertCountEqual(
            [(item["fingerprint"], item["status"]) for item in before["items"]],
            [(item["fingerprint"], item["status"]) for item in after["items"]],
        )


if __name__ == "__main__":
    unittest.main()
