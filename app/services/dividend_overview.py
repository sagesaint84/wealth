"""Compose dividend forecasts and share user-scoped tax evidence."""

from __future__ import annotations

from types import ModuleType


def create_dividend_overview(runtime: ModuleType) -> dict[str, object]:
    # Resolve the app bindings when called to preserve existing callers and patches.
    async def _get_dividend_overview(username: str, owner: str) -> dict:
        """Return dividend summary and 12-month schedule for holdings."""
        full = runtime.get_dashboard(username=username)
        holdings = full.get("holdings", [])
        accounts = full.get("accounts", [])
        if owner != "모두":
            acct_map = {a["id"]: a.get("owner", "모두") for a in accounts}
            holdings = [
                h for h in holdings
                if (h.get("owner") == owner) or (acct_map.get(h.get("account_id")) == owner)
            ]
        fx_rate = full.get("fx_rates", {}).get("USD", 1385.0)
        summary = await runtime.get_web_dividend_summary(holdings, fx_rate=fx_rate, username=username)
        return {**summary, 'dividend_tax_benefits': runtime._dividend_benefit_context(
            summary, full, username=username, owner=owner, tax_year=runtime.datetime.now(runtime.ZoneInfo('Asia/Seoul')).year)}

    def _dividend_benefit_context(summary, full, *, username, owner, tax_year, selections=None):
        import hashlib
        from app.services.tax.what_if import build_dividend_benefit_preview
        accounts = {a['id']: a.get('owner') for a in full.get('accounts', [])}
        owners = sorted({str(h.get('owner') or accounts.get(h.get('account_id')) or '')
            for h in full.get('holdings', [])} - {'', '모두'})
        invalid_owner = owner != '모두' and owner not in owners
        context = hashlib.sha256(f'{username}\0{owner}\0{tax_year}'.encode()).hexdigest()
        # Refuse mixed/ambiguous quantity scopes without changing the legacy summary.
        import math
        from app.services.dividend_event_identity import normalize_dividend_code
        quantities = {}
        for holding in full.get('holdings', []):
            if str(holding.get('currency') or 'KRW').upper() != 'KRW':
                continue
            if str(holding.get('owner') or accounts.get(holding.get('account_id')) or '') != owner:
                continue
            code = normalize_dividend_code(holding.get('code'))
            quantity = holding.get('quantity')
            if isinstance(quantity, (int, float)) and not isinstance(quantity, bool) and math.isfinite(quantity) and quantity > 0:
                quantities[code] = quantities.get(code, 0) + quantity
        scoped = {**summary, 'monthly_schedule': [{**bucket, 'items': [item for item in bucket.get('items', [])
            if isinstance(item.get('quantity'), (int, float))
            and item.get('quantity') == quantities.get(normalize_dividend_code(item.get('code')))]}
            for bucket in summary.get('monthly_schedule', [])]}
        result = ({'owner': owner, 'tax_year': tax_year, 'events': [], 'requires_owner': True,
            'session_only': True, 'invalid_owner': invalid_owner} if owner == '모두' or invalid_owner else build_dividend_benefit_preview(
                scoped, owner=owner, tax_year=tax_year, selections=selections, as_of=runtime.datetime.now(runtime.ZoneInfo('Asia/Seoul')).date()))
        return {**result, 'context_key': context, 'owners': owners}

    _actual_dividend_evidence_cache = {}

    async def _actual_dividend_evidence(records, username):
        """Small user-scoped read cache shared by list and debounced form preview."""
        import time
        from app.services.dividend_records import get_record_tax_evidence
        codes = tuple(sorted({str(r.get('code') or '') for r in records if r.get('currency', 'KRW') == 'KRW'}))
        if not codes:
            return {}
        key = (username, codes)
        cached = runtime._actual_dividend_evidence_cache.get(key)
        if cached and time.monotonic() - cached[0] < 60:
            return cached[1]
        evidence = await get_record_tax_evidence(
            [{'code': code, 'currency': 'KRW'} for code in codes], username)
        if len(runtime._actual_dividend_evidence_cache) >= 128:
            runtime._actual_dividend_evidence_cache.clear()
        runtime._actual_dividend_evidence_cache[key] = (time.monotonic(), evidence)
        return evidence

    return {
        "_get_dividend_overview": _get_dividend_overview,
        "_dividend_benefit_context": _dividend_benefit_context,
        "_actual_dividend_evidence": _actual_dividend_evidence,
        "_actual_dividend_evidence_cache": _actual_dividend_evidence_cache,
    }
