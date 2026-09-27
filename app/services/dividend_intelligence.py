"""Phase 10.5D Dividend Intelligence derived views and opt-in alerts.

The module consumes existing contracts instead of inventing new tax or dividend
rules: C-4 event identity, C-4.1 point-in-time evaluation, C-5 after-known-tax
screening, and B-1 individual family financial-income thresholds.
"""
from __future__ import annotations

import json
import math
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.services.dividend_event_identity import normalize_dividend_code
from app.services.test_safety import assert_write_allowed

ALERT_STATE_VERSION = 1
ALERT_STATE_FILENAME = "dividend_intelligence_alert_state.json"
ALERT_STATE_RETENTION = 256


def _number(value: object, default: float = 0.0) -> float:
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _won(value: object) -> int:
    return int(round(max(_number(value), 0.0)))


def _pct(numerator: float, denominator: float) -> float | None:
    return round((numerator / denominator) * 100.0, 4) if denominator > 0 else None


def _instrument_key(code: object, currency: object) -> tuple[str, str] | None:
    normalized = normalize_dividend_code(code)
    currency_text = str(currency or "").strip().upper()
    if normalized is None or not currency_text:
        return None
    return normalized, currency_text


def _https_url(value: object) -> str | None:
    text = str(value or "").strip()
    return text if text.startswith("https://") else None


def _source_evidence(row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("forecast_source")
    source = source if isinstance(source, dict) else {}
    numeric = str(source.get("numeric_source") or "legacy_fallback").strip()
    kind_applied = int(_number(source.get("kind_etf_numeric_override_count")))
    confirmed_applied = source.get("confirmed_numeric_override") is True or kind_applied > 0
    confirmed_evidence = (
        source.get("confirmed_amount") is True
        or int(_number(source.get("kind_etf_confirmed_event_count"))) > 0
    )
    official_available = source.get("official_data_available") is True

    if confirmed_applied:
        level, label = "official_confirmed_applied", "공식 확정금액 반영"
    elif confirmed_evidence:
        level, label = "official_confirmed_evidence", "공식 확정 근거 · 금액 미반영"
    elif official_available:
        level, label = "official_evidence", "공식 근거 확인"
    elif numeric == "opendart_historical_fill":
        level, label = "official_history_estimate", "공식 과거이력 기반 추정"
    elif numeric == "yahoo_history":
        level, label = "history_estimate", "최근 배당이력 기반 추정"
    elif numeric == "naver":
        level, label = "market_estimate", "시장 데이터 기반 추정"
    else:
        level, label = "heuristic", "휴리스틱 추정"

    url = None
    receipt_no = None
    for candidate in (
        source.get("structured_decision_disclosure"),
        source.get("recent_decision_disclosure"),
    ):
        if not isinstance(candidate, dict):
            continue
        if url is None:
            url = _https_url(candidate.get("viewer_url"))
        receipt_no = receipt_no or str(candidate.get("receipt_no") or "").strip() or None

    distributions = source.get("kind_etf_distributions")
    if url is None and isinstance(distributions, list):
        for event in distributions:
            if not isinstance(event, dict):
                continue
            url = (
                _https_url(event.get("viewer_url"))
                or _https_url(event.get("source_url"))
                or _https_url(event.get("document_url"))
            )
            if url:
                receipt_no = str(event.get("receipt_no") or "").strip() or receipt_no
                break
    if url is None:
        url = _https_url(source.get("kind_reference_url")) or _https_url(
            source.get("opendart_reference_url")
        )

    return {
        "level": level,
        "label": label,
        "numeric_source": numeric,
        "official_data_available": official_available,
        "confirmed_amount": confirmed_evidence,
        "confirmed_numeric_override": confirmed_applied,
        "evidence_url": url,
        "receipt_no": receipt_no,
    }


def _best_evidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = {
        "level": "unknown",
        "label": "근거 확인 불가",
        "numeric_source": "unknown",
        "official_data_available": False,
        "confirmed_amount": False,
        "confirmed_numeric_override": False,
        "evidence_url": None,
        "receipt_no": None,
    }
    if not rows:
        return fallback
    rank = {
        "official_confirmed_applied": 6,
        "official_confirmed_evidence": 5,
        "official_evidence": 4,
        "official_history_estimate": 3,
        "history_estimate": 2,
        "market_estimate": 1,
        "heuristic": 0,
    }
    return max(
        (_source_evidence(row) for row in rows),
        key=lambda item: rank.get(item["level"], -1),
    )


def _group_rows(
    rows: object, *, forecast: bool = False
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    if not isinstance(rows, list):
        return grouped
    for row in rows:
        if not isinstance(row, dict):
            continue
        currency = row.get("currency") or "KRW"
        key = _instrument_key(row.get("code"), currency)
        if key is not None:
            grouped.setdefault(key, []).append(row)
    return grouped


def _account_label(row: dict[str, Any], index: int) -> str:
    broker = str(
        row.get("broker")
        or row.get("broker_name")
        or row.get("securities_company")
        or ""
    ).strip()
    account = str(
        row.get("account_name")
        or row.get("account_label")
        or row.get("account_id")
        or row.get("account")
        or ""
    ).strip()
    owner = str(row.get("owner") or "").strip()
    parts = [item for item in (broker, account) if item]
    if not parts and owner:
        parts = [owner]
    return " · ".join(parts) if parts else f"계좌 행 {index + 1}"


def _allocate_accounts(
    instrument: dict[str, Any], holdings: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    rows = [row for row in holdings if _number(row.get("quantity")) > 0]
    total_quantity = sum(_number(row.get("quantity")) for row in rows)
    if not rows or total_quantity <= 0:
        return "unavailable", []

    gross_total = _won(instrument.get("gross_annual_dividend_krw"))
    calculated = instrument.get("calculation_status") == "calculated"
    tax_total = _won(instrument.get("known_tax_krw")) if calculated else None
    cash_total = _won(instrument.get("after_known_tax_cash_krw")) if calculated else None
    assigned_gross = assigned_tax = assigned_cash = 0
    result: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        quantity = _number(row.get("quantity"))
        ratio = quantity / total_quantity
        last = index == len(rows) - 1
        if last:
            gross = gross_total - assigned_gross
            tax = tax_total - assigned_tax if tax_total is not None else None
            cash = cash_total - assigned_cash if cash_total is not None else None
        else:
            gross = _won(gross_total * ratio)
            tax = _won(tax_total * ratio) if tax_total is not None else None
            cash = _won(cash_total * ratio) if cash_total is not None else None
            assigned_gross += gross
            assigned_tax += tax or 0
            assigned_cash += cash or 0
        market = _won(row.get("market_value_krw"))
        cost = _won(row.get("cost_value_krw"))
        result.append(
            {
                "account_label": _account_label(row, index),
                "account_id": str(row.get("account_id") or "").strip() or None,
                "owner": str(row.get("owner") or "").strip() or None,
                "quantity": quantity,
                "quantity_share_pct": round(ratio * 100.0, 4),
                "market_value_krw": market,
                "cost_value_krw": cost,
                "gross_annual_dividend_krw": gross,
                "known_tax_krw": tax,
                "after_known_tax_cash_krw": cash,
                "gross_yield_market_pct": _pct(gross, market),
                "after_known_tax_yield_market_pct": _pct(cash, market) if cash is not None else None,
                "gross_yield_cost_pct": _pct(gross, cost),
                "after_known_tax_yield_cost_pct": _pct(cash, cost) if cash is not None else None,
                "attribution_basis": "current_holding_quantity",
                "entitlement_confirmed": False,
            }
        )
    return "estimated_current_holding_allocation", result


def _instrument_views(
    summary: dict[str, Any], holdings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    after_tax = summary.get("portfolio_after_tax")
    instruments = after_tax.get("instruments") if isinstance(after_tax, dict) else None
    if not isinstance(instruments, list):
        return []
    forecast_map = _group_rows(summary.get("holding_dividends"), forecast=True)
    holding_map = _group_rows(holdings)
    canonical_gross = _number(after_tax.get("gross_annual_dividend_krw"))
    calculable_cash = _number(after_tax.get("calculable_after_known_tax_cash_krw"))
    result: list[dict[str, Any]] = []
    for raw in instruments:
        if not isinstance(raw, dict):
            continue
        row = deepcopy(raw)
        key = _instrument_key(row.get("code"), row.get("currency"))
        gross = _number(row.get("gross_annual_dividend_krw"))
        cash = (
            _number(row.get("after_known_tax_cash_krw"))
            if row.get("calculation_status") == "calculated"
            else None
        )
        status, accounts = _allocate_accounts(row, holding_map.get(key, []) if key else [])
        row["gross_portfolio_contribution_pct"] = _pct(gross, canonical_gross)
        row["calculable_after_known_tax_contribution_pct"] = (
            _pct(cash, calculable_cash) if cash is not None else None
        )
        row["forecast_evidence"] = _best_evidence(
            forecast_map.get(key, []) if key else []
        )
        row["account_attribution_status"] = status
        row["account_attribution_basis"] = "current_holding_quantity" if accounts else None
        row["account_entitlement_confirmed"] = False if accounts else None
        row["accounts"] = accounts
        result.append(row)
    return result


def _trust_summary(summary: dict[str, Any]) -> dict[str, Any]:
    rows = summary.get("holding_dividends")
    rows = rows if isinstance(rows, list) else []
    counts: dict[str, int] = {}
    for row in rows:
        if isinstance(row, dict):
            level = _source_evidence(row)["level"]
            counts[level] = counts.get(level, 0) + 1
    after_tax = summary.get("portfolio_after_tax")
    residual = _won(after_tax.get("unattributed_annual_dividend_krw")) if isinstance(after_tax, dict) else 0
    official_levels = (
        "official_confirmed_applied",
        "official_confirmed_evidence",
        "official_evidence",
        "official_history_estimate",
    )
    estimated_levels = ("history_estimate", "market_estimate", "heuristic", "unknown")
    return {
        "instrument_count": sum(counts.values()),
        "level_counts": counts,
        "official_confirmed_applied_count": counts.get("official_confirmed_applied", 0),
        "official_evidence_count": sum(counts.get(level, 0) for level in official_levels),
        "estimated_or_heuristic_count": sum(counts.get(level, 0) for level in estimated_levels),
        "unattributed_residual_krw": residual,
        "residual_assigned_to_instrument": False,
    }


def _accuracy_summary(
    username: str | None, *, as_of: date, owner: str
) -> dict[str, Any]:
    if not username:
        return {"status": "unavailable", "reason": "username_unavailable", "historical_point_in_time_only": True}
    try:
        from app.services.dividend_forecast_snapshots import (
            evaluate_dividend_forecast_snapshot,
            list_dividend_forecast_snapshots,
        )
        from app.services.dividend_records import read_dividend_records

        snapshots = [
            item
            for item in list_dividend_forecast_snapshots(username)
            if isinstance(item, dict) and str(item.get("owner") or "모두") == owner
        ]
        actual_records = read_dividend_records(username)
    except Exception:
        return {"status": "unavailable", "reason": "accuracy_storage_unavailable", "historical_point_in_time_only": True}
    snapshots.sort(
        key=lambda item: (str(item.get("as_of_date") or ""), str(item.get("captured_at") or "")),
        reverse=True,
    )
    if not snapshots:
        return {"status": "accumulating", "reason": "snapshot_not_available", "snapshot_count": 0, "scope_owner": owner, "historical_point_in_time_only": True}

    fallback: dict[str, Any] | None = None
    for snapshot in snapshots:
        try:
            evaluated = evaluate_dividend_forecast_snapshot(
                snapshot, actual_records, through_date=as_of.isoformat()
            )
        except Exception:
            continue
        fallback = fallback or evaluated
        if evaluated.get("status") == "ok" and evaluated.get("evaluated_months"):
            months = list(evaluated.get("evaluated_months") or [])
            return {
                "status": "ready",
                "scope_owner": owner,
                "snapshot_count": len(snapshots),
                "snapshot_id": evaluated.get("snapshot_id"),
                "snapshot_as_of_date": evaluated.get("snapshot_as_of_date"),
                "through_date": evaluated.get("through_date"),
                "evaluated_months": months,
                "evaluated_month_count": len(months),
                "amount_accuracy_complete": evaluated.get("amount_accuracy_complete") is True,
                "mae_krw": evaluated.get("mae_krw"),
                "wape_percent": evaluated.get("wape_percent"),
                "absolute_error_krw": evaluated.get("absolute_error_krw"),
                "predicted_remaining_krw": evaluated.get("predicted_remaining_krw"),
                "actual_comparable_gross_krw": evaluated.get("actual_comparable_gross_krw"),
                "gross_comparable_record_count": evaluated.get("gross_comparable_record_count"),
                "cash_only_record_count": evaluated.get("cash_only_record_count"),
                "forecast_attribution_complete": evaluated.get("forecast_attribution_complete"),
                "official_event_identity_match_count": evaluated.get("official_event_identity_match_count"),
                "source_metrics": deepcopy(evaluated.get("source_metrics") or {}),
                "historical_point_in_time_only": True,
                "current_month_excluded": True,
            }
    return {
        "status": "accumulating",
        "reason": str((fallback or {}).get("status") or "evaluation_horizon_unavailable"),
        "scope_owner": owner,
        "snapshot_count": len(snapshots),
        "latest_snapshot_as_of_date": snapshots[0].get("as_of_date"),
        "evaluated_months": list((fallback or {}).get("evaluated_months") or []),
        "historical_point_in_time_only": True,
        "current_month_excluded": True,
    }


def build_dividend_intelligence_summary(
    summary: dict[str, Any],
    holdings: list[dict[str, Any]],
    *,
    username: str | None = None,
    as_of: date | datetime | None = None,
    owner: str = "모두",
) -> dict[str, Any]:
    if not isinstance(summary, dict) or not isinstance(holdings, list):
        raise ValueError("DIVIDEND_INTELLIGENCE_INPUT_INVALID")
    day = as_of.date() if isinstance(as_of, datetime) else (as_of or date.today())
    owner_text = str(owner or "모두")
    return {
        "schema_version": 1,
        "as_of_date": day.isoformat(),
        "owner": owner_text,
        "trust": _trust_summary(summary),
        "instruments": _instrument_views(summary, holdings),
        "accuracy": _accuracy_summary(username, as_of=day, owner=owner_text),
        "contracts": {
            "canonical_gross_total_unchanged": True,
            "account_attribution_basis": "current_holding_quantity",
            "account_entitlement_confirmed": False,
            "residual_assigned_to_instrument": False,
            "after_known_tax_scope": "existing_verified_investment_tax_screening",
            "screening_only": True,
        },
    }


def _alert_state_path(username: str) -> Path:
    from app.services.user_manager import get_user_data_dir

    return get_user_data_dir(username) / ALERT_STATE_FILENAME


def _read_alert_state(username: str) -> dict[str, Any]:
    path = _alert_state_path(username)
    if not path.exists():
        return {"version": ALERT_STATE_VERSION, "sent_event_keys": [], "updated_at": None}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"version": ALERT_STATE_VERSION, "sent_event_keys": [], "updated_at": None}
    keys = raw.get("sent_event_keys") if isinstance(raw, dict) else None
    if not isinstance(raw, dict) or raw.get("version") != ALERT_STATE_VERSION or not isinstance(keys, list):
        return {"version": ALERT_STATE_VERSION, "sent_event_keys": [], "updated_at": None}
    return {
        "version": ALERT_STATE_VERSION,
        "sent_event_keys": [str(value) for value in keys if isinstance(value, str) and value.strip()][-ALERT_STATE_RETENTION:],
        "updated_at": raw.get("updated_at"),
    }


def _write_alert_state(username: str, state: dict[str, Any]) -> None:
    path = _alert_state_path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert_write_allowed(path)
    keys = list(dict.fromkeys(state.get("sent_event_keys") or []))[-ALERT_STATE_RETENTION:]
    payload = {
        "version": ALERT_STATE_VERSION,
        "sent_event_keys": keys,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    temp = path.with_suffix(".tmp")
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temp.replace(path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def _alert_opted_in(username: str) -> bool:
    try:
        from app.services.settings import get_effective_settings

        settings = get_effective_settings(username, include_automation_status=False)
    except Exception:
        return False
    automation = settings.get("automation")
    config = automation.get("dividend_intelligence_alerts") if isinstance(automation, dict) else None
    return isinstance(config, dict) and config.get("enabled") is True


def _official_alert_events(username: str, snapshot: dict[str, Any]) -> list[Any]:
    from app.services.notifications.models import NotificationEvent

    confirmed_receipts: set[str] = set()
    events: list[NotificationEvent] = []
    for bucket in snapshot.get("monthly_schedule") or []:
        if not isinstance(bucket, dict):
            continue
        for item in bucket.get("items") or []:
            if not isinstance(item, dict) or item.get("event_identity_confidence") != "official":
                continue
            identity = str(item.get("event_identity") or "").strip()
            source = str(item.get("forecast_source") or "").strip()
            if not identity or source not in {"opendart_confirmed_disclosure", "kind_etf_distribution"}:
                continue
            receipt = str(item.get("receipt_no") or item.get("source_event_id") or "").strip()
            if receipt:
                confirmed_receipts.add(receipt)
            code = str(item.get("code") or "").strip()
            name = str(item.get("name") or code).strip() or code
            payment = str(item.get("payment_date") or "").strip()
            amount = _won(item.get("payout_krw"))
            events.append(
                NotificationEvent(
                    event_key=f"dividend_intelligence:confirmed:{identity}",
                    event_type="dividend_confirmed_forecast",
                    body=(
                        f"{name} ({code}) 공식 배당/분배금 근거가 예상금액에 반영됐습니다.\n"
                        f"현재 보유수량 기준 예상: {amount:,}원"
                        + (f"\n지급예정일: {payment}" if payment else "")
                        + "\n현재 보유수량 기준 계산이며 배당 권리(entitlement) 확정 의미는 아닙니다."
                    ),
                    username=username,
                    title="Wealth 공식 배당금 반영",
                    metadata={
                        "code": code,
                        "event_identity": identity,
                        "payment_date": payment or None,
                        "payout_krw": amount,
                        "entitlement_confirmed": False,
                    },
                )
            )

    for row in snapshot.get("holding_forecasts") or []:
        if not isinstance(row, dict):
            continue
        source = row.get("forecast_source")
        recent = source.get("recent_decision_disclosure") if isinstance(source, dict) else None
        if not isinstance(recent, dict):
            continue
        receipt = str(recent.get("receipt_no") or "").strip()
        code = str(row.get("code") or "").strip()
        if not receipt or not code or receipt in confirmed_receipts:
            continue
        name = str(row.get("name") or code).strip() or code
        events.append(
            NotificationEvent(
                event_key=f"dividend_intelligence:disclosure:{code}:{receipt}",
                event_type="dividend_official_disclosure",
                body=(
                    f"{name} ({code})의 최근 배당결정 공시가 확인됐습니다.\n"
                    "공시 존재 확인과 미래 확정금액 반영은 별개입니다. 구조 검증된 금액만 forecast에 확정 반영합니다."
                ),
                username=username,
                title="Wealth 배당 공시 확인",
                action_url=_https_url(recent.get("viewer_url")),
                action_label="공시 원문",
                metadata={"code": code, "receipt_no": receipt, "confirmed_amount": False},
            )
        )
    return events


def _member_threshold_event(
    username: str, year: int, member: dict[str, Any]
) -> Any | None:
    """Build one alert from an existing *individual* B-1 threshold result."""
    from app.services.notifications.models import NotificationEvent

    owner = str(member.get("owner") or "").strip()
    if not owner or owner == "모두":
        return None
    projected = member.get("projected_gross_screening_income_krw")
    thresholds = member.get("thresholds")
    if projected is None or not isinstance(thresholds, dict):
        return None
    watch_state = thresholds.get("watch")
    comp_state = thresholds.get("comprehensive_tax")
    if not isinstance(comp_state, dict):
        return None

    threshold = comp_state.get("threshold_krw")
    remaining = comp_state.get("remaining_krw")
    if comp_state.get("exceeded") is True:
        state = "exceeded"
        event_type = "financial_income_threshold_exceeded"
        headline = f"{owner} 예상 금융소득이 {_won(threshold):,}원 기준을 초과했습니다."
    elif comp_state.get("at_or_above") is True:
        state = "reached"
        event_type = "financial_income_threshold_reached"
        headline = f"{owner} 예상 금융소득이 {_won(threshold):,}원 기준에 도달했습니다."
    elif isinstance(watch_state, dict) and watch_state.get("at_or_above") is True:
        state = "watch"
        event_type = "financial_income_watch_reached"
        headline = f"{owner} 예상 금융소득이 주의 기준 {_won(watch_state.get('threshold_krw')):,}원에 도달했습니다."
    else:
        return None

    return NotificationEvent(
        event_key=f"dividend_intelligence:financial_income:{username}:{year}:{owner}:{state}",
        event_type=event_type,
        body=(
            f"{headline}\n"
            f"예상 금융소득: {_won(projected):,}원\n"
            f"종합과세 screening 기준까지 남은 금액: {_won(remaining):,}원\n"
            "개인별 Wealth 자산관리 screening이며 최종 종합소득세 판단은 아닙니다."
        ),
        username=username,
        title="Wealth 금융소득 알림",
        metadata={
            "owner": owner,
            "year": year,
            "state": state,
            "projected_gross_screening_income_krw": _won(projected),
            "threshold_krw": _won(threshold),
            "remaining_krw": _won(remaining),
            "individual_threshold_only": True,
            "screening_only": True,
        },
    )


def _dispatch_events(username: str, events: list[Any]) -> dict[str, Any]:
    from app.services.notifications.service import UserNotificationService

    state = _read_alert_state(username)
    sent_keys = list(state.get("sent_event_keys") or [])
    sent_set = set(sent_keys)
    pending = [event for event in events if event.event_key not in sent_set]
    if not pending:
        return {"status": "no_new_events", "candidate_count": len(events), "sent_count": 0}
    service = UserNotificationService(username)
    sent_count = 0
    attempted = 0
    statuses: list[str] = []
    for event in pending:
        attempted += 1
        try:
            report = service.dispatch(event)
        except Exception:
            statuses.append("failed")
            continue
        statuses.append(report.status)
        if report.notifications_sent_count > 0:
            sent_count += 1
            sent_keys.append(event.event_key)
            sent_set.add(event.event_key)
    if sent_count:
        state["sent_event_keys"] = sent_keys
        try:
            _write_alert_state(username, state)
        except Exception:
            return {
                "status": "sent_state_unavailable",
                "candidate_count": len(events),
                "attempted_count": attempted,
                "sent_count": sent_count,
            }
    if sent_count == attempted and attempted > 0:
        status = "sent"
    elif sent_count > 0:
        status = "partial"
    elif statuses and all(item == "disabled" for item in statuses):
        status = "providers_disabled"
    else:
        status = "not_sent"
    return {
        "status": status,
        "candidate_count": len(events),
        "attempted_count": attempted,
        "sent_count": sent_count,
    }


def dispatch_scheduled_dividend_intelligence_alerts(
    username: str, snapshot: dict[str, Any]
) -> dict[str, Any]:
    """Send scheduled official-evidence alerts only; family thresholds are separate."""
    if not username or not isinstance(snapshot, dict):
        return {"status": "skipped", "reason": "invalid_input", "sent_count": 0}
    if str(snapshot.get("trigger") or "") != "scheduled":
        return {"status": "skipped", "reason": "not_scheduled", "sent_count": 0}
    if not _alert_opted_in(username):
        return {"status": "disabled", "reason": "not_opted_in", "sent_count": 0}
    return _dispatch_events(username, _official_alert_events(username, snapshot))


def dispatch_family_financial_income_alerts(
    username: str, family_risk: dict[str, Any]
) -> dict[str, Any]:
    """Send opt-in B-1 member alerts without ever thresholding the family total."""
    if not username or not isinstance(family_risk, dict):
        return {"status": "skipped", "reason": "invalid_input", "sent_count": 0}
    if not _alert_opted_in(username):
        return {"status": "disabled", "reason": "not_opted_in", "sent_count": 0}
    try:
        year = int(family_risk.get("year"))
    except (TypeError, ValueError):
        return {"status": "skipped", "reason": "year_unavailable", "sent_count": 0}
    members = family_risk.get("members")
    if not isinstance(members, list):
        return {"status": "skipped", "reason": "members_unavailable", "sent_count": 0}
    events = [
        event
        for member in members
        if isinstance(member, dict)
        for event in [_member_threshold_event(username, year, member)]
        if event is not None
    ]
    return _dispatch_events(username, events)


__all__ = [
    "build_dividend_intelligence_summary",
    "dispatch_family_financial_income_alerts",
    "dispatch_scheduled_dividend_intelligence_alerts",
]
