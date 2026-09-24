import io
import unittest
from copy import deepcopy
from unittest.mock import patch

from openpyxl import Workbook

from app.services.ipo.historical_import import (
    HistoricalImportError,
    SOURCE_KIND,
    SOURCE_KRX,
    _PREVIEWS,
    commit_preview,
    create_preview,
)
from app.services.ipo.presentation import derive_filter_group, derive_market_state


def workbook_bytes(headers, rows, preamble=None):
    wb = Workbook()
    ws = wb.active
    for row in preamble or []:
        ws.append(row)
    ws.append(headers)
    for row in rows:
        ws.append(row)
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()


class HistoricalOfficialImportTests(unittest.TestCase):
    def setUp(self):
        _PREVIEWS.clear()
        self.market = {"schema_version": 1, "ipos": []}
        # Mirrors the official KRX Data Marketplace [20001] column family.
        self.krx_headers = [
            "번호",
            "종목코드",
            "종목명",
            "시장구분",
            "증권구분",
            "주식종류",
            "상장일",
            "상장유형",
            "상장주선인\n(지정자문인)",
            "공모가",
            "공모주식수",
        ]
        self.krx_row = [
            1,
            "065370",
            "테스트 기업",
            "코스닥",
            "주권",
            "보통주",
            "2020.12.23",
            "신규상장",
            "테스트증권",
            10000,
            1_980_000,
        ]
        self.kind_headers = [
            "회사명",
            "종목코드",
            "시장구분",
            "신규상장일",
            "공모가",
            "공모금액(백만원)",
            "대표주관회사",
        ]
        self.kind_row = [
            "테스트 기업",
            "065370",
            "코스닥",
            "2020.12.23",
            10000,
            19800,
            "테스트증권",
        ]

    def _preview_krx(self, rows=None, market=None):
        return create_preview(
            "KRX.xlsx",
            workbook_bytes(self.krx_headers, rows or [self.krx_row]),
            "u",
            market or self.market,
        )

    def test_krx_workbook_is_recognized_and_normalized(self):
        result = self._preview_krx()
        self.assertEqual(result["source"], SOURCE_KRX)
        self.assertEqual(result["summary"]["new"], 1)
        state = _PREVIEWS[result["preview_ticket"]]
        record = state["candidates"][0]["record"]
        self.assertEqual(record["stock_code"], "065370")
        self.assertEqual(record["actual_listing_date"], "2020-12-23")
        self.assertEqual(record["final_offer_price"], 10000)
        self.assertEqual(record["offer_shares"], 1_980_000)
        self.assertEqual(record["lead_managers"], ["테스트증권"])
        self.assertIsNone(record["subscription_start"])

    def test_kind_workbook_is_recognized_and_amount_is_normalized(self):
        result = create_preview(
            "KIND.xlsx",
            workbook_bytes(self.kind_headers, [self.kind_row]),
            "u",
            self.market,
        )
        self.assertEqual(result["source"], SOURCE_KIND)
        record = _PREVIEWS[result["preview_ticket"]]["candidates"][0]["record"]
        self.assertEqual(record["offering_amount"], 19_800_000_000)
        self.assertEqual(record["lead_managers"], ["테스트증권"])

    def test_header_row_may_follow_official_export_preamble(self):
        payload = workbook_bytes(
            self.krx_headers,
            [self.krx_row],
            preamble=[["KRX 신규상장종목 현황"], ["조회조건", "최근 10년"]],
        )
        result = create_preview("KRX.xlsx", payload, "u", self.market)
        self.assertEqual(result["summary"]["new"], 1)
        self.assertEqual(_PREVIEWS[result["preview_ticket"]]["candidates"][0]["row_number"], 4)

    def test_cp949_csv_is_supported(self):
        text = ",".join(self.kind_headers) + "\n" + ",".join(map(str, self.kind_row)) + "\n"
        result = create_preview("KIND.csv", text.encode("cp949"), "u", self.market)
        self.assertEqual(result["source"], SOURCE_KIND)
        self.assertEqual(result["summary"]["new"], 1)

    def test_invalid_required_fields_are_not_auto_eligible(self):
        bad = list(self.krx_row)
        bad[9] = 0
        result = self._preview_krx([bad])
        self.assertEqual(result["summary"]["invalid"], 1)
        self.assertEqual(result["summary"]["new"], 0)
        self.assertEqual(result["issues"][0]["reason"], "FINAL_OFFER_PRICE_INVALID")

    def test_future_actual_listing_date_is_rejected_before_storage(self):
        bad = list(self.krx_row)
        bad[6] = "2999-01-01"
        result = self._preview_krx([bad])
        self.assertEqual(result["summary"]["invalid"], 1)
        self.assertEqual(result["summary"]["new"], 0)
        self.assertEqual(result["issues"][0]["reason"], "ACTUAL_LISTING_DATE_IN_FUTURE")

    def test_unknown_or_generic_headers_fail_closed(self):
        with self.assertRaises(HistoricalImportError) as caught:
            create_preview("unknown.csv", b"a,b,c\n1,2,3\n", "u", self.market)
        self.assertEqual(caught.exception.code, "SOURCE_UNRECOGNIZED")

        generic = "기업명,주식종목코드,상장일자,공모가격(원)\n테스트,065370,2020-12-23,10000\n".encode()
        with self.assertRaises(HistoricalImportError) as caught:
            create_preview("generic.csv", generic, "u", self.market)
        self.assertEqual(caught.exception.code, "SOURCE_UNRECOGNIZED")

    def test_offering_amount_without_explicit_unit_is_not_converted(self):
        headers = [
            "회사명",
            "종목코드",
            "시장구분",
            "신규상장일",
            "공모가",
            "공모금액",
            "대표주관회사",
        ]
        result = create_preview(
            "KIND.xlsx",
            workbook_bytes(headers, [self.kind_row]),
            "u",
            self.market,
        )
        record = _PREVIEWS[result["preview_ticket"]]["candidates"][0]["record"]
        self.assertNotIn("offering_amount", record)
        self.assertIn("offering_amount_raw", record["sources"]["official_historical_import"])

    def test_non_new_listing_row_is_not_imported_as_ipo(self):
        row = list(self.krx_row)
        row[7] = "이전상장"
        result = self._preview_krx([row])
        self.assertEqual(result["summary"]["invalid"], 1)
        self.assertEqual(result["summary"]["new"], 0)
        self.assertEqual(result["issues"][0]["reason"], "NOT_NEW_LISTING")

    def test_spac_is_kept_but_separate_evaluation(self):
        row = list(self.krx_row)
        row[2] = "한국제17호기업인수목적"
        row[1] = "123456"
        row[9] = 2000
        result = self._preview_krx([row])
        record = _PREVIEWS[result["preview_ticket"]]["candidates"][0]["record"]
        self.assertEqual(record["listing_track"], "spac")
        self.assertNotIn("offer_band_high", record)

    def test_numeric_equivalent_existing_price_does_not_conflict(self):
        existing = {
            "schema_version": 1,
            "ipos": [
                {
                    "ipo_id": "old",
                    "company_name": "테스트 기업",
                    "stock_code": "065370",
                    "actual_listing_date": "2020-12-23",
                    "final_offer_price": 10000.0,
                    "sources": {},
                }
            ],
        }
        result = self._preview_krx(market=existing)
        self.assertEqual(result["summary"]["conflict"], 0)
        # The official provenance is still useful, so this is safely enrichable.
        self.assertEqual(result["summary"]["enrichable"], 1)

    def test_existing_nonblank_conflict_is_never_overwritten(self):
        existing = {
            "schema_version": 1,
            "ipos": [
                {
                    "ipo_id": "old",
                    "company_name": "테스트 기업",
                    "stock_code": "065370",
                    "actual_listing_date": "2020-12-24",
                    "final_offer_price": 10000,
                    "sources": {},
                }
            ],
        }
        result = self._preview_krx(market=existing)
        self.assertEqual(result["summary"]["conflict"], 1)
        self.assertEqual(result["summary"]["enrichable"], 0)

    def test_identical_duplicate_rows_are_deduplicated(self):
        result = self._preview_krx([self.krx_row, list(self.krx_row)])
        self.assertEqual(result["summary"]["new"], 1)
        self.assertEqual(result["summary"]["duplicate_rows"], 1)
        self.assertEqual(result["summary"]["review_required"], 0)
        self.assertEqual(len(_PREVIEWS[result["preview_ticket"]]["candidates"]), 1)

    def test_conflicting_duplicate_stock_code_blocks_entire_group(self):
        other = list(self.krx_row)
        other[9] = 12000
        result = self._preview_krx([self.krx_row, other])
        self.assertEqual(result["summary"]["new"], 0)
        self.assertEqual(result["summary"]["review_required"], 2)
        self.assertEqual(len(_PREVIEWS[result["preview_ticket"]]["candidates"]), 0)

    def test_preview_ticket_is_user_bound(self):
        result = self._preview_krx()
        with self.assertRaises(HistoricalImportError) as caught:
            commit_preview(result["preview_ticket"], "other")
        self.assertEqual(caught.exception.code, "PREVIEW_TICKET_INVALID")

    def test_commit_replays_classification_and_writes_atomically(self):
        result = self._preview_krx()
        written = {}

        def capture(value):
            written["market"] = deepcopy(value)

        with patch(
            "app.services.ipo.historical_import._read_market_store_unlocked",
            return_value=deepcopy(self.market),
        ), patch(
            "app.services.ipo.historical_import._write_market_store_unlocked",
            side_effect=capture,
        ):
            committed = commit_preview(result["preview_ticket"], "u")

        self.assertEqual(committed["committed_new"], 1)
        self.assertEqual(len(written["market"]["ipos"]), 1)
        self.assertNotIn(result["preview_ticket"], _PREVIEWS)

    def test_stale_preview_is_rejected(self):
        result = self._preview_krx()
        changed = {
            "schema_version": 1,
            "updated_at": "changed",
            "ipos": [
                {
                    "ipo_id": "other",
                    "company_name": "다른 기업",
                    "stock_code": "999999",
                    "actual_listing_date": "2020-01-01",
                    "final_offer_price": 5000,
                    "sources": {},
                }
            ],
        }
        with patch(
            "app.services.ipo.historical_import._read_market_store_unlocked",
            return_value=changed,
        ):
            with self.assertRaises(HistoricalImportError) as caught:
                commit_preview(result["preview_ticket"], "u")
        self.assertEqual(caught.exception.code, "PREVIEW_STALE")
        self.assertNotIn(result["preview_ticket"], _PREVIEWS)

    def test_actual_listing_only_official_record_is_listed_and_past(self):
        item = {
            "actual_listing_date": "2020-12-23",
            "sources": {"official_historical_import": {"source": SOURCE_KRX}},
        }
        self.assertEqual(
            derive_market_state(item, today=__import__("datetime").date(2021, 1, 1)),
            "LISTED",
        )
        self.assertEqual(derive_filter_group("LISTED", "NOT_APPLIED"), "PAST")

    def test_actual_listing_only_non_historical_record_keeps_old_fail_closed_contract(self):
        item = {"actual_listing_date": "2020-12-23"}
        self.assertEqual(
            derive_market_state(item, today=__import__("datetime").date(2021, 1, 1)),
            "DATE_UNKNOWN",
        )

    def test_future_actual_listing_official_record_fails_closed_in_presentation(self):
        item = {
            "actual_listing_date": "2030-01-01",
            "sources": {"official_historical_import": {"source": SOURCE_KRX}},
        }
        self.assertEqual(
            derive_market_state(item, today=__import__("datetime").date(2029, 1, 1)),
            "DATE_UNKNOWN",
        )


if __name__ == "__main__":
    unittest.main()
