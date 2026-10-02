from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ipo.orchestrator import _run_ipo_daily_pipeline


def test_market_only_refresh_recalculates_only_touched_current_schedule_rows() -> None:
    historical = {
        "ipo_id": "old-ipo",
        "company_name": "과거회사",
        "stock_code": "111111",
        "actual_listing_date": "2023-01-10",
        "score": {"old": 1},
    }
    current = {
        "ipo_id": "jincostech-20261002",
        "company_name": "진코스텍",
        "stock_code": "250030",
        "subscription_start": "2026-10-02",
        "subscription_end": "2026-10-06",
        "expected_listing_date": "2026-10-14",
        "score": {"old": 2},
    }
    market = {"schema_version": 1, "updated_at": "old", "ipos": [historical, current]}

    kis = MagicMock()
    kis.configured = True
    kis.fetch_ipo_subscription_schedule = AsyncMock(return_value=[{
        "company_name": "진코스텍",
        "stock_code": "250030",
        "subscription_start": "2026-10-02",
        "subscription_end": "2026-10-06",
        "expected_listing_date": "2026-10-14",
        "lead_managers": ["하나증권"],
    }])
    kis.fetch_listing_schedule = AsyncMock(return_value=[])
    dart = MagicMock(); dart.is_configured.return_value = False
    krx = MagicMock()
    naver = MagicMock()

    with patch("app.services.ipo.orchestrator.read_market_store", return_value=market), \
         patch("app.services.ipo.orchestrator.write_market_store"), \
         patch("app.services.ipo.orchestrator.calculate_wealth_ipo_score", return_value={"total_score": 50}) as score:
        result = _run_ipo_daily_pipeline(
            kis_client=kis,
            dart_client=dart,
            krx_client=krx,
            naver_client=naver,
            target_date_str="2026-10-02",
            market_only=True,
        )

    assert result["status"] == "ok"
    assert score.call_count == 1
    assert score.call_args.args[0]["stock_code"] == "250030"
    assert historical["score"] == {"old": 1}
    krx.fetch_listed_master.assert_not_called()
    naver.fetch_completed_listings.assert_not_called()
