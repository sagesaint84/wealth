from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

from regression_support import import_main_without_loading_real_env


main = import_main_without_loading_real_env()
USERNAME = "backup_test_user"
MAX_BACKUP_BYTES = 16 * 1024 * 1024  # Existing IPO upload ceiling used for the safety check.


class BackupRestoreSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.user_dir = self.root / USERNAME
        self.user_dir.mkdir()
        self.original_serializer = main._serializer
        main._serializer = URLSafeTimedSerializer("backup-safety-test-only")
        self.addCleanup(setattr, main, "_serializer", self.original_serializer)
        self.user_root_patch = patch("app.services.user_manager.USERS_DIR", self.root)
        self.user_root_patch.start()
        self.addCleanup(self.user_root_patch.stop)
        self.lookup_patch = patch(
            "app.services.user_manager.get_user_by_name",
            return_value={"username": USERNAME, "role": "user", "must_change_password": False},
        )
        self.lookup_patch.start()
        self.addCleanup(self.lookup_patch.stop)
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        token = main._serializer.dumps({"user": USERNAME, "role": "user"})
        self.headers = {"Cookie": f"{main.COOKIE_NAME}={token}"}

    def post_backup(self, payload: bytes):
        return self.client.post(
            "/api/import-backup",
            headers=self.headers,
            files={"file": ("synthetic.json", payload, "application/json")},
        )

    def test_middle_write_failure_leaves_all_original_files_unchanged(self) -> None:
        originals = {
            "portfolio.json": {"settings": {}, "accounts": [], "holdings": [], "marker": "old"},
            "asset_records.json": {"records": [], "marker": "old"},
            "dividend_records.json": {"records": [], "marker": "old"},
            "realized_pnl_records.json": {"records": [], "marker": "old"},
            "ledger.json": {"version": "1.0", "transactions": [], "marker": "old"},
            "openapi_config.json": {"dart": {"api_key": "synthetic-unchanged"}},
        }
        before = {}
        for name, value in originals.items():
            path = self.user_dir / name
            path.write_text(json.dumps(value), encoding="utf-8")
            before[name] = path.read_bytes()
        bundle = {
            "version": "2.2",
            "backup_policy": "general_data_only",
            "portfolio": {"settings": {}, "accounts": [], "holdings": [], "marker": "new"},
            "asset_records": {"records": [], "marker": "new"},
            "dividend_records": [],
            "realized_pnl_records": [],
            "ledger": {"version": "1.0", "transactions": [], "marker": "new"},
        }
        with patch("app.services.asset_records.write_asset_records", side_effect=OSError("synthetic middle-write failure")):
            response = self.post_backup(json.dumps(bundle).encode("utf-8"))
        self.assertGreaterEqual(response.status_code, 400)
        for name, original in before.items():
            self.assertEqual((self.user_dir / name).read_bytes(), original, name)

    def test_oversized_backup_is_rejected_before_writing(self) -> None:
        oversized = json.dumps({"portfolio": {"marker": "x" * MAX_BACKUP_BYTES}}).encode("utf-8")
        with patch("app.services.portfolio.write_portfolio") as writer:
            response = self.post_backup(oversized)
        self.assertEqual(response.status_code, 413)
        writer.assert_not_called()

    def test_oversized_upload_read_is_bounded(self) -> None:
        from app.services.backup_restore import MAX_BACKUP_UPLOAD_BYTES

        file = unittest.mock.Mock()
        file.read = AsyncMock(return_value=b"x" * (MAX_BACKUP_UPLOAD_BYTES + 1))
        with patch.object(main, "get_current_username", return_value=USERNAME):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(main.import_backup(object(), file=file))
        self.assertEqual(caught.exception.status_code, 413)
        file.read.assert_awaited_once_with(MAX_BACKUP_UPLOAD_BYTES + 1)

    def test_backup_at_size_limit_is_accepted(self) -> None:
        prefix = b'{"portfolio":{"marker":"'
        suffix = b'"}}'
        payload = prefix + b'x' * (MAX_BACKUP_BYTES - len(prefix) - len(suffix)) + suffix
        self.assertEqual(len(payload), MAX_BACKUP_BYTES)
        with patch("app.services.portfolio.write_portfolio") as writer:
            response = self.post_backup(payload)
        self.assertEqual(response.status_code, 200)
        writer.assert_called_once()

    def test_malformed_empty_and_unauthenticated_backups_do_not_write(self) -> None:
        for payload in (b"", b"{bad-json", b"[]", b"{}", b'{"portfolio":{"marker":"new"},"asset_records":[1]}'):
            with self.subTest(payload=payload):
                response = self.post_backup(payload)
                self.assertEqual(response.status_code, 400)
        response = self.client.post(
            "/api/import-backup",
            files={"file": ("synthetic.json", b'{"portfolio":{"marker":"new"}}', "application/json")},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(list(self.user_dir.iterdir()), [])

    def test_success_restores_all_general_stores_without_secrets_or_temp_files(self) -> None:
        secret_path = self.user_dir / "openapi_config.json"
        secret_path.write_text('{"dart":{"api_key":"synthetic-unchanged"}}', encoding="utf-8")
        other_dir = self.root / "other_user"
        other_dir.mkdir()
        other_path = other_dir / "portfolio.json"
        other_path.write_text('{"marker":"other-unchanged"}', encoding="utf-8")
        bundle = {
            "version": "2.2",
            "backup_policy": "general_data_only",
            "portfolio": {"settings": {}, "accounts": [], "holdings": [], "marker": "new"},
            "asset_records": {"records": [], "marker": "new"},
            "dividend_records": [{"marker": "new"}],
            "realized_pnl_records": [{"marker": "new"}],
            "ledger": {"transactions": [], "marker": "new"},
            "openapi_config": {"dart": {"api_key": "synthetic-must-not-restore"}},
        }
        response = self.post_backup(json.dumps(bundle).encode("utf-8"))
        self.assertEqual(response.status_code, 200)
        for filename in ("portfolio.json", "asset_records.json", "ledger.json"):
            self.assertEqual(json.loads((self.user_dir / filename).read_text(encoding="utf-8"))["marker"], "new")
        for filename in ("dividend_records.json", "realized_pnl_records.json"):
            self.assertEqual(json.loads((self.user_dir / filename).read_text(encoding="utf-8"))["records"][0]["marker"], "new")
        self.assertIn("synthetic-unchanged", secret_path.read_text(encoding="utf-8"))
        self.assertEqual(other_path.read_text(encoding="utf-8"), '{"marker":"other-unchanged"}')
        self.assertFalse(list(self.user_dir.glob(".backup-restore-*")))
        self.assertFalse(list(self.user_dir.glob("*.tmp")))

    def test_failure_after_partial_third_file_write_rolls_back_all_stores(self) -> None:
        names = ("portfolio.json", "asset_records.json", "dividend_records.json", "realized_pnl_records.json", "ledger.json")
        originals = {}
        for name in names:
            path = self.user_dir / name
            path.write_text('{"marker":"old"}', encoding="utf-8")
            originals[name] = path.read_bytes()
        bundle = {
            "portfolio": {"settings": {}, "accounts": [], "holdings": [], "marker": "new"},
            "asset_records": {"records": [], "marker": "new"},
            "dividend_records": [{"marker": "new"}],
            "realized_pnl_records": [{"marker": "new"}],
            "ledger": {"transactions": [], "marker": "new"},
        }

        def partial_write(*_args, **_kwargs):
            (self.user_dir / "dividend_records.json").write_text("partial", encoding="utf-8")
            raise OSError("synthetic failure after truncation")

        with patch("app.services.dividend_records.write_dividend_records", side_effect=partial_write):
            response = self.post_backup(json.dumps(bundle).encode("utf-8"))
        self.assertGreaterEqual(response.status_code, 400)
        for name, original in originals.items():
            self.assertEqual((self.user_dir / name).read_bytes(), original, name)
        self.assertFalse(list(self.user_dir.glob(".backup-restore-*")))
        self.assertFalse(list(self.user_dir.glob("*.tmp")))

    def test_failure_removes_newly_created_store_and_temp_artifacts(self) -> None:
        bundle = {
            "portfolio": {"settings": {}, "accounts": [], "holdings": [], "marker": "new"},
            "asset_records": {"records": [], "marker": "new"},
        }
        with patch("app.services.asset_records.write_asset_records", side_effect=OSError("synthetic failure")):
            response = self.post_backup(json.dumps(bundle).encode("utf-8"))
        self.assertGreaterEqual(response.status_code, 400)
        self.assertFalse((self.user_dir / "portfolio.json").exists())
        self.assertFalse((self.user_dir / "asset_records.json").exists())
        self.assertFalse(list(self.user_dir.glob(".backup-restore-*")))
        self.assertFalse(list(self.user_dir.glob("*.tmp")))

    def test_legacy_backup_keeps_openapi_import_compatibility(self) -> None:
        bundle = {
            "portfolio": {"settings": {}, "accounts": [], "holdings": []},
            "openapi_config": {"dart": {"api_key": "synthetic-legacy"}},
        }
        with patch("app.services.user_openapi.save_user_openapi_config") as save_config:
            response = self.post_backup(json.dumps(bundle).encode("utf-8"))
        self.assertEqual(response.status_code, 200)
        save_config.assert_called_once_with(username=USERNAME, update_data=bundle["openapi_config"])

    def test_second_restore_cannot_enter_during_first_restore(self) -> None:
        from app.services.backup_restore import restore_general_data
        from app.services.settings import SettingsError

        first_entered = threading.Event()
        release_first = threading.Event()
        errors: list[Exception] = []
        calls: list[str] = []

        def blocked_writer(*_args, **_kwargs):
            calls.append("first")
            first_entered.set()
            if not release_first.wait(5):
                raise TimeoutError("synthetic test coordination timeout")

        def first_restore():
            try:
                restore_general_data(USERNAME, {"portfolio": {"marker": "first"}})
            except Exception as exc:
                errors.append(exc)

        with patch("app.services.portfolio.write_portfolio", side_effect=blocked_writer):
            thread = threading.Thread(target=first_restore)
            thread.start()
            try:
                self.assertTrue(first_entered.wait(5))
                with self.assertRaises(SettingsError):
                    restore_general_data(USERNAME, {"portfolio": {"marker": "second"}})
            finally:
                release_first.set()
                thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(calls, ["first"])

    def test_concurrent_normal_portfolio_write_survives_restore_rollback(self) -> None:
        from app.services.backup_restore import restore_general_data
        from app.services.portfolio import write_portfolio

        portfolio = self.user_dir / "portfolio.json"
        portfolio.write_text('{"marker":"original"}', encoding="utf-8")
        entered_second_write = threading.Event()
        release_second_write = threading.Event()
        errors: list[Exception] = []

        def fail_second_write(*_args, **_kwargs):
            entered_second_write.set()
            if not release_second_write.wait(5):
                raise TimeoutError("synthetic test coordination timeout")
            raise OSError("synthetic second-write failure")

        def restore():
            try:
                restore_general_data(USERNAME, {
                    "portfolio": {"settings": {}, "accounts": [], "holdings": [], "marker": "restore"},
                    "asset_records": {"records": [], "marker": "restore"},
                })
            except Exception as exc:
                errors.append(exc)

        with patch("app.services.asset_records.write_asset_records", side_effect=fail_second_write):
            thread = threading.Thread(target=restore)
            thread.start()
            try:
                self.assertTrue(entered_second_write.wait(5))
                write_portfolio(
                    {"settings": {}, "accounts": [], "holdings": [], "marker": "normal-write"},
                    username=USERNAME,
                )
            finally:
                release_second_write.set()
                thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertEqual(json.loads(portfolio.read_text(encoding="utf-8"))["marker"], "normal-write")


if __name__ == "__main__":
    unittest.main()
