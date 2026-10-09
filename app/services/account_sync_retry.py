"""Bounded retries of account reads, never canonical portfolio mutations."""
from __future__ import annotations

import asyncio

import httpx

from app.services.kb_openapi import KBOpenAPIError
from app.services.toss_openapi import TossOpenAPIError
from app.services.nhplug_openapi import NhPlugOpenAPIError
from app.services.kis_openapi import KISOpenAPIError
from app.services.kiwoom_openapi import KiwoomOpenAPIError

TRANSIENT_HTTP = frozenset({429, 500, 502, 503, 504})
RETRY_DELAY_SECONDS = 0.1


def failure_diagnostic(error: Exception, provider: str) -> dict:
    status_code = getattr(error, "status_code", None)
    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code
    transport = isinstance(error, (httpx.TimeoutException, httpx.NetworkError, TimeoutError, ConnectionError))
    transient = transport or (isinstance(status_code, int) and status_code in TRANSIENT_HTTP)
    text = str(error)
    invalid = isinstance(error, ValueError) or any(
        marker in text for marker in ("응답 형식", "올바른 JSON", "항목 형식", "연속조회")
    )
    provider_error = isinstance(error, (KBOpenAPIError, TossOpenAPIError, NhPlugOpenAPIError,
                                       KISOpenAPIError, KiwoomOpenAPIError, httpx.HTTPStatusError))
    status = ("API_ERROR" if transient else "PARSE_ERROR" if invalid
              else "API_ERROR" if provider_error else "INTERNAL_ERROR")
    reason = (f"{provider}_HTTP_{status_code}" if isinstance(status_code, int)
              else f"{provider}_TRANSPORT_ERROR" if transport
              else f"{provider}_RESPONSE_INVALID" if invalid
              else f"{provider}_PROVIDER_OR_RESPONSE_ERROR" if provider_error
              else f"{provider}_FETCH_INTERNAL_ERROR")
    return {"status": status, "failure_reason": reason, "retryable": transient}


async def read_account_with_retry(read, provider: str, *, retry_transient: bool = False):
    """Reuse the KB contract: at most two fetches, with a deterministic short delay."""
    retry_info = {}
    for attempt in range(2 if retry_transient else 1):
        try:
            records = await read()
            if retry_info:
                retry_info["retry_recovered"] = True
            return records, retry_info
        except Exception as exc:
            diagnostic = failure_diagnostic(exc, provider)
            if retry_transient and attempt == 0 and diagnostic["retryable"]:
                retry_info = {"retry_attempted": True, "retry_recovered": False,
                              "initial_failure_reason": diagnostic["failure_reason"]}
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue
            exc.account_sync_diagnostic = {**diagnostic, **retry_info}
            raise


async def fetch_account_holdings(client, provider: str, *, retry_transient: bool = False):
    return await read_account_with_retry(client.sync_holdings, provider, retry_transient=retry_transient)


def get_failure_diagnostic(error: Exception) -> dict:
    """Find structured diagnostics across the existing HTTP boundary wrappers."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        diagnostic = getattr(error, "account_sync_diagnostic", None)
        if isinstance(diagnostic, dict):
            return diagnostic
        error = error.__cause__
    return {}


class AccountSyncPersistenceError(RuntimeError):
    """Canonical account state could not be saved; never retry account reads."""
