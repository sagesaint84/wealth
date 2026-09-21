import os
import unittest

from app.services.ipo.krx_client import KrxClient


@unittest.skipUnless(os.environ.get("WEALTH_LIVE_IPO_TESTS") == "1", "Live KRX tests disabled by default.")
class IpoKrxLiveTests(unittest.TestCase):
    def test_live_krx_connection_contract(self):
        client = KrxClient()
        try:
            client.fetch_screen("MDCSTAT20001", {})
        except NotImplementedError:
            self.skipTest("live transport not implemented")


if __name__ == "__main__":
    unittest.main()
