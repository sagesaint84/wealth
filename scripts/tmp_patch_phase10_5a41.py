from pathlib import Path

path = Path("app/services/web_finance.py")
text = path.read_text(encoding="utf-8")
marker = "# Phase 10.5A-4.1 official dividend forecast source enrichment"
if marker not in text:
    text += '''


# Phase 10.5A-4.1 official dividend forecast source enrichment
_legacy_get_web_dividend_summary = get_web_dividend_summary


async def get_web_dividend_summary(
    holdings: list[dict[str, Any]], fx_rate: float = 1385.0
) -> dict[str, Any]:
    """Return the legacy forecast enriched with official domestic evidence.

    Official-source failures intentionally fail open so the existing Naver/Yahoo
    forecast remains available. OpenDART historical DPS is fill-only and never
    overwrites a non-zero legacy estimate.
    """
    summary = await _legacy_get_web_dividend_summary(holdings, fx_rate=fx_rate)
    try:
        from app.services.dividend_official_sources import (
            enrich_dividend_summary_with_official_sources,
        )

        return await enrich_dividend_summary_with_official_sources(
            summary,
            holdings,
            fx_rate=fx_rate,
        )
    except Exception:
        if isinstance(summary, dict):
            summary["forecast_source_policy"] = {
                "status": "official_enrichment_failed",
                "confirmed_amount_requires_structured_verification": True,
                "legacy_forecast_preserved": True,
            }
        return summary
'''
    path.write_text(text, encoding="utf-8")
