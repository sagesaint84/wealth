import io
import json
import unittest
import zipfile
from unittest.mock import MagicMock, patch

import httpx

from app.services.ipo.dart_client import (
    DartAuthError,
    DartClient,
    DartClientError,
    DartNoData,
    DartRateLimitError,
    DartRequestError,
    DartSourceError,
    extract_document_text_from_zip,
    select_point_in_time_filing,
)
from app.services.ipo.normalize import normalize_equity_registration_response


class IpoDartClientTests(unittest.TestCase):
    def setUp(self):
        self.api_key = "test_secret_dart_key_12345"
        self.client = DartClient(api_key=self.api_key)

    # 1. list.json 성공
    @patch("httpx.Client.get")
    def test_get_filing_list_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "000",
            "message": "정상",
            "page_no": 1,
            "page_count": 10,
            "total_count": 1,
            "total_page": 1,
            "list": [
                {
                    "rcept_no": "20260901000123",
                    "corp_cls": "K",
                    "corp_code": "00123456",
                    "corp_name": "테스트기업",
                    "report_nm": "증권신고서(지분증권)",
                    "flr_nm": "테스트대표",
                    "rcept_dt": "2026-09-01",
                    "rm": "",
                }
            ],
        }
        mock_get.return_value = mock_resp

        res = self.client.get_filing_list(
            corp_code="00123456",
            bgn_de="2026-09-01",
            end_de="2026-09-18",
        )

        self.assertEqual(res["status"], "000")
        self.assertEqual(len(res["list"]), 1)
        self.assertEqual(res["list"][0]["rcept_no"], "20260901000123")

    # 2. C001 filter parameters 정확성
    @patch("httpx.Client.get")
    def test_get_filing_list_c001_filter(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "000", "message": "정상", "list": []}
        mock_get.return_value = mock_resp

        self.client.get_filing_list(
            corp_code="00999999",
            bgn_de="2026-01-01",
            end_de="2026-06-30",
            pblntf_detail_ty="C001",
        )

        mock_get.assert_called_once()
        params = mock_get.call_args[1].get("params", {})
        self.assertEqual(params["pblntf_detail_ty"], "C001")
        self.assertEqual(params["corp_code"], "00999999")

    # 3. last_reprt_at=N 전달
    @patch("httpx.Client.get")
    def test_get_filing_list_last_reprt_at_n(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "000", "message": "정상", "list": []}
        mock_get.return_value = mock_resp

        self.client.get_filing_list(
            corp_code="00999999",
            bgn_de="2026-01-01",
            end_de="2026-06-30",
            last_reprt_at="N",
        )

        mock_get.assert_called_once()
        params = mock_get.call_args[1].get("params", {})
        self.assertEqual(params["last_reprt_at"], "N")

    # 4. estkRs: corp_code/bgn_de/end_de 전달 및 grouped structure 정규화
    @patch("httpx.Client.get")
    def test_get_equity_registration_statements_parameters(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        grouped_fixture = {
            "status": "000",
            "message": "정상",
            "group": [
                {
                    "title": "일반사항",
                    "list": [
                        {
                            "corp_code": "00123456",
                            "corp_name": "테스트기업",
                            "sbd": "20260910",
                            "pymd": "20260912",
                        }
                    ],
                },
                {
                    "title": "증권의 종류",
                    "list": [
                        {
                            "sband": "20000",
                            "asand": "25000",
                            "slprc": 0,
                            "slta": 0.0,
                        }
                    ],
                },
                {
                    "title": "인수인 정보",
                    "list": [
                        {
                            "und_nm": "한국투자증권",
                            "und_qty": 500000,
                        }
                    ],
                },
                {
                    "title": "자금의 사용목적",
                    "list": [
                        {
                            "use_prps": "시설자금",
                            "use_amt": 10000000000,
                        }
                    ],
                },
                {
                    "title": "매출인에 관한 사항",
                    "list": [
                        {
                            "slr_nm": "최대주주",
                            "sl_qty": 100000,
                        }
                    ],
                },
                {
                    "title": "일반청약자 환매청구권",
                    "list": [
                        {
                            "rp_right_at": "Y",
                            "rp_term": "3개월",
                        }
                    ],
                },
                {
                    "title": "기타특이사항(커스텀그룹)",
                    "list": [
                        {
                            "custom_field": "값1",
                        }
                    ],
                },
            ],
        }
        mock_resp.json.return_value = grouped_fixture
        mock_get.return_value = mock_resp

        res = self.client.get_equity_registration_statements(
            corp_code="00123456",
            bgn_de="20260101",
            end_de="20260901",
        )

        self.assertEqual(res["status"], "000")
        mock_get.assert_called_once()
        params = mock_get.call_args[1].get("params", {})
        self.assertEqual(params["corp_code"], "00123456")
        self.assertEqual(params["bgn_de"], "20260101")
        self.assertEqual(params["end_de"], "20260901")

        # Canonical normalization verification
        norm = normalize_equity_registration_response(res)
        self.assertEqual(len(norm["general"]), 1)
        self.assertEqual(norm["general"][0]["corp_name"], "테스트기업")
        self.assertEqual(len(norm["security_classes"]), 1)
        self.assertEqual(norm["security_classes"][0]["slprc"], 0)
        self.assertEqual(norm["security_classes"][0]["slta"], 0.0)
        self.assertEqual(len(norm["underwriters"]), 1)
        self.assertEqual(norm["underwriters"][0]["und_nm"], "한국투자증권")
        self.assertEqual(len(norm["use_of_funds"]), 1)
        self.assertEqual(norm["use_of_funds"][0]["use_prps"], "시설자금")
        self.assertEqual(len(norm["sellers"]), 1)
        self.assertEqual(norm["sellers"][0]["slr_nm"], "최대주주")
        self.assertEqual(len(norm["redemption_rights"]), 1)
        self.assertEqual(norm["redemption_rights"][0]["rp_right_at"], "Y")
        self.assertEqual(len(norm["unknown_groups"]), 1)
        self.assertEqual(norm["unknown_groups"][0]["title"], "기타특이사항(커스텀그룹)")

    # 5. document.xml: rcept_no 전달 & bytes 반환
    @patch("httpx.Client.get")
    def test_download_document_zip_bytes(self, mock_get):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("report.xml", "<document>test</document>")
        zip_bytes = buf.getvalue()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = zip_bytes
        mock_get.return_value = mock_resp

        content = self.client.download_document_zip(rcept_no="20260901000123")

        self.assertIsInstance(content, bytes)
        self.assertEqual(content, zip_bytes)
        params = mock_get.call_args[1].get("params", {})
        self.assertEqual(params["rcept_no"], "20260901000123")
        self.assertEqual(params["crtfc_key"], self.api_key)

    # 6. ZIP 정상 extraction
    def test_zip_single_document_extraction(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("filing.html", "<html><body>신고서 본문 내용</body></html>")
        zip_bytes = buf.getvalue()

        extracted = extract_document_text_from_zip(zip_bytes)
        self.assertIn("신고서 본문 내용", extracted)

    # 7. ZIP multiple document deterministic extraction
    def test_zip_multiple_document_deterministic_extraction(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("part1.html", "<html><body>섹션1</body></html>")
            zf.writestr("main.xml", "<xml>메인본문</xml>")
            zf.writestr("summary.htm", "<html>요약본문</html>")
        zip_bytes = buf.getvalue()

        extracted = extract_document_text_from_zip(zip_bytes)
        # XML is prioritized over HTML in sorting
        self.assertIn("메인본문", extracted)
        self.assertIn("섹션1", extracted)
        self.assertIn("요약본문", extracted)
        self.assertIn("NEXT_DOCUMENT_SECTION", extracted)

    # 8. corrupt ZIP error
    def test_corrupt_zip_raises_error(self):
        bad_zip = b"PK\x03\x04not_a_valid_zip_payload_corrupt"
        with self.assertRaises(DartClientError):
            extract_document_text_from_zip(bad_zip)

    # 9. empty ZIP error
    def test_empty_zip_raises_error(self):
        with self.assertRaises(DartClientError):
            extract_document_text_from_zip(b"")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            pass
        with self.assertRaises(DartClientError):
            extract_document_text_from_zip(buf.getvalue())

    # 10. fnlttSinglAcntAll: fs_div=CFS & 11. fs_div=OFS
    @patch("httpx.Client.get")
    def test_get_financial_statements_cfs_and_ofs(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "000", "message": "정상", "list": []}
        mock_get.return_value = mock_resp

        # CFS
        res_cfs = self.client.get_financial_statements(
            corp_code="00123456",
            bsns_year="2025",
            reprt_code="11011",
            fs_div="CFS",
        )
        self.assertEqual(res_cfs["status"], "000")
        params_cfs = mock_get.call_args[1].get("params", {})
        self.assertEqual(params_cfs["fs_div"], "CFS")

        # OFS
        res_ofs = self.client.get_financial_statements(
            corp_code="00123456",
            bsns_year="2025",
            reprt_code="11011",
            fs_div="OFS",
        )
        self.assertEqual(res_ofs["status"], "000")
        params_ofs = mock_get.call_args[1].get("params", {})
        self.assertEqual(params_ofs["fs_div"], "OFS")

    # 12. invalid fs_div reject
    def test_invalid_fs_div_reject(self):
        with self.assertRaises(ValueError):
            self.client.get_financial_statements(
                corp_code="00123456",
                bsns_year="2025",
                reprt_code="11011",
                fs_div="INVALID",
            )

    # 13. status=013 no_data
    @patch("httpx.Client.get")
    def test_status_013_no_data(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "013", "message": "조회된 데이터가 없습니다."}
        mock_get.return_value = mock_resp

        # get_filing_list gracefully returns empty list
        res = self.client.get_filing_list("00123456", "20260101", "20260201")
        self.assertEqual(res["status"], "013")
        self.assertEqual(res["list"], [])

    # 14. status=020 rate limit
    @patch("httpx.Client.get")
    def test_status_020_rate_limit(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "020", "message": "요청 제한 초과"}
        mock_get.return_value = mock_resp

        with self.assertRaises(DartRateLimitError):
            self.client.get_equity_registration_statements("00123456", "20260101", "20260201")

    # 15. status=010 auth error
    @patch("httpx.Client.get")
    def test_status_010_auth_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "010", "message": "등록되지 않은 키입니다."}
        mock_get.return_value = mock_resp

        with self.assertRaises(DartAuthError):
            self.client.get_filing_list("00123456", "20260101", "20260201")

    # 16. HTTP timeout
    @patch("httpx.Client.get")
    def test_http_timeout_raises_dart_client_error(self, mock_get):
        mock_get.side_effect = httpx.TimeoutException("Read timeout")

        with self.assertRaises(DartClientError):
            self.client.get_filing_list("00123456", "20260101", "20260201")

    # 17. HTTP 500
    @patch("httpx.Client.get")
    def test_http_500_raises_dart_source_error(self, mock_get):
        mock_req = httpx.Request("GET", "https://opendart.fss.or.kr/api/list.json")
        mock_resp = httpx.Response(status_code=500, request=mock_req)
        mock_get.side_effect = httpx.HTTPStatusError("Server Error", request=mock_req, response=mock_resp)

        with self.assertRaises(DartSourceError):
            self.client.get_filing_list("00123456", "20260101", "20260201")

    # 18. API key missing
    def test_api_key_missing_raises_auth_error(self):
        with patch.dict("os.environ", {"DART_API_KEY": ""}, clear=False):
            client = DartClient(api_key="")
            self.assertFalse(client.is_configured())

            with self.assertRaises(DartAuthError):
                client.get_filing_list("00123456", "20260101", "20260201")

    # 19. secret가 exception/log string에 노출되지 않음
    def test_secret_not_exposed_in_safe_log_url(self):
        params = {"crtfc_key": self.api_key, "corp_code": "00123456"}
        safe_url = self.client._safe_log_url("list.json", params)
        self.assertNotIn(self.api_key, safe_url)
        self.assertTrue("***" in safe_url or "%2A%2A%2A" in safe_url)

    @patch("httpx.Client.get")
    def test_request_error_and_document_download_never_include_query_key(self, mock_get):
        leaked_url = f"https://opendart.fss.or.kr/api/list.json?crtfc_key={self.api_key}"
        request = httpx.Request("GET", leaked_url)
        mock_get.side_effect = httpx.RequestError(f"failed request {leaked_url}", request=request)
        with self.assertRaises(DartClientError) as filing_error:
            self.client.get_filing_list("00123456", "20260101", "20260201")
        with self.assertRaises(DartClientError) as document_error:
            self.client.download_document_zip("20260901000123")
        self.assertEqual(str(filing_error.exception), "DART_NETWORK_ERROR")
        self.assertEqual(str(document_error.exception), "DART_NETWORK_ERROR")
        self.assertNotIn(self.api_key, str(filing_error.exception))
        self.assertNotIn(self.api_key, str(document_error.exception))

    @patch("httpx.Client.get")
    def test_corp_code_master_parses_official_zip(self, mock_get):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("CORPCODE.xml", """<result><list><corp_code>00123456</corp_code><corp_name>테스트 회사</corp_name><stock_code>123456</stock_code></list></result>""")
        response = MagicMock(); response.content = buf.getvalue()
        mock_get.return_value = response
        self.assertEqual(self.client.get_corp_code_master(), [{"corp_code": "00123456", "corp_name": "테스트 회사", "stock_code": "123456"}])
        self.assertEqual(mock_get.call_args.kwargs["params"]["crtfc_key"], self.api_key)

    @patch("httpx.Client.get")
    def test_corp_code_master_error_xml_uses_typed_statuses(self, mock_get):
        response = MagicMock()
        mock_get.return_value = response
        response.content = b"<result><status>010</status><message>bad key</message></result>"
        with self.assertRaises(DartAuthError):
            self.client.get_corp_code_master()
        response.content = b"<result><status>020</status><message>rate</message></result>"
        with self.assertRaises(DartRateLimitError):
            self.client.get_corp_code_master()
        response.content = b"<result><status>800</status><message>source</message></result>"
        with self.assertRaises(DartSourceError):
            self.client.get_corp_code_master()

    # 20. 0 values preserved
    @patch("httpx.Client.get")
    def test_zero_values_preserved_in_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "000",
            "message": "정상",
            "list": [
                {
                    "rcept_no": "20260901000123",
                    "slprc": 0,
                    "slta": 0.0,
                }
            ],
        }
        mock_get.return_value = mock_resp

        res = self.client.get_equity_registration_statements("00123456", "20260101", "20260201")
        item = res["list"][0]
        self.assertEqual(item["slprc"], 0)
        self.assertEqual(item["slta"], 0.0)

    # Point-in-time filing selection tests
    def test_point_in_time_filing_selection(self):
        filings = [
            {
                "rcept_no": "20260801000001",
                "report_nm": "증권신고서(지분증권)",
                "rcept_dt": "20260801",
            },
            {
                "rcept_no": "20260815000002",
                "report_nm": "[기재정정]증권신고서(지분증권)",
                "rcept_dt": "20260815",
            },
            {
                "rcept_no": "20260825000003",
                "report_nm": "증권발행실적보고서",  # Must be excluded!
                "rcept_dt": "20260825",
            },
            {
                "rcept_no": "20260910000004",  # Future date after score_as_of!
                "report_nm": "[기재정정]증권신고서(지분증권)",
                "rcept_dt": "20260910",
            },
        ]

        selected = select_point_in_time_filing(filings, score_as_of="2026-08-20")
        self.assertIsNotNone(selected)
        self.assertEqual(selected["rcept_no"], "20260815000002")


    # 21. status=014 (no file found raises DartNoData with [014])
    @patch("httpx.Client.get")
    def test_status_014_raises_dart_no_data(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "014", "message": "파일이 존재하지 않습니다."}
        mock_get.return_value = mock_resp

        with self.assertRaises(DartNoData) as cm:
            self.client.get_equity_registration_statements("00123456", "20260101", "20260201")
        self.assertIn("[014]", str(cm.exception))

    # 22. status=021 (excess company count raises DartRequestError)
    @patch("httpx.Client.get")
    def test_status_021_raises_dart_request_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "021", "message": "조회 가능한 회사 개수 초과"}
        mock_get.return_value = mock_resp

        with self.assertRaises(DartRequestError) as cm:
            self.client.get_filing_list("00123456", "20260101", "20260201")
        self.assertIn("[021]", str(cm.exception))

    # 23. status=101 & 901 (DartAuthError)
    @patch("httpx.Client.get")
    def test_status_101_and_901_raise_dart_auth_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "101", "message": "부적절한 접근입니다."}
        mock_get.return_value = mock_resp

        with self.assertRaises(DartAuthError) as cm:
            self.client.get_filing_list("00123456", "20260101", "20260201")
        self.assertIn("[101]", str(cm.exception))

        mock_resp.json.return_value = {"status": "901", "message": "사용할 수 없는 키입니다."}
        with self.assertRaises(DartAuthError) as cm:
            self.client.get_filing_list("00123456", "20260101", "20260201")
        self.assertIn("[901]", str(cm.exception))

    # 24. deprecated get_equity_registration_statement raises DartRequestError
    def test_deprecated_get_equity_registration_statement_raises_dart_request_error(self):
        with self.assertRaises(DartRequestError) as cm:
            self.client.get_equity_registration_statement("20260901000123")
        self.assertIn("Deprecated API", str(cm.exception))

    # 25. get_filing_list includes pblntf_ty="C"
    @patch("httpx.Client.get")
    def test_get_filing_list_pblntf_ty_c(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "000", "message": "정상", "list": []}
        mock_get.return_value = mock_resp

        self.client.get_filing_list("00123456", "20260101", "20260201")
        params = mock_get.call_args[1].get("params", {})
        self.assertEqual(params.get("pblntf_ty"), "C")

    # 26. download_document_zip rejects non-ZIP without PK header
    @patch("httpx.Client.get")
    def test_download_document_zip_rejects_non_zip(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"INVALID_NON_ZIP_BYTES"
        mock_get.return_value = mock_resp

        with self.assertRaises(DartClientError) as cm:
            self.client.download_document_zip("20260901000123")
        self.assertIn("Invalid ZIP binary", str(cm.exception))

    # 27. download_document_zip recognizes XML error with leading BOM/whitespace
    @patch("httpx.Client.get")
    def test_download_document_zip_xml_error_with_bom(self, mock_get):
        xml_err = b"\xef\xbb\xbf  <?xml version=\"1.0\" encoding=\"utf-8\"?><result><status>014</status><message>\xed\x8c\x8c\xec\x9d\xbc\xec\x9d\xb4 \xec\x97\x86\xec\x8a\xb5\xeb\x8b\x88\xeb\x8b\xa4.</message></result>"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = xml_err
        mock_get.return_value = mock_resp

        with self.assertRaises(DartNoData) as cm:
            self.client.download_document_zip("20260901000123")
        self.assertIn("[014]", str(cm.exception))

    # 28. select_point_in_time_filing rejects debt/non-equity and invalid date format
    def test_point_in_time_filing_equity_and_date_rules(self):
        filings = [
            {
                "rcept_no": "20260801000001",
                "report_nm": "증권신고서(채무증권)",  # Debt must be excluded
                "rcept_dt": "20260801",
            },
            {
                "rcept_no": "20260802000002",
                "report_nm": "증권신고서(사채)",  # Bond must be excluded
                "rcept_dt": "20260802",
            },
            {
                "rcept_no": "20260805000003",
                "report_nm": "증권신고서(지분증권)",
                "rcept_dt": "invalid-date",  # Non-8-digit date must be excluded
            },
            {
                "rcept_no": "20260810000004",
                "report_nm": "증권신고서(지분증권)",
                "rcept_dt": "20260810",
            },
        ]
        selected = select_point_in_time_filing(filings, score_as_of="2026-08-20")
        self.assertIsNotNone(selected)
        self.assertEqual(selected["rcept_no"], "20260810000004")

        # Invalid score_as_of format returns None
        self.assertIsNone(select_point_in_time_filing(filings, score_as_of="not-a-date"))


if __name__ == "__main__":
    unittest.main()
