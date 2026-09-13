"""Common Wealth-side accounting choices for broker realized-P/L imports.

Provider canonical rows and fingerprints deliberately remain outside this module.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Mapping


GENERAL = "general"
IPO = "ipo"
DEFAULT_IPO_SUBSCRIPTION_FEE_KRW = 2000


class BrokerRealizedImportError(ValueError):
    pass


def has_wealth_import_preferences(selected_items: list[Mapping[str, Any]]) -> bool:
    return any(isinstance(item, Mapping) and "wealth_import" in item for item in selected_items)


def normalize_wealth_import_preference(item: Mapping[str, Any]) -> dict[str, Any]:
    raw = item.get("wealth_import")
    if raw is None:
        return {"stock_type": GENERAL, "ipo_subscription_fee_krw": 0}
    if not isinstance(raw, Mapping):
        raise BrokerRealizedImportError("INVALID_WEALTH_IMPORT_METADATA")
    stock_type = str(raw.get("stock_type") or GENERAL).strip().lower()
    if stock_type not in {GENERAL, IPO}:
        raise BrokerRealizedImportError("INVALID_STOCK_TYPE")
    if stock_type == GENERAL:
        return {"stock_type": GENERAL, "ipo_subscription_fee_krw": 0}

    fee_raw = raw.get("ipo_subscription_fee_krw", DEFAULT_IPO_SUBSCRIPTION_FEE_KRW)
    if fee_raw is None or isinstance(fee_raw, bool) or str(fee_raw).strip() == "":
        raise BrokerRealizedImportError("IPO_SUBSCRIPTION_FEE_REQUIRED")
    try:
        fee = Decimal(str(fee_raw).strip())
    except (InvalidOperation, ValueError) as exc:
        raise BrokerRealizedImportError("INVALID_IPO_SUBSCRIPTION_FEE") from exc
    if not fee.is_finite() or fee < 0 or fee != fee.to_integral_value():
        raise BrokerRealizedImportError("INVALID_IPO_SUBSCRIPTION_FEE")
    return {"stock_type": IPO, "ipo_subscription_fee_krw": int(fee)}


def normalized_wealth_import_preferences(
    selected_items: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [normalize_wealth_import_preference(item) for item in selected_items]


def compute_wealth_import_items_hash(
    provider_items_hash: str, selected_items: list[Mapping[str, Any]],
) -> str:
    """Bind per-row Wealth choices to their provider-signed selection tokens."""
    pairs: list[list[Any]] = []
    for item, preference in zip(selected_items, normalized_wealth_import_preferences(selected_items)):
        token = str(item.get("selection_token") or "") if isinstance(item, Mapping) else ""
        pairs.append([token, preference["stock_type"], preference["ipo_subscription_fee_krw"]])
    payload = [str(provider_items_hash), sorted(pairs, key=lambda value: json.dumps(value, separators=(",", ":")))]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ipo_fee_memo_annotation(fee_krw: int) -> str:
    if fee_krw == 2000:
        return "공모수수료 2천원 차감"
    return f"공모수수료 {fee_krw}원 차감"


def _append_memo(existing: Any, annotation: str) -> str:
    memo = str(existing or "").strip()
    if not memo:
        return annotation
    if annotation in memo:
        return memo
    return f"{memo} · {annotation}"


def _finite_decimal(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise BrokerRealizedImportError("MISSING_PROVIDER_REALIZED_PNL")
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise BrokerRealizedImportError("INVALID_PROVIDER_REALIZED_PNL") from exc
    if not number.is_finite():
        raise BrokerRealizedImportError("INVALID_PROVIDER_REALIZED_PNL")
    return number


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def apply_wealth_import_preferences(
    preview_result: dict[str, Any], selected_items: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply preview-authorized Wealth metadata without changing provider identity."""
    preferences = normalized_wealth_import_preferences(selected_items)
    items = preview_result.get("items")
    if not isinstance(items, list):
        raise BrokerRealizedImportError("INVALID_PREVIEW_RESULT")
    for result_item in items:
        if not isinstance(result_item, dict):
            continue
        index = result_item.get("index")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(preferences):
            continue
        preference = preferences[index]
        candidate = result_item.get("candidate")
        if not isinstance(candidate, dict):
            continue
        adjusted = dict(candidate)
        provider_pnl = _finite_decimal(candidate.get("pnl"))
        provider_text = _decimal_text(provider_pnl)
        stock_type = preference["stock_type"]
        fee = preference["ipo_subscription_fee_krw"]
        if stock_type == IPO:
            if str(candidate.get("currency") or "").upper() != "KRW" or candidate.get("pnl_krw") is None:
                raise BrokerRealizedImportError("IPO_FEE_REQUIRES_KRW_PNL")
            final_pnl = provider_pnl - Decimal(fee)
            final_text = _decimal_text(final_pnl)
            annotation = ipo_fee_memo_annotation(fee)
            adjusted.update({
                "asset_type": "ipo",
                "is_ipo": True,
                "ipo_subscription_fee_krw": fee,
                "provider_realized_pnl": provider_text,
                "pnl": final_text,
                "pnl_krw": final_text,
                "memo": _append_memo(candidate.get("memo"), annotation),
            })
        else:
            annotation = ""
            final_text = provider_text
            adjusted.update({
                "asset_type": "stock",
                "is_ipo": False,
                "ipo_subscription_fee_krw": 0,
                "provider_realized_pnl": provider_text,
            })
        result_item["candidate"] = adjusted
        result_item["wealth_import"] = {
            "stock_type": stock_type,
            "ipo_subscription_fee_krw": fee,
            "provider_realized_pnl": provider_text,
            "final_wealth_pnl": final_text,
            "memo_annotation": annotation,
            "memo": adjusted.get("memo", ""),
        }
    return preview_result
