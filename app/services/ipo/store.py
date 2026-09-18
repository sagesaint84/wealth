import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.ipo.identity import find_matching_ipo, generate_ipo_id
from app.services.ipo.models import IpoRecord

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "data" / "ipo"

_STORE_LOCK = threading.RLock()


class IpoStorageError(RuntimeError):
    """Raised when IPO market store is corrupt or unreadable."""


def get_ipo_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "cache").mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def get_market_file() -> Path:
    return get_ipo_data_dir() / "market.json"


def get_score_snapshots_file() -> Path:
    return get_ipo_data_dir() / "score_snapshots.json"


def get_notification_state_file() -> Path:
    return get_ipo_data_dir() / "notification_state.json"


def default_market_store() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": datetime.now().astimezone().isoformat(),
        "ipos": [],
    }


def _read_market_store_unlocked() -> dict[str, Any]:
    f = get_market_file()
    if not f.exists():
        initial = default_market_store()
        _write_market_store_unlocked(initial)
        return initial

    try:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IpoStorageError(f"IPO market store at {f} is unreadable or corrupt") from exc

    if not isinstance(data, dict) or "schema_version" not in data or not isinstance(data.get("ipos"), list):
        raise IpoStorageError(f"IPO market store at {f} has an invalid schema")

    return data


def _write_market_store_unlocked(data: dict[str, Any]) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("ipos"), list):
        raise IpoStorageError("Refusing to write invalid IPO market store")

    f = get_market_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().astimezone().isoformat()
    data.setdefault("schema_version", 1)

    temp_path = f.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    temp_path.replace(f)


def read_market_store() -> dict[str, Any]:
    with _STORE_LOCK:
        return _read_market_store_unlocked()


def write_market_store(data: dict[str, Any]) -> None:
    with _STORE_LOCK:
        _write_market_store_unlocked(data)


def upsert_ipo_record(incoming: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Upsert an incoming IPO record into the canonical market store atomically.

    Guarantees:
    - Entire read-merge-write sequence is guarded by _STORE_LOCK.
    - Existing features with status == 'ok' and a valid value (including 0.0) are preserved
      if incoming feature status is 'parse_error', 'source_error', or 'schema_mismatch'.
    - 0.0 is an authoritative valid number and never treated as None/missing.

    Returns:
        (saved_record, review_required)
    """
    with _STORE_LOCK:
        store = _read_market_store_unlocked()
        existing_list = store.get("ipos", [])

        matched, review_required = find_matching_ipo(incoming, existing_list)
        if review_required:
            return incoming, True

        now_iso = datetime.now().astimezone().isoformat()

        if matched is not None:
            # Merge incoming into matched
            for k, v in incoming.items():
                if k == "features" and isinstance(v, dict):
                    existing_feats = matched.setdefault("features", {})
                    for feat_name, new_feat in v.items():
                        if not isinstance(new_feat, dict):
                            existing_feats[feat_name] = new_feat
                            continue

                        new_status = new_feat.get("status")
                        old_feat = existing_feats.get(feat_name)
                        # Protect existing good feature
                        if (
                            isinstance(old_feat, dict)
                            and old_feat.get("status") == "ok"
                            and old_feat.get("value") is not None
                            and new_status in ("parse_error", "source_error", "schema_mismatch")
                        ):
                            # Preserve existing good value and status, but record source status/warning if provided
                            if "source_status" in new_feat:
                                old_feat["source_status"] = new_feat["source_status"]
                        else:
                            existing_feats[feat_name] = new_feat
                elif v is not None or k not in matched:
                    if isinstance(v, dict) and isinstance(matched.get(k), dict):
                        matched[k].update(v)
                    else:
                        matched[k] = v

            matched["updated_at"] = now_iso
            target_record = matched
        else:
            rec_dict = dict(incoming)
            if not rec_dict.get("ipo_id"):
                rec_dict["ipo_id"] = generate_ipo_id(
                    company_name=rec_dict.get("company_name", ""),
                    stock_code=rec_dict.get("stock_code"),
                    corp_code=rec_dict.get("corp_code"),
                    subscription_start=rec_dict.get("subscription_start"),
                )
            rec_dict.setdefault("listing_track", "general")
            rec_dict.setdefault("lead_managers", [])
            rec_dict.setdefault("features", {})
            rec_dict.setdefault("score", {})
            rec_dict.setdefault("sources", {})
            rec_dict["updated_at"] = now_iso
            existing_list.append(rec_dict)
            target_record = rec_dict

        _write_market_store_unlocked(store)
        return target_record, False


def get_ipo_calendar_events(
    username: str | None,
    from_date: str,
    to_date: str,
    owner: str = "모두",
) -> list[dict[str, Any]]:
    """Generate calendar events from market IPO schedules.

    Rules:
    - Market store corruption raises IpoStorageError (fail-closed).
    - Market IPO schedules are always shown regardless of owner filter.
    - If actual_listing_date exists, only actual_listing_date is projected as ipo_listing.
      If not, expected_listing_date is projected.
    - If owner == '모두', is_applied_by_owner is True only if all_applied is True.
    """
    store = read_market_store()

    # Get user applications if available
    user_apps = {}
    if username:
        from app.services.ipo.applications import get_user_applications
        apps_data = get_user_applications(username)
        user_apps = apps_data.get("applications", {})

    events: list[dict[str, Any]] = []

    # Non-listing date event mappings
    base_date_events = [
        ("demand_forecast_start", "ipo_demand_start", "수요예측 시작"),
        ("demand_forecast_end", "ipo_demand_end", "수요예측 마감"),
        ("subscription_start", "ipo_subscription_start", "청약 시작"),
        ("subscription_end", "ipo_subscription_end", "청약 마감"),
        ("payment_date", "ipo_payment", "납입일"),
        ("refund_date", "ipo_refund", "환불일"),
    ]

    for ipo in store.get("ipos", []):
        ipo_id = ipo.get("ipo_id") or ""
        company = ipo.get("company_name") or "공모주"
        app_info = user_apps.get(ipo_id, {})
        applied_owners = app_info.get("applied_owners", [])
        target_owners = app_info.get("target_owners", [])
        all_applied = bool(app_info.get("all_applied", False))

        # owner == '모두' requires all_applied == True
        if owner == "모두":
            is_applied_by_owner = all_applied
        else:
            is_applied_by_owner = (owner in applied_owners)

        meta_base = {
            "ipo_id": ipo_id,
            "company_name": company,
            "market": ipo.get("market"),
            "offer_price": ipo.get("final_offer_price"),
            "lead_managers": ipo.get("lead_managers", []),
            "applied_owners": applied_owners,
            "target_owners": target_owners,
            "all_applied": all_applied,
            "is_applied_by_owner": is_applied_by_owner,
        }

        # 1. Base schedule events
        for date_key, ev_type, label in base_date_events:
            raw_val = ipo.get(date_key)
            if not raw_val:
                continue
            date_str = str(raw_val)[:10]
            if not (from_date <= date_str <= to_date):
                continue

            event_id = f"{ev_type}:{ipo_id}:{date_str}"
            if any(e["id"] == event_id for e in events):
                continue

            events.append({
                "id": event_id,
                "date": date_str,
                "type": ev_type,
                "subtype": "공모주",
                "owner": "모두",
                "title": f"🎯 {company} {label}",
                "amount_krw": None,
                "source_id": ipo_id,
                "meta": dict(meta_base),
            })

        # 2. Listing event (Actual listing date takes precedence over expected listing date)
        actual_listing = ipo.get("actual_listing_date")
        expected_listing = ipo.get("expected_listing_date")
        listing_date = None
        listing_status = None

        if actual_listing:
            listing_date = str(actual_listing)[:10]
            listing_status = "actual"
        elif expected_listing:
            listing_date = str(expected_listing)[:10]
            listing_status = "expected"

        if listing_date and (from_date <= listing_date <= to_date):
            label = "신규상장" if listing_status == "actual" else "상장예정"
            event_id = f"ipo_listing:{ipo_id}:{listing_date}"
            if not any(e["id"] == event_id for e in events):
                listing_meta = dict(meta_base)
                listing_meta["listing_status"] = listing_status
                events.append({
                    "id": event_id,
                    "date": listing_date,
                    "type": "ipo_listing",
                    "subtype": "공모주",
                    "owner": "모두",
                    "title": f"🚀 {company} {label}",
                    "amount_krw": None,
                    "source_id": ipo_id,
                    "meta": listing_meta,
                })

    return events
