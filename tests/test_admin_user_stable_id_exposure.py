import asyncio
import copy
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.services import user_manager
from app.services.user_identity import generate_user_id
from tests.test_request_state_user_id import _import_main_without_loading_real_env, _request


class AdminUserStableIdExposureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _import_main_without_loading_real_env()

    def _admin_request(self):
        request = _request("/api/admin/users")
        request.state.username = "synthetic-admin"
        request.state.role = "admin"
        return request

    def test_list_users_projects_persisted_ids_without_sensitive_fields(self):
        admin_id = generate_user_id()
        user_id = generate_user_id()
        records = [
            {"id": admin_id, "username": "synthetic-admin", "role": "admin", "must_change_password": False,
             "created_at": "synthetic", "salt": "sentinel", "password_hash": "sentinel", "future_secret_field": "sentinel"},
            {"id": user_id, "username": "synthetic-user", "role": "user", "must_change_password": True,
             "created_at": "synthetic", "salt": "sentinel", "password_hash": "sentinel", "future_secret_field": "sentinel"},
        ]
        with patch.object(user_manager, "load_users_db", return_value={"users": records}):
            listed = user_manager.list_users()
        self.assertEqual([item["id"] for item in listed], [admin_id, user_id])
        self.assertEqual(listed[0]["id"], admin_id)
        for item in listed:
            self.assertNotIn("salt", item)
            self.assertNotIn("password_hash", item)
            self.assertNotIn("future_secret_field", item)

        with patch("app.services.user_manager.list_users", return_value=listed):
            response = asyncio.run(self.main.admin_list_users(self._admin_request()))
        self.assertEqual(response["users"], listed)

    def test_legacy_id_is_null_without_backfill_or_mutation(self):
        legacy = {"username": "synthetic-legacy", "role": "user", "salt": "sentinel", "password_hash": "sentinel"}
        before = copy.deepcopy(legacy)
        with patch.object(user_manager, "load_users_db", return_value={"users": [legacy]}), \
             patch.object(user_manager, "generate_user_id", side_effect=AssertionError), \
             patch.object(user_manager, "save_users_db", side_effect=AssertionError):
            listed = user_manager.list_users()
        self.assertEqual(listed[0]["id"], None)
        self.assertEqual(legacy, before)

    def test_non_admin_and_unauthenticated_requests_cannot_get_user_list(self):
        non_admin = _request("/api/admin/users")
        non_admin.state.username = "synthetic-user"
        non_admin.state.role = "user"
        with self.assertRaises(HTTPException) as denied:
            asyncio.run(self.main.admin_list_users(non_admin))
        self.assertEqual(denied.exception.status_code, 403)

        unauthenticated = _request("/api/admin/users")
        response = asyncio.run(self.main.require_login(unauthenticated, lambda _request: None))
        self.assertEqual(response.status_code, 401)
        self.assertIsNone(unauthenticated.state.user_id)


if __name__ == "__main__":
    unittest.main()
