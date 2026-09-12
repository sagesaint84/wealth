"""Synthetic-only tests for pure stable Wealth user-ID helpers."""

from __future__ import annotations

from copy import deepcopy
import inspect
import unittest
import uuid

from app.services.user_identity import (
    INVALID_ID,
    LEGACY_MISSING_ID,
    VALID_ID,
    classify_user_id_state,
    find_duplicate_user_ids,
    generate_user_id,
    inspect_user_id_states,
    validate_user_id,
)


class StableUserIdTests(unittest.TestCase):
    def test_generator_returns_distinct_canonical_uuid4_strings_without_inputs(self):
        self.assertEqual(list(inspect.signature(generate_user_id).parameters), [])
        first = generate_user_id()
        second = generate_user_id()
        self.assertIsInstance(first, str)
        self.assertNotEqual(first, second)
        parsed = uuid.UUID(first)
        self.assertEqual(first, str(parsed))
        self.assertEqual(parsed.version, 4)
        self.assertEqual(validate_user_id(first), first)

    def test_validator_rejects_noncanonical_and_wrong_version_values(self):
        valid = generate_user_id()
        invalid_values = [
            valid.upper(),
            valid.replace("-", ""),
            f" {valid} ",
            str(uuid.uuid1()),
            str(uuid.uuid3(uuid.NAMESPACE_DNS, "synthetic.example")),
            str(uuid.uuid5(uuid.NAMESPACE_DNS, "synthetic.example")),
            "",
            "not-a-uuid",
            None,
            True,
            1,
            1.0,
            b"synthetic",
            [],
            {},
        ]
        for value in invalid_values:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):
                    validate_user_id(value)

    def test_classifier_distinguishes_absent_from_present_invalid_id_without_mutation(self):
        valid_record = {"username": "synthetic-a", "id": generate_user_id()}
        cases = [
            ({"username": "synthetic-legacy"}, LEGACY_MISSING_ID),
            (valid_record, VALID_ID),
            ({"username": "synthetic-none", "id": None}, INVALID_ID),
            ({"username": "synthetic-empty", "id": ""}, INVALID_ID),
            ({"username": "synthetic-upper", "id": valid_record["id"].upper()}, INVALID_ID),
        ]
        for record, expected in cases:
            with self.subTest(expected=expected):
                before = deepcopy(record)
                self.assertEqual(classify_user_id_state(record), expected)
                self.assertEqual(record, before)

    def test_duplicate_inspection_counts_valid_duplicates_without_treating_missing_or_invalid_as_ids(self):
        first = generate_user_id()
        second = generate_user_id()
        records = [
            {"username": "synthetic-a", "id": first},
            {"username": "synthetic-b", "id": second},
            {"username": "synthetic-c", "id": first},
            {"username": "synthetic-legacy-a"},
            {"username": "synthetic-legacy-b"},
            {"username": "synthetic-invalid", "id": "not-a-uuid"},
        ]
        before = deepcopy(records)
        self.assertEqual(find_duplicate_user_ids(records), frozenset({first}))
        self.assertEqual(
            inspect_user_id_states(records),
            {
                "legacy_missing_ids": 2,
                "valid_ids": 3,
                "invalid_ids": 1,
                "duplicate_ids": 1,
            },
        )
        self.assertEqual(records, before)

    def test_same_username_is_not_an_identity_input(self):
        records = [
            {"username": "synthetic-same", "id": generate_user_id()},
            {"username": "synthetic-same", "id": generate_user_id()},
        ]
        self.assertEqual(find_duplicate_user_ids(records), frozenset())
        self.assertEqual(inspect_user_id_states(records)["duplicate_ids"], 0)


if __name__ == "__main__":
    unittest.main()
