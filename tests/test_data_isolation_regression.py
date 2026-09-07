from __future__ import annotations

import unittest

from app.services import asset_records, dividend_records, ledger, pnl_records, portfolio
from regression_support import IsolatedDataTestCase, empty_portfolio


class UserDataIsolationRegressionTests(IsolatedDataTestCase):
    def test_portfolio_asset_pnl_dividend_and_ledger_are_isolated_by_username(self) -> None:
        for username, marker, amount in (
            ("fixture_user_a", "only-a", 100),
            ("fixture_user_b", "only-b", 200),
        ):
            portfolio.write_portfolio(
                empty_portfolio(
                    accounts=[
                        {
                            "id": f"account-{marker}",
                            "broker": "가상증권",
                            "name": marker,
                            "owner": "아빠",
                        }
                    ]
                ),
                username=username,
            )
            asset_records.write_asset_records(
                {
                    "records": [
                        {
                            "id": f"asset-{marker}",
                            "date": "2026-09-01",
                            "owner": "아빠",
                            "total_value_krw": amount,
                            "memo": marker,
                        }
                    ]
                },
                username=username,
            )
            pnl_records.write_pnl_records(
                [
                    {
                        "id": f"pnl-{marker}",
                        "date": "2026-09-02",
                        "owner": "아빠",
                        "asset_type": "stock",
                        "pnl_krw": amount,
                        "memo": marker,
                    }
                ],
                username=username,
            )
            dividend_records.write_dividend_records(
                [
                    {
                        "id": f"dividend-{marker}",
                        "date": "2026-09-03",
                        "owner": "아빠",
                        "amount_krw": amount,
                        "memo": marker,
                    }
                ],
                username=username,
            )
            ledger_data = ledger.default_ledger_data()
            ledger_data["transactions"] = [
                {
                    "id": f"ledger-{marker}",
                    "date": "2026-09-04",
                    "owner": "아빠",
                    "type": "expense",
                    "amount": amount,
                    "memo": marker,
                }
            ]
            ledger.write_ledger(ledger_data, username=username)

        actual_a = self.read_all_markers("fixture_user_a")
        actual_b = self.read_all_markers("fixture_user_b")

        self.assertEqual(actual_a, {"only-a"})
        self.assertEqual(actual_b, {"only-b"})
        self.assertTrue(actual_a.isdisjoint(actual_b))

        generated_files = [path for path in self.fixture_root.rglob("*") if path.is_file()]
        self.assertEqual(len(generated_files), 10)
        for path in generated_files:
            with self.subTest(path=path):
                self.assertTrue(path.is_relative_to(self.fixture_root))

    @staticmethod
    def read_all_markers(username: str) -> set[str]:
        values = {
            portfolio.read_portfolio(username)["accounts"][0]["name"],
            asset_records.read_asset_records(username)["records"][0]["memo"],
            pnl_records.read_pnl_records(username)[0]["memo"],
            dividend_records.read_dividend_records(username)[0]["memo"],
            ledger.read_ledger(username)["transactions"][0]["memo"],
        }
        return values


if __name__ == "__main__":
    unittest.main()
