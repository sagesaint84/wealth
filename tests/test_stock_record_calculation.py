from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from app.services import asset_records, portfolio
from regression_support import IsolatedDataTestCase, empty_portfolio


class StockRecordCalculationTests(IsolatedDataTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.base_data = empty_portfolio(
            settings={
                "fx_rates": {"KRW": 1.0, "USD": 1300.0},
                "cash_balances": {
                    "acc-dad": {"KRW": 20_000_000, "USD": 1_000.0},
                    "acc-mom": {"KRW": 5_000_000, "USD": 0.0},
                },
            },
            accounts=[
                {
                    "id": "acc-dad",
                    "broker": "테스트증권",
                    "name": "아빠 계좌",
                    "owner": "아빠",
                    "account_type": "general",
                    "source": "test",
                },
                {
                    "id": "acc-mom",
                    "broker": "테스트증권",
                    "name": "엄마 계좌",
                    "owner": "엄마",
                    "account_type": "general",
                    "source": "test",
                },
            ],
            holdings=[
                {
                    "id": "stock-krw-dad",
                    "account_id": "acc-dad",
                    "broker": "테스트증권",
                    "code": "005930",
                    "name": "삼성전자",
                    "quantity": 1000,
                    "avg_price": 70_000,
                    "current_price": 80_000,
                    "currency": "KRW",
                    "market": "KRX",
                    "day_change_rate": 0.0,
                    "owner": "아빠",
                },
                {
                    "id": "stock-usd-dad",
                    "account_id": "acc-dad",
                    "broker": "테스트증권",
                    "code": "AAPL",
                    "name": "애플",
                    "quantity": 10,
                    "avg_price": 150.0,
                    "current_price": 200.0,
                    "currency": "USD",
                    "market": "NASDAQ",
                    "day_change_rate": 0.0,
                    "owner": "아빠",
                },
                {
                    "id": "stock-krw-mom",
                    "account_id": "acc-mom",
                    "broker": "테스트증권",
                    "code": "035420",
                    "name": "NAVER",
                    "quantity": 100,
                    "avg_price": 200_000,
                    "current_price": 220_000,
                    "currency": "KRW",
                    "market": "KRX",
                    "day_change_rate": 0.0,
                    "owner": "엄마",
                },
            ],
        )
        portfolio.write_portfolio(self.base_data, username="test_user")

    def test_dashboard_summary_contract_preserved_stock_plus_cash(self) -> None:
        """대시보드 summary.total_value_krw는 기존대로 stock + cash 전체를 보존해야 함."""
        dash = portfolio.get_dashboard(username="test_user")
        summary = dash["summary"]

        # 삼성전자: 1000 * 80,000 = 80,000,000
        # 애플: 10 * 200 * 1300 = 2,600,000
        # 네이버: 100 * 220,000 = 22,000,000
        # 총 주식평가액: 104,600,000
        expected_stock_val = 80_000_000 + 2_600_000 + 22_000_000
        self.assertEqual(summary["total_stock_value_krw"], expected_stock_val)

        # 예수금: 아빠 (20,000,000 KRW + 1,000 USD * 1300 = 21,300,000) + 엄마 (5,000,000 KRW) = 26,300,000
        expected_cash_val = 20_000_000 + (1_000 * 1300.0) + 5_000_000
        self.assertEqual(summary["total_cash_krw"], expected_cash_val)

        # total_value_krw는 주식 + 예수금 유지
        self.assertEqual(summary["total_value_krw"], expected_stock_val + expected_cash_val)

    def test_stock_record_snapshot_excludes_cash_and_is_holdings_only(self) -> None:
        """주식기록 스냅샷은 예수금을 제외하고 순수 주식 평가액만 기록해야 함."""
        dash = portfolio.get_dashboard(username="test_user")
        rec = asset_records.build_stock_record_from_holdings(dash["holdings"], owner="모두")

        expected_stock_val = 80_000_000 + 2_600_000 + 22_000_000
        # 취득원가: 삼성(70M) + 애플(10 * 150 * 1300 = 1.95M) + 네이버(20M) = 91,950,000
        expected_stock_cost = 70_000_000 + (10 * 150 * 1300.0) + 20_000_000
        expected_profit = expected_stock_val - expected_stock_cost

        self.assertEqual(rec["total_value_krw"], expected_stock_val)
        self.assertEqual(rec["total_cost_krw"], expected_stock_cost)
        self.assertEqual(rec["profit_krw"], expected_profit)
        self.assertAlmostEqual(rec["return_rate"], expected_profit / expected_stock_cost * 100, places=2)
        self.assertEqual(rec["holding_count"], 3)

        # KRW 주식 평가액: 삼성 80M + 네이버 22M = 102M (KRW 예수금 25M 제외!)
        self.assertEqual(rec["krw_value_krw"], 102_000_000)
        # USD 주식 평가액: 애플 2.6M (외화 예수금 1000달러=1.3M 제외!)
        self.assertEqual(rec["usd_value_krw"], 2_600_000)

    def test_cash_increase_or_decrease_only_does_not_affect_stock_record(self) -> None:
        """단순 예수금 입출금 발생 시 주식기록 총주식자산 및 총수익/일간수익에 변화가 없어야 함."""
        # 1. 초기 스냅샷
        dash1 = portfolio.get_dashboard(username="test_user")
        rec1 = asset_records.build_stock_record_from_holdings(dash1["holdings"], owner="모두")

        # 2. 예수금 50,000,000원 입금
        data_deposit = deepcopy(self.base_data)
        data_deposit["settings"]["cash_balances"]["acc-dad"]["KRW"] += 50_000_000
        portfolio.write_portfolio(data_deposit, username="test_user")

        dash2 = portfolio.get_dashboard(username="test_user")
        rec2 = asset_records.build_stock_record_from_holdings(dash2["holdings"], owner="모두")

        self.assertEqual(rec1["total_value_krw"], rec2["total_value_krw"])
        self.assertEqual(rec1["total_cost_krw"], rec2["total_cost_krw"])
        self.assertEqual(rec1["profit_krw"], rec2["profit_krw"])
        self.assertEqual(rec1["day_profit_krw"], rec2["day_profit_krw"])
        self.assertEqual(rec2["day_profit_krw"], 0.0)

        # 3. 예수금 60,000,000원 출금
        data_withdraw = deepcopy(data_deposit)
        data_withdraw["settings"]["cash_balances"]["acc-dad"]["KRW"] -= 60_000_000
        portfolio.write_portfolio(data_withdraw, username="test_user")

        dash3 = portfolio.get_dashboard(username="test_user")
        rec3 = asset_records.build_stock_record_from_holdings(dash3["holdings"], owner="모두")

        self.assertEqual(rec1["total_value_krw"], rec3["total_value_krw"])
        self.assertEqual(rec1["profit_krw"], rec3["profit_krw"])
        self.assertEqual(rec3["day_profit_krw"], 0.0)

    def test_ipo_subscription_scenario_does_not_create_stock_loss(self) -> None:
        """공모주 청약 증거금 납입/출금 시 주식 손실로 오인되지 않아야 함."""
        # 아빠 계좌의 예수금 20,000,000원이 공모주 청약 증거금으로 빠져나가 0원이 됨
        data_ipo = deepcopy(self.base_data)
        data_ipo["settings"]["cash_balances"]["acc-dad"]["KRW"] = 0.0
        portfolio.write_portfolio(data_ipo, username="test_user")

        dash = portfolio.get_dashboard(username="test_user")
        rec_dad = asset_records.build_stock_record_from_holdings(
            [h for h in dash["holdings"] if h.get("owner") == "아빠"],
            owner="아빠",
        )

        # 아빠 주식 평가액: 삼성 80M + 애플 2.6M = 82.6M
        self.assertEqual(rec_dad["total_value_krw"], 82_600_000)
        # 공모주 청약으로 2천만원이 빠져나갔어도 주식 일간수익은 -20,000,000이 아니라 0이어야 함!
        self.assertEqual(rec_dad["day_profit_krw"], 0.0)
        # 총수익도 정상 유지
        self.assertEqual(rec_dad["profit_krw"], 82_600_000 - 71_950_000)

    def test_negative_cash_balance_preserved_without_clamping(self) -> None:
        """음수 예수금(미수/정산 대기/청약 마이너스)은 임의로 clamp(0)되지 않고 원본 보존되어야 함."""
        data_neg = deepcopy(self.base_data)
        data_neg["settings"]["cash_balances"]["acc-dad"]["KRW"] = -5_000_000.0
        portfolio.write_portfolio(data_neg, username="test_user")

        port = portfolio.read_portfolio(username="test_user")
        # settings 원본에 음수가 그대로 보존되어 있어야 함
        dad_cash = port["settings"]["cash_balances"]["acc-dad"]["KRW"]
        self.assertEqual(dad_cash, -5_000_000.0)

        dash = portfolio.get_dashboard(username="test_user")
        # dash accounts에서도 음수 그대로 보존되어 있어야 함
        dad_acc = next(a for a in dash["accounts"] if a["id"] == "acc-dad")
        self.assertEqual(dad_acc["cash_krw"], -5_000_000.0)

        # 주식기록은 음수 예수금에 영향받지 않음
        rec = asset_records.build_stock_record_from_holdings(dash["holdings"], owner="모두")
        self.assertEqual(rec["total_value_krw"], 104_600_000)
        self.assertEqual(rec["day_profit_krw"], 0.0)

    def test_split_buying_scenario_does_not_treat_capital_as_day_profit(self) -> None:
        """분할매수로 보유수량이 증가했을 때 매수 원금을 당일 투자손익으로 오인하지 않아야 함."""
        # 당일 5,000,000원어치 현대차 주식을 추가 매수함 (당일 가격변동 rate=0.0)
        data_buy = deepcopy(self.base_data)
        data_buy["settings"]["cash_balances"]["acc-dad"]["KRW"] -= 5_000_000
        data_buy["holdings"].append({
            "id": "stock-hyundai",
            "account_id": "acc-dad",
            "broker": "테스트증권",
            "code": "005380",
            "name": "현대차",
            "quantity": 25,
            "avg_price": 200_000,
            "current_price": 200_000,
            "currency": "KRW",
            "market": "KRX",
            "day_change_rate": 0.0,
            "owner": "아빠",
        })
        portfolio.write_portfolio(data_buy, username="test_user")

        dash = portfolio.get_dashboard(username="test_user")
        rec = asset_records.build_stock_record_from_holdings(dash["holdings"], owner="모두")

        # 총주식자산은 5,000,000원 증가한 109,600,000원
        self.assertEqual(rec["total_value_krw"], 104_600_000 + 5_000_000)
        # 총매입금액도 5,000,000원 증가
        self.assertEqual(rec["total_cost_krw"], 91_950_000 + 5_000_000)
        # 가격변동이 없었으므로 day_profit_krw는 5,000,000이 아니라 0이어야 함!
        self.assertEqual(rec["day_profit_krw"], 0.0)

    def test_selling_scenario_does_not_treat_cash_transfer_as_loss(self) -> None:
        """주식을 매도하여 주식이 현금으로 전환될 때 손실로 오인하지 않아야 함."""
        # 네이버(22,000,000원)를 전량 매도하여 현금으로 회수함
        data_sell = deepcopy(self.base_data)
        data_sell["settings"]["cash_balances"]["acc-mom"]["KRW"] += 22_000_000
        data_sell["holdings"] = [h for h in data_sell["holdings"] if h["id"] != "stock-krw-mom"]
        portfolio.write_portfolio(data_sell, username="test_user")

        dash = portfolio.get_dashboard(username="test_user")
        rec = asset_records.build_stock_record_from_holdings(dash["holdings"], owner="모두")

        # 네이버 제외된 주식 평가액: 삼성(80M) + 애플(2.6M) = 82.6M
        self.assertEqual(rec["total_value_krw"], 82_600_000)
        # 매도로 인한 총주식자산 감소(-22,000,000)가 day_profit_krw에 -22M 손실로 잡히면 안 됨!
        self.assertEqual(rec["day_profit_krw"], 0.0)

    def test_price_increase_and_decrease_scenarios(self) -> None:
        """실제 주가 등락률이 존재할 때 day_profit_krw가 정확히 계산되어야 함."""
        # 1. 삼성전자 +5% 상승, 애플 0%, 네이버 0%
        # 삼성전자 평가액 80,000,000원, r = 5.0
        # gain = 80,000,000 * (5.0 / 105.0) = 3,809,523.81
        data_up = deepcopy(self.base_data)
        data_up["holdings"][0]["day_change_rate"] = 5.0
        portfolio.write_portfolio(data_up, username="test_user")

        dash_up = portfolio.get_dashboard(username="test_user")
        rec_up = asset_records.build_stock_record_from_holdings(dash_up["holdings"], owner="모두")
        expected_gain = 80_000_000.0 * (5.0 / 105.0)
        self.assertAlmostEqual(rec_up["day_profit_krw"], round(expected_gain, 2), delta=1.0)
        self.assertGreater(rec_up["day_profit_krw"], 0)

        # 2. 삼성전자 -5% 하락
        # gain = 80,000,000 * (-5.0 / 95.0) = -4,210,526.32
        data_down = deepcopy(self.base_data)
        data_down["holdings"][0]["day_change_rate"] = -5.0
        portfolio.write_portfolio(data_down, username="test_user")

        dash_down = portfolio.get_dashboard(username="test_user")
        rec_down = asset_records.build_stock_record_from_holdings(dash_down["holdings"], owner="모두")
        expected_loss = 80_000_000.0 * (-5.0 / 95.0)
        self.assertAlmostEqual(rec_down["day_profit_krw"], round(expected_loss, 2), delta=1.0)
        self.assertLess(rec_down["day_profit_krw"], 0)

    def test_owner_snapshots_calculated_independently(self) -> None:
        """아빠와 엄마의 주식기록 스냅샷이 각자의 holdings만 반영하여 독립 계산되어야 함."""
        dash = portfolio.get_dashboard(username="test_user")
        holdings = dash["holdings"]

        dad_holdings = [h for h in holdings if h.get("owner") == "아빠"]
        mom_holdings = [h for h in holdings if h.get("owner") == "엄마"]

        rec_dad = asset_records.build_stock_record_from_holdings(dad_holdings, owner="아빠")
        rec_mom = asset_records.build_stock_record_from_holdings(mom_holdings, owner="엄마")

        # 아빠: 삼성(80M) + 애플(2.6M) = 82.6M
        self.assertEqual(rec_dad["total_value_krw"], 82_600_000)
        self.assertEqual(rec_dad["holding_count"], 2)
        self.assertEqual(rec_dad["krw_value_krw"], 80_000_000)
        self.assertEqual(rec_dad["usd_value_krw"], 2_600_000)

        # 엄마: 네이버(22M)
        self.assertEqual(rec_mom["total_value_krw"], 22_000_000)
        self.assertEqual(rec_mom["holding_count"], 1)
        self.assertEqual(rec_mom["krw_value_krw"], 22_000_000)
        self.assertEqual(rec_mom["usd_value_krw"], 0.0)

        # 합산 검증: 아빠 + 엄마 = 모두
        self.assertEqual(rec_dad["total_value_krw"] + rec_mom["total_value_krw"], 104_600_000)

    def test_auto_save_all_owner_snapshots_integration(self) -> None:
        """auto_save_all_owner_snapshots가 각 owner별로 순수 주식기록을 정확히 자동 저장하는지 검증."""
        from app.main import auto_save_all_owner_snapshots

        dash = portfolio.get_dashboard(username="test_user")
        auto_save_all_owner_snapshots(dash, username="test_user")

        records = asset_records.list_asset_records(username="test_user")
        by_owner = {r.get("owner"): r for r in records}

        self.assertIn("모두", by_owner)
        self.assertIn("아빠", by_owner)
        self.assertIn("엄마", by_owner)
        self.assertIn("자녀", by_owner)

        # 모두: 주식 평가액만 104,600,000 (예수금 26.3M 미포함)
        self.assertEqual(by_owner["모두"]["total_value_krw"], 104_600_000)
        self.assertEqual(by_owner["모두"]["day_profit_krw"], 0.0)

        # 아빠: 주식 평가액만 82,600,000 (예수금 21.3M 미포함)
        self.assertEqual(by_owner["아빠"]["total_value_krw"], 82_600_000)
        self.assertEqual(by_owner["아빠"]["day_profit_krw"], 0.0)

        # 엄마: 주식 평가액만 22,000,000 (예수금 5.0M 미포함)
        self.assertEqual(by_owner["엄마"]["total_value_krw"], 22_000_000)
        self.assertEqual(by_owner["엄마"]["day_profit_krw"], 0.0)

        # 자녀: 보유종목이 없어도 0원 기록을 생성하여 owner별 날짜 축을 유지
        self.assertEqual(by_owner["자녀"]["total_value_krw"], 0.0)
        self.assertEqual(by_owner["자녀"]["holding_count"], 0)

    def test_snapshot_api_endpoint_integration(self) -> None:
        """/api/asset-records/snapshot 엔드포인트가 순수 주식기록을 반환/저장하는지 검증."""
        import asyncio
        import app.main as main_mod
        from regression_support import authenticated_request

        req = authenticated_request("test_user")
        res = asyncio.run(main_mod.snapshot_asset_record(req))
        rec = res["record"]

        # 스냅샷의 total_value_krw는 주식 평가액만 104,600,000
        self.assertEqual(rec["total_value_krw"], 104_600_000)
        self.assertEqual(rec["total_cost_krw"], 91_950_000)
        self.assertEqual(rec["krw_value_krw"], 102_000_000)
        self.assertEqual(rec["usd_value_krw"], 2_600_000)
        self.assertEqual(rec["source"], "snapshot")
        by_owner = {r.get("owner"): r for r in res["records"]}
        self.assertEqual(set(by_owner), {"모두", "아빠", "엄마", "자녀"})
        self.assertEqual(by_owner["아빠"]["total_value_krw"], 82_600_000)
        self.assertEqual(by_owner["엄마"]["total_value_krw"], 22_000_000)
        self.assertEqual(by_owner["자녀"]["total_value_krw"], 0.0)
        self.assertTrue(all(r.get("source") == "snapshot" for r in res["records"]))


    def test_all_owner_net_worth_snapshots_include_zero_owner(self) -> None:
        """순자산 자동 기록도 모두/가족 구성원 전체를 동일 날짜에 저장해야 함."""
        import app.main as main_mod

        dash = portfolio.get_dashboard(username="test_user")
        dash.update({
            "bank_accounts": [],
            "savings_accounts": [],
            "insurance_accounts": [],
            "loan_accounts": [],
            "real_estates": [],
        })
        state, snapshots = main_mod.save_all_owner_net_worth_snapshots(
            dash,
            "test_user",
            source="auto",
        )

        by_owner = {item["owner"]: item for item in snapshots}
        self.assertEqual(set(by_owner), {"모두", "아빠", "엄마", "자녀"})
        self.assertEqual(by_owner["모두"]["assets"], 130_900_000)
        self.assertEqual(by_owner["아빠"]["assets"], 103_900_000)
        self.assertEqual(by_owner["엄마"]["assets"], 27_000_000)
        self.assertEqual(by_owner["자녀"]["assets"], 0.0)
        self.assertTrue(all(item["debt"] == 0 for item in snapshots))

        today_records = [r for r in state["history"] if r.get("source") == "auto"]
        self.assertEqual({r.get("owner") for r in today_records}, {"모두", "아빠", "엄마", "자녀"})


    def test_net_worth_snapshot_real_estate_single_owner_uses_full_share(self) -> None:
        """ownerships 배열이 없어도 owner 단독 부동산은 해당 owner에게 100% 반영되어야 함."""
        from app.services.planning import build_net_worth_snapshot

        dash = portfolio.get_dashboard(username="test_user")
        dash.update({
            "accounts": [],
            "holdings": [],
            "bank_accounts": [],
            "savings_accounts": [],
            "insurance_accounts": [],
            "loan_accounts": [],
            "real_estates": [{
                "id": "re-dad",
                "owner": "아빠",
                "property_type": "own",
                "current_price": 100_000_000,
            }],
        })

        rec_all = build_net_worth_snapshot(dash, "모두")
        rec_dad = build_net_worth_snapshot(dash, "아빠")
        rec_mom = build_net_worth_snapshot(dash, "엄마")
        self.assertEqual(rec_all["assets"], 100_000_000)
        self.assertEqual(rec_dad["assets"], 100_000_000)
        self.assertEqual(rec_mom["assets"], 0.0)


    def test_auto_and_manual_snapshot_financial_values_match(self) -> None:
        """Auto and manual snapshots must have identical financial values for the same dashboard state."""
        import asyncio
        import app.main as main_mod
        from regression_support import authenticated_request

        owner_all = "\ubaa8\ub450"
        dash = portfolio.get_dashboard(username="test_user")

        main_mod.auto_save_all_owner_snapshots(dash, username="test_user")
        records = asset_records.list_asset_records(username="test_user")
        auto_rec = next(
            r for r in records
            if r.get("owner") == owner_all and r.get("source") == "auto"
        )

        req = authenticated_request("test_user")
        manual_rec = asyncio.run(main_mod.snapshot_asset_record(req))["record"]

        financial_fields = (
            "total_value_krw",
            "total_cost_krw",
            "profit_krw",
            "return_rate",
            "day_profit_krw",
            "krw_value_krw",
            "usd_value_krw",
            "holding_count",
        )
        for field in financial_fields:
            self.assertEqual(
                auto_rec[field],
                manual_rec[field],
                f"auto/manual mismatch: {field}",
            )

        self.assertEqual(auto_rec["owner"], owner_all)
        self.assertEqual(manual_rec["owner"], owner_all)
        self.assertEqual(auto_rec["source"], "auto")
        self.assertEqual(manual_rec["source"], "snapshot")

    def test_day_change_rate_authoritative_zero_preserved_without_fallback(self) -> None:
        """current rate가 0.0일 때 stored/fallback 5.0으로 덮어쓰지 않고 0.0을 유지해야 함."""
        data = deepcopy(self.base_data)
        # item에 기존 등락률 5.0이 저장되어 있는 상태
        data["holdings"][0]["day_change_rate"] = 5.0
        # 하지만 최신 authoritative daily_price_changes에는 0.0% 보합으로 들어옴
        data["settings"]["daily_price_changes"] = {"005930": 0.0}
        portfolio.write_portfolio(data, username="test_user")

        dash = portfolio.get_dashboard(username="test_user")
        samsung = next(h for h in dash["holdings"] if h["code"] == "005930")
        self.assertEqual(samsung["day_change_rate"], 0.0)

        # 0.0%이므로 holding_day_gain도 0이어야 함 (+5%에 의한 gain이 발생하면 안 됨)
        rec = asset_records.build_stock_record_from_holdings(dash["holdings"], owner="모두")
        self.assertEqual(rec["day_profit_krw"], 0.0)

    def test_day_change_rate_none_falls_back_to_persisted_holding(self) -> None:
        """current rate가 None일 때 기존 item.day_change_rate(+5.0)로 정상 fallback되어야 함."""
        data = deepcopy(self.base_data)
        data["holdings"][0]["day_change_rate"] = 5.0
        # daily_price_changes나 period_rates에 005930 정보가 없음 (None)
        data["settings"]["daily_price_changes"] = {}
        portfolio.write_portfolio(data, username="test_user")

        dash = portfolio.get_dashboard(username="test_user")
        samsung = next(h for h in dash["holdings"] if h["code"] == "005930")
        self.assertEqual(samsung["day_change_rate"], 5.0)

        # +5.0% 기준 holding_day_gain 계산
        rec = asset_records.build_stock_record_from_holdings(dash["holdings"], owner="모두")
        expected_gain = 80_000_000.0 * (5.0 / 105.0)
        self.assertAlmostEqual(rec["day_profit_krw"], round(expected_gain, 2), delta=1.0)

    def test_day_change_rate_positive_and_negative_current_precedence(self) -> None:
        """current rate가 양수(+3.0) 또는 음수(-2.0)일 때 stored(+8.0)가 덮어쓰지 않고 current가 우선해야 함."""
        # 1. current = +3.0, stored = +8.0
        data_pos = deepcopy(self.base_data)
        data_pos["holdings"][0]["day_change_rate"] = 8.0
        data_pos["settings"]["daily_price_changes"] = {"005930": 3.0}
        portfolio.write_portfolio(data_pos, username="test_user")

        dash_pos = portfolio.get_dashboard(username="test_user")
        samsung_pos = next(h for h in dash_pos["holdings"] if h["code"] == "005930")
        self.assertEqual(samsung_pos["day_change_rate"], 3.0)

        # 2. current = -2.0, stored = +8.0
        data_neg = deepcopy(self.base_data)
        data_neg["holdings"][0]["day_change_rate"] = 8.0
        data_neg["settings"]["daily_price_changes"] = {"005930": -2.0}
        portfolio.write_portfolio(data_neg, username="test_user")

        dash_neg = portfolio.get_dashboard(username="test_user")
        samsung_neg = next(h for h in dash_neg["holdings"] if h["code"] == "005930")
        self.assertEqual(samsung_neg["day_change_rate"], -2.0)

    def test_day_change_rate_both_missing_normalizes_to_safe_zero(self) -> None:
        """current도 없고 stored도 None일 때 안전하게 0.0으로 정규화되어야 함."""
        data_missing = deepcopy(self.base_data)
        data_missing["holdings"][0]["day_change_rate"] = None
        data_missing["settings"]["daily_price_changes"] = {}
        portfolio.write_portfolio(data_missing, username="test_user")

        dash = portfolio.get_dashboard(username="test_user")
        samsung = next(h for h in dash["holdings"] if h["code"] == "005930")
        self.assertEqual(samsung["day_change_rate"], 0.0)

    def test_dashboard_day_change_contract_maintained(self) -> None:
        """get_dashboard()['day_change']의 change_krw 및 change_rate 계약이 보존되고 holding_day_gain이 함께 노출되는지 검증."""
        dash = portfolio.get_dashboard(username="test_user")
        self.assertIn("day_change", dash)
        self.assertIn("change_krw", dash["day_change"])
        self.assertIn("change_rate", dash["day_change"])
        self.assertIn("holding_day_gain", dash["day_change"])
        self.assertIn("holding_day_gain", dash["summary"])


    def test_daily_price_changes_code_zero_preserved_over_name_fallback(self) -> None:
        """period_rates 없고 code 기준 0.0, name 기준 5.0일 때 code 0.0이 name 5.0을 이기고 0.0으로 보존되어야 함."""
        data = deepcopy(self.base_data)
        # stored rate는 8.0
        data["holdings"][0]["day_change_rate"] = 8.0
        # period_rates 없음
        data["settings"]["period_rates"] = {}
        # daily_price_changes에 code=0.0, name=5.0
        data["settings"]["daily_price_changes"] = {
            "005930": 0.0,
            "삼성전자": 5.0,
        }
        portfolio.write_portfolio(data, username="test_user")

        dash = portfolio.get_dashboard(username="test_user")
        samsung = next(h for h in dash["holdings"] if h["code"] == "005930")
        self.assertEqual(samsung["day_change_rate"], 0.0)

        # 주식기록에서도 0.0% 반영되어 holding_day_gain이 0이어야 함 (5% gain이나 8% gain 발생 금지)
        rec = asset_records.build_stock_record_from_holdings(dash["holdings"], owner="모두")
        self.assertEqual(rec["day_profit_krw"], 0.0)

    def test_holding_day_gain_abnormal_minus_100_percent_rate_safe(self) -> None:
        """비정상 데이터로 r <= -100.0 (예: -100.0% 상장폐지/오류 또는 -150.0%)이 들어와도 ZeroDivisionError 없이 안전 처리되어야 함."""
        data = deepcopy(self.base_data)
        data["holdings"][0]["day_change_rate"] = -100.0
        portfolio.write_portfolio(data, username="test_user")

        dash = portfolio.get_dashboard(username="test_user")
        # ZeroDivisionError 없이 대시보드가 정상 반환되어야 함
        self.assertIsNotNone(dash)
        self.assertIn("holding_day_gain", dash["summary"])

        # asset_records.build_stock_record_from_holdings도 예외 없이 안전 처리되어야 함
        rec = asset_records.build_stock_record_from_holdings(dash["holdings"], owner="모두")
        self.assertIsNotNone(rec)
        self.assertIn("day_profit_krw", rec)


if __name__ == "__main__":
    unittest.main()
