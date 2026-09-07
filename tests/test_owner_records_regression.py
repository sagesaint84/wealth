from __future__ import annotations

import unittest

from app.services import dividend_records, ledger, pnl_records, portfolio, real_estate
from regression_support import IsolatedDataTestCase, PROJECT_ROOT, empty_portfolio


OWNER_AMOUNTS = {
    "모두": 10,
    "아빠": 20,
    "엄마": 30,
    "자녀": 40,
    "공동명의": 50,
}


class OwnerRecordRegressionTests(IsolatedDataTestCase):
    def test_realized_pnl_owner_filter_uses_all_as_wildcard_and_specific_as_exact_match(self) -> None:
        records = [
            {
                "id": f"pnl-{owner}",
                "date": "2026-09-01",
                "asset_type": "stock",
                "code": "SAFE",
                "owner": owner,
                "pnl_krw": amount,
            }
            for owner, amount in OWNER_AMOUNTS.items()
        ]
        pnl_records.write_pnl_records(records, username="fixture_user")

        all_summary = pnl_records.get_pnl_summary(owner="모두", year=2026, username="fixture_user")
        self.assertEqual(all_summary["record_count"], 5)
        self.assertEqual(all_summary["total_pnl_krw"], 150)

        for owner in ("아빠", "엄마", "자녀", "공동명의"):
            with self.subTest(owner=owner):
                summary = pnl_records.get_pnl_summary(owner=owner, year=2026, username="fixture_user")
                self.assertEqual(summary["record_count"], 1)
                self.assertEqual(summary["total_pnl_krw"], OWNER_AMOUNTS[owner])
                self.assertEqual(summary["records"][0]["owner"], owner)

    def test_dividend_owner_filter_uses_all_as_wildcard_and_specific_as_exact_match(self) -> None:
        records = [
            {
                "id": f"dividend-{owner}",
                "date": "2026-09-02",
                "code": "SAFE",
                "owner": owner,
                "amount_krw": amount,
            }
            for owner, amount in OWNER_AMOUNTS.items()
        ]
        dividend_records.write_dividend_records(records, username="fixture_user")

        all_summary = dividend_records.get_actual_dividend_summary(
            owner="모두", year=2026, username="fixture_user"
        )
        self.assertEqual(all_summary["record_count"], 5)
        self.assertEqual(all_summary["total_actual_dividend_krw"], 150)

        for owner in ("아빠", "엄마", "자녀", "공동명의"):
            with self.subTest(owner=owner):
                summary = dividend_records.get_actual_dividend_summary(
                    owner=owner, year=2026, username="fixture_user"
                )
                self.assertEqual(summary["record_count"], 1)
                self.assertEqual(summary["total_actual_dividend_krw"], OWNER_AMOUNTS[owner])
                self.assertEqual(summary["records"][0]["owner"], owner)

    def test_ledger_specific_owner_includes_matching_and_shared_all_transactions(self) -> None:
        data = ledger.default_ledger_data()
        data["transactions"] = [
            {
                "id": f"ledger-{owner}",
                "date": "2026-09-03",
                "type": "expense",
                "category": "기타지출",
                "owner": owner,
                "amount": amount,
            }
            for owner, amount in OWNER_AMOUNTS.items()
        ]
        ledger.write_ledger(data, username="fixture_user")

        all_summary = ledger.get_ledger_summary(
            username="fixture_user", year=2026, month=9, owner="모두"
        )
        self.assertEqual(len(all_summary["transactions"]), 5)
        self.assertEqual(all_summary["total_expense"], 150)

        for owner in ("아빠", "엄마", "자녀", "공동명의"):
            with self.subTest(owner=owner):
                summary = ledger.get_ledger_summary(
                    username="fixture_user", year=2026, month=9, owner=owner
                )
                self.assertEqual(
                    {item["owner"] for item in summary["transactions"]},
                    {"모두", owner},
                )
                self.assertEqual(summary["total_expense"], 10 + OWNER_AMOUNTS[owner])

    def test_joint_ownership_is_stored_as_structured_shares_and_full_asset_value(self) -> None:
        portfolio.write_portfolio(empty_portfolio(), username="fixture_user")
        record = real_estate.save_real_estate(
            {
                "name": "가상 공동명의 주택",
                "property_type": "own",
                "purchase_price": 800,
                "current_price": 1000,
                "is_joint_ownership": True,
                "ownerships": [
                    {"owner": "아빠", "ratio": 60},
                    {"owner": "엄마", "ratio": 40},
                ],
            },
            username="fixture_user",
        )
        result = real_estate.get_real_estate_data(username="fixture_user")

        self.assertTrue(record["is_joint_ownership"])
        self.assertEqual(record["owner"], "아빠 60% · 엄마 40%")
        self.assertEqual(
            record["ownerships"],
            [{"owner": "아빠", "ratio": 60.0}, {"owner": "엄마", "ratio": 40.0}],
        )
        self.assertEqual(result["summary"]["total_real_estate_value"], 1000)
        self.assertEqual(result["real_estates"][0]["net_equity"], 1000)

    def test_frontend_joint_owner_filter_uses_ownership_ratio(self) -> None:
        source = (PROJECT_ROOT / "app" / "static" / "wealth.js").read_text(encoding="utf-8")

        self.assertIn("let matched = ownerships.find(x => x.owner === o);", source)
        self.assertIn("share = (matched.ratio || 100) / 100;", source)


if __name__ == "__main__":
    unittest.main()
