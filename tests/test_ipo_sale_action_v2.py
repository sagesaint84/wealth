"""Phase 4 HTTP integration tests for OPEN_IPO_SALE_FLOW.

All state is isolated in a TemporaryDirectory; repository data/ is never used.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import COOKIE_NAME, _serializer, app
from app.services.action_v2 import (
    ACTION_TYPE_OPEN_IPO_SALE_FLOW,
    _load_v2,
    create_web_action,
)
from app.services.ipo.allocation import allocation_summary, link_sale
from app.services.ipo.applications import ApplicationRevisionConflict, get_user_applications
from app.services.pnl_records import create_pnl_record, read_pnl_records_readonly
from app.services.portfolio import read_portfolio, write_portfolio


class IpoSaleActionV2HttpTests(unittest.TestCase):
    IPO_ID = "ipo-sale-v2"
    OWNER = "아빠"
    STOCK_CODE = "123456"
    ACCOUNT_ID = "acct-mirae"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wealth-sale-v2-")
        self.addCleanup(self.temp.cleanup)
        self.user_dir = Path(self.temp.name) / "user"
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.action_file = Path(self.temp.name) / "action_v2_state.json"
        self.today = date(2026, 9, 29)
        self.public_origin = "https://wealth.example.com"
        self.market = {
            "ipos": [
                {
                    "ipo_id": self.IPO_ID,
                    "company_name": "테스트상장",
                    "stock_code": self.STOCK_CODE,
                    "actual_listing_date": self.today.isoformat(),
                    "expected_listing_date": self.today.isoformat(),
                    "subscription_start": "2026-09-01",
                    "subscription_end": "2026-09-02",
                    "final_offer_price": 20000,
                }
            ]
        }
        self.patches = [
            patch("app.services.user_manager.get_user_data_dir", return_value=self.user_dir),
            patch("app.services.portfolio._get_user_dir", return_value=self.user_dir),
            patch("app.services.portfolio.assert_write_allowed", return_value=None),
            patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_file),
            patch("app.services.ipo.actions.read_market_store_read_only", side_effect=lambda: self.market),
            patch("app.services.ipo.store.read_market_store_read_only", side_effect=lambda: self.market),
            patch(
                "app.services.system_settings.get_effective_system_settings",
                return_value={"public_base_url": self.public_origin},
            ),
            patch(
                "app.services.user_manager.get_user_by_name",
                side_effect=lambda username: {
                    "id": f"id-{username}", "username": username, "role": "user"
                },
            ),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

        self.client = TestClient(app)
        self._seed_portfolio(allocation_quantity=4)
        self._login("alice")

    def _login(self, username: str) -> None:
        token = _serializer.dumps({"user": username, "role": "user"})
        self.client.cookies.clear()
        self.client.cookies.set(COOKIE_NAME, token)

    def _seed_portfolio(
        self,
        *,
        allocation_quantity: int | None = 4,
        mapped: bool = True,
        revision: int = 1,
        links: list[dict] | None = None,
    ) -> None:
        applicant: dict = {}
        if mapped:
            applicant.update({"broker_id": "mirae", "account_id": self.ACCOUNT_ID})
        if allocation_quantity is not None:
            applicant["allocation"] = {
                "id": "alloc-1",
                "quantity": allocation_quantity,
                "offer_price": 20000,
                "links": list(links or []),
            }
        portfolio = {
            "settings": {
                "family_members": [self.OWNER],
                "ipo": {
                    "revision": revision,
                    "applications": {
                        self.IPO_ID: {
                            "target_owners": [self.OWNER],
                            "applied_owners": [self.OWNER],
                            "applicants": {self.OWNER: applicant},
                        }
                    },
                },
            },
            "accounts": [
                {
                    "id": self.ACCOUNT_ID,
                    "broker": "미래에셋증권",
                    "name": "IPO",
                    "owner": self.OWNER,
                },
                {"id": "other-account", "broker": "미래에셋증권", "name": "Other", "owner": self.OWNER},
            ],
            "holdings": [],
        }
        write_portfolio(portfolio, username="alice")

    def _create_action(self, *, today: date | None = None) -> dict:
        return create_web_action(
            username="alice",
            action_type=ACTION_TYPE_OPEN_IPO_SALE_FLOW,
            source_channel="telegram",
            metadata={"ipo_id": self.IPO_ID, "owner": self.OWNER},
            today=today or self.today,
            path=self.action_file,
        )

    def _sale(
        self,
        quantity: int,
        *,
        account_id: str | None = None,
        broker: str = "미래에셋증권",
        code: str | None = None,
        trade_date: str | None = None,
        pnl: int = 10000,
    ) -> dict:
        return create_pnl_record(
            {
                "date": trade_date or self.today.isoformat(),
                "code": code or self.STOCK_CODE,
                "name": "테스트상장",
                "currency": "KRW",
                "pnl": pnl,
                "pnl_krw": pnl,
                "quantity": quantity,
                "sell_amount": quantity * 30000,
                "fee": 100,
                "tax": 100,
                "broker": broker,
                "account_id": account_id or self.ACCOUNT_ID,
            },
            username="alice",
        )

    def _post(self, token: str, pnl_id: str, qty: int, *, origin: str | None = None):
        headers = {} if origin is None else {"Origin": origin}
        return self.client.post(
            f"/a/{token}/link-sale",
            data={"pnl_record_id": pnl_id, "matched_quantity": str(qty)},
            headers=headers,
        )

    def _action_record(self, action: dict) -> dict:
        return _load_v2(self.action_file)["actions"][action["token_digest"]]

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _tree_hashes(self) -> dict[str, str]:
        root = Path(self.temp.name)
        return {
            p.relative_to(root).as_posix(): self._sha(p)
            for p in sorted(root.rglob("*")) if p.is_file()
        }

    def test_get_is_read_only_and_candidate_is_sanitized(self):
        sale = self._sale(2, pnl=12345)
        action = self._create_action()
        before = self._tree_hashes()
        for _ in range(5):
            response = self.client.get(f"/a/{action['raw_token']}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("매도 실현손익 기록 선택", response.text)
            self.assertIn(sale["id"], response.text)
            self.assertIn(self.today.isoformat(), response.text)
            self.assertNotIn(self.ACCOUNT_ID, response.text)
            self.assertNotIn("sell_amount", response.text)
        after = self._tree_hashes()
        self.assertEqual(before, after)
        self.assertIsNone(self._action_record(action)["consumed_at"])
        self.assertFalse(any(name.endswith(".tmp") for name in after))

    def test_partial_then_full_consumes_only_at_full_and_pnl_hash_never_changes(self):
        first = self._sale(2, pnl=20000)
        second = self._sale(2, pnl=30000)
        pnl_file = self.user_dir / "realized_pnl_records.json"
        pnl_before = self._sha(pnl_file)
        action = self._create_action()

        partial = self._post(action["raw_token"], first["id"], 2, origin=self.public_origin)
        self.assertEqual(partial.status_code, 200)
        summary = allocation_summary("alice", self.IPO_ID, self.OWNER, self.STOCK_CODE, self.today.isoformat())
        self.assertEqual(summary["status"], "PARTIALLY_SOLD")
        self.assertEqual(summary["allocation"]["remaining_quantity"], 2)
        self.assertIsNone(self._action_record(action)["consumed_at"])
        self.assertEqual(self._sha(pnl_file), pnl_before)

        full = self._post(action["raw_token"], second["id"], 2, origin=self.public_origin)
        self.assertEqual(full.status_code, 200)
        self.assertIn("전량 매도", full.text)
        summary = allocation_summary("alice", self.IPO_ID, self.OWNER, self.STOCK_CODE, self.today.isoformat())
        self.assertEqual(summary["status"], "FULLY_SOLD")
        self.assertEqual(summary["allocation"]["remaining_quantity"], 0)
        self.assertIsNotNone(self._action_record(action)["consumed_at"])
        self.assertEqual(self._sha(pnl_file), pnl_before)

    def test_stale_fully_sold_post_is_idempotent_and_does_not_bump_revision(self):
        sale = self._sale(4)
        action = self._create_action()
        revision = get_user_applications("alice")["revision"]
        link_sale("alice", self.IPO_ID, self.OWNER, sale["id"], 4, revision, self.STOCK_CODE, self.today.isoformat())
        revision_after_link = get_user_applications("alice")["revision"]
        links_before = allocation_summary("alice", self.IPO_ID, self.OWNER, self.STOCK_CODE, self.today.isoformat())["links"]

        get_response = self.client.get(f"/a/{action['raw_token']}")
        self.assertEqual(get_response.status_code, 200)
        self.assertIn("매도 기록 완료", get_response.text)
        self.assertIsNone(self._action_record(action)["consumed_at"])

        post_response = self._post(action["raw_token"], sale["id"], 4, origin=self.public_origin)
        self.assertEqual(post_response.status_code, 200)
        self.assertEqual(get_user_applications("alice")["revision"], revision_after_link)
        links_after = allocation_summary("alice", self.IPO_ID, self.OWNER, self.STOCK_CODE, self.today.isoformat())["links"]
        self.assertEqual(links_before, links_after)
        self.assertIsNotNone(self._action_record(action)["consumed_at"])

    def test_link_data_missing_is_fail_closed(self):
        self._seed_portfolio(
            allocation_quantity=4,
            revision=1,
            links=[{"pnl_record_id": "missing-pnl", "matched_quantity": 1, "linked_at": "2026-09-29T10:00:00+09:00"}],
        )
        action = self._create_action()
        response = self.client.get(f"/a/{action['raw_token']}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("매도 연결 데이터 오류", response.text)
        post = self._post(action["raw_token"], "missing-pnl", 1, origin=self.public_origin)
        self.assertEqual(post.status_code, 409)
        self.assertIn("IPO_LINK_DATA_MISSING", post.text)
        self.assertIsNone(self._action_record(action)["consumed_at"])

    def test_no_allocation_unresolved_and_unresolved_account_have_no_mutation_form(self):
        cases = [
            ("NO_ALLOCATION", 0, True, "배정 0주"),
            ("UNRESOLVED", None, True, "배정수량 미기록"),
            ("UNRESOLVED_ACCOUNT", None, False, "청약 계좌 연결 필요"),
        ]
        for status, qty, mapped, expected in cases:
            with self.subTest(status=status):
                self._seed_portfolio(allocation_quantity=qty, mapped=mapped, revision=1)
                action = self._create_action()
                get_response = self.client.get(f"/a/{action['raw_token']}")
                self.assertEqual(get_response.status_code, 200)
                self.assertIn(expected, get_response.text)
                self.assertNotIn("매도 실현손익 기록 선택", get_response.text)
                post = self._post(action["raw_token"], "anything", 1, origin=self.public_origin)
                self.assertEqual(post.status_code, 400)
                self.assertIsNone(self._action_record(action)["consumed_at"])
                # isolate the next subcase's Action V2 store
                self.action_file.unlink(missing_ok=True)
                self.action_file.with_suffix(".lock").unlink(missing_ok=True)

    def test_cross_user_and_csrf_are_fail_closed(self):
        sale = self._sale(2)
        action = self._create_action()
        portfolio_before = self._sha(self.user_dir / "portfolio.json")
        pnl_before = self._sha(self.user_dir / "realized_pnl_records.json")

        self._login("bob")
        get_response = self.client.get(f"/a/{action['raw_token']}")
        self.assertEqual(get_response.status_code, 403)
        self.assertNotIn(self.OWNER, get_response.text)
        post_response = self._post(action["raw_token"], sale["id"], 1, origin=self.public_origin)
        self.assertEqual(post_response.status_code, 403)
        self.assertNotIn(self.OWNER, post_response.text)

        self._login("alice")
        missing_origin = self._post(action["raw_token"], sale["id"], 1)
        self.assertEqual(missing_origin.status_code, 403)
        evil = self._post(action["raw_token"], sale["id"], 1, origin="https://evil.example")
        self.assertEqual(evil.status_code, 403)
        self.assertEqual(self._sha(self.user_dir / "portfolio.json"), portfolio_before)
        self.assertEqual(self._sha(self.user_dir / "realized_pnl_records.json"), pnl_before)
        self.assertIsNone(self._action_record(action)["consumed_at"])

    def test_expired_sale_action_blocks_get_and_post(self):
        old_day = date(2000, 1, 2)
        self.market["ipos"][0]["actual_listing_date"] = old_day.isoformat()
        self.market["ipos"][0]["expected_listing_date"] = old_day.isoformat()
        sale = self._sale(2, trade_date=old_day.isoformat())
        action = self._create_action(today=old_day)
        get_response = self.client.get(f"/a/{action['raw_token']}")
        self.assertEqual(get_response.status_code, 410)
        post_response = self._post(action["raw_token"], sale["id"], 1, origin=self.public_origin)
        self.assertEqual(post_response.status_code, 410)
        self.assertIsNone(self._action_record(action)["consumed_at"])

    def test_financial_integrity_rejections_use_canonical_link_sale(self):
        action = self._create_action()
        wrong_records = [
            self._sale(2, account_id="other-account"),
            self._sale(2, broker="KB증권"),
            self._sale(2, code="654321"),
            self._sale(2, trade_date=(self.today - timedelta(days=1)).isoformat()),
        ]
        for record in wrong_records:
            with self.subTest(record=record["id"]):
                response = self._post(action["raw_token"], record["id"], 1, origin=self.public_origin)
                self.assertEqual(response.status_code, 400)
                self.assertIn("종목·계좌 조건", response.text)

        zero = self._post(action["raw_token"], wrong_records[0]["id"], 0, origin=self.public_origin)
        self.assertEqual(zero.status_code, 400)

        big = self._sale(10)
        allocation_overrun = self._post(action["raw_token"], big["id"], 5, origin=self.public_origin)
        self.assertEqual(allocation_overrun.status_code, 400)
        self.assertIn("잔여 배정수량", allocation_overrun.text)

        small = self._sale(2)
        pnl_overrun = self._post(action["raw_token"], small["id"], 3, origin=self.public_origin)
        self.assertEqual(pnl_overrun.status_code, 400)
        self.assertIn("수량이 초과", pnl_overrun.text)

        good = self._sale(4)
        first = self._post(action["raw_token"], good["id"], 1, origin=self.public_origin)
        self.assertEqual(first.status_code, 200)
        duplicate_conflict = self._post(action["raw_token"], good["id"], 2, origin=self.public_origin)
        self.assertEqual(duplicate_conflict.status_code, 400)
        self.assertIn("이미 동일한 기록", duplicate_conflict.text)
        self.assertIsNone(self._action_record(action)["consumed_at"])

    def test_cas_retry_is_bounded(self):
        sale = self._sale(2)
        action = self._create_action()
        from app.services.ipo.allocation import link_sale as real_link_sale

        calls = {"count": 0}
        def conflict_once(**kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ApplicationRevisionConflict("Revision conflict")
            return real_link_sale(**kwargs)

        with patch("app.services.ipo.allocation.link_sale", side_effect=conflict_once):
            response = self._post(action["raw_token"], sale["id"], 1, origin=self.public_origin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls["count"], 2)

        # A fresh action/portfolio for the exhaustion branch.
        self._seed_portfolio(allocation_quantity=4, mapped=True, revision=1)
        self.action_file.unlink(missing_ok=True)
        self.action_file.with_suffix(".lock").unlink(missing_ok=True)
        action2 = self._create_action()
        with patch("app.services.ipo.allocation.link_sale", side_effect=ApplicationRevisionConflict("Revision conflict")) as mocked:
            exhausted = self._post(action2["raw_token"], sale["id"], 1, origin=self.public_origin)
        self.assertEqual(exhausted.status_code, 400)
        self.assertEqual(mocked.call_count, 3)
        self.assertIsNone(self._action_record(action2)["consumed_at"])


if __name__ == "__main__":
    unittest.main()
