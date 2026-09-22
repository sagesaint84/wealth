import unittest

from app.services.ipo.account_resolution import (
    resolve_ipo_account_candidates,
    validate_ipo_account_selection,
)


class IpoAccountResolutionTests(unittest.TestCase):
    def setUp(self):
        self.accounts = [
            {"id": "mirae-general", "broker": "미래에셋증권", "account_name": "일반", "owner": "본인"},
            {"id": "mirae-isa", "broker": "미래에셋대우", "account_name": "ISA", "owner": "본인"},
            {"id": "kb-main", "broker": "KB증권", "account_name": "일반", "owner": "본인"},
            {"id": "hyundai-main", "broker": "현대차증권", "account_name": "일반", "owner": "배우자"},
        ]

    def test_candidates_are_same_broker_only_and_do_not_expose_account_numbers(self):
        resolution = resolve_ipo_account_candidates("미래에셋대우", self.accounts)
        self.assertEqual(resolution.broker_id, "mirae")
        self.assertEqual(resolution.resolution_status, "AMBIGUOUS_ACCOUNT")
        self.assertEqual({item["account_id"] for item in resolution.candidates}, {"mirae-general", "mirae-isa"})
        self.assertNotIn("account_no", str(resolution.candidates))

    def test_unknown_zero_and_sole_candidate_statuses_fail_safe(self):
        self.assertEqual(
            resolve_ipo_account_candidates("알수없는증권", self.accounts).resolution_status,
            "BROKER_UNKNOWN",
        )
        self.assertEqual(
            resolve_ipo_account_candidates("삼성증권", self.accounts).resolution_status,
            "NO_ACCOUNT_CANDIDATE",
        )
        sole = resolve_ipo_account_candidates("현대차증권", self.accounts)
        self.assertEqual(sole.resolution_status, "AUTO_SELECTED")
        self.assertEqual(sole.auto_selected_account_id, "hyundai-main")

    def test_existing_mapping_is_validated_and_cannot_be_silently_remapped(self):
        existing = {"broker_id": "mirae", "account_id": "mirae-isa"}
        resolution = resolve_ipo_account_candidates("mirae", self.accounts, existing_mapping=existing)
        self.assertEqual(resolution.resolution_status, "MAPPED")
        with self.assertRaisesRegex(ValueError, "MAPPING_CONFLICT"):
            validate_ipo_account_selection("mirae", self.accounts, "mirae-general", existing_mapping=existing)
        stale = resolve_ipo_account_candidates(
            "mirae", self.accounts, existing_mapping={"broker_id": "mirae", "account_id": "removed"},
        )
        self.assertEqual(stale.resolution_status, "MAPPING_CONFLICT")

    def test_cross_broker_selection_and_hyundai_kb_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "DESTINATION_BROKER_MISMATCH"):
            validate_ipo_account_selection("현대차증권", self.accounts, "kb-main")
        self.assertEqual(resolve_ipo_account_candidates("현대증권", self.accounts).broker_id, "kb")
        self.assertEqual(resolve_ipo_account_candidates("현대차증권", self.accounts).broker_id, "hyundai")

    def test_korean_spelling_kb_resolves_kb_account_candidate(self):
        resolution = resolve_ipo_account_candidates("케이비증권", self.accounts)
        self.assertEqual(resolution.broker_id, "kb")
        self.assertEqual(resolution.resolution_status, "AUTO_SELECTED")
        self.assertEqual(resolution.auto_selected_account_id, "kb-main")
        self.assertEqual(len(resolution.candidates), 1)
        self.assertEqual(resolution.candidates[0]["account_id"], "kb-main")
        self.assertEqual(resolution.candidates[0]["broker_id"], "kb")


if __name__ == "__main__":
    unittest.main()
