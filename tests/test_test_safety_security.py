from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.services.test_safety import TestSafetyError, assert_write_allowed

ROOT = Path(__file__).resolve().parents[1]


class TestSafetySecurityTests(unittest.TestCase):
    def setUp(self):
        self.repo_data = (ROOT / "data").resolve()

    def test_production_root_and_descendants_blocked(self):
        with patch.dict(os.environ, {"WEALTH_ENV": "test"}, clear=False):
            with self.assertRaises(TestSafetyError):
                assert_write_allowed(self.repo_data)
            with self.assertRaises(TestSafetyError):
                assert_write_allowed(self.repo_data / "users.json")
            with self.assertRaises(TestSafetyError):
                assert_write_allowed(self.repo_data / "users" / "admin" / "portfolio.json")

    def test_wealth_production_data_dir_cannot_weaken_repo_data_protection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir).resolve()
            with patch.dict(os.environ, {
                "WEALTH_ENV": "test",
                "WEALTH_PRODUCTION_DATA_DIR": str(temp_path),
            }, clear=False):
                # Repo production data must STILL be blocked
                with self.assertRaises(TestSafetyError):
                    assert_write_allowed(self.repo_data / "users.json")
                # Custom configured production data must ALSO be blocked
                with self.assertRaises(TestSafetyError):
                    assert_write_allowed(temp_path / "custom.json")

    def test_dot_dot_traversal_fails_closed(self):
        with patch.dict(os.environ, {"WEALTH_ENV": "test"}, clear=False):
            traversal_path = ROOT / "tests" / ".." / "data" / "users.json"
            with self.assertRaises(TestSafetyError):
                assert_write_allowed(traversal_path)

    def test_similar_prefix_sibling_is_not_blocked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir).resolve()
            similar_prefix = ROOT / "data_backup" / "file.json"
            with patch.dict(os.environ, {
                "WEALTH_ENV": "test",
                "DATA_DIR": str(temp_path),
            }, clear=False):
                # Should not raise TestSafetyError
                assert_write_allowed(similar_prefix)

    def test_temp_validation_still_works(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = Path(temp_dir) / "test_data.json"
            with patch.dict(os.environ, {
                "WEALTH_ENV": "test",
                "DATA_DIR": temp_dir,
            }, clear=False):
                assert_write_allowed(temp_file)

    def test_production_deny_precedes_active_data_allow(self):
        # Even if DATA_DIR is maliciously or erroneously set to repo data, production deny wins
        with patch.dict(os.environ, {
            "WEALTH_ENV": "test",
            "DATA_DIR": str(self.repo_data),
        }, clear=False):
            with self.assertRaises(TestSafetyError):
                assert_write_allowed(self.repo_data / "portfolio.json")


if __name__ == "__main__":
    unittest.main()
