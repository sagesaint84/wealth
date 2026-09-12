from __future__ import annotations

import copy
import math
import re
import unittest

from app.services.toss_wts_realized import (
    build_toss_wts_realized_fingerprint,
    map_toss_wts_profit_row,
    preview_toss_wts_realized_import,
)


class TossWtsRealizedPreviewTests(unittest.TestCase):
    @staticmethod
    def candidate(*, scope: str = "scope-a", date: str = "2026-01-02", code: str = "FAKE1") -> dict:
        return map_toss_wts_profit_row(
            {
                "date": date,
                "market_type": "us",
                "symbol": "FAKE",
                "product_code": code,
                "name": "가상종목",
                "quantity": 1.0,
                "profit_loss": {"krw": 321, "usd": 0.25},
                "profit_rate": 1.5,
                "buy_amount": {"krw": 1000, "usd": 1.0},
                "sell_amount": {"krw": 1321, "usd": 1.25},
            },
            account_name="가상계좌",
            source_account_scope=scope,
            owner="모두",
            profit_rate_basis="KRW",
            fetched_at="synthetic-fetch-time",
        )

    @staticmethod
    def persisted(candidate: dict) -> dict:
        record = copy.deepcopy(candidate)
        record["source_fingerprint"] = build_toss_wts_realized_fingerprint(record)
        record["id"] = "synthetic-local-id"
        return record

    def preview(self, candidates, existing=(), scope="scope-a"):
        return preview_toss_wts_realized_import(candidates, existing, source_account_scope=scope)

    def test_fingerprint_format_determinism_and_numeric_canonicalization(self):
        candidate = self.candidate()
        first = build_toss_wts_realized_fingerprint(candidate)
        equivalent = copy.deepcopy(candidate)
        equivalent["source_meta"]["quantity"] = 1
        equivalent["source_meta"]["profit_loss"]["krw"] = 321.0
        equivalent["source_meta"]["buy_amount"]["usd"] = 1
        equivalent["source_meta"]["sell_amount"]["usd"] = 1.250
        self.assertEqual(first, build_toss_wts_realized_fingerprint(candidate))
        self.assertEqual(first, build_toss_wts_realized_fingerprint(equivalent))
        self.assertRegex(first, r"^toss-wts-realized:v1:[0-9a-f]{64}$")

    def test_zero_none_and_identity_fields_are_distinct(self):
        base = self.candidate()
        zero = copy.deepcopy(base)
        zero["source_meta"]["buy_amount"]["usd"] = 0.0
        negative_zero = copy.deepcopy(zero)
        negative_zero["source_meta"]["buy_amount"]["usd"] = -0.0
        none = copy.deepcopy(base)
        none["source_meta"]["buy_amount"]["usd"] = None
        self.assertEqual(build_toss_wts_realized_fingerprint(zero), build_toss_wts_realized_fingerprint(negative_zero))
        self.assertNotEqual(build_toss_wts_realized_fingerprint(zero), build_toss_wts_realized_fingerprint(none))
        for mutate in (
            lambda c: c.__setitem__("source_account_scope", "scope-b"),
            lambda c: c.__setitem__("date", "2026-01-03"),
            lambda c: c["source_meta"].__setitem__("market_type", "kr"),
            lambda c: c["source_meta"].__setitem__("product_code", "OTHER"),
            lambda c: c["source_meta"].__setitem__("quantity", 2),
            lambda c: c["source_meta"]["profit_loss"].__setitem__("krw", 322),
            lambda c: c["source_meta"]["buy_amount"].__setitem__("usd", 2),
            lambda c: c["source_meta"]["sell_amount"].__setitem__("krw", 1322),
        ):
            changed = copy.deepcopy(base)
            mutate(changed)
            self.assertNotEqual(build_toss_wts_realized_fingerprint(base), build_toss_wts_realized_fingerprint(changed))

    def test_display_metadata_is_excluded_and_input_is_not_mutated(self):
        base = self.candidate()
        changed = copy.deepcopy(base)
        changed.update({"name": "다른 표시명", "memo": "memo", "account_name": "다른 계좌"})
        changed["source_meta"].update({"symbol": "OTHER", "profit_rate": 99, "profit_rate_basis": "USD", "fetched_at": "other-fetch"})
        before = copy.deepcopy(base)
        self.assertEqual(build_toss_wts_realized_fingerprint(base), build_toss_wts_realized_fingerprint(changed))
        self.assertEqual(base, before)

    def test_invalid_financial_values_are_rejected_without_payload_messages(self):
        for value in ("1", True, math.nan, math.inf, -math.inf):
            candidate = self.candidate()
            candidate["source_meta"]["quantity"] = value
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(ValueError, "source_meta.quantity") as error:
                    build_toss_wts_realized_fingerprint(candidate)
                self.assertNotIn("FAKE1", str(error.exception))

    def test_first_import_and_duplicate_multiplicity_are_multiset_safe(self):
        first = self.candidate()
        duplicate = copy.deepcopy(first)
        duplicate["name"] = "다른 표시명"
        duplicate["source_meta"]["profit_rate"] = 4.0
        result = self.preview([first, duplicate])
        self.assertEqual((result["fetched"], result["new"], result["already_imported"], result["ambiguous"], result["invalid"]), (2, 2, 0, 0, 0))
        self.assertEqual(result["new_indices"], [0, 1])
        self.assertTrue(result["write_ready"])

    def test_identical_second_import_and_existing_surplus_are_non_destructive(self):
        candidate = self.candidate()
        existing = [self.persisted(candidate), self.persisted(candidate)]
        result = self.preview([candidate], existing)
        self.assertEqual((result["new"], result["already_imported"], result["existing_surplus"]), (0, 1, 1))
        self.assertFalse(result["write_ready"])
        self.assertNotIn("delete_indices", result)

    def test_extended_range_and_exact_duplicate_growth(self):
        a, b = self.candidate(code="A"), self.candidate(code="B")
        c, d = self.candidate(code="C"), self.candidate(code="D")
        extended = self.preview([a, b, c, d], [self.persisted(a), self.persisted(b)])
        self.assertEqual((extended["new"], extended["already_imported"], extended["ambiguous"]), (2, 2, 0))
        duplicate_growth = self.preview([a, copy.deepcopy(a)], [self.persisted(a)])
        self.assertEqual((duplicate_growth["new"], duplicate_growth["already_imported"], duplicate_growth["ambiguous"]), (1, 1, 0))

    def test_historical_correction_is_ambiguous_but_first_import_is_not(self):
        existing_candidate = self.candidate()
        changed = copy.deepcopy(existing_candidate)
        changed["source_meta"]["sell_amount"]["krw"] = 1999
        first_import = self.preview([existing_candidate, changed])
        self.assertEqual((first_import["new"], first_import["ambiguous"]), (2, 0))
        correction = self.preview([changed], [self.persisted(existing_candidate)])
        self.assertEqual((correction["new"], correction["already_imported"], correction["ambiguous"]), (0, 0, 1))
        mixed = self.preview([existing_candidate, changed], [self.persisted(existing_candidate)])
        self.assertEqual((mixed["new"], mixed["already_imported"], mixed["ambiguous"]), (0, 1, 1))
        self.assertFalse(mixed["write_ready"])

    def test_manual_legacy_spreadsheet_and_other_scope_are_ignored(self):
        candidate = self.candidate()
        ignored = [
            {"source": "manual", "broker": "토스증권", "source_account_scope": "scope-a"},
            {"source": "spreadsheet", "source_account_scope": "scope-a"},
            {"date": candidate["date"], "code": candidate["code"]},
            self.persisted(self.candidate(scope="scope-b")),
        ]
        result = self.preview([candidate], ignored)
        self.assertEqual((result["new"], result["already_imported"], result["manual_affected"]), (1, 0, 0))
        self.assertTrue(result["write_ready"])

    def test_invalid_scope_and_existing_unresolved_block_without_mutation(self):
        candidate = self.candidate()
        wrong_scope = self.candidate(scope="scope-b")
        unresolved = copy.deepcopy(candidate)
        unresolved["source_fingerprint"] = "toss-wts-realized:v2:" + "0" * 64
        candidates = [candidate, wrong_scope]
        existing = [unresolved]
        before_candidates, before_existing = copy.deepcopy(candidates), copy.deepcopy(existing)
        result = self.preview(candidates, existing)
        self.assertEqual(result["invalid_indices"], [1])
        self.assertEqual(result["existing_unresolved_indices"], [0])
        self.assertFalse(result["write_ready"])
        self.assertEqual(candidates, before_candidates)
        self.assertEqual(existing, before_existing)

    def test_malformed_candidates_are_invalid_and_block_the_entire_batch(self):
        valid = self.candidate()
        missing_source = copy.deepcopy(valid)
        missing_source.pop("source")
        malformed_meta = copy.deepcopy(valid)
        malformed_meta["source_meta"] = []
        invalid_numeric = copy.deepcopy(valid)
        invalid_numeric["source_meta"]["quantity"] = "1"
        result = self.preview([valid, missing_source, malformed_meta, invalid_numeric])
        self.assertEqual(result["new_indices"], [0])
        self.assertEqual(result["invalid_indices"], [1, 2, 3])
        self.assertEqual(result["invalid"], 3)
        self.assertFalse(result["write_ready"])

    def test_empty_fetch_is_non_destructive_and_preview_exposes_only_indices_counts_hashes(self):
        result = self.preview([], [self.persisted(self.candidate())])
        self.assertEqual((result["fetched"], result["new"], result["already_imported"]), (0, 0, 0))
        self.assertFalse(result["write_ready"])
        self.assertEqual(result["existing_surplus"], 1)
        self.assertIn("fingerprints_by_index", result)
        self.assertNotIn("candidates", result)
        self.assertNotIn("existing_records", result)


if __name__ == "__main__":
    unittest.main()
