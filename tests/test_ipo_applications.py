import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.services.ipo.applications import (
    ApplicationAccountMappingConflict,
    get_user_applications,
    resolve_user_application_account,
    remap_user_application_account,
    set_user_application_account,
    update_user_application,
    ApplicationRevisionConflict,
    InvalidApplicationError,
    freeze_untouched_ipo_application,
)
from app.services.portfolio import write_portfolio, read_portfolio


class IpoApplicationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.data_dir = Path(self.tmp_dir.name)
        self.username = "testuser"

        self.patches = [
            patch("app.services.user_manager.get_user_data_dir", return_value=self.data_dir),
            patch("app.services.portfolio._get_user_dir", return_value=self.data_dir),
            patch("app.services.portfolio.assert_write_allowed", return_value=None),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

        # Seed initial portfolio with 3 family members
        initial_portfolio = {
            "settings": {
                "family_members": ["아빠", "엄마", "자녀"],
                "ipo": {"revision": 0, "applications": {}},
            },
            "accounts": [
                {"id": "mirae-general", "broker": "미래에셋증권", "account_name": "일반", "owner": "아빠", "account_type": "general"},
                {"id": "mirae-isa", "broker": "미래에셋대우", "account_name": "ISA", "owner": "아빠", "account_type": "isa"},
                {"id": "kb-account", "broker": "KB증권", "account_name": "KB", "owner": "아빠"},
                {"id": "hyundai-account", "broker": "현대차증권", "account_name": "현대차", "owner": "엄마"},
            ],
            "holdings": [],
        }
        write_portfolio(initial_portfolio, username=self.username)

    def test_initial_empty_application_state(self):
        apps = get_user_applications(self.username)
        self.assertEqual(apps["revision"], 0)
        self.assertEqual(apps["applications"], {})
        self.assertEqual(apps["family_members"], ["아빠", "엄마", "자녀"])

    def test_apply_some_family_members(self):
        res = update_user_application(
            username=self.username,
            ipo_id="ipo_test_1",
            applied_owners=["아빠"],
            client_revision=0,
        )
        self.assertEqual(res["revision"], 1)
        self.assertEqual(res["applied_owners"], ["아빠"])
        self.assertEqual(res["target_owners"], ["아빠", "엄마", "자녀"])
        self.assertEqual(res["state"], "some")
        self.assertFalse(res["all_applied"])
        self.assertIsNotNone(res["target_frozen_at"])

    def test_apply_all_family_members(self):
        res = update_user_application(
            username=self.username,
            ipo_id="ipo_test_1",
            applied_owners=["아빠", "엄마", "자녀"],
            client_revision=0,
        )
        self.assertEqual(res["revision"], 1)
        self.assertEqual(res["state"], "all")
        self.assertTrue(res["all_applied"])

    def test_uncheck_all_results_in_none_state(self):
        # First check one
        update_user_application(
            username=self.username,
            ipo_id="ipo_test_1",
            applied_owners=["엄마"],
            client_revision=0,
        )
        # Then uncheck all
        res = update_user_application(
            username=self.username,
            ipo_id="ipo_test_1",
            applied_owners=[],
            client_revision=1,
        )
        self.assertEqual(res["revision"], 2)
        self.assertEqual(res["applied_owners"], [])
        self.assertEqual(res["state"], "none")
        self.assertFalse(res["all_applied"])

    def test_modu_strictly_forbidden_in_applied_owners(self):
        with self.assertRaises(InvalidApplicationError):
            update_user_application(
                username=self.username,
                ipo_id="ipo_test_1",
                applied_owners=["모두"],
                client_revision=0,
            )

    def test_unknown_owner_rejected(self):
        with self.assertRaises(InvalidApplicationError):
            update_user_application(
                username=self.username,
                ipo_id="ipo_test_1",
                applied_owners=["낯선사람"],
                client_revision=0,
            )

    def test_revision_conflict_detection(self):
        # Client sends revision=0
        update_user_application(
            username=self.username,
            ipo_id="ipo_test_1",
            applied_owners=["아빠"],
            client_revision=0,
        )
        # Another client also tries with stale revision=0
        with self.assertRaises(ApplicationRevisionConflict):
            update_user_application(
                username=self.username,
                ipo_id="ipo_test_1",
                applied_owners=["엄마"],
                client_revision=0,
            )

    def test_target_owners_remain_frozen_after_family_setting_changes(self):
        # 1. Freeze target_owners for ipo_test_1 with current family (아빠, 엄마, 자녀)
        res1 = update_user_application(
            username=self.username,
            ipo_id="ipo_test_1",
            applied_owners=["아빠"],
            client_revision=0,
        )
        self.assertEqual(res1["target_owners"], ["아빠", "엄마", "자녀"])
        frozen_time = res1["target_frozen_at"]

        # 2. Family members change in portfolio settings (add '할머니')
        port = read_portfolio(self.username)
        port["settings"]["family_members"] = ["아빠", "엄마", "자녀", "할머니"]
        write_portfolio(port, username=self.username)

        # 3. Update application for ipo_test_1 again with revision 1
        res2 = update_user_application(
            username=self.username,
            ipo_id="ipo_test_1",
            applied_owners=["아빠", "엄마"],
            client_revision=1,
        )
        # Target owners must still be the original 3 members!
        self.assertEqual(res2["target_owners"], ["아빠", "엄마", "자녀"])
        self.assertEqual(res2["target_frozen_at"], frozen_time)

    def test_frozen_application_rejects_new_family_member(self):
        # 1. Freeze target_owners for ipo_test_frozen with current family (아빠, 엄마, 자녀)
        update_user_application(
            username=self.username,
            ipo_id="ipo_test_frozen",
            applied_owners=["아빠"],
            client_revision=0,
        )

        # 2. Later, family members in settings are expanded with '할머니'
        port = read_portfolio(self.username)
        port["settings"]["family_members"] = ["아빠", "엄마", "자녀", "할머니"]
        write_portfolio(port, username=self.username)

        # 3. Attempting to add '할머니' to the frozen past IPO must be rejected!
        with self.assertRaises(InvalidApplicationError):
            update_user_application(
                username=self.username,
                ipo_id="ipo_test_frozen",
                applied_owners=["아빠", "할머니"],
                client_revision=1,
            )

        # 4. A new IPO (not yet frozen) can accept '할머니'
        res_new = update_user_application(
            username=self.username,
            ipo_id="ipo_test_new",
            applied_owners=["할머니"],
            client_revision=1,
        )
        self.assertIn("할머니", res_new["target_owners"])
        self.assertEqual(res_new["applied_owners"], ["할머니"])

    def test_api_put_and_get_applications(self):
        client = TestClient(main.app)
        token = main._serializer.dumps({"user": self.username, "role": "user"})
        headers = {"Cookie": f"{main.COOKIE_NAME}={token}"}
        fake_user = {"username": self.username, "role": "user"}

        with patch("app.services.user_manager.get_user_by_name", return_value=fake_user):
            # GET initial
            get_resp = client.get("/api/ipo/applications", headers=headers)
            self.assertEqual(get_resp.status_code, 200)
            self.assertEqual(get_resp.json()["revision"], 0)

            # PUT update
            put_resp = client.put(
                "/api/ipo/applications/ipo_api_test",
                headers=headers,
                json={"applied_owners": ["아빠", "엄마"], "revision": 0},
            )
            self.assertEqual(put_resp.status_code, 200)
            data = put_resp.json()
            self.assertEqual(data["revision"], 1)
            self.assertEqual(data["applied_owners"], ["아빠", "엄마"])
            self.assertEqual(data["state"], "some")

            # PUT with revision conflict
            conflict_resp = client.put(
                "/api/ipo/applications/ipo_api_test",
                headers=headers,
                json={"applied_owners": ["아빠"], "revision": 0},
            )
            self.assertEqual(conflict_resp.status_code, 409)

            # PUT with '모두' in applied_owners -> 400
            bad_resp = client.put(
                "/api/ipo/applications/ipo_api_test",
                headers=headers,
                json={"applied_owners": ["모두"], "revision": 1},
            )
            self.assertEqual(bad_resp.status_code, 400)

    def test_applicant_account_resolution_and_persistence_are_broker_scoped(self):
        update_user_application(self.username, "ipo_mirae", ["아빠"], 0)
        result = resolve_user_application_account(
            self.username, "ipo_mirae", "아빠", "미래에셋대우",
        )
        self.assertEqual(result.broker_id, "mirae")
        self.assertEqual(result.resolution_status, "AMBIGUOUS_ACCOUNT")
        self.assertEqual({item["account_id"] for item in result.candidates}, {"mirae-general", "mirae-isa"})
        self.assertNotIn("kb-account", {item["account_id"] for item in result.candidates})

        saved = set_user_application_account(
            self.username, "ipo_mirae", "아빠", "mirae", "mirae-isa", 1,
        )
        self.assertEqual(saved["account_id"], "mirae-isa")
        app = get_user_applications(self.username)["applications"]["ipo_mirae"]
        self.assertEqual(app["applicants"]["아빠"], {"broker_id": "mirae", "account_id": "mirae-isa"})

        with self.assertRaises(ApplicationAccountMappingConflict):
            set_user_application_account(
                self.username, "ipo_mirae", "아빠", "mirae", "mirae-general", 2,
            )

    def test_applicant_account_rejects_cross_broker_and_preserves_hyundai_kb_distinction(self):
        update_user_application(self.username, "ipo_hyundai", ["엄마"], 0)
        with self.assertRaisesRegex(InvalidApplicationError, "DESTINATION_BROKER_MISMATCH"):
            set_user_application_account(
                self.username, "ipo_hyundai", "엄마", "현대차증권", "kb-account", 1,
            )
        result = resolve_user_application_account(
            self.username, "ipo_hyundai", "엄마", "현대차증권",
        )
        self.assertEqual(result.broker_id, "hyundai")
        self.assertEqual(result.auto_selected_account_id, "hyundai-account")

    def test_explicit_remap_requires_compare_and_swap_and_keeps_other_applicants_intact(self):
        update_user_application(self.username, "ipo_mirae", ["아빠", "엄마"], 0)
        set_user_application_account(self.username, "ipo_mirae", "아빠", "mirae", "mirae-isa", 1)
        set_user_application_account(self.username, "ipo_mirae", "엄마", "hyundai", "hyundai-account", 2)
        with self.assertRaises(ApplicationAccountMappingConflict):
            set_user_application_account(self.username, "ipo_mirae", "아빠", "mirae", "mirae-general", 3)
        with self.assertRaises(ApplicationAccountMappingConflict):
            remap_user_application_account(self.username, "ipo_mirae", "아빠", "mirae", "mirae-general", "wrong", 3)
        remapped = remap_user_application_account(
            self.username, "ipo_mirae", "아빠", "mirae", "mirae-general", "mirae-isa", 3,
        )
        self.assertEqual(remapped["resolution_status"], "REMAPPED")
        self.assertEqual(remapped["revision"], 4)
        same = remap_user_application_account(
            self.username, "ipo_mirae", "아빠", "mirae", "mirae-general", "mirae-general", 4,
        )
        self.assertEqual(same["revision"], 4)
        with self.assertRaises(ApplicationRevisionConflict):
            remap_user_application_account(
                self.username, "ipo_mirae", "아빠", "mirae", "mirae-isa", "mirae-general", 3,
            )
        with self.assertRaisesRegex(InvalidApplicationError, "DESTINATION_BROKER_MISMATCH"):
            remap_user_application_account(
                self.username, "ipo_mirae", "아빠", "mirae", "kb-account", "mirae-general", 4,
            )
        app = get_user_applications(self.username)["applications"]["ipo_mirae"]
        self.assertEqual(app["applicants"]["아빠"]["account_id"], "mirae-general")
        self.assertEqual(app["applicants"]["엄마"]["account_id"], "hyundai-account")

    def test_account_candidate_api_and_persistence_endpoint_revalidate_market_broker(self):
        client = TestClient(main.app)
        token = main._serializer.dumps({"user": self.username, "role": "user"})
        headers = {"Cookie": f"{main.COOKIE_NAME}={token}"}
        fake_user = {"username": self.username, "role": "user"}
        market = {"ipos": [{"ipo_id": "ipo_api_mirae", "lead_managers": ["미래에셋증권"]}]}
        with patch("app.services.user_manager.get_user_by_name", return_value=fake_user), \
             patch("app.services.ipo.store.read_market_store", return_value=market):
            apply = client.put(
                "/api/ipo/applications/ipo_api_mirae", headers=headers,
                json={"applied_owners": ["아빠"], "revision": 0},
            )
            self.assertEqual(apply.status_code, 200)
            brokers = client.get(
                "/api/ipo/applications/ipo_api_mirae/broker-options",
                headers=headers,
            )
            self.assertEqual(brokers.status_code, 200)
            self.assertEqual(brokers.json()["brokers"], [{"broker_id": "mirae", "display_name": "미래에셋증권"}])
            candidates = client.get(
                "/api/ipo/applications/ipo_api_mirae/account-candidates?owner=%EC%95%84%EB%B9%A0&broker=%EB%AF%B8%EB%9E%98%EC%97%90%EC%85%8B%EB%8C%80%EC%9A%B0",
                headers=headers,
            )
            self.assertEqual(candidates.status_code, 200)
            self.assertEqual(candidates.json()["broker_id"], "mirae")
            self.assertEqual(len(candidates.json()["candidates"]), 2)
            self.assertNotIn("account_no", str(candidates.json()))

            cross = client.put(
                "/api/ipo/applications/ipo_api_mirae/applicants/%EC%95%84%EB%B9%A0/account",
                headers=headers,
                json={"broker": "미래에셋증권", "account_id": "kb-account", "revision": 1},
            )
            self.assertEqual(cross.status_code, 400)
            self.assertEqual(cross.json()["detail"]["code"], "DESTINATION_BROKER_MISMATCH")
            wrong_broker = client.put(
                "/api/ipo/applications/ipo_api_mirae/applicants/%EC%95%84%EB%B9%A0/account/remap",
                headers=headers,
                json={"broker": "KB증권", "account_id": "kb-account", "expected_current_account_id": "mirae-isa", "revision": 1},
            )
            self.assertEqual(wrong_broker.status_code, 400)
            self.assertEqual(wrong_broker.json()["detail"]["code"], "IPO_BROKER_NOT_AVAILABLE")


if __name__ == "__main__":
    unittest.main()
