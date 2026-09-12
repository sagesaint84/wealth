"""Unit tests for Toss WTS feed static allowed-user authorization layer."""

from __future__ import annotations

import copy
import inspect
import os
import unittest
from unittest.mock import patch
import uuid

from app.services.toss_wts_feed_auth import (
    AUTHORIZED,
    CURRENT_USER_ID_UNAVAILABLE,
    INVALID_CONFIGURATION,
    NOT_AUTHORIZED,
    NOT_CONFIGURED,
    WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID,
    WtsFeedStaticAuthDecision,
    check_wts_feed_static_authorization,
)
from app.services.user_identity import generate_user_id, validate_user_id


class TossWtsFeedStaticAuthTests(unittest.TestCase):
    def test_exact_canonical_uuid4_match_authorizes(self):
        synthetic_id = generate_user_id()
        with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: synthetic_id}, clear=False):
            decision = check_wts_feed_static_authorization(synthetic_id)

        self.assertIsInstance(decision, WtsFeedStaticAuthDecision)
        self.assertTrue(decision.authorized)
        self.assertTrue(bool(decision))
        self.assertEqual(decision.code, AUTHORIZED)
        self.assertEqual(decision["authorized"], True)
        self.assertEqual(decision["code"], AUTHORIZED)

    def test_distinct_valid_user_id_is_not_authorized(self):
        allowed_id = generate_user_id()
        other_user_id = generate_user_id()
        self.assertNotEqual(allowed_id, other_user_id)

        with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: allowed_id}, clear=False):
            decision = check_wts_feed_static_authorization(other_user_id)

        self.assertFalse(decision.authorized)
        self.assertFalse(bool(decision))
        self.assertEqual(decision.code, NOT_AUTHORIZED)

    def test_env_missing_fails_closed_with_not_configured(self):
        current_id = generate_user_id()
        env_without_var = dict(os.environ)
        env_without_var.pop(WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID, None)

        with patch.dict(os.environ, env_without_var, clear=True):
            decision = check_wts_feed_static_authorization(current_id)

        self.assertFalse(decision.authorized)
        self.assertEqual(decision.code, NOT_CONFIGURED)

    def test_env_empty_string_fails_closed_with_not_configured(self):
        current_id = generate_user_id()
        with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: ""}, clear=False):
            decision = check_wts_feed_static_authorization(current_id)

        self.assertFalse(decision.authorized)
        self.assertEqual(decision.code, NOT_CONFIGURED)

    def test_whitespace_env_fails_closed_with_invalid_configuration_without_strip(self):
        current_id = generate_user_id()
        whitespace_cases = [
            f" {current_id} ",
            f"\t{current_id}\n",
            "   ",
        ]
        for bad_val in whitespace_cases:
            with self.subTest(bad_val=repr(bad_val)):
                with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: bad_val}, clear=False):
                    decision = check_wts_feed_static_authorization(current_id)
                self.assertFalse(decision.authorized)
                self.assertEqual(decision.code, INVALID_CONFIGURATION)

    def test_uppercase_env_fails_closed_with_invalid_configuration_without_normalization(self):
        synthetic_id = generate_user_id()
        uppercase_env = synthetic_id.upper()
        with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: uppercase_env}, clear=False):
            decision = check_wts_feed_static_authorization(synthetic_id)

        self.assertFalse(decision.authorized)
        self.assertEqual(decision.code, INVALID_CONFIGURATION)

    def test_compact_hyphenless_env_fails_closed_with_invalid_configuration(self):
        synthetic_id = generate_user_id()
        compact_env = synthetic_id.replace("-", "")
        with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: compact_env}, clear=False):
            decision = check_wts_feed_static_authorization(synthetic_id)

        self.assertFalse(decision.authorized)
        self.assertEqual(decision.code, INVALID_CONFIGURATION)

    def test_wrong_uuid_version_env_fails_closed_with_invalid_configuration(self):
        current_id = generate_user_id()
        wrong_versions = [
            str(uuid.uuid1()),
            str(uuid.uuid3(uuid.NAMESPACE_DNS, "synthetic.example")),
            str(uuid.uuid5(uuid.NAMESPACE_DNS, "synthetic.example")),
        ]
        for wrong_uuid in wrong_versions:
            with self.subTest(wrong_uuid=wrong_uuid):
                with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: wrong_uuid}, clear=False):
                    decision = check_wts_feed_static_authorization(current_id)
                self.assertFalse(decision.authorized)
                self.assertEqual(decision.code, INVALID_CONFIGURATION)

    def test_malformed_env_fails_closed_with_invalid_configuration(self):
        current_id = generate_user_id()
        malformed_values = [
            "not-a-uuid",
            "12345",
            "*",
            "null",
            f"{current_id},{generate_user_id()}",
            f'["{current_id}"]',
        ]
        for malformed in malformed_values:
            with self.subTest(malformed=malformed):
                with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: malformed}, clear=False):
                    decision = check_wts_feed_static_authorization(current_id)
                self.assertFalse(decision.authorized)
                self.assertEqual(decision.code, INVALID_CONFIGURATION)

    def test_current_user_none_fails_closed_with_current_user_unavailable(self):
        allowed_id = generate_user_id()
        with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: allowed_id}, clear=False):
            decision = check_wts_feed_static_authorization(None)
            decision_no_arg = check_wts_feed_static_authorization()

        self.assertFalse(decision.authorized)
        self.assertEqual(decision.code, CURRENT_USER_ID_UNAVAILABLE)
        self.assertFalse(decision_no_arg.authorized)
        self.assertEqual(decision_no_arg.code, CURRENT_USER_ID_UNAVAILABLE)

    def test_malformed_current_user_id_fails_closed_with_current_user_unavailable(self):
        allowed_id = generate_user_id()
        malformed_current_ids = [
            "",
            "   ",
            "not-a-uuid",
            allowed_id.upper(),
            allowed_id.replace("-", ""),
            f" {allowed_id} ",
            123,
            True,
            ["uuid"],
            {"id": allowed_id},
        ]
        for malformed in malformed_current_ids:
            with self.subTest(malformed=repr(malformed)):
                with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: allowed_id}, clear=False):
                    decision = check_wts_feed_static_authorization(malformed)
                self.assertFalse(decision.authorized)
                self.assertEqual(decision.code, CURRENT_USER_ID_UNAVAILABLE)

    def test_admin_has_no_bypass_and_signature_excludes_role_and_username(self):
        sig = inspect.signature(check_wts_feed_static_authorization)
        param_names = list(sig.parameters.keys())
        self.assertEqual(param_names, ["user_id"])
        self.assertNotIn("role", param_names)
        self.assertNotIn("username", param_names)
        self.assertNotIn("is_admin", param_names)

        allowed_id = generate_user_id()
        admin_user_id = generate_user_id()
        self.assertNotEqual(allowed_id, admin_user_id)

        # Passing admin user's stable ID to helper results in NOT_AUTHORIZED
        with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: allowed_id}, clear=False):
            decision = check_wts_feed_static_authorization(admin_user_id)

        self.assertFalse(decision.authorized)
        self.assertEqual(decision.code, NOT_AUTHORIZED)

    def test_recreated_user_with_same_username_has_different_id_and_is_denied(self):
        old_user_id_a = generate_user_id()
        recreated_user_id_b = generate_user_id()
        self.assertNotEqual(old_user_id_a, recreated_user_id_b)

        # Deployment environment still configured for original ID_A
        with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: old_user_id_a}, clear=False):
            # Recreated user request with new ID_B cannot inherit access
            decision = check_wts_feed_static_authorization(recreated_user_id_b)

        self.assertFalse(decision.authorized)
        self.assertEqual(decision.code, NOT_AUTHORIZED)

    def test_exact_string_matching_only(self):
        allowed_id = generate_user_id()
        non_matching_variations = [
            allowed_id[:-1],
            allowed_id + "a",
            allowed_id[1:],
            " " + allowed_id,
            allowed_id + " ",
            allowed_id.upper(),
        ]
        with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: allowed_id}, clear=False):
            for variation in non_matching_variations:
                with self.subTest(variation=variation):
                    decision = check_wts_feed_static_authorization(variation)
                    self.assertFalse(decision.authorized)

    def test_decision_privacy_does_not_leak_identifiers(self):
        sentinel_allowed = "00000000-0000-4000-8000-000000000001"
        sentinel_current = "00000000-0000-4000-8000-000000000002"
        self.assertEqual(validate_user_id(sentinel_allowed), sentinel_allowed)
        self.assertEqual(validate_user_id(sentinel_current), sentinel_current)

        with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: sentinel_allowed}, clear=False):
            decisions = [
                check_wts_feed_static_authorization(sentinel_allowed),
                check_wts_feed_static_authorization(sentinel_current),
                check_wts_feed_static_authorization(None),
            ]

        for decision in decisions:
            rep = repr(decision)
            st = str(decision)
            d = decision.as_dict()
            for sensitive in (sentinel_allowed, sentinel_current, "username", "admin", "role"):
                self.assertNotIn(sensitive, rep)
                self.assertNotIn(sensitive, st)
                self.assertNotIn(sensitive, str(d))
            self.assertEqual(set(d.keys()), {"authorized", "code"})

    def test_no_environment_mutation(self):
        allowed_id = generate_user_id()
        current_id = generate_user_id()
        env_snapshot = {
            WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: allowed_id,
            "UNRELATED_KEY": "unrelated_value",
        }
        with patch.dict(os.environ, env_snapshot, clear=False):
            before = dict(os.environ)
            check_wts_feed_static_authorization(current_id)
            check_wts_feed_static_authorization(allowed_id)
            check_wts_feed_static_authorization(None)
            check_wts_feed_static_authorization("invalid-uuid")
            after = dict(os.environ)

        self.assertEqual(before, after)

    def test_no_external_storage_provider_or_filesystem_side_effects(self):
        allowed_id = generate_user_id()
        with patch.dict(os.environ, {WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: allowed_id}, clear=False):
            with patch("subprocess.run", side_effect=AssertionError("subprocess called")), \
                 patch("subprocess.Popen", side_effect=AssertionError("subprocess called")), \
                 patch("pathlib.Path.read_text", side_effect=AssertionError("filesystem read")), \
                 patch("pathlib.Path.write_text", side_effect=AssertionError("filesystem write")):
                decision = check_wts_feed_static_authorization(allowed_id)

        self.assertTrue(decision.authorized)


if __name__ == "__main__":
    unittest.main()
