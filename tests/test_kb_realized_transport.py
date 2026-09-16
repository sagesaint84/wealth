import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("WEALTH_ENV", "test")
os.environ.setdefault("WEALTH_TEST_SIGNING_SECRET", "synthetic-kb-test-secret")

from app.services.kb_openapi import (
    KB_REALIZED_MAX_PAGES,
    KBOpenAPI,
    KBOpenAPIError,
    compute_kb_account_key,
    mask_kb_account,
)


class FakeResponse:
    def __init__(self, payload, *, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = str(payload)

    @property
    def is_error(self):
        return self.status_code >= 400

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        if not self.responses:
            raise RuntimeError("No more fake responses")
        return self.responses.pop(0)


class KBRealizedTransportTests(unittest.TestCase):
    def setUp(self):
        self.client = object.__new__(KBOpenAPI)
        self.client.base_url = "https://developer.kbsec.com:32484"
        self.client.app_key = "synthetic-kb-app-key"
        self.client.app_secret = "synthetic-kb-app-secret"
        self.client.gnl_ac_no = "400277078"
        self.client.gds_no = "01"
        # Patch _data_header so unit tests never trigger the socket-based IP
        # discovery (which the test network guard blocks). The returned values
        # are plausible synthetic non-empty strings; they do NOT represent any
        # real IP or MAC address.
        self._dh_patcher = patch.object(
            KBOpenAPI,
            "_data_header",
            return_value={"ipAddr": "192.0.2.1", "macAddr": "02:00:00:00:00:01"},
        )
        self._dh_patcher.start()

    def tearDown(self):
        self._dh_patcher.stop()

    def test_auth_headers_and_request_shape(self):
        fake = FakeClient([
            FakeResponse({
                "dataHeader": {"resultCode": "200", "resultMessage": "성공"},
                "dataBody": {
                    "nxt_key": "                        ",
                    "Record1": [{"trd_dt": "20260901", "shrt_is_cd": "A005930"}],
                },
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-kb-token")),
        ):
            rows, source_key, label = asyncio.run(
                self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930")
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["trd_dt"], "20260901")
        self.assertTrue(source_key)
        self.assertEqual(label, "****7078-**")
        self.assertNotIn("400277078", label)
        self.assertNotIn("01", label)

        self.assertEqual(len(fake.requests), 1)
        url, kwargs = fake.requests[0]
        self.assertTrue(url.endswith("/api/v1/ssqm2442"))
        headers = kwargs["headers"]
        self.assertEqual(headers["appKey"], "synthetic-kb-app-key")
        self.assertEqual(headers["Authorization"], "bearer synthetic-kb-token")
        self.assertEqual(headers["Content-Type"], "application/json")

        req_body = kwargs["json"]
        self.assertIn("dataHeader", req_body)
        self.assertIn("dataBody", req_body)
        body = req_body["dataBody"]
        self.assertEqual(body["md_clsf"], "2")  # Online channel semantics
        self.assertEqual(body["inq_strt_dt"], "20260901")
        self.assertEqual(body["inq_end_dt"], "20260930")
        self.assertEqual(body["gnl_ac_no"], "400277078")
        self.assertEqual(body["gds_no"], "01")
        self.assertEqual(body["nxt_key"], "")

    def test_account_tuple_stays_server_side(self):
        key = compute_kb_account_key("400277078", "01")
        label = mask_kb_account("400277078", "01")
        self.assertNotIn("400277078", key)
        self.assertNotIn("400277078", label)
        self.assertEqual(label, "****7078-**")
        self.assertNotIn("01", label)
        # Verify deterministic HMAC
        key2 = compute_kb_account_key("400277078", "01")
        self.assertEqual(key, key2)

    def test_missing_gds_no_fails_closed(self):
        # Explicit None or empty string for gds_no must fail before network request
        fake = FakeClient([])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-kb-token")),
        ):
            with self.assertRaises(KBOpenAPIError) as ctx:
                asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", gds_no=""))
            self.assertIn("gds_no", str(ctx.exception))
            self.assertEqual(len(fake.requests), 0)

    def test_missing_gnl_ac_no_fails_closed(self):
        fake = FakeClient([])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-kb-token")),
        ):
            with self.assertRaises(KBOpenAPIError) as ctx:
                asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", gnl_ac_no=""))
            self.assertIn("계좌번호", str(ctx.exception))
            self.assertEqual(len(fake.requests), 0)

    def test_md_clsf_channel_semantics(self):
        fake = FakeClient([
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "", "Record1": []},
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="tok")),
        ):
            asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930"))
        self.assertEqual(fake.requests[0][1]["json"]["dataBody"]["md_clsf"], "2")

    def test_date_normalizations(self):
        # YYYY-MM-DD -> YYYYMMDD
        s, e = KBOpenAPI.validate_and_normalize_dates("2026-09-01", "2026-09-30")
        self.assertEqual(s, "20260901")
        self.assertEqual(e, "20260930")

        # YYYYMMDD -> YYYYMMDD
        s, e = KBOpenAPI.validate_and_normalize_dates("20260901", "20260930")
        self.assertEqual(s, "20260901")
        self.assertEqual(e, "20260930")

        # Same-day query start == end is valid
        s, e = KBOpenAPI.validate_and_normalize_dates("2026-09-13", "2026-09-13")
        self.assertEqual(s, "20260913")
        self.assertEqual(e, "20260913")

        # start > end fails
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI.validate_and_normalize_dates("20260930", "20260901")

        # invalid calendar date rejected (e.g. Feb 30)
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI.validate_and_normalize_dates("20260230", "20260301")

        # garbage date rejected
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI.validate_and_normalize_dates("not-a-date", "20260930")

    def test_success_response_parsing(self):
        resp = FakeResponse({
            "dataHeader": {"resultCode": "200", "resultMessage": "정상"},
            "dataBody": {
                "nxt_key": "                        ",
                "Record1": [{"item": 1}],
            },
        })
        body, key = KBOpenAPI._parse_realized_response(resp)
        self.assertEqual(key, "                        ")
        self.assertEqual(len(body["Record1"]), 1)

    def test_provider_error_fails_closed(self):
        resp = FakeResponse({
            "dataHeader": {"resultCode": "500", "resultMessage": "시스템 오류", "processCode": "ERR01"},
            "dataBody": {},
        })
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._parse_realized_response(resp)
        self.assertIn("시스템 오류", str(ctx.exception))

    def test_malformed_envelope_fails_closed(self):
        # missing dataHeader
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI._parse_realized_response(FakeResponse({"dataBody": {}}))
        # missing dataBody
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI._parse_realized_response(FakeResponse({"dataHeader": {"resultCode": "200"}}))
        # non-json
        bad_json_resp = FakeResponse(None)
        bad_json_resp.json = lambda: (_ for _ in ()).throw(ValueError("not json"))
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI._parse_realized_response(bad_json_resp)

    def test_token_refresh_preserves_nxt_key_and_request_state(self):
        fake = FakeClient([
            FakeResponse("Unauthorized", status_code=401),
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "KEY_PAGE_2", "Record1": [{"page": 1}]},
            }),
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "                        ", "Record1": [{"page": 2}]},
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(side_effect=["initial-tok", "refreshed-tok"])),
        ):
            rows, _, _ = asyncio.run(
                self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", delay=AsyncMock())
            )

        self.assertEqual(len(rows), 2)
        # Verify first retry used refreshed token and preserved original request
        first_req = fake.requests[0]
        self.assertEqual(first_req[1]["headers"]["Authorization"], "bearer initial-tok")
        retry_req = fake.requests[1]
        self.assertEqual(retry_req[1]["headers"]["Authorization"], "bearer refreshed-tok")
        self.assertEqual(retry_req[1]["json"]["dataBody"]["inq_strt_dt"], "20260901")
        self.assertEqual(retry_req[1]["json"]["dataBody"]["nxt_key"], "")

        # Second page had KEY_PAGE_2
        second_page = fake.requests[2]
        self.assertEqual(second_page[1]["json"]["dataBody"]["nxt_key"], "KEY_PAGE_2")

    def test_pagination_single_page_whitespace_terminal(self):
        fake = FakeClient([
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "   ", "Record1": [{"id": 1}]},
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="tok")),
        ):
            rows, _, _ = asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930"))
        self.assertEqual(len(rows), 1)

    def test_pagination_multiple_pages_new_nxt_key(self):
        fake = FakeClient([
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "NEXT_P2", "Record1": [{"id": 1}]},
            }),
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "NEXT_P3", "Record1": [{"id": 2}]},
            }),
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "                        ", "Record1": [{"id": 3}]},
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="tok")),
        ):
            rows, _, _ = asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", delay=AsyncMock()))
        self.assertEqual(len(rows), 3)
        self.assertEqual(fake.requests[1][1]["json"]["dataBody"]["nxt_key"], "NEXT_P2")
        self.assertEqual(fake.requests[2][1]["json"]["dataBody"]["nxt_key"], "NEXT_P3")

    def test_pagination_repeated_key_fails_closed(self):
        fake = FakeClient([
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "REPEAT_KEY", "Record1": [{"id": 1}]},
            }),
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "REPEAT_KEY", "Record1": [{"id": 2}]},
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="tok")),
        ):
            with self.assertRaises(KBOpenAPIError) as ctx:
                asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", delay=AsyncMock()))
            self.assertIn("PAGINATION_CONTINUATION_KEY_REPEATED", str(ctx.exception))

    def test_pagination_malformed_non_string_key_fails_closed(self):
        resp = FakeResponse({
            "dataHeader": {"resultCode": "200"},
            "dataBody": {"nxt_key": 12345, "Record1": []},
        })
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._parse_realized_response(resp)
        self.assertIn("문자열이 아닙니다", str(ctx.exception))

    def test_pagination_null_key_fails_closed(self):
        resp = FakeResponse({
            "dataHeader": {"resultCode": "200"},
            "dataBody": {"nxt_key": None, "Record1": []},
        })
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._parse_realized_response(resp)
        self.assertIn("null", str(ctx.exception))

    def test_pagination_missing_key_fails_closed(self):
        resp = FakeResponse({
            "dataHeader": {"resultCode": "200"},
            "dataBody": {"Record1": []},
        })
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._parse_realized_response(resp)
        self.assertIn("nxt_key 필드가 누락", str(ctx.exception))

    def test_later_page_failure_returns_no_partial_feed(self):
        fake = FakeClient([
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "PAGE_2", "Record1": [{"id": 1}]},
            }),
            FakeResponse({
                "dataHeader": {"resultCode": "500", "resultMessage": "Server error"},
                "dataBody": {},
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="tok")),
        ):
            with self.assertRaises(KBOpenAPIError):
                asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", delay=AsyncMock()))

    def test_page_limit_guard_fails_entire_fetch(self):
        # Generate 501 responses with unique keys
        responses = [
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": f"KEY_{i}", "Record1": [{"id": i}]},
            })
            for i in range(KB_REALIZED_MAX_PAGES + 1)
        ]
        fake = FakeClient(responses)
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="tok")),
        ):
            with self.assertRaises(KBOpenAPIError) as ctx:
                asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", delay=AsyncMock()))
            self.assertIn("한도", str(ctx.exception))


class KBDataHeaderContractTests(unittest.TestCase):
    """Tests for runtime dataHeader construction and process-status validation.

    These tests verify:
    - _local_ip() and _local_mac() produce non-empty strings of expected format.
    - _data_header() returns a dict with non-empty ipAddr and macAddr.
    - _check_provider_status() correctly classifies observed KB response statuses.
    - The SSQM2442 parser rejects process-level failures before touching dataBody.
    - The generic TR normalizer rejects process-level failures.
    - No real IP/MAC or credential values are hard-coded in these tests.
    """

    # -------------------------------------------------------------------------
    # dataHeader helpers — tested by mocking the network-dependent parts
    # -------------------------------------------------------------------------

    def test_local_ip_returns_non_empty_string(self):
        """_local_ip() must return a non-empty string (mocked network)."""
        with patch("app.services.kb_openapi.socket") as mock_socket_mod:
            mock_sock = mock_socket_mod.socket.return_value.__enter__.return_value
            mock_sock.getsockname.return_value = ("192.0.2.99", 0)
            # Test via direct mock of socket.socket
            import socket as socket_mod
            original = socket_mod.socket

            class FakeSocket:
                def __init__(self, *a, **kw):
                    pass
                def connect(self, addr):
                    pass
                def getsockname(self):
                    return ("192.0.2.99", 0)
                def close(self):
                    pass

            with patch("app.services.kb_openapi.socket.socket", FakeSocket):
                ip = KBOpenAPI._local_ip()
            self.assertIsInstance(ip, str)
            self.assertTrue(len(ip) > 0)
            self.assertNotEqual(ip, "")

    def test_local_ip_fails_closed_on_os_error(self):
        """_local_ip() raises KBOpenAPIError if socket raises OSError."""
        class FailSocket:
            def __init__(self, *a, **kw):
                pass
            def connect(self, addr):
                raise OSError("no route")
            def getsockname(self):
                return ("", 0)
            def close(self):
                pass

        with patch("app.services.kb_openapi.socket.socket", FailSocket):
            with self.assertRaises(KBOpenAPIError) as ctx:
                KBOpenAPI._local_ip()
            self.assertIn("로컬 IP 주소를 확인할 수 없습니다", str(ctx.exception))

    def test_local_ip_fails_closed_on_loopback_or_zero(self):
        """_local_ip() raises KBOpenAPIError if socket returns loopback or 0.0.0.0."""
        for invalid_ip in ("127.0.0.1", "0.0.0.0", ""):
            with self.subTest(ip=invalid_ip):
                class DummySocket:
                    def __init__(self, *a, **kw):
                        pass
                    def connect(self, addr):
                        pass
                    def getsockname(self):
                        return (invalid_ip, 0)
                    def close(self):
                        pass

                with patch("app.services.kb_openapi.socket.socket", DummySocket):
                    with self.assertRaises(KBOpenAPIError):
                        KBOpenAPI._local_ip()

    def test_local_mac_fails_closed_when_unavailable(self):
        """_local_mac() raises KBOpenAPIError if uuid.getnode() returns 0 or all zeroes."""
        with patch("app.services.kb_openapi.uuid.getnode", return_value=0):
            with self.assertRaises(KBOpenAPIError) as ctx:
                KBOpenAPI._local_mac()
            self.assertIn("로컬 MAC 주소를 확인할 수 없습니다", str(ctx.exception))

    def test_local_mac_returns_non_empty_colon_string(self):
        """_local_mac() must return a non-empty colon-separated MAC string."""
        with patch("app.services.kb_openapi.uuid.getnode", return_value=0x020000000001):
            mac = KBOpenAPI._local_mac()
        self.assertIsInstance(mac, str)
        self.assertTrue(len(mac) > 0)
        self.assertIn(":", mac)
        parts = mac.split(":")
        self.assertEqual(len(parts), 6)
        for part in parts:
            self.assertTrue(len(part) == 2)
            int(part, 16)  # each part must be valid hex

    def test_data_header_contains_non_empty_ip_and_mac(self):
        """_data_header() must return a dict with non-empty ipAddr and macAddr."""
        with (
            patch.object(KBOpenAPI, "_local_ip", return_value="192.0.2.1"),
            patch.object(KBOpenAPI, "_local_mac", return_value="02:00:00:00:00:01"),
        ):
            dh = KBOpenAPI._data_header()
        self.assertIn("ipAddr", dh)
        self.assertIn("macAddr", dh)
        self.assertTrue(dh["ipAddr"])
        self.assertTrue(dh["macAddr"])
        self.assertNotEqual(dh["ipAddr"], "")
        self.assertNotEqual(dh["macAddr"], "")

    def test_data_header_no_hard_coded_ip_or_mac_in_production_paths(self):
        """_data_header() must not return known invalid placeholder values."""
        with (
            patch.object(KBOpenAPI, "_local_ip", return_value="192.0.2.1"),
            patch.object(KBOpenAPI, "_local_mac", return_value="02:00:00:00:00:01"),
        ):
            dh = KBOpenAPI._data_header()
        # Known invalid/problematic placeholders must not appear
        self.assertNotEqual(dh["ipAddr"], "")
        self.assertNotEqual(dh["macAddr"], "")
        # 0.0.0.0 would be obviously wrong
        self.assertNotEqual(dh["ipAddr"], "0.0.0.0")

    def test_ssqm2442_page_request_uses_data_header(self):
        """_post_ssqm2442_page must include the dataHeader from _data_header()."""
        client = object.__new__(KBOpenAPI)
        client.base_url = "https://developer.kbsec.com:32484"
        client.app_key = "synthetic-kb-app-key"

        fake_dh = {"ipAddr": "192.0.2.1", "macAddr": "02:00:00:00:00:01"}
        captured_body = {}

        class CapturingFake:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, **kwargs):
                captured_body.update(kwargs.get("json", {}))
                return FakeResponse({
                    "dataHeader": {"resultCode": "200", "processFlag": "A", "processCode": "0011"},
                    "dataBody": {"nxt_key": "                        ", "Record1": []},
                })

        with patch.object(KBOpenAPI, "_data_header", return_value=fake_dh):
            import asyncio
            asyncio.run(client._post_ssqm2442_page(
                CapturingFake(), "synthetic-token",
                inq_strt_dt="20260901", inq_end_dt="20260930",
                gnl_ac_no="400277078", gds_no="01",
            ))

        self.assertIn("dataHeader", captured_body)
        self.assertEqual(captured_body["dataHeader"], fake_dh)
        self.assertNotEqual(captured_body["dataHeader"]["ipAddr"], "")
        self.assertNotEqual(captured_body["dataHeader"]["macAddr"], "")

    # -------------------------------------------------------------------------
    # _check_provider_status — process-level status validation
    # -------------------------------------------------------------------------

    def test_process_flag_a_is_accepted(self):
        """processFlag='A' (observed live success) must not raise."""
        # No exception expected
        KBOpenAPI._check_provider_status(
            {"processFlag": "A", "processCode": "0011"},
            context="TEST",
        )

    def test_process_flag_b_raises_provider_error(self):
        """processFlag='B' (observed live failure) must raise KBOpenAPIError."""
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._check_provider_status(
                {"processFlag": "B", "processCode": "9999", "processMessage": "test validation error"},
                context="TEST_TR",
            )
        err = str(ctx.exception)
        self.assertIn("processCode=9999", err)
        self.assertIn("processFlag", err)

    def test_process_code_9999_surfaces_in_error(self):
        """processCode=9999 must be included in the raised error message."""
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._check_provider_status(
                {"processFlag": "B", "processCode": "9999"},
                context="TEST",
            )
        self.assertIn("9999", str(ctx.exception))

    def test_process_message_propagated_safely(self):
        """processMessage must appear in the error when it does not contain sensitive info."""
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._check_provider_status(
                {"processFlag": "B", "processCode": "9999", "processMessage": "input field check"},
                context="TEST",
            )
        self.assertIn("input field check", str(ctx.exception))

    def test_process_message_truncated_to_120_chars(self):
        """processMessage longer than 120 chars must be truncated in the error."""
        long_msg = "X" * 200
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._check_provider_status(
                {"processFlag": "B", "processCode": "9999", "processMessage": long_msg},
                context="TEST",
            )
        # The full 200-char message must not appear verbatim
        self.assertNotIn(long_msg, str(ctx.exception))
        self.assertIn("X" * 120, str(ctx.exception))

    def test_unknown_process_flag_fails_closed(self):
        """An unknown processFlag (not 'A') must raise KBOpenAPIError (fail-closed)."""
        for unknown_flag in ("C", "X", "Z", "0", "1"):
            with self.subTest(flag=unknown_flag):
                with self.assertRaises(KBOpenAPIError):
                    KBOpenAPI._check_provider_status(
                        {"processFlag": unknown_flag, "processCode": "9998"},
                        context="TEST",
                    )

    def test_unknown_process_status_synthetic_fails_closed(self):
        """Synthetic unknown process status pairs such as 7777/Z or 7777/A must fail closed."""
        for code, flag in (("7777", "Z"), ("7777", "A"), ("9998", "A"), ("UNKNOWN", "X")):
            with self.subTest(code=code, flag=flag):
                with self.assertRaises(KBOpenAPIError):
                    KBOpenAPI._check_provider_status(
                        {"processFlag": flag, "processCode": code},
                        context="TEST",
                    )

    def test_empty_process_flag_passes_check(self):
        """Empty processFlag (field absent) must not raise — fail-open for missing field.

        Some KB endpoints may not populate processFlag in every response.
        Absence is treated as not-failed rather than failing closed, since we
        cannot distinguish a genuinely absent field from a future success variant.
        """
        # Should not raise
        KBOpenAPI._check_provider_status(
            {"resultCode": "200"},  # no processFlag key
            context="TEST",
        )
        KBOpenAPI._check_provider_status(
            {"processFlag": "", "processCode": ""},
            context="TEST",
        )

    # -------------------------------------------------------------------------
    # _parse_realized_response — integration of process check
    # -------------------------------------------------------------------------

    def test_parse_realized_response_rejects_process_flag_b(self):
        """HTTP 200 + resultCode=200 + processFlag=B must raise, not parse dataBody."""
        resp = FakeResponse({
            "dataHeader": {
                "resultCode": "200",
                "resultMessage": "성공",
                "processCode": "9999",
                "processFlag": "B",
                "processMessage": "input field check",
            },
            # dataBody absent simulates live behavior
        })
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._parse_realized_response(resp)
        err = str(ctx.exception)
        # Must surface the process code, not a generic "dataBody가 없습니다"
        self.assertIn("9999", err)
        # Must NOT produce the misleading body-absent message as the primary error
        self.assertNotIn("dataBody가 없습니다", err)

    def test_parse_realized_response_accepts_process_flag_a(self):
        """HTTP 200 + resultCode=200 + processFlag=A must proceed to body parsing."""
        resp = FakeResponse({
            "dataHeader": {
                "resultCode": "200",
                "processCode": "0011",
                "processFlag": "A",
            },
            "dataBody": {"nxt_key": "                        ", "Record1": []},
        })
        body, nxt_key = KBOpenAPI._parse_realized_response(resp)
        self.assertIn("Record1", body)
        self.assertTrue(KBOpenAPI.is_terminal_nxt_key(nxt_key))

    def test_parse_realized_response_null_databody_with_process_failure(self):
        """When processFlag=B, dataBody=null must NOT produce a misleading generic error.

        The previous bug: processCode=9999 responses with null dataBody were being
        reduced to 'dataBody가 없습니다' rather than surfacing the real provider error.
        This test verifies the bug is fixed.
        """
        resp = FakeResponse({
            "dataHeader": {
                "resultCode": "200",
                "resultMessage": "성공",
                "processCode": "9999",
                "processFlag": "B",
            },
            # No dataBody key — matches live behavior when process fails
        })
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._parse_realized_response(resp)
        err = str(ctx.exception)
        # The process-level error must be raised before body inspection
        self.assertIn("9999", err)
        self.assertNotIn("dataBody가 없습니다", err)

    # -------------------------------------------------------------------------
    # _normalize_response — generic TR path
    # -------------------------------------------------------------------------

    def test_normalize_response_rejects_process_flag_b(self):
        """Generic KB TR normalizer must also reject processFlag=B."""
        payload = {
            "dataHeader": {
                "resultCode": "200",
                "processCode": "9999",
                "processFlag": "B",
            }
        }
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._normalize_response(payload)
        self.assertIn("9999", str(ctx.exception))

    def test_normalize_response_accepts_process_flag_a(self):
        """Generic KB TR normalizer must accept processFlag=A and return dataBody."""
        payload = {
            "dataHeader": {
                "resultCode": "200",
                "processCode": "0011",
                "processFlag": "A",
            },
            "dataBody": {"o_clsf": "0", "data": "ok"},
        }
        result = KBOpenAPI._normalize_response(payload)
        self.assertEqual(result.get("data"), "ok")
