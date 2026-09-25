import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app, _serializer, COOKIE_NAME
from app.services import kftc_openbanking_config as cfg
from app.services import kftc_openbanking_service as service
from app.services import kftc_openbanking_storage as storage


class KftcOpenBankingBalanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        # Isolate system and user data directories
        self.patch_env = patch.dict("os.environ", {"WEALTH_DATA_DIR": self.tmp.name})
        self.patch_env.start()
        self.addCleanup(self.patch_env.stop)

        self.patch_storage_user_dir = patch(
            "app.services.kftc_openbanking_storage.get_user_data_dir",
            side_effect=lambda u: Path(self.tmp.name) / "users" / (u or "default"),
        )
        self.patch_storage_user_dir.start()
        self.addCleanup(self.patch_storage_user_dir.stop)

        self.patch_cfg_user_dir = patch(
            "app.services.kftc_openbanking_config.get_user_data_dir",
            side_effect=lambda u: Path(self.tmp.name) / "users" / (u or "default"),
        )
        self.patch_cfg_user_dir.start()
        self.addCleanup(self.patch_cfg_user_dir.stop)

    def _make_client(self, username: str | None = None, role: str = "user") -> TestClient:
        client = TestClient(app)
        if username:
            client.cookies.set(COOKIE_NAME, _serializer.dumps({"user": username, "role": role}))
            user_patch = patch(
                "app.services.user_manager.get_user_by_name",
                return_value={"username": username, "id": f"id-{username}", "role": role},
            )
            user_patch.start()
            self.addCleanup(user_patch.stop)
        return client

    def _setup_alice_account(self, scope: str = "login inquiry", client_use_code: str = "B123456789"):
        # Setup config
        cfg.patch_user_kftc_config(
            "alice",
            {
                "enabled": True,
                "environment": "test",
                "client_id": "alice-cid",
                "client_secret": "alice-sec",
                "client_use_code": client_use_code,
            },
        )
        # Setup tokens
        storage.save_user_tokens(
            "alice",
            access_token="alice-access-token",
            refresh_token="alice-refresh-token",
            user_seq_no="alice-seq-1",
            scope=scope,
            expires_in=7776000,
        )
        # Setup accounts
        accounts = [
            {
                "provider_account_id": "kftc-acc-alice-1",
                "fintech_use_num": "120230226588951223594984",
                "bank_code_std": "092",
                "bank_name": "토스뱅크",
                "account_num_masked": "1000-0000-****",
                "account_alias": "토스생활비",
                "account_type": "1",
                "product_name": "토스뱅크통장",
                "inquiry_agree_yn": "Y",
            }
        ]
        storage.save_user_kftc_accounts("alice", accounts)

    async def test_bank_tran_id_generation_rules(self):
        # 10-character client_use_code -> prefix 11 chars ('B123456789' + 'U') + 9 suffix chars = 20
        tran_id_10 = service.generate_bank_tran_id("B123456789", tran_date="20260925")
        self.assertEqual(len(tran_id_10), 20)
        self.assertTrue(tran_id_10.startswith("B123456789U"))

        # Non-10-character client_use_code fails closed
        with self.assertRaises(service.KftcServiceError) as ctx:
            service.generate_bank_tran_id("B12345678")
        self.assertEqual(ctx.exception.code, "KFTC_CLIENT_USE_CODE_INVALID")

        with self.assertRaises(service.KftcServiceError) as ctx:
            service.generate_bank_tran_id("B12345678901")
        self.assertEqual(ctx.exception.code, "KFTC_CLIENT_USE_CODE_INVALID")

        # Missing client_use_code fails closed
        with self.assertRaises(service.KftcServiceError) as ctx:
            service.generate_bank_tran_id("")
        self.assertEqual(ctx.exception.code, "KFTC_CLIENT_USE_CODE_REQUIRED")

        # Monotonically increasing base36 suffix
        self.assertEqual(tran_id_10, "B123456789U000000001")
        tran_id_2 = service.generate_bank_tran_id("B123456789", tran_date="20260925")
        self.assertEqual(tran_id_2, "B123456789U000000002")

    async def test_bank_tran_id_uniqueness_and_reset(self):
        # 1. 1000 sequential calls on same day are strictly unique and strictly 20 chars
        ids = [service.generate_bank_tran_id("A123456789", tran_date="20260925") for _ in range(1000)]
        self.assertEqual(len(set(ids)), 1000)
        for tid in ids:
            self.assertEqual(len(tid), 20)
            self.assertTrue(tid.startswith("A123456789U"))
            suffix = tid[11:]
            self.assertEqual(len(suffix), 9)
            self.assertTrue(suffix.isalnum())

        # 2. Process state reload simulation (reads existing file directly)
        next_id = service.generate_bank_tran_id("A123456789", tran_date="20260925")
        self.assertEqual(next_id, f"A123456789U{storage.int_to_base36_9(1001)}")

        # 3. Next calendar day resets sequence to 1
        next_day_id = service.generate_bank_tran_id("A123456789", tran_date="20260926")
        self.assertEqual(next_day_id, "A123456789U000000001")

        # 4. Independent client_use_codes maintain independent sequences
        code_b_id = service.generate_bank_tran_id("B987654321", tran_date="20260925")
        self.assertEqual(code_b_id, "B987654321U000000001")

    def test_bank_tran_sequence_store_corruption_fails_closed(self):
        # A. Corrupt JSON in sequence file
        seq_file = storage.get_bank_tran_sequence_file()
        seq_file.parent.mkdir(parents=True, exist_ok=True)
        seq_file.write_text("{invalid json content...", encoding="utf-8")

        with self.assertRaises(storage.KftcStorageError) as ctx:
            storage.next_bank_tran_sequence("A123456789", "20260925")
        self.assertEqual(str(ctx.exception), "BANK_TRAN_SEQUENCE_STORE_CORRUPT")
        # Ensure file was not overwritten with a new clean document
        self.assertEqual(seq_file.read_text(encoding="utf-8"), "{invalid json content...")

        # B. Malformed version
        seq_file.write_text(json.dumps({"version": 2, "entries": {}}), encoding="utf-8")
        with self.assertRaises(storage.KftcStorageError) as ctx:
            storage.next_bank_tran_sequence("A123456789", "20260925")
        self.assertEqual(str(ctx.exception), "BANK_TRAN_SEQUENCE_STORE_CORRUPT")

        # C. Malformed entries type
        seq_file.write_text(json.dumps({"version": 1, "entries": []}), encoding="utf-8")
        with self.assertRaises(storage.KftcStorageError) as ctx:
            storage.next_bank_tran_sequence("A123456789", "20260925")
        self.assertEqual(str(ctx.exception), "BANK_TRAN_SEQUENCE_STORE_CORRUPT")

    def test_bank_tran_sequence_malformed_entry_fails_closed(self):
        seq_file = storage.get_bank_tran_sequence_file()
        seq_file.parent.mkdir(parents=True, exist_ok=True)

        # 1. next_sequence is a string instead of int
        seq_file.write_text(
            json.dumps({"version": 1, "entries": {"A123456789": {"date": "20260925", "next_sequence": "abc"}}}),
            encoding="utf-8",
        )
        with self.assertRaises(storage.KftcStorageError) as ctx:
            storage.next_bank_tran_sequence("A123456789", "20260925")
        self.assertEqual(str(ctx.exception), "BANK_TRAN_SEQUENCE_STORE_CORRUPT")

        # 2. next_sequence is a boolean (which is a subclass of int in Python)
        seq_file.write_text(
            json.dumps({"version": 1, "entries": {"A123456789": {"date": "20260925", "next_sequence": True}}}),
            encoding="utf-8",
        )
        with self.assertRaises(storage.KftcStorageError) as ctx:
            storage.next_bank_tran_sequence("A123456789", "20260925")
        self.assertEqual(str(ctx.exception), "BANK_TRAN_SEQUENCE_STORE_CORRUPT")

        # 3. next_sequence < 1
        seq_file.write_text(
            json.dumps({"version": 1, "entries": {"A123456789": {"date": "20260925", "next_sequence": 0}}}),
            encoding="utf-8",
        )
        with self.assertRaises(storage.KftcStorageError) as ctx:
            storage.next_bank_tran_sequence("A123456789", "20260925")
        self.assertEqual(str(ctx.exception), "BANK_TRAN_SEQUENCE_STORE_CORRUPT")

        # 4. date is malformed
        seq_file.write_text(
            json.dumps({"version": 1, "entries": {"A123456789": {"date": "invalid", "next_sequence": 1}}}),
            encoding="utf-8",
        )
        with self.assertRaises(storage.KftcStorageError) as ctx:
            storage.next_bank_tran_sequence("A123456789", "20260925")
        self.assertEqual(str(ctx.exception), "BANK_TRAN_SEQUENCE_STORE_CORRUPT")

    def test_bank_tran_sequence_old_date_entry_resets_safely(self):
        seq_file = storage.get_bank_tran_sequence_file()
        seq_file.parent.mkdir(parents=True, exist_ok=True)

        # Yesterday's valid sequence at 500
        seq_file.write_text(
            json.dumps({"version": 1, "entries": {"A123456789": {"date": "20260924", "next_sequence": 500}}}),
            encoding="utf-8",
        )
        # Calling on new day resets to 1 and increments to 2
        seq1 = storage.next_bank_tran_sequence("A123456789", "20260925")
        self.assertEqual(seq1, 1)

        saved = json.loads(seq_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["entries"]["A123456789"]["date"], "20260925")
        self.assertEqual(saved["entries"]["A123456789"]["next_sequence"], 2)

    def test_secure_files_fsync_before_replace_and_retry(self):
        from unittest.mock import MagicMock
        from app.services.secure_files import atomic_write_private_json

        target_file = Path(self.tmp.name) / "test_secure.json"
        events = []

        # 1. Verify fsync is called before replace
        orig_fsync = os.fsync
        orig_replace = os.replace

        def mock_fsync(fd):
            events.append("fsync")
            return orig_fsync(fd)

        def mock_replace(src, dst):
            events.append("replace")
            return orig_replace(src, dst)

        with patch("os.fsync", side_effect=mock_fsync), patch("os.replace", side_effect=mock_replace):
            atomic_write_private_json(target_file, {"key": "val"})

        self.assertEqual(events, ["fsync", "replace"])
        self.assertTrue(target_file.exists())

        # 2. Windows replace retry on transient PermissionError
        call_count = 0
        def transient_replace(src, dst):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise PermissionError("WinError 5 Access is denied")
            return orig_replace(src, dst)

        with patch("os.name", "nt"), patch("os.replace", side_effect=transient_replace), patch("time.sleep", return_value=None):
            atomic_write_private_json(target_file, {"key": "retried_val"})
            self.assertEqual(call_count, 3)

        # 3. Windows replace retry exhaustion raises PermissionError
        with patch("os.name", "nt"), patch("os.replace", side_effect=PermissionError("Persistent WinError 5")), patch("time.sleep", return_value=None):
            with self.assertRaises(PermissionError):
                atomic_write_private_json(target_file, {"key": "fail_val"})

        # 4. Other OSError is raised immediately without retry
        generic_os_error_calls = 0
        def fail_os_error(src, dst):
            nonlocal generic_os_error_calls
            generic_os_error_calls += 1
            raise OSError("Disk failure")

        with patch("os.name", "nt"), patch("os.replace", side_effect=fail_os_error), patch("time.sleep", return_value=None):
            with self.assertRaises(OSError):
                atomic_write_private_json(target_file, {"key": "fail_os_val"})
            self.assertEqual(generic_os_error_calls, 1)

    def test_bank_tran_id_thread_safety(self):
        import concurrent.futures
        results = []

        def worker():
            return service.generate_bank_tran_id("C112233445", tran_date="20260925")

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker) for _ in range(200)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        self.assertEqual(len(results), 200)
        self.assertEqual(len(set(results)), 200)
        for tid in results:
            self.assertEqual(len(tid), 20)
            self.assertTrue(tid.startswith("C112233445U"))

    async def test_preview_balance_service_success(self):
        self._setup_alice_account()

        mock_balance_res = {
            "bank_name": "토스뱅크",
            "product_name": "토스뱅크통장",
            "account_num_masked": "1000-0000-****",
            "account_type": "1",
            "balance_amt": 550000,
            "available_amt": 500000,
            "account_issue_date": "20240101",
            "maturity_date": None,
            "last_tran_date": "20260924",
            "bank_rsp_code": "000",
            "rsp_code": "A0000",
        }

        with patch("app.services.kftc_openbanking_service.fetch_account_balance", new_callable=AsyncMock, return_value=mock_balance_res), \
             patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True):
            res = await service.preview_account_balance("alice", "kftc-acc-alice-1")
            self.assertEqual(res["provider_account_id"], "kftc-acc-alice-1")
            self.assertEqual(res["balance_amt"], 550000)
            self.assertEqual(res["available_amt"], 500000)
            self.assertEqual(res["account_type_label"], "수시입출금")
            self.assertIn("checked_at", res)

            # Strictly verify NO sensitive or internal tracking identifiers leaked
            for forbidden_key in ("fintech_use_num", "bank_tran_id", "api_tran_id", "access_token", "refresh_token", "user_seq_no", "client_secret"):
                self.assertNotIn(forbidden_key, res)

            # Strictly verify NO ledger or portfolio file was touched
            portfolio_file = Path(self.tmp.name) / "users" / "alice" / "portfolio.json"
            self.assertFalse(portfolio_file.exists())

    async def test_preview_balance_service_automatic_refresh_on_401(self):
        self._setup_alice_account()

        mock_success_res = {
            "bank_name": "토스뱅크",
            "product_name": "토스뱅크통장",
            "account_num_masked": "1000-0000-****",
            "account_type": "1",
            "balance_amt": 880000,
            "available_amt": 880000,
            "account_issue_date": "20240101",
            "maturity_date": None,
            "last_tran_date": "20260924",
            "bank_rsp_code": "000",
            "rsp_code": "A0000",
        }

        from app.services.kftc_openbanking_client import KftcAuthError
        err_401 = KftcAuthError("Token unauthorized", code="401", http_status=401)

        mock_fetch = AsyncMock(side_effect=[err_401, mock_success_res])
        mock_refresh = AsyncMock(return_value={"status": "valid"})

        with patch("app.services.kftc_openbanking_service.fetch_account_balance", mock_fetch), \
             patch("app.services.kftc_openbanking_service.refresh_user_token", mock_refresh), \
             patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True):
            res = await service.preview_account_balance("alice", "kftc-acc-alice-1")
            self.assertEqual(res["balance_amt"], 880000)
            self.assertEqual(mock_refresh.await_count, 1)
            self.assertEqual(mock_fetch.await_count, 2)

    async def test_preview_balance_service_a0002_does_not_trigger_refresh(self):
        self._setup_alice_account()

        from app.services.kftc_openbanking_client import KftcProviderError
        err_a0002 = KftcProviderError(
            "KFTC balance error (A0002)",
            code="A0002",
            rsp_code="A0002",
            bank_rsp_code="",
            rsp_message="조회대상계좌가 존재하지 않습니다.",
            http_status=200,
        )

        mock_fetch = AsyncMock(side_effect=err_a0002)
        mock_refresh = AsyncMock()

        with patch("app.services.kftc_openbanking_service.fetch_account_balance", mock_fetch), \
             patch("app.services.kftc_openbanking_service.refresh_user_token", mock_refresh), \
             patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True):
            with self.assertRaises(service.KftcServiceError) as ctx:
                await service.preview_account_balance("alice", "kftc-acc-alice-1")

            self.assertEqual(ctx.exception.code, "A0002")
            self.assertIn("A0002", str(ctx.exception))
            # Critical verification: A0002 MUST NOT trigger token refresh!
            self.assertEqual(mock_refresh.await_count, 0)
            self.assertEqual(mock_fetch.await_count, 1)

    async def test_preview_balance_service_second_401_does_not_loop(self):
        self._setup_alice_account()

        from app.services.kftc_openbanking_client import KftcAuthError
        err_401_first = KftcAuthError("First 401", code="401", http_status=401)
        err_401_second = KftcAuthError("Second 401", code="401", http_status=401)

        mock_fetch = AsyncMock(side_effect=[err_401_first, err_401_second])
        mock_refresh = AsyncMock(return_value={"status": "valid"})

        with patch("app.services.kftc_openbanking_service.fetch_account_balance", mock_fetch), \
             patch("app.services.kftc_openbanking_service.refresh_user_token", mock_refresh), \
             patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True):
            with self.assertRaises(service.KftcServiceError) as ctx:
                await service.preview_account_balance("alice", "kftc-acc-alice-1")

            self.assertEqual(ctx.exception.code, "TOKEN_EXPIRED")
            # Refreshed exactly once, attempted twice, no infinite retry
            self.assertEqual(mock_refresh.await_count, 1)
            self.assertEqual(mock_fetch.await_count, 2)

    async def test_preview_balance_service_bank_error_does_not_trigger_refresh(self):
        self._setup_alice_account()

        from app.services.kftc_openbanking_client import KftcProviderError
        err_bank = KftcProviderError(
            "Bank error (824)",
            code="BANK_824",
            rsp_code="824",
            bank_rsp_code="824",
            http_status=200,
        )

        mock_fetch = AsyncMock(side_effect=err_bank)
        mock_refresh = AsyncMock()

        with patch("app.services.kftc_openbanking_service.fetch_account_balance", mock_fetch), \
             patch("app.services.kftc_openbanking_service.refresh_user_token", mock_refresh), \
             patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True):
            with self.assertRaises(service.KftcServiceError) as ctx:
                await service.preview_account_balance("alice", "kftc-acc-alice-1")

            self.assertEqual(ctx.exception.code, "BANK_824")
            self.assertEqual(mock_refresh.await_count, 0)
            self.assertEqual(mock_fetch.await_count, 1)

    async def test_httpx_mock_transport_kftc_query_log_redaction(self):
        """Integration test: verify httpx AsyncClient logging redacts KFTC queries from real LogRecord and Formatter."""
        import logging
        import httpx

        captured: list[str] = []

        class CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(self.format(record))

        logger = logging.getLogger("httpx")
        handler = CaptureHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        old_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            mock_transport = httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "rsp_code": "A0000",
                        "bank_rsp_code": "000",
                        "balance_amt": "50000",
                        "available_amt": "50000",
                    },
                )
            )

            fake_fintech_num = "123456789012345678901234"
            fake_bank_tran_id = "XXXXXXXXXXU000000001"
            fake_tran_dtime = "20260925093000"

            async with httpx.AsyncClient(transport=mock_transport) as client:
                await client.get(
                    "https://testapi.openbanking.or.kr/v2.0/account/balance/fin_num",
                    params={
                        "fintech_use_num": fake_fintech_num,
                        "bank_tran_id": fake_bank_tran_id,
                        "tran_dtime": fake_tran_dtime,
                    },
                    headers={"Authorization": "Bearer secret_fake_token"},
                )

            self.assertTrue(len(captured) > 0, "No httpx logs captured")
            combined_logs = "\n".join(captured)

            # Strict assertions: no sensitive identifiers anywhere in formatted logs
            self.assertNotIn(fake_fintech_num, combined_logs)
            self.assertNotIn(fake_bank_tran_id, combined_logs)
            self.assertNotIn(fake_tran_dtime, combined_logs)
            self.assertNotIn("secret_fake_token", combined_logs)
            self.assertNotIn("fintech_use_num=", combined_logs)
            self.assertNotIn("bank_tran_id=", combined_logs)
            self.assertNotIn("tran_dtime=", combined_logs)

            # URL path remains visible, query string is replaced with ?[REDACTED]
            self.assertIn("https://testapi.openbanking.or.kr/v2.0/account/balance/fin_num?[REDACTED]", combined_logs)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)

    def test_kftc_log_redaction_filter(self):
        import logging
        from app.services.kftc_openbanking_client import KftcLogRedactionFilter

        redaction_filter = KftcLogRedactionFilter()

        # Log record containing KFTC testapi URL with sensitive query params
        raw_url = "https://testapi.openbanking.or.kr/v2.0/account/balance/fin_num?bank_tran_id=1234567890U123456789&fintech_use_num=120230226588951223594984&tran_dtime=20260925090000"
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname="client.py",
            lineno=100,
            msg='HTTP Request: GET %s "HTTP/1.1 200 OK"',
            args=(raw_url,),
            exc_info=None,
        )

        redaction_filter.filter(record)
        rendered = record.msg % record.args

        # Ensure fintech_use_num and bank_tran_id are stripped from log message
        self.assertNotIn("fintech_use_num=", rendered)
        self.assertNotIn("bank_tran_id=", rendered)
        self.assertNotIn("120230226588951223594984", rendered)
        self.assertIn("https://testapi.openbanking.or.kr/v2.0/account/balance/fin_num?[REDACTED]", rendered)

    def test_provider_message_sanitization(self):
        from app.services.kftc_openbanking_client import sanitize_provider_message

        # Control characters and excess whitespace
        dirty = "Error occurred:\r\n\tDetails: \x00\x1fSomething bad\n\n\thappened."
        clean = sanitize_provider_message(dirty)
        self.assertEqual(clean, "Error occurred: Details: Something bad happened.")

        # Max length truncation
        long_msg = "A" * 300
        truncated = sanitize_provider_message(long_msg, max_len=50)
        self.assertEqual(len(truncated), 53)  # 50 chars + "..."
        self.assertTrue(truncated.endswith("..."))

        # Echoed fintech_use_num (24 digits) and bank_tran_id (20 chars) in provider message
        echoed_msg = "Account 120230226588951223594984 failed for tran 1234567890U000000001"
        sanitized_echo = sanitize_provider_message(echoed_msg)
        self.assertNotIn("120230226588951223594984", sanitized_echo)
        self.assertNotIn("1234567890U000000001", sanitized_echo)
        self.assertIn("[REDACTED_FINTECH_NUM]", sanitized_echo)
        self.assertIn("[REDACTED_BANK_TRAN_ID]", sanitized_echo)

    async def test_preview_balance_service_scope_check(self):
        # Setup tokens without 'inquiry' scope
        self._setup_alice_account(scope="login")

        with patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True):
            with self.assertRaises(service.KftcServiceError) as ctx:
                await service.preview_account_balance("alice", "kftc-acc-alice-1")
            self.assertEqual(ctx.exception.code, "KFTC_SCOPE_INSUFFICIENT")

    async def test_preview_balance_service_missing_client_use_code(self):
        # Setup without client_use_code
        self._setup_alice_account(client_use_code="")

        with patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True):
            with self.assertRaises(service.KftcServiceError) as ctx:
                await service.preview_account_balance("alice", "kftc-acc-alice-1")
            self.assertEqual(ctx.exception.code, "KFTC_CLIENT_USE_CODE_REQUIRED")

    def test_preview_balance_api_endpoint(self):
        self._setup_alice_account()

        mock_balance_res = {
            "bank_name": "토스뱅크",
            "product_name": "토스뱅크통장",
            "account_num_masked": "1000-0000-****",
            "account_type": "1",
            "balance_amt": 1200000,
            "available_amt": 1200000,
            "account_issue_date": "20240101",
            "maturity_date": None,
            "last_tran_date": "20260924",
            "bank_rsp_code": "000",
            "rsp_code": "A0000",
        }

        with patch("app.services.kftc_openbanking_service.fetch_account_balance", new_callable=AsyncMock, return_value=mock_balance_res), \
             patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True):
            client = self._make_client("alice")
            resp = client.post("/api/kftc/openbanking/accounts/kftc-acc-alice-1/balance/preview")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["balance_amt"], 1200000)
            self.assertEqual(data["available_amt"], 1200000)
            self.assertEqual(data["account_type_label"], "수시입출금")
            self.assertEqual(resp.headers.get("cache-control"), "no-store")

            for forbidden_key in ("fintech_use_num", "bank_tran_id", "api_tran_id", "access_token", "refresh_token", "user_seq_no", "client_secret"):
                self.assertNotIn(forbidden_key, data)

    def test_preview_balance_api_user_isolation(self):
        # Alice sets up her account
        self._setup_alice_account()

        # Bob attempts to inquire balance for Alice's account
        client_bob = self._make_client("bob")
        with patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True):
            resp = client_bob.post("/api/kftc/openbanking/accounts/kftc-acc-alice-1/balance/preview")
            # Bob is not connected or doesn't have this account -> rejected
            self.assertIn(resp.status_code, [400, 404])


if __name__ == "__main__":
    unittest.main()
