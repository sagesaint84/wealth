"""Synthetic TEMP-file tests for explicit stable user-ID migration only."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
from unittest.mock import patch

from app.services.user_identity import generate_user_id, preview_user_id_migration, validate_user_id
from app.services.user_identity_migration import (
    UserIdMigrationError,
    build_user_id_migration,
    execute_user_id_migration_file,
)


class StableUserIdMigrationExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "synthetic-users.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def legacy(label: str, **extra):
        return {"username": f"synthetic-{label}", "salt": "synthetic-salt", "password_hash": "synthetic-hash", **extra}

    @staticmethod
    def valid(label: str, user_id: str | None = None, **extra):
        return {"username": f"synthetic-{label}", "id": user_id or generate_user_id(), **extra}

    def write_root(self, root):
        self.path.write_text(json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_root(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def execute(self, root, expected=None):
        self.write_root(root)
        preview = preview_user_id_migration(root["users"])
        return execute_user_id_migration_file(self.path, expected_preview=expected or preview)

    def test_all_legacy_migrates_only_ids_and_preserves_records(self):
        records = [self.legacy("a", future_field={"marker": 1}), self.legacy("b"), self.legacy("c")]
        before = deepcopy(records)
        result = self.execute({"users": records, "synthetic_meta": {"keep": True}})
        root = self.read_root()
        self.assertEqual(result, {
            "total_users": 3, "migrated_users": 3, "preserved_valid_ids": 0,
            "post_validation_ok": True, "write_performed": True, "precondition_match": True,
        })
        self.assertEqual(records, before)
        self.assertEqual(root["synthetic_meta"], {"keep": True})
        self.assertEqual([user["username"] for user in root["users"]], [user["username"] for user in before])
        for old, new in zip(before, root["users"]):
            self.assertEqual({key: value for key, value in new.items() if key != "id"}, old)
            validate_user_id(new["id"])
        self.assertEqual(preview_user_id_migration(root["users"])["valid_ids"], 3)

    def test_mixed_records_preserve_valid_id_and_order(self):
        existing_id = generate_user_id()
        root = {"users": [self.valid("first", existing_id), self.legacy("second"), self.legacy("third")]}
        self.execute(root)
        users = self.read_root()["users"]
        self.assertEqual([user["username"] for user in users], ["synthetic-first", "synthetic-second", "synthetic-third"])
        self.assertEqual(users[0]["id"], existing_id)
        self.assertEqual(len({user["id"] for user in users}), 3)

    def test_invalid_or_duplicate_precondition_blocks_before_generation_and_write(self):
        duplicate = generate_user_id()
        for root in (
            {"users": [self.legacy("legacy"), {**self.legacy("invalid"), "id": None}]},
            {"users": [self.legacy("legacy"), self.valid("a", duplicate), self.valid("b", duplicate)]},
        ):
            with self.subTest(root=root["users"][1].get("id") is None):
                self.write_root(root)
                before = self.path.read_bytes()
                with patch("app.services.user_identity_migration.generate_user_id", side_effect=AssertionError("no generation")):
                    with self.assertRaises(UserIdMigrationError):
                        execute_user_id_migration_file(self.path, expected_preview=preview_user_id_migration(root["users"]))
                self.assertEqual(self.path.read_bytes(), before)

    def test_builder_rejects_invalid_factory_and_collisions_without_mutating_input(self):
        existing = generate_user_id()
        records = [self.valid("valid", existing), self.legacy("legacy-a"), self.legacy("legacy-b")]
        before = deepcopy(records)
        for factory in (lambda: "invalid", lambda: existing, lambda: generate_user_id()):
            if factory is not None:
                pass
        with self.assertRaises(UserIdMigrationError):
            build_user_id_migration(records, id_factory=lambda: "invalid")
        self.assertEqual(records, before)
        with self.assertRaises(UserIdMigrationError):
            build_user_id_migration(records, id_factory=lambda: existing)
        self.assertEqual(records, before)
        new_id = generate_user_id()
        values = iter((new_id, new_id))
        with self.assertRaises(UserIdMigrationError):
            build_user_id_migration(records, id_factory=lambda: next(values))
        self.assertEqual(records, before)
        calls = iter((generate_user_id(), RuntimeError("synthetic factory failure")))
        def fail_midway():
            value = next(calls)
            if isinstance(value, Exception):
                raise value
            return value
        with self.assertRaises(UserIdMigrationError):
            build_user_id_migration(records, id_factory=fail_midway)
        self.assertEqual(records, before)

    def test_stale_or_malformed_expected_preview_blocks_before_write(self):
        root = {"users": [self.legacy("a")]}
        self.write_root(root)
        before = self.path.read_bytes()
        stale = preview_user_id_migration(root["users"])
        stale["legacy_missing_ids"] = 0
        with patch("app.services.user_identity_migration.generate_user_id", side_effect=AssertionError("no generation")):
            with self.assertRaises(UserIdMigrationError):
                execute_user_id_migration_file(self.path, expected_preview=stale)
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(UserIdMigrationError):
            execute_user_id_migration_file(self.path, expected_preview={})
        self.assertEqual(self.path.read_bytes(), before)

    def test_all_valid_and_empty_are_noop_byte_identical(self):
        for root in ({"users": [self.valid("a"), self.valid("b")]}, {"users": []}):
            with self.subTest(total=len(root["users"])):
                self.write_root(root)
                before = self.path.read_bytes()
                result = execute_user_id_migration_file(
                    self.path, expected_preview=preview_user_id_migration(root["users"])
                )
                self.assertFalse(result["write_performed"])
                self.assertEqual(self.path.read_bytes(), before)

    def test_replace_failure_preserves_original_and_cleans_temp_file(self):
        root = {"users": [self.legacy("a")]}
        self.write_root(root)
        before = self.path.read_bytes()
        with patch("app.services.user_identity_migration.os.replace", side_effect=OSError("synthetic")):
            with self.assertRaises(UserIdMigrationError):
                execute_user_id_migration_file(self.path, expected_preview=preview_user_id_migration(root["users"]))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob(f".{self.path.name}.*.tmp")), [])

    def test_report_is_privacy_safe_and_malformed_roots_fail(self):
        root = {"users": [self.legacy("secret", password_hash="secret-hash")]} 
        report = self.execute(root)
        serialized = json.dumps(report, ensure_ascii=False)
        for forbidden in ("synthetic-secret", "secret-hash", "username", "password_hash"):
            self.assertNotIn(forbidden, serialized)
        for invalid_root in ([], {"missing": []}, {"users": {}}, "not-json"):
            self.path.write_text(invalid_root if isinstance(invalid_root, str) else json.dumps(invalid_root), encoding="utf-8")
            with self.assertRaises(UserIdMigrationError):
                execute_user_id_migration_file(self.path, expected_preview={})


if __name__ == "__main__":
    unittest.main()
