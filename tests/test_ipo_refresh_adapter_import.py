from __future__ import annotations

import unittest

import app.services.ipo
from app.services.ipo import orchestrator


class IpoRefreshAdapterImportTests(unittest.TestCase):
    def test_public_refresh_functions_are_installed(self):
        self.assertEqual(orchestrator.refresh_ipo_market.__module__, "app.services.ipo.refresh_adapter")
        self.assertEqual(orchestrator.refresh_ipo_market_enriched.__module__, "app.services.ipo.refresh_adapter")


if __name__ == "__main__":
    unittest.main()
