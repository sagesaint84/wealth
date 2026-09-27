from __future__ import annotations

import json
import math
import threading
import uuid
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.services.dividend_event_identity import normalize_dividend_code
from app.services.test_safety import assert_write_allowed


SCHEMA_VERSION = 1
STORAGE_FILENAME = "dividend_forecast_snapshots.json"
_LOCK = threading.RLock()


class DividendForecastSnapshotStorageError(RuntimeError):
    """Snapshot storage is unreadable or violates the versioned contract."""


def _get_user_dir(username: str | None = None) -> Path:
    from app.services.user_manager import get_user_data_dir

    return get_user_data_dir(username)


def _get_snapshot_file(username: str | None = None) -> Path:
    return _get_user_dir(username) / STORAGE_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _iso_date(value: object, field: str) -> str:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def _finite_number(value: object, field: str, *, allow_none: bool = True) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def _copy_present(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        if field in source:
            result[field] = deepcopy(source[field])
    return result


def _portfolio_basis(holdings: object) -> list[dict[str, Any]]:
    if not isinstance(holdings, list):
        raise ValueError("holdings must be a list")
    result: list[dict[str, Any]] = []
    for raw in holdings:
        if not isinstance(raw, dict):
            continue
        result.append(
            _copy_present(raw, ("code", "name", "currency", "quantity"))
        )
    return result


def _holding_forecasts(rows: object) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    fields = (
        "code",
        "name",
        "currency",
        "quantity",
        "annual_div_per_share",
        "annual_payout_orig",
        "annual_payout_krw",
        "payout_months",
        "is_etf",
        "forecast_source",
    )
    return [_copy_present(row, fields) for row in rows if isinstance(row, dict)]


def _monthly_schedule(schedule: object) -> list[dict[str, Any]]:
    if isinstance(schedule, dict):
        values = list(schedule.values())
    elif isinstance(schedule, list):
        values = schedule
    else:
        return []

    item_fields = (
        "code",
        "name",
        "quantity",
        "currency",
        "payout_orig",
        "payout_krw",
        "forecast_source",
        "event_identity",
        "event_identity_confidence",
        "record_date",
        "payment_date",
        "receipt_no",
        "source_event_id",
        "quantity_basis",
        "entitlement_confirmed",
    )
    result: list[dict[str, Any]] = []
    for raw in values:
        if not isinstance(raw, dict):
            continue
        try:
            month = int(raw.get("month"))
        except (TypeError, ValueError):
            continue
        if not 1 <= month <= 12:
            continue
        items = raw.get("items")
        copied_items = (
            [_copy_present(item, item_fields) for item in items if isinstance(item, dict)]
            if isinstance(items, list)
            else []
        )
        result.append(
            {
                "month": month,
                "total_krw": deepcopy(raw.get("total_krw")),
                "items": copied_items,
            }
        )
    result.sort(key=lambda item: item["month"])
    return result


def build_dividend_forecast_snapshot(
    forecast_summary: dict[str, Any],
    holdings: list[dict[str, Any]],
    *,
    as_of_date: str,
    owner: str = "모두",
    source: str = "manual",
    trigger: str = "manual",
    capture_fx_rate_usd_krw: float | None = None,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """Freeze an already-computed enriched forecast without recalculating it."""
    if not isinstance(forecast_summary, dict):
        raise ValueError("forecast_summary must be an object")
    as_of = _iso_date(as_of_date, "as_of_date")
    fx_rate = _finite_number(
        capture_fx_rate_usd_krw,
        "capture_fx_rate_usd_krw",
    )
    aggregate_fields = (
        "total_annual_dividend_krw",
        "monthly_avg_dividend_krw",
        "portfolio_yield",
        "dividend_paying_count",
    )
    return {
        "id": str(uuid.uuid4()),
        "schema_version": SCHEMA_VERSION,
        "captured_at": str(captured_at or _now_iso()),
        "as_of_date": as_of,
        "owner": str(owner or "모두").strip() or "모두",
        "source": str(source or "manual").strip() or "manual",
        "trigger": str(trigger or "manual").strip() or "manual",
        "capture_fx_rate_usd_krw": fx_rate,
        "portfolio_basis": _portfolio_basis(holdings),
        "forecast_aggregate": _copy_present(forecast_summary, aggregate_fields),
        "holding_forecasts": _holding_forecasts(
            forecast_summary.get("holding_dividends")
        ),
        "monthly_schedule": _monthly_schedule(
            forecast_summary.get("monthly_schedule")
        ),
        "forecast_source_policy": deepcopy(
            forecast_summary.get("forecast_source_policy")
        ),
    }


def _empty_storage() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "snapshots": [], "updated_at": None}


def _read_storage_unlocked(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_storage()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DividendForecastSnapshotStorageError(
            "dividend forecast snapshot storage is unreadable"
        ) from exc
    if (
        not isinstance(raw, dict)
        or raw.get("schema_version") != SCHEMA_VERSION
        or not isinstance(raw.get("snapshots"), list)
        or not all(isinstance(item, dict) for item in raw["snapshots"])
    ):
        raise DividendForecastSnapshotStorageError(
            "dividend forecast snapshot storage has an invalid structure"
        )
    return raw


def list_dividend_forecast_snapshots(
    username: str | None = None,
) -> list[dict[str, Any]]:
    with _LOCK:
        data = _read_storage_unlocked(_get_snapshot_file(username))
        return deepcopy(data["snapshots"])


def upsert_dividend_forecast_snapshot(
    snapshot: dict[str, Any],
    username: str | None = None,
) -> dict[str, Any]:
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("snapshot schema_version is unsupported")
    owner = str(snapshot.get("owner") or "").strip()
    as_of = _iso_date(snapshot.get("as_of_date"), "as_of_date")
    if not owner:
        raise ValueError("snapshot owner is required")

    path = _get_snapshot_file(username)
    with _LOCK:
        data = _read_storage_unlocked(path)
        replacement = deepcopy(snapshot)
        replacement["as_of_date"] = as_of
        existing_index: int | None = None
        for index, current in enumerate(data["snapshots"]):
            if (
                str(current.get("owner") or "") == owner
                and str(current.get("as_of_date") or "") == as_of
            ):
                existing_index = index
                replacement["id"] = current.get("id") or replacement.get("id")
                break
        if existing_index is None:
            data["snapshots"].append(replacement)
        else:
            data["snapshots"][existing_index] = replacement
        data["snapshots"].sort(
            key=lambda item: (
                str(item.get("as_of_date") or ""),
                str(item.get("owner") or ""),
            )
        )
        data["updated_at"] = _now_iso()
        path.parent.mkdir(parents=True, exist_ok=True)
        assert_write_allowed(path)
        temp_path = path.with_suffix(".json.tmp")
        try:
            temp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False),
                encoding="utf-8",
            )
            temp_path.replace(path)
        except (OSError, TypeError, ValueError) as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise DividendForecastSnapshotStorageError(
                "dividend forecast snapshot storage write failed"
            ) from exc
        return deepcopy(replacement)


def classify_forecast_source(item: dict[str, Any]) -> str:
    source = item.get("forecast_source")
    if isinstance(source, dict):
        source = source.get("numeric_source")
    normalized = str(source or "").strip()
    mapping = {
        "opendart_confirmed_disclosure": "opendart_confirmed",
        "kind_etf_distribution": "kind_confirmed",
        "opendart_historical_fill": "opendart_historical_fill",
        "yahoo_history": "yahoo_history",
        "naver": "naver_legacy",
        "legacy_fallback": "heuristic",
    }
    return mapping.get(normalized, "unknown")


def _gross_actual_krw(record: dict[str, Any]) -> float | None:
    gross = record.get("gross_amount")
    if gross is None or isinstance(gross, bool):
        return None
    try:
        amount = float(gross)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(amount) or amount < 0:
        return None
    currency = str(record.get("currency") or "KRW").strip().upper()
    if currency == "KRW":
        return amount
    if currency == "USD":
        fx = record.get("fx_rate")
        if isinstance(fx, bool):
            return None
        try:
            rate = float(fx)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(rate) or rate <= 0:
            return None
        return amount * rate
    return None


def _month_key(value: str) -> str | None:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return f"{parsed.year:04d}-{parsed.month:02d}"


def evaluate_dividend_forecast_snapshot(
    snapshot: dict[str, Any] | None,
    actual_records: list[dict[str, Any]],
    *,
    through_date: str,
) -> dict[str, Any]:
    """Evaluate a frozen snapshot only; this function performs no I/O or network work."""
    if not isinstance(snapshot, dict):
        return {
            "status": "historical_point_in_time_accuracy_unavailable",
            "reason": "snapshot_not_available",
        }
    if not isinstance(actual_records, list):
        raise ValueError("actual_records must be a list")
    snapshot_day = date.fromisoformat(str(snapshot.get("as_of_date") or ""))
    through_day = date.fromisoformat(through_date)
    current_month_start = date(through_day.year, through_day.month, 1)
    month_occurrences: list[tuple[int, int, str]] = []
    for offset in range(1, 13):
        zero_based = snapshot_day.month - 1 + offset
        year = snapshot_day.year + (zero_based // 12)
        month = (zero_based % 12) + 1
        month_start = date(year, month, 1)
        if month_start < current_month_start:
            month_occurrences.append((year, month, f"{year:04d}-{month:02d}"))
    evaluated_month_keys = [key for _, _, key in month_occurrences]
    if not month_occurrences:
        return {
            "status": "evaluation_horizon_unavailable",
            "snapshot_id": snapshot.get("id"),
            "evaluated_months": [],
            "historical_point_in_time_only": True,
            "network_access_used": False,
        }

    raw_schedule = snapshot.get("monthly_schedule") or []
    bucket_by_month: dict[int, dict[str, Any]] = {}
    for bucket in raw_schedule:
        if not isinstance(bucket, dict):
            continue
        try:
            month = int(bucket.get("month"))
        except (TypeError, ValueError):
            continue
        if 1 <= month <= 12:
            bucket_by_month[month] = bucket

    predicted: dict[tuple[str, int, int], dict[str, Any]] = {}
    monthly_bucket_results: list[dict[str, Any]] = []
    predicted_total = 0.0
    unattributed_total = 0.0
    forecast_attribution_complete = True
    for year, month, occurrence_key in month_occurrences:
        bucket = bucket_by_month.get(month)
        if bucket is None:
            monthly_bucket_results.append(
                {
                    "month": occurrence_key,
                    "bucket_total_krw": 0,
                    "attributed_item_krw": 0,
                    "unattributed_forecast_krw": 0,
                    "attribution_status": "bucket_missing",
                }
            )
            forecast_attribution_complete = False
            continue
        raw_bucket_total = _finite_number(bucket.get("total_krw"), "total_krw")
        bucket_total_valid = raw_bucket_total is not None and raw_bucket_total >= 0
        bucket_total = raw_bucket_total if bucket_total_valid else 0.0
        predicted_total += bucket_total
        attributed_item_total = 0.0
        item_amounts_valid = True
        for item in bucket.get("items") or []:
            if not isinstance(item, dict):
                continue
            code = normalize_dividend_code(item.get("code"))
            if code is None:
                item_amounts_valid = False
                continue
            payout_value = _finite_number(item.get("payout_krw"), "payout_krw")
            if payout_value is None or payout_value < 0:
                item_amounts_valid = False
                continue
            payout = payout_value
            attributed_item_total += payout
            key = (code, year, month)
            current = predicted.setdefault(
                key,
                {
                    "amount": 0.0,
                    "sources": set(),
                    "event_identities": [],
                },
            )
            current["amount"] += payout
            current["sources"].add(classify_forecast_source(item))
            identity = item.get("event_identity")
            if identity:
                current["event_identities"].append(str(identity))

        residual = max(0.0, bucket_total - attributed_item_total)
        unattributed_total += residual
        if not bucket_total_valid or not item_amounts_valid:
            attribution_status = "invalid_bucket_or_item_amount"
        elif attributed_item_total > bucket_total:
            attribution_status = "items_exceed_bucket_total"
        elif attributed_item_total < bucket_total:
            attribution_status = "unattributed_residual"
        else:
            attribution_status = "complete"
        bucket_complete = attribution_status == "complete"
        forecast_attribution_complete = (
            forecast_attribution_complete and bucket_complete
        )
        monthly_bucket_results.append(
            {
                "month": occurrence_key,
                "bucket_total_krw": round(bucket_total),
                "attributed_item_krw": round(attributed_item_total),
                "unattributed_forecast_krw": round(residual),
                "attribution_status": attribution_status,
            }
        )

    actual_timing: set[tuple[str, int, int]] = set()
    actual_gross: dict[tuple[str, int, int], float] = {}
    actual_identities: dict[tuple[str, int, int], set[str]] = {}
    gross_count = 0
    cash_only_count = 0
    for record in actual_records:
        if not isinstance(record, dict):
            continue
        if str(record.get("income_type") or "").strip() == "account_interest":
            continue
        date_text = str(record.get("date") or "")
        month_key = _month_key(date_text)
        if month_key not in evaluated_month_keys:
            continue
        code = normalize_dividend_code(record.get("code"))
        if code is None:
            continue
        year = int(month_key[:4])
        month = int(month_key[-2:])
        key = (code, year, month)
        actual_timing.add(key)
        actual_identity = str(record.get("event_identity") or "").strip()
        if actual_identity:
            actual_identities.setdefault(key, set()).add(actual_identity)
        gross = _gross_actual_krw(record)
        if gross is None:
            cash_only_count += 1
        else:
            gross_count += 1
            actual_gross[key] = actual_gross.get(key, 0.0) + gross

    keys = sorted(set(predicted) | actual_timing)
    monthly_results: list[dict[str, Any]] = []
    absolute_errors: list[float] = []
    actual_total = sum(actual_gross.values())
    identity_match_count = 0
    for code, year, month in keys:
        pred = predicted.get((code, year, month))
        predicted_amount = float(pred["amount"]) if pred else 0.0
        actual_amount = actual_gross.get((code, year, month), 0.0)
        if cash_only_count == 0 and forecast_attribution_complete:
            absolute_errors.append(abs(predicted_amount - actual_amount))
        sources = sorted(pred["sources"]) if pred else ["unknown"]
        source_class = sources[0] if len(sources) == 1 else "mixed"
        identities = list(dict.fromkeys(pred["event_identities"])) if pred else []
        identity_match = bool(
            set(identities) & actual_identities.get((code, year, month), set())
        )
        if identity_match:
            identity_match_count += 1
        monthly_results.append(
            {
                "month": f"{year:04d}-{month:02d}",
                "code": code,
                "predicted_krw": round(predicted_amount),
                "actual_payment_present": (code, year, month) in actual_timing,
                "payment_month_hit": predicted_amount > 0 and (code, year, month) in actual_timing,
                "actual_comparable_gross_krw": (
                    round(actual_amount)
                    if (code, year, month) in actual_gross
                    else None
                ),
                "source_class": source_class,
                "event_identity": identities[0] if len(identities) == 1 else None,
                "event_identities": identities,
                "actual_event_identity_match": identity_match,
            }
        )

    amount_complete = cash_only_count == 0 and forecast_attribution_complete
    error_sum = sum(absolute_errors) if amount_complete else None
    source_metrics: dict[str, dict[str, Any]] = {}
    if amount_complete and gross_count > 0:
        for row in monthly_results:
            source_class = row["source_class"]
            entry = source_metrics.setdefault(
                source_class,
                {"sample_count": 0, "predicted_krw": 0, "actual_gross_krw": 0},
            )
            entry["sample_count"] += 1
            entry["predicted_krw"] += row["predicted_krw"]
            entry["actual_gross_krw"] += row["actual_comparable_gross_krw"] or 0

    return {
        "status": "ok",
        "snapshot_id": snapshot.get("id"),
        "snapshot_as_of_date": snapshot_day.isoformat(),
        "through_date": through_day.isoformat(),
        "evaluated_months": evaluated_month_keys,
        "predicted_remaining_krw": round(predicted_total),
        "unattributed_forecast_krw": round(unattributed_total),
        "forecast_attribution_complete": forecast_attribution_complete,
        "actual_comparable_gross_krw": round(actual_total),
        "gross_comparable_record_count": gross_count,
        "cash_only_record_count": cash_only_count,
        "amount_accuracy_complete": amount_complete,
        "absolute_error_krw": (
            round(abs(predicted_total - actual_total)) if amount_complete else None
        ),
        "mae_krw": (
            round(error_sum / len(absolute_errors))
            if amount_complete and absolute_errors
            else None
        ),
        "wape_percent": (
            round((error_sum / actual_total) * 100.0, 2)
            if amount_complete and error_sum is not None and actual_total > 0
            else None
        ),
        "monthly_results": monthly_results,
        "monthly_bucket_results": monthly_bucket_results,
        "source_metrics": source_metrics,
        "official_event_identity_match_count": identity_match_count,
        "historical_point_in_time_only": True,
        "network_access_used": False,
        "current_month_excluded": True,
    }
