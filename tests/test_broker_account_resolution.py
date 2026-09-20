import unittest

from app.services.broker_account_resolution import (
    canonical_broker_id,
    resolve_realized_destination_candidates,
    validate_realized_destination,
)


ACCOUNTS = [
    {"id": "kis-a", "broker": "한국투자증권", "account_no": "1234567801"},
    {"id": "kis-b", "broker": "KIS", "account_no": "1234567802"},
    {"id": "nh-a", "broker": "NH투자증권(나무)", "account_no": "2222333344"},
    {"id": "kiwoom-a", "broker": "키움증권", "account_no": "3333444455"},
    {"id": "kb-a", "broker": "KB증권"},
]


class BrokerAccountResolutionTests(unittest.TestCase):
    def test_explicit_broker_aliases_only(self):
        self.assertEqual(canonical_broker_id("한국투자증권"), "kis")
        self.assertEqual(canonical_broker_id("NH투자증권(나무)"), "nh")
        self.assertEqual(canonical_broker_id("키움증권"), "kiwoom")
        self.assertEqual(canonical_broker_id("KB Securities"), "kb")
        self.assertIsNone(canonical_broker_id("unknown broker"))

    def test_candidates_are_strictly_same_broker(self):
        for provider, expected in {
            "kis": {"kis-a", "kis-b"}, "nh": {"nh-a"},
            "kiwoom": {"kiwoom-a"}, "kb": {"kb-a"},
        }.items():
            result = resolve_realized_destination_candidates(provider, ACCOUNTS)
            self.assertEqual(set(result.candidate_account_ids), expected)

    def test_exact_identity_and_ambiguous_identity(self):
        result = resolve_realized_destination_candidates(
            "kis", ACCOUNTS, provider_account_identity="12345678-01"
        )
        self.assertEqual(result.auto_selected_account_id, "kis-a")
        self.assertEqual(result.reason, "exact_identity")

        duplicate = ACCOUNTS + [{"id": "kis-copy", "broker": "한국투자증권", "account_no": "1234567801"}]
        result = resolve_realized_destination_candidates(
            "kis", duplicate, provider_account_identity="1234567801"
        )
        self.assertIsNone(result.auto_selected_account_id)
        self.assertEqual(result.reason, "ambiguous_identity")

        for provider, identity, account_id in (
            ("nh", "2222333344", "nh-a"),
            ("kiwoom", "3333444455", "kiwoom-a"),
        ):
            with self.subTest(provider=provider):
                result = resolve_realized_destination_candidates(
                    provider, ACCOUNTS, provider_account_identity=identity
                )
                self.assertEqual(result.auto_selected_account_id, account_id)
                self.assertEqual(result.reason, "exact_identity")

        result = resolve_realized_destination_candidates(
            "kb", ACCOUNTS, mapped_destination_account_id="kb-a"
        )
        self.assertEqual(result.auto_selected_account_id, "kb-a")
        self.assertEqual(result.reason, "existing_mapping")

    def test_mapping_stale_cross_broker_and_validation(self):
        stale = resolve_realized_destination_candidates(
            "kb", ACCOUNTS, mapped_destination_account_id="gone"
        )
        self.assertIsNone(stale.auto_selected_account_id)
        self.assertEqual(stale.mapping_status, "stale")

        cross = resolve_realized_destination_candidates(
            "kis", ACCOUNTS, mapped_destination_account_id="kb-a"
        )
        self.assertIsNone(cross.auto_selected_account_id)
        self.assertEqual(cross.mapping_status, "cross_broker")
        with self.assertRaisesRegex(ValueError, "DESTINATION_BROKER_MISMATCH"):
            validate_realized_destination("kis", ACCOUNTS, "kb-a")
