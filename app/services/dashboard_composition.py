"""Compose a user's dashboard and coordinate owner-scoped snapshots."""

from __future__ import annotations

from types import ModuleType
from datetime import datetime
from typing import Any


def create_dashboard_composition(runtime: ModuleType) -> dict[str, object]:
    # Resolve the app bindings when called to preserve existing callers and patches.
    DEFAULT_FAMILY_MEMBERS = ["아빠", "엄마", "자녀"]

    def get_family_members(data: dict) -> list:
        return data.get("settings", {}).get("family_members", list(runtime.DEFAULT_FAMILY_MEMBERS))

    def _snapshot_target_owners(data: dict) -> list[str]:
        """Return all configured/discovered owners, always including '모두'."""
        candidates = list(runtime.get_family_members(data) or runtime.DEFAULT_FAMILY_MEMBERS)
        for key in ("accounts", "bank_accounts", "savings_accounts", "insurance_accounts", "loan_accounts"):
            for item in data.get(key, []) or []:
                owner = str(item.get("owner") or "").strip()
                if owner and owner != "모두":
                    candidates.append(owner)
        for item in data.get("real_estates", []) or []:
            for ownership in item.get("ownerships") or []:
                owner = str(ownership.get("owner") or "").strip()
                if owner and owner != "모두":
                    candidates.append(owner)
            owner = str(item.get("owner") or "").strip()
            if owner and owner != "모두" and owner in runtime.DEFAULT_FAMILY_MEMBERS:
                candidates.append(owner)
        return ["모두"] + list(dict.fromkeys(owner for owner in candidates if owner and owner != "모두"))

    def auto_save_all_owner_snapshots(
        data: dict[str, Any],
        username: str | None = None,
        source: str = "auto",
        memo: str = "자동 기록",
        as_of: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        '모두' 및 모든 가족 구성원의 당일 주식기록을 동일한 canonical 계산으로 upsert합니다.
        보유종목이 없는 owner도 0원 스냅샷을 남겨 전체 owner의 날짜 축을 일관되게 유지합니다.

        Session de-duplication: for each owner, the most recent prior asset record is
        consulted for its holdings_session provenance map.  Holdings whose market session
        date has not advanced since that prior record contribute 0 to day_profit_krw,
        preventing the same session gain from being booked again on non-trading days.
        """
        if not data:
            return []

        if as_of is not None:
            today = (as_of.astimezone() if as_of.tzinfo else as_of).date().isoformat()
        else:
            today = runtime.datetime.now().astimezone().date().isoformat()
        fx_rates = data.get("fx_rates")
        accounts = data.get("accounts", []) or []
        all_holdings = data.get("holdings", []) or []
        saved: list[dict[str, Any]] = []

        # Pre-load existing records once per call for prev_session_map extraction
        try:
            existing_records = runtime.list_asset_records(username=username)
        except Exception:
            existing_records = []

        for owner in runtime._snapshot_target_owners(data):
            if owner == "모두":
                owned_holdings = all_holdings
            else:
                owned_accounts = [a for a in accounts if (a.get("owner") or "모두") == owner]
                owned_acc_ids = {a.get("id") for a in owned_accounts if a.get("id")}
                owned_holdings = [
                    h for h in all_holdings
                    if h.get("account_id") in owned_acc_ids or h.get("owner") == owner
                ]

            # Extract session provenance from the most recent prior record for this owner
            # Default to {} (not None): {} means "baseline exists but empty" → suppress all contributions
            # on first provenance-aware snapshot, preventing fabrication of unverified P/L.
            prev_session_map: dict[str, str] = {}
            try:
                owner_norm = owner or "모두"
                prior_records = [
                    r for r in existing_records
                    if (r.get("owner") or "모두") == owner_norm
                    and r.get("date")
                    and r.get("date") < today
                ]
                if prior_records:
                    prior_records.sort(key=lambda r: r.get("date") or "")
                    latest_prior = prior_records[-1]
                    hs = latest_prior.get("holdings_session")
                    if isinstance(hs, dict) and hs:
                        prev_session_map = hs  # use the stored provenance map
                    # else: prior record exists but has no/empty provenance → keep {} (suppress all)
            except Exception:
                prev_session_map = {}  # on error, suppress all (safe)

            payload = runtime.build_stock_record_from_holdings(
                owned_holdings,
                owner=owner,
                today=today,
                source=source,
                memo=memo,
                fx_rates=fx_rates,
                prev_session_map=prev_session_map,
            )
            saved.append(runtime.upsert_asset_record(payload, by_date=True, username=username))

        return saved

    def save_all_owner_net_worth_snapshots(
        data: dict[str, Any],
        username: str,
        source: str = "auto",
        as_of: datetime | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Calculate and atomically save current net-worth snapshots for all owners."""
        from app.services.planning import build_net_worth_snapshot, upsert_current_snapshots

        snapshots = [build_net_worth_snapshot(data, owner) for owner in runtime._snapshot_target_owners(data)]
        state = upsert_current_snapshots(username, snapshots, source=source, as_of=as_of)
        return state, snapshots

    def get_full_dashboard_for_user(username: str, record_snapshots: bool = False) -> dict:
        if username == "admin":
            return {
                "summary": {"total_value_krw": 0, "total_cost_krw": 0, "profit_krw": 0, "return_rate": 0, "holding_count": 0, "account_count": 0},
                "holdings": [],
                "accounts": [],
                "classifications": [],
                "currency_summary": {},
                "fx_rates": {"KRW": 1.0, "USD": 1385.0},
                "day_change": {"change_krw": 0, "change_rate": 0},
                "updated_at": runtime.datetime.now().astimezone().isoformat(),
            }
        data = runtime.get_dashboard(username=username)
        from app.services.savings import get_savings_data
        savings_info = get_savings_data(username=username)
        data["bank_accounts"] = savings_info.get("bank_accounts", [])
        data["savings_accounts"] = savings_info.get("savings_accounts", [])
        data["savings_summary"] = savings_info.get("summary", {})
        data["insurance_accounts"] = savings_info.get("insurance_accounts", [])
        data["loan_accounts"] = savings_info.get("loan_accounts", [])

        from app.services.real_estate import get_real_estate_data
        re_info = get_real_estate_data(username=username)
        data["real_estates"] = re_info.get("real_estates", [])
        data["sold_real_estates"] = re_info.get("sold_real_estates", [])
        data["real_estate_summary"] = re_info.get("summary", {})

        from app.services.pnl_records import get_pnl_summary, read_pnl_records
        from app.services.dividend_records import get_actual_dividend_summary, read_dividend_records
        data["realized_pnl_records"] = read_pnl_records(username=username)
        data["realized_pnl_summary"] = get_pnl_summary(owner="모두", username=username)
        data["actual_dividend_records"] = read_dividend_records(username=username)
        data["dividend_summary"] = get_actual_dividend_summary(owner="모두", username=username)

        if record_snapshots:
            runtime.auto_save_all_owner_snapshots(data, username=username, source="auto", memo="접속 자동 기록")
        return data

    return {
        "DEFAULT_FAMILY_MEMBERS": DEFAULT_FAMILY_MEMBERS,
        "get_family_members": get_family_members,
        "_snapshot_target_owners": _snapshot_target_owners,
        "auto_save_all_owner_snapshots": auto_save_all_owner_snapshots,
        "save_all_owner_net_worth_snapshots": save_all_owner_net_worth_snapshots,
        "get_full_dashboard_for_user": get_full_dashboard_for_user,
    }
