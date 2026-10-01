from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.services.pnl_records import PnlRecordsLinkedToIpoError
from tests.regression_support import authenticated_request, import_main_without_loading_real_env


class RealizedPnlBrokerScopedClearApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main = import_main_without_loading_real_env()

    def test_selected_broker_routes_to_atomic_scoped_clear(self) -> None:
        request = authenticated_request("scoped-clear-user")
        with patch.object(
            self.main,
            "clear_pnl_records_for_broker",
            return_value=7,
        ) as clear_scope:
            result = asyncio.run(
                self.main.clear_realized_pnl_endpoint(
                    request,
                    broker="토스증권",
                )
            )

        clear_scope.assert_called_once_with("토스증권", username="scoped-clear-user")
        self.assertEqual(result["deleted"], 7)
        self.assertEqual(result["broker"], "토스증권")
        self.assertIn("토스증권", result["message"])
        self.assertIn("7건", result["message"])

    def test_omitted_broker_keeps_existing_global_clear_contract(self) -> None:
        request = authenticated_request("global-clear-user")
        with patch.object(self.main, "clear_pnl_records") as clear_all, patch.object(
            self.main,
            "clear_pnl_records_for_broker",
        ) as clear_scope:
            result = asyncio.run(
                self.main.clear_realized_pnl_endpoint(request, broker=None)
            )

        clear_all.assert_called_once_with(username="global-clear-user")
        clear_scope.assert_not_called()
        self.assertEqual(result, {"message": "모든 매도 실현손익 기록이 삭제되었습니다."})

    def test_scoped_ipo_link_conflict_remains_structured_409(self) -> None:
        request = authenticated_request("linked-clear-user")
        with patch.object(
            self.main,
            "clear_pnl_records_for_broker",
            side_effect=PnlRecordsLinkedToIpoError("PNL_RECORDS_LINKED_TO_IPO"),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    self.main.clear_realized_pnl_endpoint(
                        request,
                        broker="토스증권",
                    )
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(
            raised.exception.detail["code"],
            "PNL_RECORDS_LINKED_TO_IPO",
        )

    def test_blank_broker_scope_is_rejected(self) -> None:
        request = authenticated_request("blank-clear-user")
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(
                self.main.clear_realized_pnl_endpoint(request, broker="   ")
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail["code"], "BROKER_SCOPE_INVALID")


if __name__ == "__main__":
    unittest.main()
