from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import os

os.environ.setdefault("WEALTH_ENV", "test")
from app import main
from app.services import asset_records, historical_fx, portfolio
from app.services.test_safety import TestSafetyError


class DockerConfigurationTests(unittest.TestCase):
    def test_compose_variants_use_env_file_without_env_bind_mount(self):
        project_root = Path(__file__).resolve().parents[1]
        for name in ("docker-compose.yml", "docker-compose.override.yml", "docker-compose.ghcr.yml"):
            text = (project_root / name).read_text(encoding="utf-8")
            self.assertNotIn("./.env:/app/.env", text)
        self.assertIn("env_file:", (project_root / "docker-compose.yml").read_text(encoding="utf-8"))
        self.assertIn("env_file:", (project_root / "docker-compose.ghcr.yml").read_text(encoding="utf-8"))

    def test_directory_env_fails_with_configuration_error(self):
        with tempfile.TemporaryDirectory(prefix="wealth-config-") as temp:
            root = Path(temp)
            (root / ".env").mkdir()
            with patch.object(main, "ROOT_DIR", root):
                with self.assertRaisesRegex(RuntimeError, r"\.env must be a regular file"):
                    main.load_env_file()

    def test_regular_env_does_not_override_runtime_environment(self):
        with tempfile.TemporaryDirectory(prefix="wealth-config-") as temp:
            root = Path(temp)
            (root / ".env").write_text("DASHBOARD_SECRET_KEY=file-value\n", encoding="utf-8")
            with patch.object(main, "ROOT_DIR", root), patch.dict("os.environ", {"DASHBOARD_SECRET_KEY": "runtime-value"}, clear=False):
                main.load_env_file()
                self.assertEqual(__import__("os").environ["DASHBOARD_SECRET_KEY"], "runtime-value")

    def test_production_data_writers_are_blocked_in_test_mode(self):
        with self.assertRaises(TestSafetyError):
            portfolio.write_portfolio({}, username="sagesaint")
        with self.assertRaises(TestSafetyError):
            asset_records.write_asset_records({}, username="sagesaint")
        with patch.object(historical_fx, "FX_CACHE_FILE", Path(__file__).resolve().parents[1] / "data" / "historical_fx_cache.json"):
            with self.assertRaises(TestSafetyError):
                historical_fx.save_cached_fx({"synthetic": 1.0})

    def test_synthetic_writer_path_is_allowed(self):
        with tempfile.TemporaryDirectory(prefix="wealth-writer-") as temp:
            root = Path(temp)
            with patch.object(portfolio, "_get_portfolio_file", return_value=root / "portfolio.json"):
                portfolio.write_portfolio({"settings": {}, "accounts": [], "holdings": []}, username="synthetic")
            with patch.object(asset_records, "_get_records_file", return_value=root / "asset_records.json"):
                asset_records.write_asset_records({"records": []}, username="synthetic")


if __name__ == "__main__":
    unittest.main()
