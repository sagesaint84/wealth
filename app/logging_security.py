"""Redact credential query parameters while retaining useful HTTP diagnostics."""

from __future__ import annotations

import logging
import re
import traceback


_CREDENTIAL_QUERY = re.compile(
    r"([?&](?:crtfc_key|api_key|apikey|appkey|appsecret|access_token|client_secret|token)=)"
    r"([^\s&#\"'<>]*)",
    re.IGNORECASE,
)


def redact_credential_urls(text: str) -> str:
    return _CREDENTIAL_QUERY.sub(r"\1[REDACTED]", text)


def install_credential_log_redaction() -> None:
    """Protect records before any handler (including httpx INFO) can emit them.

    Chain the existing factory so logging configuration and request diagnostics
    remain intact. Exception chains need the same treatment as message URLs.
    """
    previous = logging.getLogRecordFactory()
    if getattr(previous, "_wealth_credential_redaction", False):
        return

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        message = record.getMessage()
        redacted = redact_credential_urls(message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        if record.exc_info:
            formatted = "".join(traceback.format_exception(*record.exc_info))
            redacted_exception = redact_credential_urls(formatted)
            if redacted_exception != formatted:
                record.exc_text = redacted_exception.rstrip()
                record.exc_info = None
        if record.stack_info:
            record.stack_info = redact_credential_urls(record.stack_info)
        return record

    factory._wealth_credential_redaction = True
    logging.setLogRecordFactory(factory)
