import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.ipo.allocation import AllocationConflict, allocation_summary, link_sale, sale_candidates, set_allocation, unlink_sale
from app.services.ipo.applications import (ApplicationAccountMappingConflict, remap_user_application_account)
from app.services.pnl_records import (PnlRecordLinkedToIpoError, PnlRecordsLinkedToIpoError,
                                      clear_pnl_records, create_pnl_record, delete_pnl_record,
                                      read_pnl_records_readonly, write_pnl_records)
from app.services.portfolio import write_portfolio


class IpoAllocationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.dir=Path(self.temp.name); self.user="ipo-lot"
        for target, value in (("app.services.user_manager.get_user_data_dir", self.dir), ("app.services.portfolio._get_user_dir", self.dir), ("app.services.portfolio.assert_write_allowed", None)):
            p=patch(target, return_value=value); p.start(); self.addCleanup(p.stop)
        write_portfolio({"settings":{"family_members":["아빠","엄마"],"ipo":{"revision":1,"applications":{
            "ipo-a":{"target_owners":["아빠"],"applied_owners":["아빠"],"applicants":{"아빠":{"broker_id":"mirae","account_id":"a","allocation":None}}},
            "ipo-b":{"target_owners":["엄마"],"applied_owners":["엄마"],"applicants":{"엄마":{"broker_id":"mirae","account_id":"a","allocation":None}}},
        }}},"accounts":[{"id":"a","broker":"미래에셋증권"},{"id":"b","broker":"미래에셋증권"},{"id":"kb","broker":"KB증권"}],"holdings":[]}, username=self.user)

    def sale(self, qty, *, account="a", broker="미래에셋증권", code="123456", date="2026-10-01", pnl=100000):
        return create_pnl_record({"date":date,"code":code,"name":"테스트","currency":"KRW","pnl":pnl,"pnl_krw":pnl,"quantity":qty,"sell_amount":qty*30000,"fee":100,"tax":100,"broker":broker,"account_id":account}, username=self.user)

    def allocate(self, qty=5, rev=1): return set_allocation(self.user,"ipo-a","아빠",qty,20000,rev)

    def test_full_partial_multiple_and_partial_pnl_value(self):
        self.allocate(5); a=self.sale(2,pnl=20000); b=self.sale(1,pnl=10000); c=self.sale(2,pnl=20000)
        link_sale(self.user,"ipo-a","아빠",a["id"],2,2,"123456","2026-09-30")
        link_sale(self.user,"ipo-a","아빠",b["id"],1,3,"123456","2026-09-30")
        link_sale(self.user,"ipo-a","아빠",c["id"],2,4,"123456","2026-09-30")
        summary=allocation_summary(self.user,"ipo-a","아빠","123456","2026-09-30")
        self.assertEqual(summary["status"],"FULLY_SOLD"); self.assertEqual(summary["allocation"]["remaining_quantity"],0); self.assertEqual(summary["allocation"]["realized_pnl_krw"],50000)
        before=len(read_pnl_records_readonly(self.user)); self.assertEqual(before,3)

    def test_partial_oversized_boundaries_and_idempotence(self):
        self.allocate(5); sale=self.sale(10,pnl=100000)
        with self.assertRaises(AllocationConflict): link_sale(self.user,"ipo-a","아빠",sale["id"],6,2,"123456","2026-09-30")
        linked=link_sale(self.user,"ipo-a","아빠",sale["id"],5,2,"123456","2026-09-30"); self.assertEqual(linked["status"],"LINKED")
        same=link_sale(self.user,"ipo-a","아빠",sale["id"],5,3,"123456","2026-09-30"); self.assertEqual(same["status"],"IDEMPOTENT")
        summary=allocation_summary(self.user,"ipo-a","아빠","123456","2026-09-30"); self.assertEqual(summary["allocation"]["realized_pnl_krw"],50000)

    def test_account_broker_stock_date_and_shared_consumption_are_hard_boundaries(self):
        self.allocate(5); good=self.sale(5); self.sale(5,account="b"); self.sale(5,broker="KB증권"); self.sale(5,code="654321"); early=self.sale(5,date="2026-09-01")
        for record in read_pnl_records_readonly(self.user)[1:]:
            with self.assertRaises(Exception): link_sale(self.user,"ipo-a","아빠",record["id"],1,2,"123456","2026-09-30")
        link_sale(self.user,"ipo-a","아빠",good["id"],5,2,"123456","2026-09-30")
        set_allocation(self.user,"ipo-b","엄마",5,20000,3)
        with self.assertRaises(AllocationConflict): link_sale(self.user,"ipo-b","엄마",good["id"],1,4,"123456","2026-09-30")
        with self.assertRaises(AllocationConflict): set_allocation(self.user,"ipo-a","아빠",3,20000,4)
        with self.assertRaises(ApplicationAccountMappingConflict): remap_user_application_account(self.user,"ipo-a","아빠","mirae","b","a",4)

    def test_candidates_are_backend_filtered_and_exclude_consumed_quantity(self):
        self.allocate(5); good=self.sale(5); self.sale(5, account="b")
        candidates=sale_candidates(self.user,"ipo-a","아빠","123456","2026-09-30")
        self.assertEqual([item["pnl_record_id"] for item in candidates], [good["id"]])
        link_sale(self.user,"ipo-a","아빠",good["id"],5,2,"123456","2026-09-30")
        self.assertEqual(sale_candidates(self.user,"ipo-a","아빠","123456","2026-09-30"), [])

    def test_unlink_restores_quantity_is_revision_safe_and_does_not_change_pnl(self):
        self.allocate(5); first=self.sale(2, pnl=20000); second=self.sale(3, pnl=30000)
        link_sale(self.user,"ipo-a","아빠",first["id"],2,2,"123456","2026-09-30")
        link_sale(self.user,"ipo-a","아빠",second["id"],3,3,"123456","2026-09-30")
        before = list(read_pnl_records_readonly(self.user))
        with self.assertRaises(ApplicationAccountMappingConflict):
            # This verifies the existing remap lock while links remain.
            remap_user_application_account(self.user,"ipo-a","아빠","mirae","b","a",4)
        with self.assertRaises(Exception): unlink_sale(self.user,"ipo-a","아빠",first["id"],3)
        unlink_sale(self.user,"ipo-a","아빠",first["id"],4)
        summary=allocation_summary(self.user,"ipo-a","아빠","123456","2026-09-30")
        self.assertEqual((summary["allocation"]["sold_quantity"], summary["allocation"]["remaining_quantity"]), (3, 2))
        self.assertEqual(len(summary["links"]), 1)
        self.assertEqual(read_pnl_records_readonly(self.user), before)
        self.assertEqual(sale_candidates(self.user,"ipo-a","아빠","123456","2026-09-30")[0]["available_quantity"], 2)

    def test_global_delete_and_clear_guards_require_unlink(self):
        self.allocate(5); linked=self.sale(2); other=self.sale(1)
        link_sale(self.user,"ipo-a","아빠",linked["id"],2,2,"123456","2026-09-30")
        with self.assertRaises(PnlRecordLinkedToIpoError): delete_pnl_record(linked["id"], self.user)
        self.assertEqual(len(read_pnl_records_readonly(self.user)), 2)
        with self.assertRaises(PnlRecordsLinkedToIpoError): clear_pnl_records(self.user)
        self.assertEqual(len(read_pnl_records_readonly(self.user)), 2)
        self.assertTrue(delete_pnl_record(other["id"], self.user))
        unlink_sale(self.user,"ipo-a","아빠",linked["id"],3)
        self.assertTrue(delete_pnl_record(linked["id"], self.user))

    def test_shared_pnl_unlink_releases_only_its_own_quantity(self):
        self.allocate(5); shared=self.sale(5)
        link_sale(self.user,"ipo-a","아빠",shared["id"],2,2,"123456","2026-09-30")
        set_allocation(self.user,"ipo-b","엄마",5,20000,3)
        link_sale(self.user,"ipo-b","엄마",shared["id"],3,4,"123456","2026-09-30")
        unlink_sale(self.user,"ipo-a","아빠",shared["id"],5)
        candidates=sale_candidates(self.user,"ipo-a","아빠","123456","2026-09-30")
        self.assertEqual(candidates[0]["available_quantity"], 2)
        other=allocation_summary(self.user,"ipo-b","엄마","123456","2026-09-30")
        self.assertEqual(other["allocation"]["sold_quantity"], 3)
        with self.assertRaises(PnlRecordLinkedToIpoError): delete_pnl_record(shared["id"], self.user)

    def test_dangling_link_reserves_quantity_and_is_explicitly_recoverable(self):
        self.allocate(5); sale=self.sale(2, pnl=20000)
        link_sale(self.user,"ipo-a","아빠",sale["id"],2,2,"123456","2026-09-30")
        write_pnl_records([], self.user)  # synthetic legacy/corrupt state only
        summary=allocation_summary(self.user,"ipo-a","아빠","123456","2026-09-30")
        self.assertEqual(summary["status"], "LINK_DATA_MISSING")
        self.assertTrue(summary["has_dangling_links"])
        self.assertFalse(summary["realized_pnl_complete"])
        self.assertIsNone(summary["allocation"]["realized_pnl_krw"])
        self.assertEqual((summary["allocation"]["sold_quantity"], summary["allocation"]["remaining_quantity"]), (2, 3))
        self.assertEqual(sale_candidates(self.user,"ipo-a","아빠","123456","2026-09-30"), [])
        unlink_sale(self.user,"ipo-a","아빠",sale["id"],3)
        self.assertEqual(allocation_summary(self.user,"ipo-a","아빠","123456","2026-09-30")["allocation"]["remaining_quantity"], 5)


if __name__ == "__main__": unittest.main()
