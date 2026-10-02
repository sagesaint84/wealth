from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "app" / "services" / "ipo" / "store.py"
REMINDERS = ROOT / "app" / "services" / "ipo" / "reminders.py"
ORCHESTRATOR = ROOT / "app" / "services" / "ipo" / "orchestrator.py"
REMINDER_TEST = ROOT / "tests" / "test_ipo_subscription_reminders.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {text.count(old)}")
    return text.replace(old, new, 1)


def patch_store() -> None:
    text = STORE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from datetime import datetime, timedelta\n",
        "from datetime import datetime\n",
        "store datetime import",
    )
    start = text.index("        # Project every day of the canonical subscription period.")
    end = text.index("        # 2. Listing event", start)
    new_block = '''        # Project only the canonical subscription boundaries.  A range can span
        # weekends/holidays even though subscriptions are accepted only on the
        # actual opening and closing business days.  Keeping only the first and
        # last canonical dates avoids implying that every intervening date is an
        # actionable subscription day.
        sub_start = str(ipo.get("subscription_start") or "")[:10]
        sub_end = str(ipo.get("subscription_end") or "")[:10]
        try:
            start_day = datetime.strptime(sub_start, "%Y-%m-%d").date()
            end_day = datetime.strptime(sub_end, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            start_day = end_day = None
        if start_day is not None and end_day is not None and start_day <= end_day:
            if start_day == end_day:
                boundary_days = [(start_day, "single", "청약일")]
            else:
                boundary_days = [
                    (start_day, "first", "청약 첫째날"),
                    (end_day, "last", "청약 마지막날"),
                ]
            for event_day, phase, label in boundary_days:
                date_str = event_day.isoformat()
                if not (from_date <= date_str <= to_date):
                    continue
                event_meta = dict(meta_base)
                event_meta["subscription_phase"] = phase
                events.append({
                    "id": f"ipo_subscription:{ipo_id}:{date_str}",
                    "date": date_str,
                    "type": "ipo_subscription",
                    "subtype": "공모주",
                    "owner": "모두",
                    "title": f"🎯 {company} {label}",
                    "amount_krw": None,
                    "source_id": ipo_id,
                    "meta": event_meta,
                })

'''
    text = text[:start] + new_block + text[end:]
    STORE.write_text(text, encoding="utf-8")


def patch_reminders() -> None:
    text = REMINDERS.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''        if end < start or not (start <= current <= end):
            continue
        ipo_id = str(ipo.get("ipo_id") or "").strip()
''',
        '''        if end < start:
            continue
        is_first_day = current == start
        is_last_day = current == end
        if not (is_first_day or is_last_day):
            continue
        if is_first_day and is_last_day:
            phase_label = "청약일"
        elif is_first_day:
            phase_label = "청약 첫째날"
        else:
            phase_label = "청약 마지막날"
        ipo_id = str(ipo.get("ipo_id") or "").strip()
''',
        "reminder boundary eligibility",
    )
    text = replace_once(
        text,
        '            f"📌 <b>공모주 청약 확인 — {reminder_slot[:2]}:{reminder_slot[2:]}</b>\\n"\n',
        '            f"📌 <b>공모주 {phase_label} — {reminder_slot[:2]}:{reminder_slot[2:]}</b>\\n"\n',
        "reminder phase heading",
    )
    text = replace_once(
        text,
        '''        should_warn = is_last_slot if is_last_slot is not None else (reminder_slot == "1500")
        if should_warn:
''',
        '''        should_warn = is_last_slot if is_last_slot is not None else (reminder_slot == "1500")
        if is_last_day and should_warn:
''',
        "reminder deadline warning",
    )
    REMINDERS.write_text(text, encoding="utf-8")


def patch_orchestrator() -> None:
    text = ORCHESTRATOR.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''    async def _fetch() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        subscriptions = await kis.fetch_ipo_subscription_schedule(from_date, to_date)
        listings = await kis.fetch_listing_schedule(from_date, to_date)
        return subscriptions, listings
''',
        '''    async def _fetch() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        subscriptions, listings = await asyncio.gather(
            kis.fetch_ipo_subscription_schedule(from_date, to_date),
            kis.fetch_listing_schedule(from_date, to_date),
        )
        return subscriptions, listings
''',
        "parallel KIS schedule fetch",
    )
    text = replace_once(
        text,
        '''    market_only: bool = False,
    user_side_effects: bool = True,
) -> dict[str, Any]:
''',
        '''    market_only: bool = False,
    user_side_effects: bool = True,
    interactive_fast: bool = False,
) -> dict[str, Any]:
''',
        "public pipeline interactive_fast parameter",
    )
    text = replace_once(
        text,
        '''            market_only=market_only, user_side_effects=user_side_effects,
        )
''',
        '''            market_only=market_only, user_side_effects=user_side_effects,
            interactive_fast=interactive_fast,
        )
''',
        "pipeline pass interactive_fast",
    )
    text = replace_once(
        text,
        '''    market_only: bool = False, user_side_effects: bool = True,
) -> dict[str, Any]:
''',
        '''    market_only: bool = False, user_side_effects: bool = True,
    interactive_fast: bool = False,
) -> dict[str, Any]:
''',
        "private pipeline interactive_fast parameter",
    )
    text = replace_once(
        text,
        '''    # Check KRX & NAVER
    sources_status["krx"] = "pending"
    sources_status["naver"] = "pending"
''',
        '''    # KRX/NAVER completed-listing confirmation is historical reconciliation.
    # The interactive button can skip it while scheduled/enriched refresh paths
    # retain the existing full confirmation behavior.
    skip_historical_confirmation = bool(market_only and interactive_fast)
    sources_status["krx"] = "not_requested (interactive_fast)" if skip_historical_confirmation else "pending"
    sources_status["naver"] = "not_requested (interactive_fast)" if skip_historical_confirmation else "pending"
''',
        "interactive secondary source status",
    )

    start = text.index("    # 5. KRX master data fetch")
    end = text.index("    # 6. Reconcile", start)
    new_section = '''    # 5. KRX master data fetch.  The explicit interactive fast path skips
    # historical confirmation so a manual schedule refresh does not wait for
    # the KRX master plus NAVER's paginated completed-listing history.
    krx_master: list[dict[str, Any]] = []
    krx_fetch_ok = False
    if not skip_historical_confirmation:
        try:
            if not hasattr(krx, "fetch_listed_master"):
                raise NotImplementedError("KRX listed master client capability unavailable")
            krx_master = krx.fetch_listed_master()
            krx_fetch_ok = True
            sources_status["krx"] = f"sync_ok (master={len(krx_master)})"
        except ExternalNetworkDisabled:
            sources_status["krx"] = "source_unavailable (external_network_disabled)"
        except NotImplementedError:
            sources_status["krx"] = "implementation_blocker"
        except Exception as e:
            logger.warning("KRX sync error: %s", e)
            sources_status["krx"] = f"source_error ({e})"

    # 5.1 NAVER completed listings fetch.  Full historical reconciliation stays
    # in all non-interactive refresh paths, including the enriched daily job.
    naver_completed: list[dict[str, Any]] = []
    naver_fetch_ok = False
    if not skip_historical_confirmation:
        try:
            if not hasattr(naver, "fetch_completed_listings"):
                raise NotImplementedError("NAVER IPO completed-listing client capability unavailable")
            naver_completed = naver.fetch_completed_listings()
            naver_fetch_ok = True
            sources_status["naver"] = f"sync_ok (completed={len(naver_completed)})"
        except ExternalNetworkDisabled:
            sources_status["naver"] = "source_unavailable (external_network_disabled)"
        except NotImplementedError:
            sources_status["naver"] = "implementation_blocker"
        except Exception as e:
            logger.warning("NAVER sync error: %s", e)
            sources_status["naver"] = f"source_error ({e})"

'''
    text = text[:start] + new_section + text[end:]
    text = replace_once(
        text,
        '''        market_only=True,
    )


def refresh_ipo_market_enriched''',
        '''        market_only=True,
        interactive_fast=True,
    )


def refresh_ipo_market_enriched''',
        "interactive refresh wrapper fast flag",
    )
    ORCHESTRATOR.write_text(text, encoding="utf-8")


def patch_existing_reminder_test() -> None:
    text = REMINDER_TEST.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''        self.assertIn("배우자, 자녀", message)
        self.assertIn("증권사별 실제 청약 접수 마감 시간을 확인", message)
        self.assertNotIn("16:00", message)
''',
        '''        self.assertIn("배우자, 자녀", message)
        self.assertIn("공모주 청약 첫째날 — 15:00", message)
        self.assertNotIn("증권사별 실제 청약 접수 마감 시간을 확인", message)
        self.assertNotIn("16:00", message)
''',
        "existing first-day reminder expectation",
    )
    REMINDER_TEST.write_text(text, encoding="utf-8")


def main() -> None:
    patch_store()
    patch_reminders()
    patch_orchestrator()
    patch_existing_reminder_test()
    print("PR82_IPO_BOUNDARY_AND_FAST_REFRESH_PATCHED")


if __name__ == "__main__":
    main()
