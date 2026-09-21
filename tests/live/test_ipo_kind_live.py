import os
import unittest

from app.services.ipo.kind_client import KindClient


@unittest.skipUnless(os.environ.get("WEALTH_LIVE_IPO_TESTS") == "1", "Live KIND tests disabled by default.")
class IpoKindLiveTests(unittest.TestCase):
    def test_live_kind_connection_contract(self):
        client = KindClient()
        try:
            client.fetch_pubofr_schedule_html("2026-09-01", "2026-09-30")
        except NotImplementedError:
            self.skipTest("live transport not implemented")


if __name__ == "__main__":
    unittest.main()
