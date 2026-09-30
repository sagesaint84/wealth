from __future__ import annotations

import re
from typing import Any, Callable

from app.services.ipo.dart_parser import (
    DartSemanticParser as _BaseDartSemanticParser,
    extract_tables,
    parse_number,
    parse_table_to_matrix,
)


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


class AccurateDartSemanticParser(_BaseDartSemanticParser):
    """Accuracy overrides for real-world DART IPO table layouts."""

    VERSION = _BaseDartSemanticParser.VERSION

    def extract_competition_ratio(self, text: str) -> float | None:
        """Extract the total institutional demand competition ratio."""
        match = re.search(
            r"(?:기관투자자|수요예측)[^\n\r]{0,80}?경쟁률[^\d\n\r]{0,30}"
            r"(\d+(?:,\d+)*(?:\.\d+)?)\s*:\s*1",
            text,
        )
        if match:
            value = parse_number(match.group(1))
            if value is not None and value > 0:
                return round(value, 2)

        for table in extract_tables(text):
            if "경쟁률" not in table:
                continue
            matrix = parse_table_to_matrix(table)
            table_text = " ".join(" ".join(row) for row in matrix)
            has_demand_context = (
                "수요예측" in table
                or (
                    "합계" in table_text
                    and "기관투자자" in table_text
                    and "수량" in table_text
                )
            )
            if not has_demand_context:
                continue

            for row in matrix:
                if not any("경쟁률" in cell for cell in row):
                    continue
                values = [parse_number(cell) for cell in row[1:]]
                values = [value for value in values if value is not None and value > 0]
                if values:
                    return round(values[-1], 2)
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
        """Extract committed shares / total demand, rejecting partial tables."""
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

            committed_shares = 0.0
            total_shares = None
            has_commitment_rows = False

            for row in matrix:
                if not row:
                    continue
                label = _normalize_label(row[0])
                quantity = quantity_for(row)
                if any(term in label for term in commitment_terms):
                    if quantity is not None and quantity >= 0:
                        committed_shares += quantity
                        has_commitment_rows = True
                elif label in {"합계", "총계"}:
                    if quantity is not None and quantity > 0:
                        total_shares = quantity

            if (
                has_commitment_rows
                and total_shares is not None
                and total_shares > 0
                and 0 <= committed_shares <= total_shares
            ):
                return round((committed_shares / total_shares) * 100.0, 2)

        match = re.search(
            r"의무보유\s*확약(?:\s*신청)?\s*(?:비율|비중)"
            r"[^\d\n\r]{0,30}(\d+(?:\.\d+)?)\s*%",
            text,
        )
        if match:
            value = parse_number(match.group(1))
            if value is not None and 0.0 <= value <= 100.0:
                return round(value, 2)
        return None

    def extract_high_bid_ratio(self, text: str) -> float | None:
        """Extract at-or-above-band-high shares / specified-price shares."""
        for table in extract_tables(text):
            if ("신청가격" not in table and "가격대별" not in table) or (
                "밴드" not in table and "이상" not in table and "상단" not in table
            ):
                continue
            matrix = parse_table_to_matrix(table)
            high_bid_shares = 0.0
            unspecified_shares = 0.0
            total_shares = 0.0

            for row in matrix:
                if not row:
                    continue
                normalized = _normalize_label(" ".join(row))
                quantity = _largest_non_percent_number(row[1:])
                if quantity is None:
                    continue

                if any(term in normalized for term in ("가격미제시", "가격불문", "미제시")):
                    unspecified_shares += quantity
                elif (
                    "상단초과" in normalized
                    or "상단이상" in normalized
                    or "밴드상단" in normalized
                    or "(상단)" in normalized
                ):
                    high_bid_shares += quantity
                elif _normalize_label(row[0]) in {"합계", "총계"}:
                    total_shares = max(total_shares, quantity)

            specified_shares = max(0.0, total_shares - unspecified_shares)
            if total_shares > 0 and (specified_shares / total_shares) < 0.50:
                return None
            if specified_shares > 0 and high_bid_shares > 0:
                ratio = (high_bid_shares / specified_shares) * 100.0
                return round(min(100.0, max(0.0, ratio)), 2)
        return None

    def extract_tradable_share_ratio(self, text: str) -> float | None:
        """Extract the latest explicit immediately-tradable share ratio."""
        candidates: list[float] = []
        for table in extract_tables(text):
            if ("유통가능" in table or "상장 직후" in table or "유통 가능" in table) and (
                "비율" in table or "%" in table or "주식수" in table
            ):
                matrix = parse_table_to_matrix(table)
                for row in matrix:
                    row_text = " ".join(row)
                    if any(
                        term in row_text
                        for term in ("유통가능", "상장직후 유통가능", "유통 가능")
                    ):
                        for cell in reversed(row):
                            value = parse_number(cell)
                            if value is not None and 0.0 < value <= 100.0:
                                candidates.append(round(value, 2))
                                break
        if candidates:
            return candidates[-1]

        regex_candidates = [
            parse_number(match.group(1))
            for match in re.finditer(
                r"유통\s*가능[^\n\r%]{0,100}?(\d+(?:\.\d+)?)\s*%",
                text,
            )
        ]
        regex_candidates = [
            value
            for value in regex_candidates
            if value is not None and 0.0 < value <= 100.0
        ]
        return round(regex_candidates[-1], 2) if regex_candidates else None

    def extract_relative_valuation(self, text: str) -> dict[str, Any]:
        """Extract issuer/peer valuation ratio from direct multiples or price discount."""
        result: dict[str, Any] = {
            "valuation_method": None,
            "issuer_multiple": None,
            "peer_median_multiple": None,
            "valuation_ratio": None,
            "peer_count": None,
        }

        if "PER" in text or "주가수익비율" in text:
            result["valuation_method"] = "PER"
        elif "EV/EBITDA" in text or "EV_EBITDA" in text:
            result["valuation_method"] = "EV_EBITDA"
        elif "PSR" in text or "주가매출비율" in text:
            result["valuation_method"] = "PSR"
        else:
            return result

        peer_patterns = (
            r"유사(?:회사|회)?의?\s*평균\s*PER",
            r"비교기업\s*평균\s*PER",
            r"비교대상회사\s*PER",
            r"적용\s*PER",
            r"적용\s*EV/EBITDA",
        )
        for pattern in peer_patterns:
            match = re.search(
                pattern + r"[^\d\n\r]{0,30}(\d+(?:\.\d+)?)\s*배?",
                text,
            )
            if match:
                value = parse_number(match.group(1))
                if value is not None and value > 0:
                    result["peer_median_multiple"] = round(value, 2)
                    break

        issuer_patterns = (
            r"당사(?:의)?\s*공모가\s*기준\s*PER",
            r"공모가\s*기준\s*PER",
            r"당사\s*PER",
            r"평가\s*PER",
        )
        for pattern in issuer_patterns:
            match = re.search(
                pattern + r"[^\d\n\r]{0,30}(\d+(?:\.\d+)?)\s*배?",
                text,
            )
            if match:
                value = parse_number(match.group(1))
                if value is not None and value > 0:
                    result["issuer_multiple"] = round(value, 2)
                    break

        if result["issuer_multiple"] and result["peer_median_multiple"]:
            result["valuation_ratio"] = round(
                result["issuer_multiple"] / result["peer_median_multiple"],
                4,
            )
            return result

        eval_match = re.search(
            r"주당\s*평가가액[^\d\n\r]{0,30}"
            r"(\d{1,3}(?:,\d{3})+|\d+)\s*원",
            text,
        )
        final_match = re.search(
            r"(?:주당\s*확정공모가액|확정\s*주당\s*공모가액)"
            r"[^\d\n\r]{0,30}(\d{1,3}(?:,\d{3})+|\d+)\s*원",
            text,
        )
        eval_price = parse_number(eval_match.group(1)) if eval_match else None
        final_price = parse_number(final_match.group(1)) if final_match else None
        if eval_price and eval_price > 0 and final_price and final_price > 0:
            ratio = final_price / eval_price
            if 0 < ratio < 10:
                result["valuation_ratio"] = round(ratio, 4)
                if result["peer_median_multiple"]:
                    result["issuer_multiple"] = round(
                        result["peer_median_multiple"] * ratio,
                        2,
                    )
        return result
