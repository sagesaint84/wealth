from __future__ import annotations

import datetime
import sys
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from app.services import asset_records, portfolio
from regression_support import IsolatedDataTestCase, empty_portfolio


class DashboardDailyMetricSeparationTests(IsolatedDataTestCase):
    def _dashboard(
        self,
        *,
        quantity: float,
        price: float,
        currency: str = "KRW",
        fx_rate: float = 1.0,
        day_rate: float = 0.0,
        current_session: str | None = "2026-09-22",
        previous_session: str | None = "2026-09-21",
        previous_value: float | None = None,
    ) -> dict:
        code = "005930" if currency == "KRW" else "AAPL"
        settings = {
            "fx_rates": {"KRW": 1.0, currency: fx_rate},
            "price_session_obs": (
                {code: {"rate": day_rate, "as_of": current_session, "source": "test"}}
                if current_session
                else {}
            ),
        }
        data = empty_portfolio(
            settings=settings,
            accounts=[{"id": "acct", "name": "계좌", "broker": "테스트", "owner": "모두"}],
            holdings=[{
                "id": "holding",
                "account_id": "acct",
                "broker": "테스트",
                "code": code,
                "name": code,
                "quantity": quantity,
                "avg_price": price,
                "current_price": price,
                "currency": currency,
                "market": "KRX" if currency == "KRW" else "NASDAQ",
                "day_change_rate": day_rate,
            }],
        )
        portfolio.write_portfolio(data, username="test_user")
        if previous_value is not None:
            yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
            record = {
                "date": yesterday,
                "owner": "모두",
                "total_value_krw": previous_value,
                "day_profit_krw": 0,
            }
            if previous_session:
                record["holdings_session"] = {f"{currency}:{code}": previous_session}
            asset_records.upsert_asset_record(record, by_date=True, username="test_user")
        return portfolio.get_dashboard(username="test_user")

    def test_quantity_only_change_is_record_change_not_price_profit(self) -> None:
        dash = self._dashboard(quantity=200, price=100, previous_value=10_000)
        day = dash["day_change"]
        self.assertEqual(day["day_profit_krw"], 0)
        self.assertEqual(day["record_change_krw"], 10_000)
        self.assertEqual(day["price_profit_status"], "complete")

    def test_fx_only_change_is_record_change_not_price_profit(self) -> None:
        dash = self._dashboard(
            quantity=10,
            price=100,
            currency="USD",
            fx_rate=1_400,
            previous_value=1_300_000,
            current_session="2026-09-21",
            previous_session="2026-09-21",
        )
        day = dash["day_change"]
        self.assertEqual(day["day_profit_krw"], 0)
        self.assertEqual(day["record_change_krw"], 100_000)

    def test_usd_price_only_change_uses_canonical_price_profit(self) -> None:
        dash = self._dashboard(
            quantity=10,
            price=110,
            currency="USD",
            fx_rate=1_000,
            day_rate=10,
            previous_value=1_000_000,
        )
        day = dash["day_change"]
        self.assertEqual(day["day_profit_krw"], 100_000)
        self.assertEqual(day["record_change_krw"], 100_000)

    def test_no_prior_provenance_does_not_promote_stale_rate(self) -> None:
        dash = self._dashboard(
            quantity=100,
            price=100,
            day_rate=5,
            current_session=None,
            previous_session=None,
            previous_value=None,
        )
        day = dash["day_change"]
        self.assertIsNone(day["day_profit_krw"])
        self.assertEqual(day["price_profit_status"], "unavailable")


class DashboardDailyMetricFrontendTests(IsolatedDataTestCase):
    def test_dashboard_labels_price_profit_and_record_change_separately(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "app/static/wealth.js").read_text(encoding="utf-8")
        html = (Path(__file__).resolve().parents[1] / "app/static/index.html").read_text(encoding="utf-8")
        self.assertIn("당일 가격변동 손익", source)
        self.assertIn("전 기록 대비 평가액 변화", source)
        self.assertIn("day.day_profit_krw", source)
        self.assertIn("day.record_change_krw", source)
        self.assertIn('id="recordChangeVal"', html)
        self.assertNotIn("`일간 수익 ${sign}${money(day.change_krw)}", source)
