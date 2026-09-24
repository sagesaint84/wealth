import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services import kftc_openbanking_config as cfg
from app.services import kftc_openbanking_service as service
from app.services import kftc_openbanking_storage as storage


class KftcOpenBankingOAuthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.patch_user_dir = patch(
            "app.services.kftc_openbanking_storage.get_user_data_dir",
            return_value=Path(self.tmp.name),
        )
        self.patch_user_dir.start()
        self.addCleanup(self.patch_user_dir.stop)

    def test_start_oauth_forbids_non_default_scopes(self):
        # Forbidden scopes must be rejected
        for bad_scope in ["transfer", "login inquiry transfer", "sa", "oob", "login inquiry sa"]:
            with self.assertRaises(service.KftcServiceError) as ctx:
                service.start_oauth_flow("alice", session_id="sess-1", scope=bad_scope)
            self.assertEqual(ctx.exception.code, "KFTC_SCOPE_FORBIDDEN")

    def test_start_oauth_generates_32char_hex_bound_state_and_url(self):
        import re
        with patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True), \
             patch("app.services.kftc_openbanking_service.get_effective_kftc_config", return_value={
                 "enabled": True, "environment": "test", "client_id": "test-client", "client_secret": "test-sec", "allowed_users": []
             }), patch("app.services.kftc_openbanking_service.get_kftc_callback_url", return_value="https://wealth.example.com/api/kftc/openbanking/oauth/callback"):
            res1 = service.start_oauth_flow("alice", session_id="sess-1")
            res2 = service.start_oauth_flow("alice", session_id="sess-1")

            state1 = res1["state"]
            state2 = res2["state"]

            # Exact 32 characters
            self.assertEqual(len(state1), 32)
            self.assertEqual(len(state2), 32)

            # Lowercase hex format [0-9a-f]{32}
            self.assertTrue(re.fullmatch(r"[0-9a-f]{32}", state1))
            self.assertTrue(re.fullmatch(r"[0-9a-f]{32}", state2))

            # Two successive generations differ
            self.assertNotEqual(state1, state2)

            # URL verification: scope is strictly 'login+inquiry'
            self.assertIn("authorize_url", res1)
            self.assertIn("client_id=test-client", res1["authorize_url"])
            self.assertIn("scope=login+inquiry", res1["authorize_url"])
            self.assertIn(f"state={state1}", res1["authorize_url"])
            # Ensure client_use_code is NOT part of authorize URL
            self.assertNotIn("client_use_code", res1["authorize_url"])

            # Verify state was persisted
            state_file = Path(self.tmp.name) / "kftc_openbanking_oauth_state.json"
            self.assertTrue(state_file.exists())

    def test_valid_state_consumed_exactly_once(self):
        storage.save_oauth_state("alice", state="valid-state-1", session_id="sess-1", ttl_seconds=600)
        state_file = Path(self.tmp.name) / "kftc_openbanking_oauth_state.json"
        self.assertTrue(state_file.exists())

        # First consumption passes and deletes state file
        self.assertTrue(storage.consume_oauth_state("alice", state="valid-state-1", session_id="sess-1"))
        self.assertFalse(state_file.exists())

        # Replay fails
        self.assertFalse(storage.consume_oauth_state("alice", state="valid-state-1", session_id="sess-1"))

    def test_wrong_state_does_not_destroy_valid_pending_state(self):
        storage.save_oauth_state("alice", state="valid-state-correct", session_id="sess-1", ttl_seconds=600)
        state_file = Path(self.tmp.name) / "kftc_openbanking_oauth_state.json"
        self.assertTrue(state_file.exists())

        # Wrong state submitted
        self.assertFalse(storage.consume_oauth_state("alice", state="wrong-state", session_id="sess-1"))
        # Valid state file MUST still exist!
        self.assertTrue(state_file.exists())

        # Legitimate submission subsequently succeeds
        self.assertTrue(storage.consume_oauth_state("alice", state="valid-state-correct", session_id="sess-1"))
        self.assertFalse(state_file.exists())

    def test_wrong_session_does_not_destroy_valid_pending_state(self):
        storage.save_oauth_state("alice", state="valid-state-session", session_id="sess-alice", ttl_seconds=600)
        state_file = Path(self.tmp.name) / "kftc_openbanking_oauth_state.json"
        self.assertTrue(state_file.exists())

        # Wrong session submitted
        self.assertFalse(storage.consume_oauth_state("alice", state="valid-state-session", session_id="sess-attacker"))
        # Valid state file MUST still exist!
        self.assertTrue(state_file.exists())

        # Legitimate session subsequently succeeds
        self.assertTrue(storage.consume_oauth_state("alice", state="valid-state-session", session_id="sess-alice"))
        self.assertFalse(state_file.exists())

    def test_callback_state_wrong_user_fails(self):
        storage.save_oauth_state("alice", state="valid-state-user", session_id="sess-alice", ttl_seconds=600)
        # Attempting to consume with wrong user
        self.assertFalse(storage.consume_oauth_state("bob", state="valid-state-user", session_id="sess-alice"))

    def test_callback_state_expired_fails(self):
        # Save state with negative TTL (already expired)
        storage.save_oauth_state("alice", state="expired-state", session_id="sess-alice", ttl_seconds=-1)
        self.assertFalse(storage.consume_oauth_state("alice", state="expired-state", session_id="sess-alice"))

    @patch("app.services.kftc_openbanking_service.exchange_authorization_code", new_callable=AsyncMock)
    @patch("app.services.kftc_openbanking_service.refresh_and_sync_accounts", new_callable=AsyncMock)
    async def test_callback_never_calls_token_endpoint_if_state_invalid(self, mock_sync, mock_exchange):
        with patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True):
            # State does not exist
            with self.assertRaises(service.KftcServiceError) as ctx:
                await service.handle_oauth_callback(
                    "alice",
                    session_id="sess-1",
                    code="auth-code-123",
                    state="nonexistent-state",
                )
            self.assertEqual(ctx.exception.code, "KFTC_STATE_INVALID")
            # Ensure token endpoint was NEVER called
            mock_exchange.assert_not_called()
            mock_sync.assert_not_called()

    @patch("app.services.kftc_openbanking_service.exchange_authorization_code", new_callable=AsyncMock)
    async def test_token_exchange_failure_after_valid_consume_still_blocks_replay(self, mock_exchange):
        storage.save_oauth_state("alice", state="state-consume-then-fail", session_id="sess-1")
        # Token endpoint throws an exception
        mock_exchange.side_effect = service.KftcAuthError("Token exchange failed", code="INVALID_GRANT")

        with patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True), \
             patch("app.services.kftc_openbanking_service.get_effective_kftc_config", return_value={
                 "enabled": True, "environment": "test", "client_id": "test-client", "client_secret": "test-sec", "allowed_users": []
             }), patch("app.services.kftc_openbanking_service.get_kftc_callback_url", return_value="https://wealth.example.com/api/kftc/openbanking/oauth/callback"):
            with self.assertRaises(service.KftcAuthError):
                await service.handle_oauth_callback(
                    "alice",
                    session_id="sess-1",
                    code="code-fail",
                    state="state-consume-then-fail",
                )

            # Replay with same code and state MUST fail at state verification without calling exchange again
            mock_exchange.reset_mock()
            with self.assertRaises(service.KftcServiceError) as ctx:
                await service.handle_oauth_callback(
                    "alice",
                    session_id="sess-1",
                    code="code-fail",
                    state="state-consume-then-fail",
                )
            self.assertEqual(ctx.exception.code, "KFTC_STATE_INVALID")
            mock_exchange.assert_not_called()

    @patch("app.services.kftc_openbanking_service.exchange_authorization_code", new_callable=AsyncMock)
    @patch("app.services.kftc_openbanking_service.refresh_and_sync_accounts", new_callable=AsyncMock)
    async def test_callback_success_stores_encrypted_tokens(self, mock_sync, mock_exchange):
        storage.save_oauth_state("alice", state="state-ok", session_id="sess-1")
        mock_exchange.return_value = {
            "access_token": "access-123",
            "refresh_token": "refresh-456",
            "user_seq_no": "seq-999",
            "scope": "login inquiry",
            "expires_in": 123456,
        }
        with patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True), \
             patch("app.services.kftc_openbanking_service.get_effective_kftc_config", return_value={
                 "enabled": True, "environment": "test", "client_id": "test-client", "client_secret": "test-sec", "allowed_users": []
             }), patch("app.services.kftc_openbanking_service.get_kftc_callback_url", return_value="https://wealth.example.com/api/kftc/openbanking/oauth/callback"):
            res = await service.handle_oauth_callback(
                "alice",
                session_id="sess-1",
                code="auth-code-123",
                state="state-ok",
            )
            self.assertTrue(res["connected"])

            token_file = Path(self.tmp.name) / "kftc_openbanking_token.json"
            self.assertTrue(token_file.exists())
            raw_text = token_file.read_text(encoding="utf-8")
            self.assertNotIn("access-123", raw_text)
            self.assertNotIn("refresh-456", raw_text)

            # Retrieve decrypted tokens internally
            decrypted = storage.get_decrypted_user_tokens("alice")
            self.assertEqual(decrypted["access_token"], "access-123")
            self.assertEqual(decrypted["refresh_token"], "refresh-456")

            # Verify provider expires_in was directly preserved without hardcoded fallback
            status = storage.load_user_token_status("alice")
            self.assertAlmostEqual(status["expires_in"], 123456, delta=2)


if __name__ == "__main__":
    unittest.main()
