"""Cryptographic protection for KFTC Open Banking tokens and sensitive fields.

Uses standardized AEAD primitives:
- cryptography.hazmat.primitives.ciphers.aead.AESGCM (AES-256-GCM)
- cryptography.hazmat.primitives.kdf.hkdf.HKDF with SHA-256
- Root secret resolved from app.services.system_secrets.resolve_application_secret()
- 32-byte encryption key derived via HKDF (salt, info=context)
- 12-byte random nonce per encryption
- AAD (Additional Authenticated Data) bound to version and context
- Base64url encoded envelope:
  {
    "version": 1,
    "algorithm": "AES-256-GCM",
    "nonce": "<base64url>",
    "ciphertext": "<base64url>"
  }

Context separation:
- Token: "wealth:kftc-openbanking-token:v1"
- Account: "wealth:kftc-openbanking-account:v1"
- Config Secret: "wealth:kftc-openbanking-config-secret:v1"

Plaintext, keys, and tokens are never logged.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.services.system_secrets import resolve_application_secret

DEFAULT_TOKEN_CONTEXT = "wealth:kftc-openbanking-token:v1"
ACCOUNT_CONTEXT = "wealth:kftc-openbanking-account:v1"
CONFIG_SECRET_CONTEXT = "wealth:kftc-openbanking-config-secret:v1"

SALT = b"wealth:kftc-openbanking:kdf:v1"
NONCE_LENGTH = 12  # Standard 96-bit nonce for AES-GCM
KEY_LENGTH = 32    # 256 bits for AES-256-GCM
SUPPORTED_VERSION = 1
SUPPORTED_ALGORITHM = "AES-256-GCM"


class KftcCryptoError(Exception):
    """Raised when encryption or decryption fails."""


def get_kftc_config_secret_context(username: str) -> str:
    """Return cryptographic context bound to username for client_secret encryption."""
    normalized = str(username or "").strip()
    if not normalized:
        raise KftcCryptoError("USERNAME_REQUIRED")
    return f"{CONFIG_SECRET_CONTEXT}:{normalized}"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad_len = (4 - len(s) % 4) % 4
    return base64.urlsafe_b64decode((s + "=" * pad_len).encode("ascii"))


def derive_kftc_key(secret: str, *, context: str = DEFAULT_TOKEN_CONTEXT) -> bytes:
    """Derive a 256-bit symmetric encryption key using HKDF-SHA256."""
    if not secret:
        raise KftcCryptoError("APPLICATION_SECRET_EMPTY")
    if not context:
        raise KftcCryptoError("CONTEXT_EMPTY")

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH,
        salt=SALT,
        info=context.encode("utf-8"),
    )
    return hkdf.derive(secret.encode("utf-8"))


def _build_aad(version: int, context: str) -> bytes:
    return f"wealth:aad:v{version}:{context}".encode("utf-8")


def encrypt_string(
    plaintext: str,
    *,
    secret_override: str | None = None,
    context: str = DEFAULT_TOKEN_CONTEXT,
) -> str:
    """Encrypt a plaintext string using AES-256-GCM and return a serialized envelope."""
    if not isinstance(plaintext, str):
        raise KftcCryptoError("PLAINTEXT_INVALID")
    if not plaintext:
        raise KftcCryptoError("PLAINTEXT_EMPTY")
    if not context:
        raise KftcCryptoError("CONTEXT_EMPTY")

    secret = secret_override if secret_override is not None else resolve_application_secret()
    key = derive_kftc_key(secret, context=context)

    nonce = secrets.token_bytes(NONCE_LENGTH)
    aad = _build_aad(SUPPORTED_VERSION, context)

    aesgcm = AESGCM(key)
    try:
        ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)
    except Exception as exc:
        raise KftcCryptoError("ENCRYPTION_FAILED") from exc

    envelope = {
        "version": SUPPORTED_VERSION,
        "algorithm": SUPPORTED_ALGORITHM,
        "nonce": _b64url_encode(nonce),
        "ciphertext": _b64url_encode(ciphertext_with_tag),
    }

    raw_json = json.dumps(envelope, separators=(",", ":"))
    return _b64url_encode(raw_json.encode("utf-8"))


def decrypt_string(
    token_str: str,
    *,
    secret_override: str | None = None,
    context: str = DEFAULT_TOKEN_CONTEXT,
) -> str:
    """Decrypt and authenticate an AES-256-GCM envelope, returning plaintext.

    Raises KftcCryptoError on tampering, invalid context, corrupt payload, or wrong secret.
    """
    if not isinstance(token_str, str) or not token_str.strip():
        raise KftcCryptoError("TOKEN_EMPTY_OR_INVALID")
    if not context:
        raise KftcCryptoError("CONTEXT_EMPTY")

    try:
        raw_json_bytes = _b64url_decode(token_str.strip())
        envelope = json.loads(raw_json_bytes.decode("utf-8"))
    except Exception as exc:
        raise KftcCryptoError("TOKEN_CORRUPT") from exc

    if not isinstance(envelope, dict):
        raise KftcCryptoError("TOKEN_ENVELOPE_INVALID")

    if envelope.get("version") != SUPPORTED_VERSION or envelope.get("algorithm") != SUPPORTED_ALGORITHM:
        raise KftcCryptoError("TOKEN_ALGORITHM_UNSUPPORTED")

    nonce_b64 = envelope.get("nonce")
    ct_b64 = envelope.get("ciphertext")
    if not isinstance(nonce_b64, str) or not isinstance(ct_b64, str):
        raise KftcCryptoError("TOKEN_ENVELOPE_MALFORMED")

    try:
        nonce = _b64url_decode(nonce_b64)
        ciphertext_with_tag = _b64url_decode(ct_b64)
    except Exception as exc:
        raise KftcCryptoError("TOKEN_PAYLOAD_CORRUPT") from exc

    if len(nonce) != NONCE_LENGTH:
        raise KftcCryptoError("TOKEN_NONCE_INVALID")

    secret = secret_override if secret_override is not None else resolve_application_secret()
    key = derive_kftc_key(secret, context=context)
    aad = _build_aad(SUPPORTED_VERSION, context)

    aesgcm = AESGCM(key)
    try:
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, aad)
    except InvalidTag as exc:
        raise KftcCryptoError("TOKEN_AUTHENTICATION_FAILED") from exc
    except Exception as exc:
        raise KftcCryptoError("DECRYPTION_FAILED") from exc

    try:
        return decrypted_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KftcCryptoError("DECRYPTION_DECODE_FAILED") from exc
