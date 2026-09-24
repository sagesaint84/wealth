import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import kftc_openbanking_crypto as crypto
from app.services import kftc_openbanking_storage as storage


class KftcOpenBankingCryptoTests(unittest.TestCase):
    def test_roundtrip_encryption_decryption(self):
        token = "test-access-token-xyz-12345"
        encrypted = crypto.encrypt_string(token, secret_override="secret-key-1")
        self.assertNotEqual(token, encrypted)
        decrypted = crypto.decrypt_string(encrypted, secret_override="secret-key-1")
        self.assertEqual(token, decrypted)

    def test_same_plaintext_encrypt_twice_differs(self):
        plaintext = "repeated-sensitive-secret-token"
        enc1 = crypto.encrypt_string(plaintext, secret_override="key-1")
        enc2 = crypto.encrypt_string(plaintext, secret_override="key-1")
        self.assertNotEqual(enc1, enc2)
        # Both must decrypt to the exact same plaintext
        self.assertEqual(crypto.decrypt_string(enc1, secret_override="key-1"), plaintext)
        self.assertEqual(crypto.decrypt_string(enc2, secret_override="key-1"), plaintext)

    def test_wrong_application_secret_fails_decryption(self):
        token = "test-token"
        encrypted = crypto.encrypt_string(token, secret_override="key-a")
        with self.assertRaises(crypto.KftcCryptoError):
            crypto.decrypt_string(encrypted, secret_override="key-b")

    def test_tampered_ciphertext_fails(self):
        token = "test-token-to-tamper"
        encrypted = crypto.encrypt_string(token, secret_override="key-a")
        raw = json.loads(crypto._b64url_decode(encrypted).decode("utf-8"))
        ct_bytes = bytearray(crypto._b64url_decode(raw["ciphertext"]))
        ct_bytes[0] ^= 0xFF
        raw["ciphertext"] = crypto._b64url_encode(bytes(ct_bytes))
        tampered = crypto._b64url_encode(json.dumps(raw).encode("utf-8"))
        with self.assertRaises(crypto.KftcCryptoError):
            crypto.decrypt_string(tampered, secret_override="key-a")

    def test_tampered_nonce_fails(self):
        token = "test-token-to-tamper-nonce"
        encrypted = crypto.encrypt_string(token, secret_override="key-a")
        raw = json.loads(crypto._b64url_decode(encrypted).decode("utf-8"))
        nonce_bytes = bytearray(crypto._b64url_decode(raw["nonce"]))
        nonce_bytes[0] ^= 0xFF
        raw["nonce"] = crypto._b64url_encode(bytes(nonce_bytes))
        tampered = crypto._b64url_encode(json.dumps(raw).encode("utf-8"))
        with self.assertRaises(crypto.KftcCryptoError):
            crypto.decrypt_string(tampered, secret_override="key-a")

    def test_wrong_context_fails(self):
        token = "test-token"
        token_ctx = "wealth:kftc-openbanking-token:v1"
        account_ctx = "wealth:kftc-openbanking-account:v1"

        encrypted = crypto.encrypt_string(token, secret_override="key-a", context=token_ctx)
        # Token ciphertext MUST NOT decrypt under account context
        with self.assertRaises(crypto.KftcCryptoError):
            crypto.decrypt_string(encrypted, secret_override="key-a", context=account_ctx)

    def test_corrupt_envelope_fails_closed(self):
        with self.assertRaises(crypto.KftcCryptoError):
            crypto.decrypt_string("not-a-valid-base64-envelope!!!", secret_override="key-a")

        # Envelope with wrong version
        bad_ver = crypto._b64url_encode(json.dumps({
            "version": 99,
            "algorithm": "AES-256-GCM",
            "nonce": crypto._b64url_encode(b"0" * 12),
            "ciphertext": crypto._b64url_encode(b"0" * 32),
        }).encode("utf-8"))
        with self.assertRaises(crypto.KftcCryptoError):
            crypto.decrypt_string(bad_ver, secret_override="key-a")

        # Envelope with wrong algorithm
        bad_algo = crypto._b64url_encode(json.dumps({
            "version": 1,
            "algorithm": "DES-CBC",
            "nonce": crypto._b64url_encode(b"0" * 12),
            "ciphertext": crypto._b64url_encode(b"0" * 32),
        }).encode("utf-8"))
        with self.assertRaises(crypto.KftcCryptoError):
            crypto.decrypt_string(bad_algo, secret_override="key-a")

    def test_empty_string_fails(self):
        with self.assertRaises(crypto.KftcCryptoError):
            crypto.encrypt_string("", secret_override="key-a")
        with self.assertRaises(crypto.KftcCryptoError):
            crypto.decrypt_string("", secret_override="key-a")

    def test_storage_encryption_applied_to_access_refresh_and_fintech_num(self):
        """Verify tokens and fintech_use_num are stored encrypted and plaintexts never appear in JSON."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("app.services.kftc_openbanking_storage.get_user_data_dir", return_value=Path(tmp_dir)):
                raw_access = "real-kftc-access-token-999"
                raw_refresh = "real-kftc-refresh-token-888"
                raw_fintech = "120230226588951223594984"

                # 1. Save user tokens
                storage.save_user_tokens(
                    "alice",
                    access_token=raw_access,
                    refresh_token=raw_refresh,
                    user_seq_no="seq-alice",
                    scope="login inquiry",
                    expires_in=7776000,
                )
                token_file = Path(tmp_dir) / "kftc_openbanking_token.json"
                self.assertTrue(token_file.exists())
                token_json_text = token_file.read_text(encoding="utf-8")
                # Plaintext substrings MUST NOT exist in JSON file
                self.assertNotIn(raw_access, token_json_text)
                self.assertNotIn(raw_refresh, token_json_text)

                # Decrypted retrieval matches original
                decrypted = storage.get_decrypted_user_tokens("alice")
                self.assertEqual(decrypted["access_token"], raw_access)
                self.assertEqual(decrypted["refresh_token"], raw_refresh)

                # 2. Save user accounts with fintech_use_num
                accounts = [{
                    "provider_account_id": "kftc-acc-1",
                    "fintech_use_num": raw_fintech,
                    "bank_code_std": "004",
                    "bank_name": "KB국민은행",
                    "account_num_masked": "123-***-456",
                    "inquiry_agree_yn": "Y",
                }]
                storage.save_user_kftc_accounts("alice", accounts)
                acc_file = Path(tmp_dir) / "kftc_openbanking_accounts.json"
                self.assertTrue(acc_file.exists())
                acc_json_text = acc_file.read_text(encoding="utf-8")
                # Plaintext fintech_use_num MUST NOT exist in JSON file
                self.assertNotIn(raw_fintech, acc_json_text)

                # Decrypted fintech_use_num matches original
                resolved_num = storage.resolve_fintech_use_num("alice", "kftc-acc-1")
                self.assertEqual(resolved_num, raw_fintech)


if __name__ == "__main__":
    unittest.main()
