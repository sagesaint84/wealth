import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services import kftc_openbanking_service as service
from app.services import kftc_openbanking_storage as storage


class KftcOpenBankingAccountsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.patch_user_dir = patch(
            "app.services.kftc_openbanking_storage.get_user_data_dir",
            return_value=Path(self.tmp.name),
        )
        self.patch_user_dir.start()
        self.addCleanup(self.patch_user_dir.stop)

    async def test_accounts_discovery_and_masked_persistence(self):
        # Setup tokens
        storage.save_user_tokens(
            "alice",
            access_token="acc-tok",
            refresh_token="ref-tok",
            user_seq_no="seq-1",
            scope="login inquiry",
            expires_in=7776000,
        )

        mock_accounts = [
            {
                "fintech_use_num": "fin-123456789012345678901234",
                "bank_code_std": "004",
                "bank_name": "KB국민은행",
                "account_num_masked": "123-456-789***",
                "account_alias": "생활비통장",
                "account_type": "1",
                "product_name": "KB급여통장",
                "inquiry_agree_yn": "Y",
            }
        ]

        with patch("app.services.kftc_openbanking_service.fetch_user_accounts", new_callable=AsyncMock, return_value=mock_accounts), \
             patch("app.services.kftc_openbanking_service.is_user_allowed_kftc", return_value=True):
            accounts = await service.refresh_and_sync_accounts("alice")
            self.assertEqual(len(accounts), 1)
            acc = accounts[0]
            self.assertEqual(acc["bank_name"], "KB국민은행")
            self.assertEqual(acc["account_num_masked"], "123-456-789***")
            self.assertTrue(acc["inquiry_available"])
            # Ensure raw fintech_use_num is never returned in loaded account list
            self.assertNotIn("fintech_use_num", acc)
            self.assertTrue(acc["provider_account_id"].startswith("kftc-"))

            # Verify fintech_use_num is securely encrypted on disk
            accounts_file = Path(self.tmp.name) / "kftc_openbanking_accounts.json"
            raw_text = accounts_file.read_text(encoding="utf-8")
            self.assertNotIn("fin-123456789012345678901234", raw_text)

            # Test internal resolution for Phase 2/3
            resolved_fin_num = storage.resolve_fintech_use_num("alice", acc["provider_account_id"])
            self.assertEqual(resolved_fin_num, "fin-123456789012345678901234")


if __name__ == "__main__":
    unittest.main()
