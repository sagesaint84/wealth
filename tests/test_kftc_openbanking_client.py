import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.services import kftc_openbanking_client as client


class KftcOpenBankingClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_token_exchange_success(self):
        mock_resp = httpx.Response(
            200,
            json={
                "access_token": "acc-token-1",
                "token_type": "Bearer",
                "expires_in": 7776000,
                "refresh_token": "ref-token-1",
                "scope": "login inquiry",
                "user_seq_no": "1101038125",
            },
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        res = await client.exchange_authorization_code(
            environment="test",
            client_id="cid",
            client_secret="csec",
            code="testcode",
            redirect_uri="https://wealth-sage.duckdns.org/api/kftc/openbanking/oauth/callback",
            client=mock_client,
        )
        self.assertEqual(res["access_token"], "acc-token-1")
        self.assertEqual(res["refresh_token"], "ref-token-1")
        self.assertEqual(res["user_seq_no"], "1101038125")

    async def test_token_exchange_invalid_grant_error(self):
        mock_resp = httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "code expired or already used"},
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        with self.assertRaises(client.KftcAuthError) as ctx:
            await client.exchange_authorization_code(
                environment="test",
                client_id="cid",
                client_secret="csec",
                code="expiredcode",
                redirect_uri="https://wealth-sage.duckdns.org/api/kftc/openbanking/oauth/callback",
                client=mock_client,
            )
        self.assertEqual(ctx.exception.code, "INVALID_GRANT")
        # Ensure raw provider response error_description is NOT leaked in message
        self.assertNotIn("code expired or already used", str(ctx.exception))

    async def test_token_exchange_invalid_client_error(self):
        mock_resp = httpx.Response(
            401,
            json={"error": "invalid_client", "error_description": "Client authentication failed"},
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        with self.assertRaises(client.KftcAuthError) as ctx:
            await client.exchange_authorization_code(
                environment="test",
                client_id="cid",
                client_secret="csec",
                code="code1",
                redirect_uri="https://wealth-sage.duckdns.org/api/kftc/openbanking/oauth/callback",
                client=mock_client,
            )
        self.assertEqual(ctx.exception.code, "INVALID_CLIENT")

    async def test_token_exchange_malformed_json_fails(self):
        mock_resp = httpx.Response(
            200,
            content=b"<!DOCTYPE html><html>Service Unavailable</html>",
            headers={"Content-Type": "text/html"},
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        with self.assertRaises(client.KftcProviderError) as ctx:
            await client.exchange_authorization_code(
                environment="test",
                client_id="cid",
                client_secret="csec",
                code="code1",
                redirect_uri="https://wealth-sage.duckdns.org/api/kftc/openbanking/oauth/callback",
                client=mock_client,
            )
        self.assertEqual(ctx.exception.code, "MALFORMED_JSON")

    async def test_token_exchange_missing_access_token_fails(self):
        mock_resp = httpx.Response(
            200,
            json={"user_seq_no": "1101038125", "expires_in": 7776000},
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        with self.assertRaises(client.KftcProviderError) as ctx:
            await client.exchange_authorization_code(
                environment="test",
                client_id="cid",
                client_secret="csec",
                code="code1",
                redirect_uri="https://wealth-sage.duckdns.org/api/kftc/openbanking/oauth/callback",
                client=mock_client,
            )
        self.assertEqual(ctx.exception.code, "MISSING_ACCESS_TOKEN")

    async def test_token_exchange_invalid_expires_in_fails(self):
        mock_resp = httpx.Response(
            200,
            json={"access_token": "acc", "user_seq_no": "1101038125", "expires_in": "not-an-integer"},
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        with self.assertRaises(client.KftcProviderError) as ctx:
            await client.exchange_authorization_code(
                environment="test",
                client_id="cid",
                client_secret="csec",
                code="code1",
                redirect_uri="https://wealth-sage.duckdns.org/api/kftc/openbanking/oauth/callback",
                client=mock_client,
            )
        self.assertEqual(ctx.exception.code, "INVALID_EXPIRES_IN")

    async def test_fetch_user_accounts_success_and_filtering(self):
        mock_resp = httpx.Response(
            200,
            json={
                "rsp_code": "A0000",
                "rsp_message": "",
                "user_seq_no": "1101038125",
                "res_cnt": "3",
                "res_list": [
                    {
                        "fintech_use_num": "120230226588951223594984",
                        "bank_code_std": "004",
                        "bank_name": "KB국민은행",
                        "account_num_masked": "123456-04-123***",
                        "account_alias": "급여통장",
                        "account_type": "1",
                        "product_name": "KB내맘대로통장",
                        "inquiry_agree_yn": "Y",
                        "account_state": "01",
                    },
                    {
                        "fintech_use_num": "120230226588951223594985",
                        "bank_code_std": "088",
                        "bank_name": "신한은행",
                        "account_num_masked": "110-123-456***",
                        "account_alias": "해지된통장",
                        "account_type": "1",
                        "product_name": "신한주거래",
                        "inquiry_agree_yn": "N",
                        "account_state": "09",  # Canceled/Closed
                    },
                    {
                        "fintech_use_num": "120230226588951223594986",
                        "bank_code_std": "020",
                        "bank_name": "우리은행",
                        "account_num_masked": "1002-123-456***",
                        "account_alias": "비정상상태통장",
                        "account_type": "1",
                        "product_name": "우리주거래",
                        "inquiry_agree_yn": "Y",
                        "account_state": "정상",  # Non-official enum guess should NOT match '01'
                    },
                ],
            },
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        accounts = await client.fetch_user_accounts(
            environment="test",
            access_token="test-acc",
            user_seq_no="1101038125",
            client=mock_client,
        )
        # Only the account with official account_state="01" passes
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["bank_name"], "KB국민은행")
        self.assertEqual(accounts[0]["inquiry_agree_yn"], "Y")

    async def test_fetch_user_accounts_production_strict_fail_closed(self):
        # In production: ONLY '01' is accepted. Missing/empty/02/09/unknown are all rejected.
        mock_resp = httpx.Response(
            200,
            json={
                "rsp_code": "A0000",
                "rsp_message": "",
                "user_seq_no": "1101038125",
                "res_cnt": "6",
                "res_list": [
                    {"fintech_use_num": "acc_01", "account_state": "01", "inquiry_agree_yn": "Y"},
                    {"fintech_use_num": "acc_missing", "inquiry_agree_yn": "Y"},
                    {"fintech_use_num": "acc_empty", "account_state": "", "inquiry_agree_yn": "Y"},
                    {"fintech_use_num": "acc_02", "account_state": "02", "inquiry_agree_yn": "Y"},
                    {"fintech_use_num": "acc_09", "account_state": "09", "inquiry_agree_yn": "Y"},
                    {"fintech_use_num": "acc_unknown", "account_state": "99", "inquiry_agree_yn": "Y"},
                ],
            },
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        accounts = await client.fetch_user_accounts(
            environment="production",
            access_token="prod-acc",
            user_seq_no="1101038125",
            client=mock_client,
        )
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["fintech_use_num"], "acc_01")

    async def test_fetch_user_accounts_testbed_compatibility(self):
        # In test environment:
        # - account_state missing/None/"" with inquiry_agree_yn="Y" and fintech_num -> included
        # - account_state missing/None/"" with inquiry_agree_yn="N" -> excluded
        # - account_state "02", "09", or unknown non-empty -> excluded
        # - account_state "01" -> included
        mock_resp = httpx.Response(
            200,
            json={
                "rsp_code": "A0000",
                "rsp_message": "",
                "user_seq_no": "1101038125",
                "res_cnt": "8",
                "res_list": [
                    {"fintech_use_num": "acc_01", "account_state": "01", "inquiry_agree_yn": "Y"},
                    {"fintech_use_num": "acc_missing_y", "inquiry_agree_yn": "Y"},
                    {"fintech_use_num": "acc_none_y", "account_state": None, "inquiry_agree_yn": "Y"},
                    {"fintech_use_num": "acc_empty_y", "account_state": "", "inquiry_agree_yn": "Y"},
                    {"fintech_use_num": "acc_empty_n", "account_state": "", "inquiry_agree_yn": "N"},
                    {"fintech_use_num": "acc_02", "account_state": "02", "inquiry_agree_yn": "Y"},
                    {"fintech_use_num": "acc_09", "account_state": "09", "inquiry_agree_yn": "Y"},
                    {"fintech_use_num": "acc_unknown", "account_state": "99", "inquiry_agree_yn": "Y"},
                ],
            },
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        accounts = await client.fetch_user_accounts(
            environment="test",
            access_token="test-acc",
            user_seq_no="1101038125",
            client=mock_client,
        )
        passed_ids = [a["fintech_use_num"] for a in accounts]
        self.assertEqual(passed_ids, ["acc_01", "acc_missing_y", "acc_none_y", "acc_empty_y"])


if __name__ == "__main__":
    unittest.main()
