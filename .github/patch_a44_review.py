from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"target not found: {path}: {old[:140]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


path = "app/services/etf_kind_distributions.py"
replace_once(
    path,
    "import math\nimport re\nfrom typing import Any, Iterable\n",
    "import math\nimport re\nimport time\nfrom typing import Any, Iterable\n",
)
replace_once(
    path,
    '''KIND_MAX_FILINGS_PER_ETF = 15

_HEADERS = {
''',
    '''KIND_MAX_FILINGS_PER_ETF = 15
KIND_EVENT_CACHE_TTL_SECONDS = 30 * 60
_KIND_EVENT_CACHE: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}

_HEADERS = {
''',
)

# Corrections should replace the prior filing for the same ETF/record date even
# if the correction changes payment date or amount.
replace_once(
    path,
    '''        selected: dict[tuple[str, str, str], dict[str, Any]] = {}
        for event in events:
            key = (
                str(event.get("short_code") or ""),
                str(event.get("record_date") or ""),
                str(event.get("payment_date") or ""),
            )
''',
    '''        selected: dict[tuple[str, str], dict[str, Any]] = {}
        for event in events:
            key = (
                str(event.get("short_code") or ""),
                str(event.get("record_date") or ""),
            )
''',
)

# Add a short current-year cache.  Return fresh event dicts because the overlay
# annotates events with numeric_override metadata.
replace_once(
    path,
    '''    if not external_network_allowed():
        return {"status": "network_disabled", "events": []}

    own_client = client is None
''',
    '''    if not external_network_allowed():
        return {"status": "network_disabled", "events": []}

    cache_key = (clean_code, day.year)
    cached = _KIND_EVENT_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < KIND_EVENT_CACHE_TTL_SECONDS:
        payload = cached[1]
        return {
            **payload,
            "events": [dict(event) for event in payload.get("events", [])],
            "cached": True,
        }

    own_client = client is None
''',
)
replace_once(
    path,
    '''        if not filings:
            return {"status": "no_official_filing", "events": []}
''',
    '''        if not filings:
            payload = {"status": "no_official_filing", "events": [], "filing_count": 0}
            _KIND_EVENT_CACHE[cache_key] = (time.monotonic(), payload)
            return dict(payload)
''',
)
replace_once(
    path,
    '''        return {
            "status": "ok" if final_events else "no_structured_distribution",
            "events": final_events,
            "filing_count": len(filings),
        }
''',
    '''        payload = {
            "status": "ok" if final_events else "no_structured_distribution",
            "events": [dict(event) for event in final_events],
            "filing_count": len(filings),
        }
        _KIND_EVENT_CACHE[cache_key] = (time.monotonic(), payload)
        return {
            **payload,
            "events": [dict(event) for event in payload["events"]],
        }
''',
)

# Keep per-row yield and monthly item yield consistent after official overlays.
replace_once(
    path,
    '''            applied, delta = _apply_kind_events_to_row(summary, row, events, as_of=day)
            source["kind_etf_numeric_override_count"] = applied
            if applied:
                source["numeric_source"] = "kind_etf_confirmed_overlay"
            total_applied += applied
''',
    '''            applied, delta = _apply_kind_events_to_row(summary, row, events, as_of=day)
            source["kind_etf_numeric_override_count"] = applied
            if applied:
                source["numeric_source"] = "kind_etf_confirmed_overlay"
                holding = next(
                    (
                        item
                        for item in holdings
                        if isinstance(item, dict)
                        and _stock_code(item.get("code")) == _stock_code(row.get("code"))
                        and str(item.get("currency") or "KRW").upper() == "KRW"
                    ),
                    {},
                )
                price = _money(holding.get("current_price")) or _money(holding.get("purchase_price")) or 0.0
                if price > 0:
                    row["div_yield"] = round(
                        ((_money(row.get("annual_div_per_share")) or 0.0) / price) * 100.0,
                        2,
                    )
                    for bucket in _schedule_buckets(summary).values():
                        items = bucket.get("items") if isinstance(bucket, dict) else None
                        if not isinstance(items, list):
                            continue
                        for schedule_item in items:
                            if (
                                isinstance(schedule_item, dict)
                                and _stock_code(schedule_item.get("code")) == _stock_code(row.get("code"))
                            ):
                                schedule_item["div_yield"] = row["div_yield"]
            total_applied += applied
''',
)

# Extend tests for correction semantics, cache safety, and row yield consistency.
test_path = Path("tests/test_kind_etf_distributions.py")
test = test_path.read_text(encoding="utf-8")
test = test.replace(
    '''        self.assertEqual(row["forecast_source"]["kind_etf_numeric_override_count"], 1)
        self.assertTrue(official["events"][0]["numeric_override"])
''',
    '''        self.assertEqual(row["forecast_source"]["kind_etf_numeric_override_count"], 1)
        self.assertEqual(row["div_yield"], round((207 / 20_000) * 100, 2))
        self.assertEqual(
            result["monthly_schedule"][7]["items"][0]["div_yield"],
            row["div_yield"],
        )
        self.assertTrue(official["events"][0]["numeric_override"])
''',
    1,
)
insert = '''
    async def test_latest_correction_wins_even_when_payment_date_changes(self):
        kind._KIND_EVENT_CACHE.clear()
        filings = [
            {"receipt_no": "20260729000001", "filing_datetime": "2026-07-29 10:00"},
            {"receipt_no": "20260730000001", "filing_datetime": "2026-07-30 10:00"},
        ]

        async def fake_events(_client, filing, *, target_code):
            if filing["receipt_no"] == "20260729000001":
                return [{
                    "short_code": target_code,
                    "record_date": "2026-07-31",
                    "payment_date": "2026-08-04",
                    "amount_per_unit_krw": 100,
                    "filing_datetime": filing["filing_datetime"],
                    "receipt_no": filing["receipt_no"],
                }]
            return [{
                "short_code": target_code,
                "record_date": "2026-07-31",
                "payment_date": "2026-08-05",
                "amount_per_unit_krw": 120,
                "filing_datetime": filing["filing_datetime"],
                "receipt_no": filing["receipt_no"],
            }]

        with (
            patch.object(kind, "external_network_allowed", return_value=True),
            patch.object(kind, "_search_filings", new=AsyncMock(return_value=filings)),
            patch.object(kind, "_events_from_receipt", side_effect=fake_events),
        ):
            result = await kind.fetch_kind_etf_distribution_events(
                "379800", as_of=date(2026, 9, 26), client=AsyncMock()
            )
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["receipt_no"], "20260730000001")
        self.assertEqual(result["events"][0]["payment_date"], "2026-08-05")
        self.assertEqual(result["events"][0]["amount_per_unit_krw"], 120)

    async def test_current_year_cache_returns_fresh_event_dicts(self):
        kind._KIND_EVENT_CACHE.clear()
        filings = [{"receipt_no": "20260729000001", "filing_datetime": "2026-07-29 10:00"}]
        events = [{
            "short_code": "379800",
            "record_date": "2026-07-31",
            "payment_date": "2026-08-04",
            "amount_per_unit_krw": 100,
            "filing_datetime": "2026-07-29 10:00",
            "receipt_no": "20260729000001",
        }]
        search = AsyncMock(return_value=filings)
        receipt = AsyncMock(return_value=events)
        with (
            patch.object(kind, "external_network_allowed", return_value=True),
            patch.object(kind, "_search_filings", new=search),
            patch.object(kind, "_events_from_receipt", new=receipt),
        ):
            first = await kind.fetch_kind_etf_distribution_events(
                "379800", as_of=date(2026, 9, 26), client=AsyncMock()
            )
            first["events"][0]["numeric_override"] = True
            second = await kind.fetch_kind_etf_distribution_events(
                "379800", as_of=date(2026, 9, 26), client=AsyncMock()
            )
        self.assertEqual(search.await_count, 1)
        self.assertTrue(second["cached"])
        self.assertNotIn("numeric_override", second["events"][0])

'''
marker = '\n\nif __name__ == "__main__":\n'
if marker not in test:
    raise SystemExit("test insertion marker missing")
test_path.write_text(test.replace(marker, "\n" + insert + marker, 1), encoding="utf-8")
