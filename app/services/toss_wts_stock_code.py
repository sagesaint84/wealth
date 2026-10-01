"""Canonical stock-code projection for Toss WTS provider identifiers."""

from __future__ import annotations

import re
from typing import Any


_KR_PROVIDER_CODE_RE = re.compile(r"^A([0-9A-Z]{6})$")


def canonicalize_toss_wts_stock_code(market: Any, stock_code: Any) -> str:
    """Return the Wealth display/storage code while preserving provider identity elsewhere.

    Toss WTS prefixes Korean security short codes with ``A``.  Korean short
    codes can be six alphanumeric characters (for example ``091160`` and
    ``0193T0``), so only the exact Korean ``A`` + six uppercase alphanumeric
    shape is normalized.  Other markets and other shapes are returned intact.
    """
    normalized_market = str(market or "").strip().lower()
    code = str(stock_code or "").strip()
    if normalized_market == "kr":
        matched = _KR_PROVIDER_CODE_RE.fullmatch(code)
        if matched:
            return matched.group(1)
    return code
