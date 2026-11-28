"""Remove sensitive keys from financial backup exports."""

from __future__ import annotations

from types import ModuleType


def create_backup_security(runtime: ModuleType) -> dict[str, object]:
    # Keep the existing app-level helper bindings live for callers and patches.
    _SENSITIVE_EXPORT_KEYS = {
        "accesstoken",
        "apikey",
        "apisecret",
        "appkey",
        "appsecret",
        "authtoken",
        "bearertoken",
        "clientsecret",
        "credential",
        "credentials",
        "password",
        "passwordhash",
        "passwordsalt",
        "privatekey",
        "refreshtoken",
        "salt",
        "secret",
        "secretkey",
        "sessionid",
        "sessionsecret",
        "sessiontoken",
        "token",
        "tokencache",
        "webhookurl",
    }

    def _normalize_sensitive_key(key: object) -> str:
        return "".join(char.lower() for char in str(key) if char.isalnum())

    def _is_sensitive_export_key(key: object) -> bool:
        normalized = runtime._normalize_sensitive_key(key)
        return normalized in runtime._SENSITIVE_EXPORT_KEYS or normalized.endswith(
            (
                "accesstoken",
                "apikey",
                "apisecret",
                "appkey",
                "appsecret",
                "clientsecret",
                "credential",
                "credentials",
                "password",
                "passwordhash",
                "privatekey",
                "refreshtoken",
                "secret",
                "sessionsecret",
                "token",
                "tokencache",
                "webhookurl",
            )
        )

    def _sanitize_export_data(value: object) -> object:
        """백업 데이터 어디에도 인증정보가 포함되지 않도록 재귀적으로 제거한다."""
        if isinstance(value, dict):
            return {
                key: runtime._sanitize_export_data(item)
                for key, item in value.items()
                if not runtime._is_sensitive_export_key(key)
            }
        if isinstance(value, list):
            return [runtime._sanitize_export_data(item) for item in value]
        if isinstance(value, tuple):
            return [runtime._sanitize_export_data(item) for item in value]
        return value

    return {
        "_SENSITIVE_EXPORT_KEYS": _SENSITIVE_EXPORT_KEYS,
        "_normalize_sensitive_key": _normalize_sensitive_key,
        "_is_sensitive_export_key": _is_sensitive_export_key,
        "_sanitize_export_data": _sanitize_export_data,
    }
