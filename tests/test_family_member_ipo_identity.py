import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.family_members import IpoApplicantRenameCollision, rename_family_member_references
from app.services.ipo.allocation import unlink_sale
from app.services.ipo.applications import ApplicationRevisionConflict, update_user_application
from app.services.portfolio import read_portfolio, write_portfolio


class FamilyMemberIpoIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data_dir = Path(self.temp.name)
        self.username = "family-ipo-test"
        self.patches = [
            patch("app.services.user_manager.get_user_data_dir", return_value=self.data_dir),
            patch("app.services.portfolio._get_user_dir", return_value=self.data_dir),
            patch("app.services.portfolio.assert_write_allowed", return_value=None),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        write_portfolio({
            "settings": {"family_members": ["아빠", "엄마"], "ipo": {"revision": 7, "applications": {
                "ipo-one": {"target_owners": ["아빠", "엄마"], "applied_owners": ["아빠", "엄마"],
                            "target_frozen_at": "2026-09-01T00:00:00+09:00", "applicants": {
                                "아빠": {"broker_id": "mirae", "account_id": "account-a", "updated_at": "old", "future": "keep",
                                         "allocation": {"id": "allocation-a", "quantity": 2, "offer_price": 10000,
                                                        "links": [{"pnl_record_id": "pnl-a", "matched_quantity": 1}]}},
                                "엄마": {"broker_id": "kb", "account_id": "account-b"},
                            }},
                "ipo-two": {"target_owners": ["아빠"], "applied_owners": ["아빠"], "applicants": {
                    "아빠": {"broker_id": "kis", "account_id": "account-c"},
                }},
            }}},
            "accounts": [{"id": "account-a", "owner": "아빠"}, {"id": "account-b", "owner": "엄마"}],
            "holdings": [],
        }, username=self.username)

    def test_rename_cascades_all_ipo_owner_references_and_increments_revision(self):
        result = rename_family_member_references(self.username, "아빠", "본인")
        data = read_portfolio(self.username)
        self.assertEqual(result["ipo_revision"], 8)
        self.assertEqual(data["settings"]["family_members"], ["본인", "엄마"])
        self.assertEqual(data["accounts"][0]["owner"], "본인")
        first = data["settings"]["ipo"]["applications"]["ipo-one"]
        second = data["settings"]["ipo"]["applications"]["ipo-two"]
        self.assertEqual(first["target_owners"], ["본인", "엄마"])
        self.assertEqual(first["applied_owners"], ["본인", "엄마"])
        self.assertIn("본인", first["applicants"])
        self.assertNotIn("아빠", first["applicants"])
        self.assertEqual(first["applicants"]["본인"], {
            "broker_id": "mirae", "account_id": "account-a", "updated_at": "old", "future": "keep",
            "allocation": {"id": "allocation-a", "quantity": 2, "offer_price": 10000,
                           "links": [{"pnl_record_id": "pnl-a", "matched_quantity": 1}]},
        })
        self.assertEqual(first["applicants"]["엄마"], {"broker_id": "kb", "account_id": "account-b"})
        self.assertEqual(second["applicants"]["본인"]["account_id"], "account-c")

    def test_rename_keeps_frozen_targets_valid_and_stale_ipo_revision_conflicts(self):
        rename_family_member_references(self.username, "아빠", "본인")
        with self.assertRaises(ApplicationRevisionConflict):
            update_user_application(self.username, "ipo-one", ["본인"], 7)
        updated = update_user_application(self.username, "ipo-one", ["본인"], 8)
        self.assertEqual(updated["target_owners"], ["본인", "엄마"])

    def test_rename_keeps_linked_allocation_addressable_for_explicit_unlink(self):
        rename_family_member_references(self.username, "아빠", "본인")
        result = unlink_sale(self.username, "ipo-one", "본인", "pnl-a", 8)
        self.assertEqual(result["status"], "UNLINKED")
        data = read_portfolio(self.username)
        allocation = data["settings"]["ipo"]["applications"]["ipo-one"]["applicants"]["본인"]["allocation"]
        self.assertEqual(allocation["id"], "allocation-a")
        self.assertEqual(allocation["links"], [])

    def test_legacy_applicant_collision_fails_without_partial_rename(self):
        data = read_portfolio(self.username)
        data["settings"]["ipo"]["applications"]["ipo-one"]["applicants"]["본인"] = {"broker_id": "nh", "account_id": "other"}
        write_portfolio(data, username=self.username)
        before = json.dumps(read_portfolio(self.username), ensure_ascii=False, sort_keys=True)
        with self.assertRaises(IpoApplicantRenameCollision):
            rename_family_member_references(self.username, "아빠", "본인")
        self.assertEqual(json.dumps(read_portfolio(self.username), ensure_ascii=False, sort_keys=True), before)


if __name__ == "__main__":
    unittest.main()
