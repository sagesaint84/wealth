from __future__ import annotations

import json

from app.services import pnl_records, portfolio
from app.services.pnl_broker_clear import (
    UNASSIGNED_BROKER_SCOPE,
    clear_pnl_records_for_broker,
)
from tests.regression_support import IsolatedDataTestCase, empty_portfolio


class RealizedPnlBrokerScopedClearTests(IsolatedDataTestCase):
    username = "broker-scoped-clear"

    def _record(
        self,
        record_id: str,
        broker: str,
        *,
        asset_type: str = "stock",
        source: str = "manual",
    ) -> dict:
        return {
            "id": record_id,
            "date": "2026-09-07",
            "code": record_id.upper(),
            "name": record_id,
            "asset_type": asset_type,
            "currency": "KRW",
            "pnl": 1000,
            "pnl_krw": 1000,
            "broker": broker,
            "source": source,
        }

    def _write_records(self, records: list[dict]) -> None:
        pnl_records.write_pnl_records(records, self.username)

    def _link_pnl_record(self, record_id: str) -> None:
        data = empty_portfolio()
        data["settings"]["ipo"] = {
            "applications": {
                "fixture-ipo": {
                    "applicants": {
                        "fixture-user": {
                            "allocation": {
                                "links": [{"pnl_record_id": record_id}]
                            }
                        }
                    }
                }
            }
        }
        path = portfolio._get_portfolio_file(self.username)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_scoped_clear_deletes_only_requested_broker(self) -> None:
        records = [
            self._record("toss-1", "토스증권", source="toss_wts"),
            self._record("toss-2", "토스증권", source="toss_wts"),
            self._record("kis-1", "한국투자증권", source="kis"),
            self._record("manual-1", "", source="manual"),
            self._record("real-estate-1", "토스증권", asset_type="real_estate"),
        ]
        self._write_records(records)

        deleted = clear_pnl_records_for_broker("토스증권", self.username)

        self.assertEqual(deleted, 2)
        remaining = pnl_records.read_pnl_records(self.username)
        self.assertEqual(
            [record["id"] for record in remaining],
            ["kis-1", "manual-1", "real-estate-1"],
        )

    def test_linked_target_blocks_entire_scope_without_partial_delete(self) -> None:
        records = [
            self._record("toss-1", "토스증권", source="toss_wts"),
            self._record("toss-2", "토스증권", source="toss_wts"),
            self._record("kis-1", "한국투자증권", source="kis"),
        ]
        self._write_records(records)
        self._link_pnl_record("toss-2")

        with self.assertRaisesRegex(
            pnl_records.PnlRecordsLinkedToIpoError,
            "PNL_RECORDS_LINKED_TO_IPO",
        ):
            clear_pnl_records_for_broker("토스증권", self.username)

        self.assertEqual(pnl_records.read_pnl_records(self.username), records)

    def test_link_on_other_broker_does_not_block_requested_scope(self) -> None:
        records = [
            self._record("toss-1", "토스증권", source="toss_wts"),
            self._record("kis-1", "한국투자증권", source="kis"),
        ]
        self._write_records(records)
        self._link_pnl_record("kis-1")

        deleted = clear_pnl_records_for_broker("토스증권", self.username)

        self.assertEqual(deleted, 1)
        self.assertEqual(
            [record["id"] for record in pnl_records.read_pnl_records(self.username)],
            ["kis-1"],
        )

    def test_unassigned_scope_only_deletes_records_without_broker(self) -> None:
        records = [
            self._record("unassigned-1", ""),
            self._record("toss-1", "토스증권", source="toss_wts"),
        ]
        self._write_records(records)

        deleted = clear_pnl_records_for_broker(
            UNASSIGNED_BROKER_SCOPE,
            self.username,
        )

        self.assertEqual(deleted, 1)
        self.assertEqual(
            [record["id"] for record in pnl_records.read_pnl_records(self.username)],
            ["toss-1"],
        )

    def test_empty_scope_is_rejected_without_write(self) -> None:
        records = [self._record("toss-1", "토스증권", source="toss_wts")]
        self._write_records(records)

        with self.assertRaisesRegex(ValueError, "BROKER_SCOPE_INVALID"):
            clear_pnl_records_for_broker("   ", self.username)

        self.assertEqual(pnl_records.read_pnl_records(self.username), records)


if __name__ == "__main__":
    import unittest

    unittest.main()
