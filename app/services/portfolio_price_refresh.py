"""Refresh portfolio prices or apply a standalone USD/KRW rate."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import ModuleType


def _record_fx_metadata(settings: dict, rate: float, updated_at: str) -> None:
    settings["fx_info"] = {"source": "실시간 웹 환율", "rate": rate, "updated_at": updated_at}
    settings["fx_updated_at"] = updated_at


def create_portfolio_price_refresh(
    runtime: ModuleType,
) -> tuple[Callable[[str], Awaitable[dict]], Callable[[str], Awaitable[dict]]]:
    # Resolve existing app dependencies at call time so caller patches stay effective.
    async def refresh_prices_for_user(username: str) -> dict:
        data = runtime.read_portfolio(username=username)
        if runtime.is_test_mode():
            return {
                "message": "테스트 환경에서는 외부 시세 갱신을 실행하지 않습니다. 기존 데이터를 유지했습니다.",
                "count": 0,
                "fx_rate": data.get("settings", {}).get("fx_rates", {}).get("USD"),
                "warnings": [],
                "status": "TEST_MODE",
                "data_preserved": True,
            }
        now_str = runtime.datetime.now().astimezone().isoformat(timespec="seconds")

        # 보유종목이 없는 경우에도 지수 및 환율 정상 갱신
        if not data.get("holdings"):
            fx_rate = await runtime.fetch_fx_rate_usd_krw()
            if fx_rate and fx_rate > 0:
                with runtime.financial_user_locks(username, 'portfolio.json'):
                    data = runtime.read_portfolio(username=username)
                    data.setdefault("settings", {})
                    data["settings"].setdefault("exchange_rates", {})["USD"] = fx_rate
                    data["settings"]["fx_rates"] = {"KRW": 1.0, "USD": fx_rate}
                    _record_fx_metadata(data["settings"], fx_rate, now_str)
                    runtime.write_portfolio(data, username=username)
            return {
                "message": "지수 및 환율을 갱신했습니다.",
                "count": 0,
                "fx_rate": fx_rate,
                "warnings": [],
            }

        # 네이버페이 증권 & 야후 파이낸스 & 웹 실시간 환율 병렬 직접 갱신 (토큰 불필요)
        res = await runtime.refresh_all_holdings_prices(data["holdings"])
        prices = res.get("prices", {})
        daily_changes = res.get("daily_changes", {})
        period_rates = res.get("period_rates", {})
        fx_rate = res.get("fx_rate", 1385.0)

        with runtime.financial_user_locks(username, 'portfolio.json'):
            data = runtime.read_portfolio(username=username)
            # 포트폴리오 업데이트
            for holding in data["holdings"]:
                hid = holding["id"]
                if hid in prices and prices[hid] > 0:
                    holding["current_price"] = prices[hid]
                    holding["price_updated_at"] = now_str

            if daily_changes:
                data["settings"].setdefault("daily_price_changes", {}).update(daily_changes)
            if period_rates:
                data["settings"].setdefault("period_rates", {}).update(period_rates)
            session_obs = res.get("session_obs", {})
            if session_obs:
                stored_obs = data["settings"].setdefault("price_session_obs", {})
                runtime.merge_price_session_obs(stored_obs, session_obs)

            session_dates = res.get("session_dates", {})
            if session_dates:
                stored_dates = data["settings"].setdefault("price_session_dates", {})
                for code, inc_date in session_dates.items():
                    inc_norm = runtime.normalize_session_date(inc_date)
                    if not inc_norm:
                        continue
                    cur_date = runtime.normalize_session_date(stored_dates.get(code))
                    if cur_date and inc_norm < cur_date:
                        continue
                    stored_dates[code] = inc_date
            if fx_rate and fx_rate > 0:
                data["settings"].setdefault("exchange_rates", {})["USD"] = fx_rate
                data["settings"]["fx_updated_at"] = now_str

            runtime.write_portfolio(data, username=username)
        return {
            "message": f"전체 {len(prices)}개 종목 시세 및 환율({fx_rate:,.1f}원)을 갱신했습니다.",
            "count": len(prices),
            "fx_rate": fx_rate,
            "warnings": [],
        }

    async def refresh_fx_for_user(username: str) -> dict:
        rate = await runtime.fetch_fx_rate_usd_krw()
        with runtime.financial_user_locks(username, 'portfolio.json'):
            data = runtime.read_portfolio(username=username)
            data["settings"]["fx_rates"]["USD"] = rate
            now_str = runtime.datetime.now().astimezone().isoformat(timespec="seconds")
            _record_fx_metadata(data["settings"], rate, now_str)
            runtime.write_portfolio(data, username=username)
            return {"message": f"실시간 환율(USD/KRW: {rate:,.1f}원)을 반영했습니다.", "rate": rate}

    return refresh_prices_for_user, refresh_fx_for_user
