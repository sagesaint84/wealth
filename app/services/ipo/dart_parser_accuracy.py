from __future__ import annotations

import re
from typing import Any, Callable, Iterator

from app.services.ipo.dart_parser import (
    DartSemanticParser as _BaseDartSemanticParser,
    clean_text,
    extract_tables,
    parse_number,
    parse_table_to_matrix,
)


_TABLE_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.IGNORECASE | re.DOTALL)
_NUMBER_TOKEN = r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)"


def _normalize_label(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _largest_non_percent_number(cells: list[str]) -> float | None:
    numbers: list[float] = []
    for cell in cells:
        if "%" in cell:
            continue
        num = parse_number(cell)
        if num is not None and num >= 0:
            numbers.append(num)
    return max(numbers) if numbers else None


def _number_before_unit(value: str, unit_pattern: str) -> float | None:
    match = re.search(_NUMBER_TOKEN + rf"\s*{unit_pattern}", value or "", re.IGNORECASE)
    if not match:
        return None
    return parse_number(match.group(1))


def _ranked_tables(text: str) -> Iterator[tuple[str, int, int]]:
    """Yield tables with an amendment rank.

    DART correction filings often place the current disclosure before a later
    ``정정 전`` block.  A raw "first/last number wins" rule therefore promotes
    stale values.  Prefer ``정정 후`` (2), then neutral/current text (1), and
    reject ``정정 전`` (0) when a better candidate exists.
    """

    amendment_rank = 1
    cursor = 0
    for index, match in enumerate(_TABLE_RE.finditer(text)):
        between = clean_text(text[cursor : match.start()])
        before_pos = between.rfind("정정 전")
        after_pos = between.rfind("정정 후")
        if before_pos >= 0 or after_pos >= 0:
            amendment_rank = 2 if after_pos > before_pos else 0
        yield match.group(0), amendment_rank, index
        cursor = match.end()


def _best_value(candidates: list[tuple[int, int, float]]) -> float | None:
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


class AccurateDartSemanticParser(_BaseDartSemanticParser):
    """Accuracy overrides for real-world DART IPO table layouts."""

    VERSION = _BaseDartSemanticParser.VERSION

    def extract_competition_ratio(self, text: str) -> float | None:
        """Extract the authoritative total institutional demand competition ratio."""

        def plausible(value: float | None) -> bool:
            return value is not None and 0.0 < value <= 10000.0

        def numeric_tokens(value: object) -> list[float]:
            raw = clean_text(str(value or ""))
            pattern = (
                r"(?<![\d,])"
                r"(?:\d{1,3}(?:,\d{3})+|\d+)"
                r"(?:\.\d+)?"
                r"(?![\d,])"
            )
            values: list[float] = []
            for token in re.findall(pattern, raw):
                try:
                    values.append(float(token.replace(",", "")))
                except ValueError:
                    continue
            return values

        # Explicit prose: "기관투자자 경쟁률 1,097.62 : 1"
        match = re.search(
            r"(?:기관투자자|수요예측)[^\n\r]{0,80}?경쟁률[^\d\n\r]{0,40}"
            r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*:\s*1",
            text,
        )
        if match:
            value = parse_number(match.group(1))
            if plausible(value):
                return round(float(value), 2)

        # Wide DART result tables contain one ratio per investor group and
        # the authoritative overall ratio in the final total column.
        for table in extract_tables(text):
            if "경쟁률" not in table:
                continue

            matrix = parse_table_to_matrix(table)
            if not matrix:
                continue

            normalized_rows = [
                [_normalize_label(cell) for cell in row]
                for row in matrix
            ]

            has_quantity_context = any(
                any(
                    "신청수량" in cell
                    or cell in {"수량", "참여수량"}
                    for cell in row
                )
                for row in normalized_rows
            )

            has_total_context = any(
                any(
                    cell in {"합계", "총계", "계"}
                    or cell.endswith("합계")
                    or cell.endswith("총계")
                    for cell in row
                )
                for row in normalized_rows
            )

            has_demand_context = (
                "수요예측" in table
                or "기관투자자" in table
                or (has_quantity_context and has_total_context)
            )

            if not has_demand_context:
                continue

            for row in matrix:
                label_idx = next(
                    (
                        idx
                        for idx, cell in enumerate(row)
                        if _normalize_label(cell).startswith("경쟁률")
                    ),
                    None,
                )
                if label_idx is None:
                    continue

                values: list[float] = []
                for cell in row[label_idx + 1:]:
                    values.extend(numeric_tokens(cell))

                valid = [value for value in values if plausible(value)]
                if valid:
                    return round(valid[-1], 2)

        return None

    @staticmethod
    def _lockup_quantity_extractor(
        matrix: list[list[str]],
    ) -> Callable[[list[str]], float | None] | None:
        header_rows = matrix[:3]
        header_text = " ".join(" ".join(row) for row in header_rows)

        if "신청가격" in header_text:
            has_total_group = any(
                _normalize_label(cell) in {"합계", "총계"}
                for row in header_rows
                for cell in row
            )
            if not has_total_group:
                return None

            def from_total_triplet(row: list[str]) -> float | None:
                if len(row) < 3:
                    return None
                return parse_number(row[-2])

            return from_total_triplet

        qty_idx = None
        for row in header_rows:
            for idx, cell in enumerate(row):
                normalized = _normalize_label(cell)
                if "신청수량" in normalized or normalized in {"수량", "주식수"}:
                    qty_idx = idx
                    break
            if qty_idx is not None:
                break
        if qty_idx is None:
            return None

        def from_column(row: list[str]) -> float | None:
            if qty_idx >= len(row):
                return None
            return parse_number(row[qty_idx])

        return from_column

    def extract_lockup_commitment_ratio(self, text: str) -> float | None:
        """Extract committed requested shares / total requested shares."""

        commitment_terms = ("6개월", "3개월", "1개월", "15일")

        for table in extract_tables(text):
            if not any(
                term in table
                for term in ("의무보유확약", "확약신청", "의무보유", "미확약")
            ):
                continue

            matrix = parse_table_to_matrix(table)
            if not matrix:
                continue

            quantity_for = self._lockup_quantity_extractor(matrix)
            if quantity_for is None:
                continue

            committed_quantities: list[float] = []
            uncommitted_quantities: list[float] = []
            total_quantities: list[float] = []

            for row in matrix:
                if not row:
                    continue

                label = _normalize_label(row[0])
                quantity = quantity_for(row)

                if quantity is None or quantity < 0:
                    continue

                if any(term in label for term in commitment_terms):
                    committed_quantities.append(quantity)

                elif "미확약" in label:
                    uncommitted_quantities.append(quantity)

                elif (
                    label in {"계", "합계", "총계"}
                    or label.endswith("합계")
                    or label.endswith("총계")
                ):
                    total_quantities.append(quantity)

            # Preferred for real wide DART tables:
            # committed = total demand - uncommitted demand.
            #
            # This is robust even when commitment-period rows are split over
            # several investor categories.
            if (
                committed_quantities
                and uncommitted_quantities
                and total_quantities
            ):
                total_shares = max(total_quantities)
                uncommitted_shares = max(uncommitted_quantities)

                if (
                    total_shares > 0
                    and 0 <= uncommitted_shares <= total_shares
                ):
                    committed_shares = total_shares - uncommitted_shares
                    ratio = committed_shares / total_shares * 100.0
                    return round(
                        min(100.0, max(0.0, ratio)),
                        2,
                    )

            # Legacy/simple table fallback.
            if committed_quantities and total_quantities:
                total_shares = max(total_quantities)
                committed_shares = sum(committed_quantities)

                if (
                    total_shares > 0
                    and 0 <= committed_shares <= total_shares
                ):
                    ratio = committed_shares / total_shares * 100.0
                    return round(
                        min(100.0, max(0.0, ratio)),
                        2,
                    )

        # Only accept an explicitly labelled result percentage.
        match = re.search(
            r"(?:의무보유\s*확약(?:\s*신청)?\s*(?:비율|비중|률)|확약\s*비율)"
            r"[^\d\n\r]{0,30}"
            r"(\d+(?:\.\d+)?)\s*%",
            text,
        )
        if match:
            value = parse_number(match.group(1))
            if value is not None and 0.0 <= value <= 100.0:
                return round(value, 2)

        return None

    def extract_high_bid_ratio(self, text: str) -> float | None:
        """Extract at-or-above-band-high shares / specified-price shares.

        Real DART filings often put the ``수요예측 신청가격 분포`` heading in
        a paragraph *before* the table, so table qualification is based on the
        semantic row labels rather than requiring that heading inside <table>.
        """

        candidates: list[tuple[int, int, float]] = []
        for table, rank, index in _ranked_tables(text):
            matrix = parse_table_to_matrix(table)
            if not matrix:
                continue

            labels = [_normalize_label(row[0]) for row in matrix if row]
            has_unspecified = any(
                any(term in label for term in ("가격미제시", "가격불문", "미제시"))
                for label in labels
            )
            has_band_high = any("상단" in label for label in labels)
            has_total = any(label in {"합계", "총계"} for label in labels)
            if not (has_unspecified and has_band_high and has_total):
                continue

            high_bid_shares = 0.0
            unspecified_shares = 0.0
            total_shares = 0.0

            for row in matrix:
                if not row:
                    continue
                label = _normalize_label(row[0])
                quantity = _largest_non_percent_number(row[1:])
                if quantity is None:
                    continue

                if any(term in label for term in ("가격미제시", "가격불문", "미제시")):
                    unspecified_shares += quantity
                elif "상단" in label and "하단" not in label:
                    high_bid_shares += quantity
                elif label in {"합계", "총계"}:
                    total_shares = max(total_shares, quantity)

            specified_shares = max(0.0, total_shares - unspecified_shares)
            if total_shares <= 0 or specified_shares <= 0 or high_bid_shares <= 0:
                continue
            if (specified_shares / total_shares) < 0.50:
                continue

            ratio = (high_bid_shares / specified_shares) * 100.0
            candidates.append(
                (rank, index, round(min(100.0, max(0.0, ratio)), 2))
            )

        return _best_value(candidates)

    def extract_tradable_share_ratio(self, text: str) -> float | None:
        """Extract the current immediately-tradable ratio from explicit prose."""

        candidates: list[tuple[int, int, float]] = []
        patterns = (
            re.compile(
                r"상장(?:예정)?주식수[^%]{0,180}?중\s*"
                r"(\d+(?:\.\d+)?)\s*%[^.]{0,220}?"
                r"상장\s*직후\s*유통\s*가능"
            ),
            re.compile(
                r"상장\s*직후\s*유통\s*가능[^%]{0,180}?"
                r"(\d+(?:\.\d+)?)\s*%"
            ),
            re.compile(
                r"(\d+(?:\.\d+)?)\s*%[^.]{0,140}?"
                r"상장\s*직후\s*유통\s*가능"
            ),
        )

        for table, rank, index in _ranked_tables(text):
            table_text = clean_text(table)
            if "유통" not in table_text or "상장" not in table_text:
                continue
            for pattern in patterns:
                match = pattern.search(table_text)
                if not match:
                    continue
                value = parse_number(match.group(1))
                if value is not None and 0.0 < value <= 100.0:
                    candidates.append((rank, index, round(value, 2)))
                    break

        if candidates:
            return _best_value(candidates)

        clean_doc = clean_text(text)
        for pattern in patterns:
            values = [
                parse_number(match.group(1))
                for match in pattern.finditer(clean_doc)
            ]
            values = [
                value for value in values if value is not None and 0.0 < value <= 100.0
            ]
            if values:
                return round(values[0], 2)
        return None

    @staticmethod
    def _table_valuation_fields(matrix: list[list[str]]) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "method": None,
            "peer_multiple": None,
            "issuer_multiple": None,
            "evaluation_price": None,
            "offer_price": None,
        }

        for row in matrix:
            if not row:
                continue
            row_text = " ".join(row)
            normalized = _normalize_label(row_text)

            if "평가모형" in normalized:
                if "PER" in row_text:
                    fields["method"] = "PER"
                elif "EV/EBITDA" in row_text or "EV_EBITDA" in row_text:
                    fields["method"] = "EV_EBITDA"
                elif "PSR" in row_text:
                    fields["method"] = "PSR"

            if (
                ("비교대상회사" in normalized and "PER" in row_text)
                or "비교기업평균PER" in normalized
                or "유사회사평균PER" in normalized
                or "적용PER" in normalized
            ):
                for cell in row[1:]:
                    value = _number_before_unit(cell, r"배")
                    if value is not None and value > 0:
                        fields["peer_multiple"] = round(value, 2)
                        break

            if any(
                label in normalized
                for label in ("당사PER", "공모가기준PER", "평가PER")
            ):
                for cell in row[1:]:
                    value = _number_before_unit(cell, r"배")
                    if value is not None and value > 0:
                        fields["issuer_multiple"] = round(value, 2)
                        break

            if "주당평가가액" in normalized:
                for cell in row[1:]:
                    value = _number_before_unit(cell, r"원")
                    if value is not None and value > 0:
                        fields["evaluation_price"] = value
                        break

            if any(
                label in normalized
                for label in ("주당확정공모가액", "확정주당공모가액", "공모가산정결과")
            ):
                for cell in row[1:]:
                    value = _number_before_unit(cell, r"원")
                    if value is not None and value > 0:
                        fields["offer_price"] = value
                        break

        return fields

    def extract_relative_valuation(self, text: str) -> dict[str, Any]:
        """Extract valuation from semantic table rows, avoiding raw HTML digits."""

        result: dict[str, Any] = {
            "valuation_method": None,
            "issuer_multiple": None,
            "peer_median_multiple": None,
            "valuation_ratio": None,
            "peer_count": None,
        }

        summaries: list[tuple[int, int, dict[str, Any]]] = []
        explicit_offer_prices: list[tuple[int, int, float]] = []

        for table, rank, index in _ranked_tables(text):
            matrix = parse_table_to_matrix(table)
            if not matrix:
                continue
            fields = self._table_valuation_fields(matrix)
            table_text = _normalize_label(" ".join(" ".join(row) for row in matrix))

            if (
                fields["evaluation_price"] is not None
                and (
                    fields["peer_multiple"] is not None
                    or "평가모형" in table_text
                    or "상대가치" in table_text
                )
            ):
                summaries.append((rank, index, fields))

            if fields["offer_price"] is not None and any(
                label in table_text
                for label in ("주당확정공모가액", "확정주당공모가액")
            ):
                explicit_offer_prices.append((rank, index, fields["offer_price"]))

        if not summaries:
            return super().extract_relative_valuation(text)

        _, _, fields = max(summaries, key=lambda item: (item[0], item[1]))
        method = fields.get("method")
        if method is None:
            method = "PER" if fields.get("peer_multiple") is not None else None

        result["valuation_method"] = method
        result["peer_median_multiple"] = fields.get("peer_multiple")
        result["issuer_multiple"] = fields.get("issuer_multiple")

        offer_price = _best_value(explicit_offer_prices)
        if offer_price is None:
            offer_price = fields.get("offer_price")
        evaluation_price = fields.get("evaluation_price")

        if (
            offer_price is not None
            and evaluation_price is not None
            and offer_price > 0
            and evaluation_price > 0
        ):
            ratio = offer_price / evaluation_price
            if 0 < ratio < 10:
                result["valuation_ratio"] = round(ratio, 4)
                if result["peer_median_multiple"]:
                    result["issuer_multiple"] = round(
                        result["peer_median_multiple"] * ratio,
                        2,
                    )
                return result

        if result["issuer_multiple"] and result["peer_median_multiple"]:
            result["valuation_ratio"] = round(
                result["issuer_multiple"] / result["peer_median_multiple"],
                4,
            )
        return result
