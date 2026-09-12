"""Synthetic temporary-storage tests for stable user-ID wiring only."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import inspect
import unittest
from unittest.mock import patch

from app.services import user_manager
from app.services.user_identity import validate_user_id


class StableUserIdWiringTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.users_file = root / "users.json"
        self.patches = [
            patch.object(user_manager, "DATA_DIR", root),
            patch.object(user_manager, "USERS_DIR", root / "users"),
            patch.object(user_manager, "USERS_FILE", self.users_file),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def _legacy_user(username: str) -> dict[str, object]:
        salt, password_hash = user_manager.hash_password("1234")
        return {
            "username": username,
            "salt": salt,
            "password_hash": password_hash,
            "role": "user",
            "must_change_password": False,
            "created_at": "2026-01-01T00:00:00",
        }

    def _write_users(self, users: list[dict[str, object]]) -> None:
        # Direct synthetic fixture setup, never the production users file.
        import json

        self.users_file.write_text(json.dumps({"users": users}), encoding="utf-8")

    def test_new_users_receive_distinct_server_generated_ids(self):
        self.assertNotIn("id", inspect.signature(user_manager.create_new_user).parameters)
        self.assertNotIn("user_id", inspect.signature(user_manager.create_new_user).parameters)
        user_manager.create_new_user("synthetic-a", "1234")
        user_manager.create_new_user("synthetic-b", "5678")
        users = user_manager.load_users_db()["users"]
        ids = [validate_user_id(user["id"]) for user in users]
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)

    def test_delete_and_recreate_same_username_receives_new_id(self):
        user_manager.create_new_user("synthetic-user", "1234")
        first_id = user_manager.get_user_by_name("synthetic-user")["id"]
        user_manager.delete_user_account("synthetic-user")
        user_manager.create_new_user("synthetic-user", "1234")
        second_id = user_manager.get_user_by_name("synthetic-user")["id"]
        self.assertNotEqual(first_id, second_id)

    def test_mixed_legacy_and_new_users_remain_readable_without_backfill(self):
        legacy = self._legacy_user("synthetic-legacy")
        self._write_users([legacy])
        self.assertEqual(user_manager.get_user_by_name("synthetic-legacy")["username"], "synthetic-legacy")
        self.assertEqual(user_manager.authenticate_user("synthetic-legacy", "1234")["username"], "synthetic-legacy")
        user_manager.create_new_user("synthetic-new", "1234")
        users = user_manager.load_users_db()["users"]
        loaded_legacy = next(user for user in users if user["username"] == "synthetic-legacy")
        loaded_new = next(user for user in users if user["username"] == "synthetic-new")
        self.assertNotIn("id", loaded_legacy)
        validate_user_id(loaded_new["id"])

    def test_legacy_password_update_does_not_backfill_id(self):
        legacy = self._legacy_user("synthetic-legacy")
        self._write_users([legacy])
        user_manager.force_set_user_password("synthetic-legacy", "5678")
        updated = user_manager.get_user_by_name("synthetic-legacy")
        self.assertNotIn("id", updated)
        self.assertTrue(user_manager.verify_password("5678", updated["salt"], updated["password_hash"]))

    def test_valid_id_is_preserved_across_password_reset(self):
        user_manager.create_new_user("synthetic-user", "1234")
        original_id = user_manager.get_user_by_name("synthetic-user")["id"]
        user_manager.admin_reset_password_to_4digit("synthetic-user", "5678")
        self.assertEqual(user_manager.get_user_by_name("synthetic-user")["id"], original_id)

    def test_role_normalization_preserves_valid_id_and_does_not_backfill_legacy_id(self):
        valid_id = user_manager.generate_user_id()
        valid_user = {**self._legacy_user("synthetic-valid"), "id": valid_id, "role": "admin"}
        legacy_user = {**self._legacy_user("synthetic-legacy"), "role": "admin"}
        self._write_users([valid_user, legacy_user])
        with patch.dict("os.environ", {"DASHBOARD_USERNAME": "synthetic-valid", "DASHBOARD_PASSWORD": "1234"}, clear=False):
            user_manager.init_users_and_migration()
        users = user_manager.load_users_db()["users"]
        loaded_valid = next(user for user in users if user["username"] == "synthetic-valid")
        loaded_legacy = next(user for user in users if user["username"] == "synthetic-legacy")
        self.assertEqual(loaded_valid["id"], valid_id)
        self.assertEqual(loaded_valid["role"], "user")
        self.assertNotIn("id", loaded_legacy)
        self.assertEqual(loaded_legacy["role"], "user")

    def test_invalid_and_duplicate_ids_block_load_and_save_without_repair(self):
        self._write_users([{**self._legacy_user("synthetic-invalid"), "id": None}])
        with self.assertRaisesRegex(ValueError, "invalid user identity database"):
            user_manager.load_users_db()

        valid_id = user_manager.generate_user_id()
        duplicate_users = [
            {**self._legacy_user("synthetic-a"), "id": valid_id},
            {**self._legacy_user("synthetic-b"), "id": valid_id},
        ]
        self._write_users(duplicate_users)
        with self.assertRaisesRegex(ValueError, "duplicate stable user identity"):
            user_manager.load_users_db()
        self.users_file.unlink()
        user_manager.save_users_db({"users": [self._legacy_user("synthetic-good")]})
        before = self.users_file.read_text(encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid user identity database"):
            user_manager.save_users_db(
                {"users": [{**self._legacy_user("synthetic-malformed"), "id": None}]}
            )
        self.assertEqual(self.users_file.read_text(encoding="utf-8"), before)
        with self.assertRaisesRegex(ValueError, "duplicate stable user identity"):
            user_manager.save_users_db({"users": duplicate_users})
        self.assertEqual(self.users_file.read_text(encoding="utf-8"), before)

    def test_generated_collision_fails_closed_without_appending_user(self):
        existing_id = user_manager.generate_user_id()
        self._write_users([{**self._legacy_user("synthetic-existing"), "id": existing_id}])
        with patch.object(user_manager, "generate_user_id", return_value=existing_id):
            with self.assertRaisesRegex(ValueError, "unable to allocate stable user identity"):
                user_manager.create_new_user("synthetic-new", "1234")
        self.assertIsNone(user_manager.get_user_by_name("synthetic-new"))

    def test_fresh_bootstrap_creates_ids_but_existing_legacy_records_are_not_backfilled(self):
        with patch.dict("os.environ", {"DASHBOARD_USERNAME": "synthetic-default", "DASHBOARD_PASSWORD": "1234"}, clear=False):
            user_manager.init_users_and_migration()
        self.assertTrue(all("id" in user for user in user_manager.load_users_db()["users"]))

        legacy = self._legacy_user("synthetic-legacy")
        self._write_users([legacy])
        with patch.dict("os.environ", {"DASHBOARD_USERNAME": "synthetic-legacy", "DASHBOARD_PASSWORD": "1234"}, clear=False):
            user_manager.init_users_and_migration()
        loaded_legacy = user_manager.get_user_by_name("synthetic-legacy")
        self.assertNotIn("id", loaded_legacy)


if __name__ == "__main__":
    unittest.main()
