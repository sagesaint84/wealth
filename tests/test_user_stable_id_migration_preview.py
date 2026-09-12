"""Synthetic-only tests for the in-memory stable-ID migration preview."""

from __future__ import annotations

from copy import deepcopy
import unittest
import uuid
from unittest.mock import patch

from app.services import user_identity


class StableUserIdMigrationPreviewTests(unittest.TestCase):
    @staticmethod
    def _legacy(label: str) -> dict[str, object]:
        return {"username": f"synthetic-{label}"}

    @staticmethod
    def _valid(label: str, user_id: str | None = None) -> dict[str, object]:
        return {"username": f"synthetic-{label}", "id": user_id or user_identity.generate_user_id()}

    def assert_preview(self, records, **expected):
        self.assertEqual(user_identity.preview_user_id_migration(records), expected)

    def test_all_legacy_is_valid_and_write_ready_without_id_generation(self):
        records = [self._legacy("a"), self._legacy("b"), self._legacy("c")]
        with patch.object(user_identity, "generate_user_id", side_effect=AssertionError("must not generate")):
            self.assert_preview(
                records,
                total_users=3,
                legacy_missing_ids=3,
                valid_ids=0,
                invalid_ids=0,
                duplicate_ids=0,
                migration_required=True,
                validation_ok=True,
                write_ready=True,
            )

    def test_all_valid_and_empty_inputs_are_noop_not_write_ready(self):
        all_valid = [self._valid("a"), self._valid("b"), self._valid("c")]
        self.assert_preview(
            all_valid,
            total_users=3,
            legacy_missing_ids=0,
            valid_ids=3,
            invalid_ids=0,
            duplicate_ids=0,
            migration_required=False,
            validation_ok=True,
            write_ready=False,
        )
        self.assert_preview(
            [],
            total_users=0,
            legacy_missing_ids=0,
            valid_ids=0,
            invalid_ids=0,
            duplicate_ids=0,
            migration_required=False,
            validation_ok=True,
            write_ready=False,
        )

    def test_mixed_legacy_and_valid_is_write_ready(self):
        self.assert_preview(
            [self._legacy("a"), self._valid("b"), self._legacy("c"), self._valid("d")],
            total_users=4,
            legacy_missing_ids=2,
            valid_ids=2,
            invalid_ids=0,
            duplicate_ids=0,
            migration_required=True,
            validation_ok=True,
            write_ready=True,
        )

    def test_invalid_id_blocks_readiness_but_keeps_legacy_count(self):
        self.assert_preview(
            [self._valid("a"), self._legacy("b"), {"username": "synthetic-invalid", "id": None}],
            total_users=3,
            legacy_missing_ids=1,
            valid_ids=1,
            invalid_ids=1,
            duplicate_ids=0,
            migration_required=True,
            validation_ok=False,
            write_ready=False,
        )

    def test_duplicate_valid_ids_block_readiness_without_collapsing_records(self):
        duplicate = user_identity.generate_user_id()
        records = [self._valid("a", duplicate), self._valid("b", duplicate), self._legacy("c")]
        self.assert_preview(
            records,
            total_users=3,
            legacy_missing_ids=1,
            valid_ids=2,
            invalid_ids=0,
            duplicate_ids=1,
            migration_required=True,
            validation_ok=False,
            write_ready=False,
        )

    def test_missing_ids_are_not_duplicates_and_present_noncanonical_or_wrong_version_ids_are_invalid(self):
        valid = user_identity.generate_user_id()
        records = [
            self._legacy("a"),
            self._legacy("b"),
            {"username": "synthetic-uppercase", "id": valid.upper()},
            {"username": "synthetic-uuid1", "id": str(uuid.uuid1())},
            {"username": "synthetic-uuid3", "id": str(uuid.uuid3(uuid.NAMESPACE_DNS, "synthetic.example"))},
            {"username": "synthetic-uuid5", "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "synthetic.example"))},
        ]
        result = user_identity.preview_user_id_migration(records)
        self.assertEqual(result["legacy_missing_ids"], 2)
        self.assertEqual(result["duplicate_ids"], 0)
        self.assertEqual(result["invalid_ids"], 4)
        self.assertFalse(result["validation_ok"])
        self.assertFalse(result["write_ready"])

    def test_preview_is_deterministic_and_does_not_mutate_or_reorder_input(self):
        records = [self._valid("first"), self._legacy("second"), self._valid("third")]
        before = deepcopy(records)
        first = user_identity.preview_user_id_migration(records)
        second = user_identity.preview_user_id_migration(deepcopy(records))
        self.assertEqual(first, second)
        self.assertEqual(records, before)
        self.assertEqual([record["username"] for record in records], [record["username"] for record in before])

    def test_malformed_record_or_root_fails_closed_without_record_details(self):
        for records in (None, "not-records", {"users": []}, [{"username": "synthetic"}, None]):
            with self.subTest(root_type=type(records).__name__):
                with self.assertRaisesRegex(ValueError, "^invalid user migration preview input$"):
                    user_identity.preview_user_id_migration(records)


if __name__ == "__main__":
    unittest.main()
