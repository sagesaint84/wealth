from __future__ import annotations

import re
from typing import Any


class DartParserError(RuntimeError):
    """Raised when semantic parsing of DART document fails."""


def clean_text(s: str) -> str:
    if not s:
        return ""
    # Strip HTML/XML tags
    s = re.sub(r"<[^>]+>", " ", s)
    # Strip extra whitespace
    return re.sub(r"\s+", " ", s).strip()


def parse_number(s: Any) -> float | None:
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        return float(s)
    clean = re.sub(r"[^\d.\-]", "", str(s))
    if not clean or clean == "-":
        return None
    try:
        return float(clean)
    except ValueError:
        return None


def extract_tables(doc_text: str) -> list[str]:
    return re.findall(r"<table[^>]*>(.*?)</table>", doc_text, re.DOTALL | re.IGNORECASE)


def parse_table_to_matrix(table_html: str) -> list[list[str]]:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE)
    matrix = []
    for r in rows:
        cells = re.findall(r"<(?:td|th)[^>]*>(.*?)</(?:td|th)>", r, re.DOTALL | re.IGNORECASE)
        clean_cells = [clean_text(c) for c in cells]
        if clean_cells:
            matrix.append(clean_cells)
    return matrix


class DartSemanticParser:
    """Semantic parser for DART registration statements and prospectuses.

    Never relies on page numbers; uses semantic section and table header synonyms.
    """

    VERSION = "ipo-dart-v1"

    def parse_document(self, doc_text: str, rcept_no: str = "", source_date: str = "") -> dict[str, Any]:
        """Extract available IPO features from document text with provenance metadata."""
        features = {}

        # 1. Institutional competition ratio
        comp_ratio = self.extract_competition_ratio(doc_text)
        features["institutional_competition_ratio"] = self._wrap_feature(
            comp_ratio, rcept_no, source_date,
            confidence="high" if comp_ratio is not None else "missing"
        )

        # 2. Lockup commitment ratio (shares based)
        lockup_ratio = self.extract_lockup_commitment_ratio(doc_text)
        features["lockup_commitment_ratio"] = self._wrap_feature(
            lockup_ratio, rcept_no, source_date,
            confidence="high" if lockup_ratio is not None else "missing"
        )

        # 3. High bid ratio (band high or higher / specified price total)
        high_bid = self.extract_high_bid_ratio(doc_text)
        features["high_bid_ratio"] = self._wrap_feature(
            high_bid, rcept_no, source_date,
            confidence="high" if high_bid is not None else "missing"
        )

        # 4. Tradable share ratio
        tradable_ratio = self.extract_tradable_share_ratio(doc_text)
        features["tradable_share_ratio"] = self._wrap_feature(
            tradable_ratio, rcept_no, source_date,
            confidence="high" if tradable_ratio is not None else "missing"
        )

        # 5. Secondary sale ratio
        secondary_ratio = self.extract_secondary_sale_ratio(doc_text)
        features["secondary_sale_ratio"] = self._wrap_feature(
            secondary_ratio, rcept_no, source_date,
            confidence="high" if secondary_ratio is not None else "missing"
        )

        # 6. Unlock within 3 months ratio
        unlock_3m = self.extract_unlock_3m_ratio(doc_text)
        features["unlock_3m_ratio"] = self._wrap_feature(
            unlock_3m, rcept_no, source_date,
            confidence="high" if unlock_3m is not None else "missing"
        )

        # 7. Relative valuation
        val_info = self.extract_relative_valuation(doc_text)
        features["relative_valuation"] = self._wrap_feature(
            val_info.get("valuation_ratio"), rcept_no, source_date,
            confidence="high" if val_info.get("valuation_ratio") is not None else "missing",
            extra=val_info,
        )

        # 8. Financials: revenue cagr, operating margin, net debt to assets
        fin_info = self.extract_financial_ratios(doc_text)
        features["revenue_cagr"] = self._wrap_feature(
            fin_info.get("revenue_cagr"), rcept_no, source_date,
            confidence="high" if fin_info.get("revenue_cagr") is not None else "missing",
            extra={"revenue_history": fin_info.get("revenue_history")},
        )
        features["operating_margin"] = self._wrap_feature(
            fin_info.get("operating_margin"), rcept_no, source_date,
            confidence="high" if fin_info.get("operating_margin") is not None else "missing",
        )
        features["net_debt_to_assets"] = self._wrap_feature(
            fin_info.get("net_debt_to_assets"), rcept_no, source_date,
            confidence="high" if fin_info.get("net_debt_to_assets") is not None else "missing",
        )

        return features

    def extract_offer_band(self, text: str) -> tuple[float, float] | None:
        """Extract an explicitly labelled 희망공모가 range, never a fixed price.

        The pattern deliberately requires a public-offering-band label and a
        range connector.  Two arbitrary numbers elsewhere in a filing must not
        be promoted into canonical pricing inputs.
        """
        label = r"(?:희망\s*공모\s*(?:가액|가격)|공모\s*희망\s*(?:가액|가격))"
        number = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*원?"
        connector = r"(?:~|∼|\-|부터\s*|이상\s*)"
        match = re.search(label + r"[^\d]{0,40}" + number + r"\s*" + connector + r"\s*" + number, text)
        if match:
            return self._validated_offer_band(parse_number(match.group(1)), parse_number(match.group(2)))

        for table in extract_tables(text):
            matrix = parse_table_to_matrix(table)
            for row in matrix:
                row_text = " ".join(row)
                if not re.search(label, row_text):
                    continue
                values = [parse_number(cell) for cell in row]
                values = [value for value in values if value is not None]
                if len(values) >= 2:
                    return self._validated_offer_band(values[-2], values[-1])
        return None

    def extract_offer_band_from_structured(self, structured: dict[str, Any]) -> tuple[float, float] | None:
        """Use only explicitly named official structured fields before document text."""
        for group in ("general", "security_classes"):
            for row in structured.get(group, []) if isinstance(structured, dict) else []:
                if not isinstance(row, dict):
                    continue
                for key, value in row.items():
                    if not re.search(r"(?:희망.*공모.*(?:가액|가격)|offer[_ ]?band)", str(key), re.I):
                        continue
                    band = self.extract_offer_band(f"희망공모가액 {value}")
                    if band:
                        return band
        return None

    @staticmethod
    def _validated_offer_band(low: float | None, high: float | None) -> tuple[float, float] | None:
        if low is None or high is None or low <= 0 or high <= 0 or low > high:
            return None
        return (float(low), float(high))

    def _wrap_feature(
        self,
        value: Any,
        rcept_no: str,
        source_date: str,
        confidence: str = "high",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status = "ok" if value is not None else "missing"
        res = {
            "value": value,
            "status": status,
            "source": "dart_document",
            "rcept_no": rcept_no,
            "source_date": source_date,
            "parser_version": self.VERSION,
            "confidence": confidence if status == "ok" else "none",
        }
        if extra:
            res.update({k: v for k, v in extra.items() if k not in res})
        return res

    def extract_competition_ratio(self, text: str) -> float | None:
        """Extract competition ratio like '854.2 : 1' or from demand forecast table."""
        # Regex search for explicit ratio
        m = re.search(r"(?:기관투자자|수요예측)[^\n\r]{0,50}?경쟁률[^\d\n\r]{0,30}(\d+(?:,\d+)*(?:\.\d+)?)\s*:\s*1", text)
        if m:
            val = parse_number(m.group(1))
            if val is not None and val > 0:
                return round(val, 2)

        # Search tables for '수요예측' and '경쟁률'
        tables = extract_tables(text)
        for tbl in tables:
            if "수요예측" in tbl and "경쟁률" in tbl:
                mat = parse_table_to_matrix(tbl)
                for row in mat:
                    for i, c in enumerate(row):
                        if "경쟁률" in c and i + 1 < len(row):
                            val = parse_number(row[i + 1])
                            if val is not None and val > 0:
                                return round(val, 2)
        return None

    def extract_lockup_commitment_ratio(self, text: str) -> float | None:
        """Extract lockup commitment ratio: commitment requested shares / total requested shares * 100."""
        # Find tables with 의무보유확약 / 의무보유
        tables = extract_tables(text)
        for tbl in tables:
            if ("의무보유확약" in tbl or "확약신청" in tbl or "의무보유" in tbl) and ("수량" in tbl or "주식수" in tbl or "합계" in tbl):
                mat = parse_table_to_matrix(tbl)
                # Look for commitment shares vs uncommitted / total
                committed_shares = 0.0
                total_shares = 0.0
                has_commitment_rows = False

                for row in mat:
                    row_txt = " ".join(row)
                    if any(term in row_txt for term in ["6개월", "3개월", "1개월", "15일"]):
                        has_commitment_rows = True
                        for cell in reversed(row):
                            num = parse_number(cell)
                            if num is not None and num > 0:
                                committed_shares += num
                                break
                    elif "합계" in row_txt or "총계" in row_txt:
                        for cell in reversed(row):
                            num = parse_number(cell)
                            if num is not None and num > 0:
                                total_shares = max(total_shares, num)

                if has_commitment_rows and total_shares > 0:
                    ratio = (committed_shares / total_shares) * 100.0
                    return round(min(100.0, max(0.0, ratio)), 2)

        # Fallback: look for direct percentage in text
        m = re.search(r"의무보유\s*확약[^\d\n\r]{0,30}(\d+(?:\.\d+)?)\s*%", text)
        if m:
            val = parse_number(m.group(1))
            if val is not None:
                return round(min(100.0, max(0.0, val)), 2)

        return None

    def extract_high_bid_ratio(self, text: str) -> float | None:
        """Extract high bid ratio: requested shares at or above band high / specified price total * 100."""
        tables = extract_tables(text)
        for tbl in tables:
            if ("신청가격" in tbl or "가격대별" in tbl) and ("밴드" in tbl or "이상" in tbl or "상단" in tbl):
                mat = parse_table_to_matrix(tbl)
                # Find column index for quantity/shares (신청수량 or 수량) vs ratio (비율)
                qty_col_idx = None
                for row in mat:
                    for idx, c in enumerate(row):
                        if "신청수량" in c or (c == "수량") or ("주식수" in c):
                            qty_col_idx = idx
                            break
                    if qty_col_idx is not None:
                        break

                high_bid_shares = 0.0
                specified_shares = 0.0
                unspecified_shares = 0.0
                total_shares = 0.0

                for row in mat:
                    row_txt = " ".join(row)
                    # Extract number from qty_col_idx if available, else first valid number backwards before any '%' cell
                    target_num = None
                    if qty_col_idx is not None and qty_col_idx < len(row):
                        target_num = parse_number(row[qty_col_idx])
                    if target_num is None:
                        for cell in reversed(row):
                            if "%" in cell:
                                continue
                            num = parse_number(cell)
                            if num is not None and num > 0:
                                target_num = num
                                break

                    if target_num is not None:
                        # High end or above
                        if any(term in row_txt for term in ["상단 초과", "상단초과", "상단 이상", "상단이상", "밴드상단"]):
                            high_bid_shares += target_num
                        elif any(term in row_txt for term in ["가격미제시", "가격불문", "미제시"]):
                            unspecified_shares += target_num
                        elif "합계" in row_txt or "총계" in row_txt:
                            total_shares = max(total_shares, target_num)

                specified_shares = max(0.0, total_shares - unspecified_shares)
                # Rule: if specified shares is < 50% of total demand, high_bid_ratio is missing
                if total_shares > 0 and (specified_shares / total_shares) < 0.50:
                    return None

                if specified_shares > 0 and high_bid_shares > 0:
                    ratio = (high_bid_shares / specified_shares) * 100.0
                    return round(min(100.0, max(0.0, ratio)), 2)

        return None

    def extract_tradable_share_ratio(self, text: str) -> float | None:
        """Extract tradable share ratio: immediately tradable shares / post-offer total shares * 100."""
        tables = extract_tables(text)
        for tbl in tables:
            if ("유통가능" in tbl or "상장 직후" in tbl or "유통 가능" in tbl) and ("비율" in tbl or "%" in tbl or "주식수" in tbl):
                mat = parse_table_to_matrix(tbl)
                for row in mat:
                    row_txt = " ".join(row)
                    if any(term in row_txt for term in ["유통가능", "상장직후 유통가능", "유통 가능"]):
                        for cell in reversed(row):
                            num = parse_number(cell)
                            # If ratio is directly given (0~100)
                            if num is not None and 0.0 < num <= 100.0:
                                return round(num, 2)

        # Fallback: direct regex tolerating longer descriptive text before percentage
        m = re.search(r"유통\s*가능[^\n\r%]{0,100}?(\d+(?:\.\d+)?)\s*%", text)
        if m:
            val = parse_number(m.group(1))
            if val is not None and 0.0 < val <= 100.0:
                return round(val, 2)

        return None

    def extract_secondary_sale_ratio(self, text: str) -> float | None:
        """Extract secondary sale ratio: secondary shares / total offering shares * 100."""
        # Search tables for 구주매출 and 신주모집
        tables = extract_tables(text)
        for tbl in tables:
            if "구주매출" in tbl and ("신주모집" in tbl or "공모" in tbl):
                mat = parse_table_to_matrix(tbl)
                sec_shares = None
                total_offering = None

                for row in mat:
                    row_txt = " ".join(row)
                    if "구주매출" in row_txt:
                        for cell in reversed(row):
                            num = parse_number(cell)
                            if num is not None and num >= 0:
                                sec_shares = num
                                break
                    elif "합계" in row_txt or "공모" in row_txt:
                        for cell in reversed(row):
                            num = parse_number(cell)
                            if num is not None and num > 0:
                                total_offering = max(total_offering or 0, num)

                if sec_shares is not None and total_offering and total_offering > 0:
                    ratio = (sec_shares / total_offering) * 100.0
                    return round(min(100.0, max(0.0, ratio)), 2)

        # If text explicitly states "구주매출 없음" or "신주모집 100%" -> 0.0 (explicit zero)
        if "구주매출 없음" in text or "구주매출이 없" in text or "전량 신주모집" in text or "신주모집 100%" in text:
            return 0.0

        return None

    def extract_unlock_3m_ratio(self, text: str) -> float | None:
        """Extract unlock within 3 months ratio: shares unlocking within 3 months / post-offer shares * 100."""
        tables = extract_tables(text)
        for tbl in tables:
            # Exclude demand forecast commitment tables!
            if "확약" in tbl or "수요예측" in tbl:
                continue
            if ("의무보유" in tbl or "매각제한" in tbl or "보호예수" in tbl) and ("3개월" in tbl or "1개월" in tbl or "해제" in tbl):
                mat = parse_table_to_matrix(tbl)
                unlock_3m_shares = 0.0
                total_shares = 0.0

                qty_col = None
                for row in mat:
                    for idx, c in enumerate(row):
                        if "주식수" in c or "수량" in c:
                            qty_col = idx
                            break
                    if qty_col is not None:
                        break

                for row in mat:
                    row_txt = " ".join(row)
                    target_num = None
                    if qty_col is not None and qty_col < len(row):
                        target_num = parse_number(row[qty_col])
                    if target_num is None:
                        for cell in row:
                            num = parse_number(cell)
                            if num is not None and num > 0:
                                target_num = num
                                break

                    if target_num is not None:
                        if any(term in row_txt for term in ["1개월", "2개월", "3개월"]):
                            unlock_3m_shares += target_num
                        elif "상장예정" in row_txt or "발행주식총수" in row_txt or "합계" in row_txt:
                            total_shares = max(total_shares, target_num)

                if total_shares > 0 and unlock_3m_shares > 0:
                    ratio = (unlock_3m_shares / total_shares) * 100.0
                    return round(min(100.0, max(0.0, ratio)), 2)

        return None

    def extract_relative_valuation(self, text: str) -> dict[str, Any]:
        """Extract relative valuation method, issuer multiple, peer median multiple."""
        res: dict[str, Any] = {
            "valuation_method": None,
            "issuer_multiple": None,
            "peer_median_multiple": None,
            "valuation_ratio": None,
            "peer_count": None,
        }
        # Check method synonyms: PER, PSR, EV/EBITDA
        method = None
        if "PER" in text or "주가수익비율" in text:
            method = "PER"
        elif "EV/EBITDA" in text or "EV_EBITDA" in text:
            method = "EV_EBITDA"
        elif "PSR" in text or "주가매출비율" in text:
            method = "PSR"

        if not method:
            return res

        res["valuation_method"] = method

        # Look for peer average/median multiple
        m_peer = re.search(r"(?:유사회사의?\s*평균|비교기업\s*평균|적용\s*PER|적용\s*EV/EBITDA)[^\d\n\r]{0,30}(\d+(?:\.\d+)?)\s*배?", text)
        if m_peer:
            peer_mul = parse_number(m_peer.group(1))
            if peer_mul and peer_mul > 0:
                res["peer_median_multiple"] = round(peer_mul, 2)

        # Look for issuer multiple
        m_issuer = re.search(r"(?:당사\s*PER|공모가\s*기준\s*PER|평가\s*PER)[^\d\n\r]{0,30}(\d+(?:\.\d+)?)\s*배?", text)
        if m_issuer:
            iss_mul = parse_number(m_issuer.group(1))
            if iss_mul and iss_mul > 0:
                res["issuer_multiple"] = round(iss_mul, 2)

        if res["issuer_multiple"] and res["peer_median_multiple"]:
            ratio = res["issuer_multiple"] / res["peer_median_multiple"]
            res["valuation_ratio"] = round(ratio, 4)

        return res

    def extract_financial_ratios(self, text: str) -> dict[str, Any]:
        """Extract revenue CAGR (minimum 3 years required), operating margin, and net debt ratio."""
        res: dict[str, Any] = {
            "revenue_cagr": None,
            "revenue_history": [],
            "operating_margin": None,
            "net_debt_to_assets": None,
        }

        # Look for financial summary tables
        tables = extract_tables(text)
        for tbl in tables:
            if ("매출액" in tbl or "수익" in tbl) and ("영업이익" in tbl or "당기순이익" in tbl):
                mat = parse_table_to_matrix(tbl)
                revenues = []
                operating_income = None
                latest_revenue = None
                total_assets = None
                cash_equiv = 0.0
                interest_debt = 0.0

                for row in mat:
                    row_txt = " ".join(row)
                    if "매출액" in row_txt or "영업수익" in row_txt:
                        nums = [parse_number(c) for c in row if parse_number(c) is not None and parse_number(c) > 0]
                        if len(nums) >= 3:
                            revenues = nums
                            latest_revenue = nums[0]
                    elif "영업이익" in row_txt:
                        nums = [parse_number(c) for c in row if parse_number(c) is not None]
                        if nums:
                            operating_income = nums[0]
                    elif "자산총계" in row_txt:
                        nums = [parse_number(c) for c in row if parse_number(c) is not None and parse_number(c) > 0]
                        if nums:
                            total_assets = nums[0]
                    elif "현금및현금성자산" in row_txt:
                        nums = [parse_number(c) for c in row if parse_number(c) is not None and parse_number(c) >= 0]
                        if nums:
                            cash_equiv = nums[0]
                    elif any(k in row_txt for k in ["단기차입금", "장기차입금", "사채", "유동성장기부채"]):
                        nums = [parse_number(c) for c in row if parse_number(c) is not None and parse_number(c) >= 0]
                        if nums:
                            interest_debt += nums[0]

                # Revenue CAGR (must have at least 3 years)
                if len(revenues) >= 3:
                    rev_t = revenues[0]
                    rev_t_minus_2 = revenues[2]
                    if rev_t_minus_2 > 0:
                        cagr = (rev_t / rev_t_minus_2) ** 0.5 - 1.0
                        res["revenue_cagr"] = round(cagr * 100.0, 2)
                        res["revenue_history"] = revenues[:3]

                # Operating margin
                if latest_revenue and latest_revenue > 0 and operating_income is not None:
                    res["operating_margin"] = round((operating_income / latest_revenue) * 100.0, 2)

                # Net debt to assets
                if total_assets and total_assets > 0:
                    net_debt = interest_debt - cash_equiv
                    res["net_debt_to_assets"] = round((net_debt / total_assets) * 100.0, 2)

                if res["revenue_cagr"] is not None or res["operating_margin"] is not None:
                    break

        return res
