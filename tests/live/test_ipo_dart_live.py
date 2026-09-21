import os
import re
import unittest

from app.services.ipo.dart_client import DartClient, DartClientError


@unittest.skipUnless(os.environ.get("WEALTH_LIVE_IPO_TESTS") == "1", "Live DART tests disabled by default.")
class IpoDartLiveTests(unittest.TestCase):
    def test_live_dart_connection_contract(self):
        # Must skip if DART_API_KEY is not configured
        api_key = os.environ.get("DART_API_KEY", "").strip()
        if not api_key:
            self.skipTest("DART_API_KEY not configured in environment")

        # Must skip if DART_LIVE_CORP_CODE is not provided to avoid hardcoded external company dependency
        corp_code = os.environ.get("DART_LIVE_CORP_CODE", "").strip()
        if not corp_code:
            self.skipTest("DART_LIVE_CORP_CODE not set; skipping live probe")

        client = DartClient(api_key=api_key)
        try:
            res = client.get_filing_list(
                corp_code=corp_code,
                bgn_de="2026-01-01",
                end_de="2026-09-18",
                pblntf_detail_ty="C001",
                last_reprt_at="N",
                page_no=1,
                page_count=10,
            )
            self.assertIn("status", res)
            filings = res.get("list", [])
            if filings:
                first = filings[0]
                rcept_no = first.get("rcept_no", "")
                self.assertTrue(bool(re.match(r"^\d{14}$", rcept_no)), f"Invalid rcept_no format: {rcept_no}")
        except DartClientError as exc:
            self.fail(f"Live DART request failed with client error: {exc}")


if __name__ == "__main__":
    unittest.main()
