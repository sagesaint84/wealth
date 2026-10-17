"""Structured parsing for OpenDART cash-dividend decision filings.

This parser is intentionally conservative.  A filing-title match is not enough:
`confirmed_amount` becomes true only when an ordinary-share per-share cash
amount is found in the original disclosure document.  Dates are returned only
when they are explicitly present in the filing; no payment date is inferred.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from html import unescape
from html.parser import HTMLParser
import math
import re
from typing import Any

PARSER_VERSION = "2026-09-26-a43-v1"


class _DisclosureTableParser(HTMLParser):
    _CELL_TAGS = {"td", "th", "te", "tu"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        tag = tag.lower()
        if tag == "tr":
            if self._row:
                self.rows.append(self._row)
            self._row = []
        elif tag in self._CELL_TAGS:
            if self._row is None:
                self._row = []
            self._cell_parts = []
        elif tag == "br" and self._cell_parts is not None:
            self._cell_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._CELL_TAGS and self._cell_parts is not None:
            text = " ".join("".join(self._cell_parts).split())
            if self._row is None:
                self._row = []
            self._row.append(text)
            self._cell_parts = None
        elif tag == "tr":
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell_parts = None

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def close(self) -> None:
        super().close()
        if self._row:
            self.rows.append(self._row)
            self._row = None


def _normalize(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _money(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "").replace("원", "")
    text = text.replace("₩", "").strip()
    if not text or text in {"-", "--", "해당없음", "없음"}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        number = float(match.group(0))
    except ValueError:
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _parse_date(value: object) -> str | None:
    text = str(value or "").strip()
    if not text or text in {"-", "--", "미정", "추후결정", "해당없음"}:
        return None
    match = re.search(
        r"(?P<y>20\d{2})\s*(?:[./-]|년)\s*(?P<m>\d{1,2})\s*(?:[./-]|월)\s*(?P<d>\d{1,2})\s*(?:일)?",
        text,
    )
    if not match:
        match = re.search(r"(?P<y>20\d{2})(?P<m>\d{2})(?P<d>\d{2})", text)
    if not match:
        return None
    try:
        parsed = date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
    except ValueError:
        return None
    return parsed.isoformat()


def _fallback_rows(markup: str) -> list[list[str]]:
    text = re.sub(r"(?i)</(?:td|th|te|tu)\s*>", "\t", markup)
    text = re.sub(r"(?i)</tr\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    rows: list[list[str]] = []
    for raw_row in unescape(text).splitlines():
        cells = [" ".join(cell.split()) for cell in raw_row.split("\t")]
        cells = [cell for cell in cells if cell]
        if cells:
            rows.append(cells)
    return rows


def _table_rows(markup: str) -> list[list[str]]:
    parser = _DisclosureTableParser()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:
        pass
    rows = [row for row in parser.rows if row]
    rows.extend(_fallback_rows(markup))
    deduped: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        key = tuple(row)
        if key and key not in seen:
            seen.add(key)
            deduped.append(row)
    return deduped


def _ordinary_cash_dps(rows: list[list[str]]) -> float | None:
    for row in rows:
        normalized = [_normalize(cell) for cell in row]
        if not any("1주당배당금" in cell or "주당배당금" in cell for cell in normalized):
            continue
        ordinary_indexes = [
            idx for idx, cell in enumerate(normalized)
            if "보통주" in cell or "ordinary" in cell
        ]
        if ordinary_indexes:
            for idx in ordinary_indexes:
                for cell in row[idx + 1 :]:
                    amount = _money(cell)
                    if amount is not None:
                        return amount
        # Some single-class issuers omit the stock-kind cell.  Accept the row
        # only when it does not mention a preferred/class share at all.
        if not any("우선주" in cell or "종류주" in cell for cell in normalized):
            label_index = next(
                (idx for idx, cell in enumerate(normalized) if "주당배당금" in cell),
                -1,
            )
            if label_index >= 0:
                for cell in row[label_index + 1 :]:
                    amount = _money(cell)
                    if amount is not None:
                        return amount
    return None


def _date_after_label(rows: list[list[str]], labels: tuple[str, ...]) -> str | None:
    normalized_labels = tuple(_normalize(label) for label in labels)
    for row in rows:
        normalized = [_normalize(cell) for cell in row]
        for idx, cell in enumerate(normalized):
            if not any(label in cell for label in normalized_labels):
                continue
            for value in row[idx + 1 :]:
                parsed = _parse_date(value)
                if parsed:
                    return parsed
    return None


def parse_dividend_decision_document(
    document_text: str,
    *,
    report_name: str,
    receipt_no: str,
    receipt_date: str = "",
    viewer_url: str = "",
    as_of: date | None = None,
) -> dict[str, Any]:
    """Parse one dividend-decision disclosure into structurally verified fields."""
    normalized_report = _normalize(report_name)
    base = {
        "report_name": report_name,
        "receipt_no": receipt_no,
        "receipt_date": receipt_date,
        "viewer_url": viewer_url,
        "parser_version": PARSER_VERSION,
        "structured_verification": False,
        "confirmed_amount": False,
        "confirmed_payment_date": False,
        "ordinary_cash_dps_krw": None,
        "record_date": None,
        "payment_date": None,
        "future_payment": None,
    }
    if "배당" not in normalized_report or "결정" not in normalized_report:
        return {**base, "reason": "not_dividend_decision_report"}
    if not isinstance(document_text, str) or not document_text.strip():
        return {**base, "reason": "empty_document"}

    rows = _table_rows(document_text)
    dps = _ordinary_cash_dps(rows)
    record_date = _date_after_label(rows, ("배당기준일",))
    payment_date = _date_after_label(
        rows,
        ("배당금지급예정일자", "배당금 지급 예정일자", "지급예정일자"),
    )
    if dps is None:
        return {
            **base,
            "record_date": record_date,
            "payment_date": payment_date,
            "confirmed_payment_date": payment_date is not None,
            "reason": "ordinary_cash_dps_not_structurally_verified",
        }

    future_payment: bool | None = None
    if payment_date and as_of:
        future_payment = date.fromisoformat(payment_date) >= as_of

    return {
        **base,
        "structured_verification": True,
        "confirmed_amount": True,
        "confirmed_payment_date": payment_date is not None,
        "ordinary_cash_dps_krw": dps,
        "record_date": record_date,
        "payment_date": payment_date,
        "future_payment": future_payment,
        "reason": None,
    }


COMPONENT_PARSER_VERSION = "2026-10-17-capital-a-v3"


def _component_money(value: str) -> Decimal | None:
    text = value.strip().removeprefix('₩').removesuffix('원').strip()
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', text) or len(text) > 48:
        return None
    try:
        amount = Decimal(text.replace(',', ''))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def _component_blocks(markup: str) -> list[tuple[list[list[str]], str]]:
    """Keep table boundaries and row order; never deduplicate across events.

    An explicit outside heading scopes subsequent tables, until another heading
    or section boundary. Nested/unbalanced tables are rejected by the caller.
    """
    # Some HTMLParser versions silently discard unknown marked sections. Their
    # contents cannot establish an event boundary; do not confirm such input.
    if re.search(r'<!\[(?!CDATA\[)', markup, flags=re.I):
        raise ValueError('Unsupported disclosure marked section')
    blocks = []
    section = ''
    for part in re.split(r'(<table\b[^>]*>.*?</table\s*>)', markup, flags=re.I | re.S):
        if re.match(r'<table\b', part, flags=re.I):
            parser = _DisclosureTableParser()
            parser.feed(part)
            parser.close()
            captions = [[caption_text] for caption in re.findall(
                r'<caption\b[^>]*>(.*?)</caption\s*>', part, flags=re.I | re.S)
                if (caption_text := ' '.join(unescape(re.sub(r'<[^>]+>', ' ', caption)).split()))]
            blocks.append((captions + parser.rows, section))
        else:
            # Preserve prose line boundaries, including adjacent HTML paragraphs.
            prose = re.sub(r'</(?:h[1-6]|p|div|section)\s*>|<br\s*/?>', '\n', part, flags=re.I)
            rows = _fallback_rows(prose)
            if rows:
                blocks.append((rows, section))
            for boundary in re.finditer(
                r'<h[1-6]\b[^>]*>(.*?)</h[1-6]\s*>|</?section\b[^>]*>', part, flags=re.I | re.S):
                section = (' '.join(unescape(re.sub(r'<[^>]+>', ' ', boundary[1])).split())
                           if boundary[1] is not None else '')
    return blocks


def _component_scope(rows: list[list[str]], section: str) -> dict[str, set[str]]:
    """Explicit round/period identifiers establish identity; dates only constrain it."""
    scope: dict[str, set[str]] = {key: set() for key in (
        'round', 'period', 'year', 'record_date', 'payment_date')}
    for text in [section, *(' '.join(row) for row in rows)]:
        norm = _normalize(text)
        scope['round'].update(re.findall(r'(?:제)?(\d+)(?:차|회)(?:현금|중간|결산|기말|감액)?(?:배당|지급)', norm))
        scope['round'].update(re.findall(r'(?:배당|지급)(?:회차|차수)[:：]?(?:제)?(\d+)(?:차|회)?', norm))
        scope['period'].update(re.findall(r'([1-4]분기|상반기|하반기|중간|결산|기말)(?:배당|지급)', norm))
        scope['year'].update(re.findall(r'(20\d{2})년', norm))
        labels = list(re.finditer(r'배당기준일|(?:배당금)?지급예정일(?:자)?', norm))
        for position, label in enumerate(labels):
            end = labels[position + 1].start() if position + 1 < len(labels) else len(norm)
            day = _parse_date(norm[label.end():end])
            if day:
                key = 'record_date' if label[0] == '배당기준일' else 'payment_date'
                scope[key].add(day)
    return scope


def _component_single_event(scopes: list[tuple[dict[str, set[str]], bool]]) -> bool:
    """Do not collapse a multi-event/ambiguous document into one dividend."""
    if not scopes:
        return True
    combined = {key: set(values) for key, values in scopes[0][0].items()}
    if any(len(values) > 1 for values in combined.values()):
        return False
    for scope, reference in scopes[1:]:
        if any(len(combined[key] | values) > 1 for key, values in scope.items()):
            return False
        explicit_identity = bool(scope['round'] or scope['period'])
        same_identity = explicit_identity and all(
            scope[key] == combined[key] for key in ('round', 'period', 'year'))
        # A bare table, equal amount or equal date is not a cross-table link.
        if not same_identity and not (reference and not explicit_identity):
            return False
        for key, values in scope.items():
            combined[key].update(values)
    return True


def _component_evidence(
    text: str, *, index: int, key: str, raw: str,
    role_span: tuple[int, int] | None, amount_span: tuple[int, int] | None,
) -> dict[str, Any]:
    """Spans index the returned contiguous quote of the normalized row text.

    Never search for another equal number. If a role and its amount cannot both
    fit, retain the amount window and omit the out-of-window role span.
    """
    def valid(span: tuple[int, int] | None) -> bool:
        return span is not None and 0 <= span[0] < span[1] <= len(text)

    amount_valid = valid(amount_span) and text[slice(*amount_span)] == raw
    start = 0
    if amount_valid:
        first, last = amount_span
        if valid(role_span) and max(last, role_span[1]) - min(first, role_span[0]) <= 320:
            first, last = min(first, role_span[0]), max(last, role_span[1])
        start = max(0, last - 320)
        start = min(start, first)
    quote = text[start:start + 320]
    evidence = {'row_index': index, 'role': key, 'text': quote}
    if amount_valid and amount_span[1] - start <= len(quote):
        evidence['amount_span'] = [amount_span[0] - start, amount_span[1] - start]
        if valid(role_span) and start <= role_span[0] < role_span[1] <= start + len(quote):
            evidence['role_span'] = [role_span[0] - start, role_span[1] - start]
    return evidence


def parse_dividend_payment_components(
    document_text: str, *, report_name: str, share_class: str = 'ordinary',
) -> dict[str, Any]:
    """Evidence only. Never changes the legacy parser or determines investor tax.

    Accept labelled per-share component rows or explicitly scoped payout notes.
    Unlabelled examples, mixed share-class notes and reserve approvals fail closed.
    Decimal values are emitted as strings; null never means a confirmed zero.
    Multiple unlinked events return unverified/not_evaluated, with no aggregated
    amounts. Evidence spans are relative to each returned quote, not HTML bytes.
    """
    components = dict(total_cash_dps_krw=None, disclosed_regular_dps_krw=None,
        disclosed_capital_reduction_dps_krw=None, unclassified_dps_krw=None,
        share_class=share_class, amount_status='insufficient_evidence',
        reconciliation_status='not_evaluated', reserve_description=None,
        evidence_locations=[], parser_version=COMPONENT_PARSER_VERSION)
    result = {'payment_components': components, 'tax_assessment': {
        'status': 'not_assessed', 'excluded_income_amount_krw': None,
        'withholding_adjustment_krw': None}}
    if share_class not in {'ordinary', 'preferred'}:
        raise ValueError('Unsupported share class')
    if not isinstance(document_text, str) or len(document_text) > 200_000:
        return result
    title = _normalize(report_name)
    if '배당' not in title or '결정' not in title:
        return result
    rows = _table_rows(document_text)
    wanted = '보통' if share_class == 'ordinary' else '종류'
    other = '종류' if share_class == 'ordinary' else '보통'
    mixed = any('보통' in ''.join(row) for row in rows) and any(
        '종류' in ''.join(row) or '우선' in ''.join(row) for row in rows)
    values: dict[str, set[Decimal]] = {key: set() for key in ('total', 'regular', 'capital')}
    invalid = False
    active_scopes: set[int] = set()
    role_pattern = r'(?P<regular>(?:일반(?:\s*이익)?|이익|정기)\s*배당)|(?P<capital>감액\s*배당)'
    excluded_contexts = (
        '지급하지', '미지급', '지급취소', '배당취소', '지급안함', '지급되지', '해당없',
        '과거지급', '과거배당', '지난배당', '지난해배당', '전년도배당',
        '이전배당', '이전회차', '다른회차', '다른지급회차', '다른분기',
        '조건부', '승인대기', '승인전', '승인되지', '승인될경우',
        '승인되는경우', '승인된경우에만', '충족되지',
    )

    def record(key: str, raw: str, index: int, text: str,
               role_span: tuple[int, int] | None = None,
               amount_span: tuple[int, int] | None = None) -> None:
        nonlocal invalid
        amount = _component_money(raw)
        if amount is None:
            invalid = True
            return
        values[key].add(amount)
        active_scopes.add(row_scopes[index])
        evidence = _component_evidence(text, index=index, key=key, raw=raw,
            role_span=role_span, amount_span=amount_span)
        components['evidence_locations'].append(evidence)
        if key == 'capital' and '자본준비금' in text:
            components['reserve_description'] = evidence['text']

    # Keep heading scope within each explicit table. A denied/past/conditional
    # table must not contaminate another table containing the current payout.
    tables = re.findall(r'<table\b[^>]*>.*?</table\s*>', document_text, flags=re.I | re.S)
    if (len(re.findall(r'<table\b', document_text, flags=re.I)) != len(tables)
            or len(re.findall(r'</table\s*>', document_text, flags=re.I)) != len(tables)):
        components['amount_status'] = 'unverified'
        return result
    scoped_rows = []
    row_scopes = []
    scopes = []
    try:
        blocks = _component_blocks(document_text)
    except (AssertionError, ValueError):
        components['amount_status'] = 'unverified'
        return result
    for block_rows, section in blocks:
        blocked = False
        accepted_rows = []
        for row in block_rows:
            heading = _normalize(' '.join(row))
            if (any(marker in heading for marker in excluded_contexts)
                    and not re.search(role_pattern, ' '.join(row))
                    and '주당배당금' not in heading
                    and ('배당' in heading or '지급' in heading)):
                blocked = True
            if not blocked:
                accepted_rows.append(row)
        scope_index = len(scopes)
        scopes.append((_component_scope(accepted_rows, section), any(
            re.search(r'상기(?:배당|1주당|주당)', _normalize(' '.join(row))) for row in accepted_rows)))
        scoped_rows.extend(accepted_rows)
        row_scopes.extend([scope_index] * len(accepted_rows))

    for index, row in enumerate(scoped_rows):
        text = ' '.join(row)
        norm = _normalize(text)
        if any(word in norm for word in ('예시', '타사', '가정', '과거사례', *excluded_contexts)):
            continue
        has_wanted = wanted in norm or (share_class == 'preferred' and '우선' in norm)
        has_other = other in norm or (share_class == 'ordinary' and '우선' in norm)
        if has_other and (not has_wanted or mixed):
            continue
        if mixed and not has_wanted:
            continue
        if share_class == 'preferred' and not has_wanted:
            continue
        if '주당배당금' in norm and '감액배당' not in norm and '이익배당' not in norm and '일반배당' not in norm:
            # Total comes only from a labelled stock-kind row, not arbitrary notes.
            labels = [i for i, cell in enumerate(row) if '주당배당금' in _normalize(cell)]
            if labels:
                candidates = [(i, cell) for i, cell in enumerate(row) if i > labels[0]
                              and _normalize(cell) not in {'보통주식', '보통주', '종류주식', '우선주식', '우선주'}]
                if len(candidates) == 1:
                    # Keep the original cell position; repeated equal numbers
                    # elsewhere in the row must never move this amount span.
                    cell_index, raw = candidates[0]
                    start = sum(len(cell) + 1 for cell in row[:cell_index])
                    label_start = sum(len(cell) + 1 for cell in row[:labels[0]])
                    record('total', raw, index, text,
                        (label_start, label_start + len(row[labels[0]])), (start, start + len(raw)))

    for index, row in enumerate(scoped_rows):
        text = ' '.join(row); norm = _normalize(text)
        if any(word in norm for word in ('예시', '타사', '가정', '과거사례')):
            continue
        has_wanted = wanted in norm or (share_class == 'preferred' and '우선' in norm)
        if ((other in norm or (share_class == 'ordinary' and '우선' in norm)) and not has_wanted) or (mixed and not has_wanted):
            continue
        if mixed and has_wanted and (other in norm or (share_class == 'ordinary' and '우선' in norm)):
            continue
        if share_class == 'preferred' and not has_wanted:
            continue
        # Scope exclusions to the candidate row. An unrelated denied payment
        # elsewhere in the disclosure must not invalidate a positive payout row.
        if any(marker in norm for marker in excluded_contexts):
            continue
        roles = list(re.finditer(role_pattern, text))
        if not roles or not ('주당' in norm or '1주당' in norm):
            continue
        # A component table must have exactly one role and one separate value
        # cell. Never assign the final cell to every role in a combined label.
        if (len(row) == 2 and len(roles) == 1
                and re.search(role_pattern, row[0]) and ('주당' in row[0] or '1주' in row[0])):
            role = roles[0]
            start = len(row[0]) + 1
            record(role.lastgroup, row[1], index, text, role.span(), (start, len(text)))
            continue
        # Pair each narrative role with the immediately following amount, before
        # another role starts. A shared or unexplained value makes the row unsafe.
        pairs = []
        for position, role in enumerate(roles):
            end = roles[position + 1].start() if position + 1 < len(roles) else len(text)
            segment = text[role.end():end]
            match = re.match(r'\s*[:：]?\s*([^\s()+]+?)\s*원', segment)
            if not match:
                pairs = []
                break
            amount_start = role.end() + match.start(1)
            amount_end = role.end() + match.end(1)
            # Extra currency amounts in the same role segment have no reliable
            # association (e.g. a slash-separated list of two unexplained values).
            if re.search(r'(?:\d|NaN|Infinity)[^\s]*\s*원', segment[match.end():]):
                pairs = []
                break
            pairs.append((role.lastgroup, match[1], role.span(), (amount_start, amount_end)))
        spans = [pair[3] for pair in pairs]
        if len(spans) != len(set(spans)):
            continue
        for key, raw, role_span, amount_span in pairs:
            record(key, raw, index, text, role_span, amount_span)

    if invalid or any(len(items) > 1 for items in values.values()):
        components['amount_status'] = 'unverified'
        components['reconciliation_status'] = 'inconsistent' if any(len(items) > 1 for items in values.values()) else 'invalid_amount'
        return result
    if not _component_single_event([scopes[index] for index in sorted(active_scopes)]):
        components.update(amount_status='unverified', reserve_description=None)
        return result
    total, regular, capital = [next(iter(values[key]), None) for key in ('total', 'regular', 'capital')]
    components.update(total_cash_dps_krw=_decimal_text(total),
        disclosed_regular_dps_krw=_decimal_text(regular),
        disclosed_capital_reduction_dps_krw=_decimal_text(capital))
    if total is None or (regular is None and capital is None):
        return result
    with localcontext() as context:
        context.prec = 100
        known = sum((value for value in (regular, capital) if value is not None), Decimal(0))
        if known > total or (regular is not None and capital is not None and known != total):
            components.update(amount_status='unverified', reconciliation_status='inconsistent')
        else:
            components['unclassified_dps_krw'] = _decimal_text(total - known)
            complete = regular is not None and capital is not None
            components.update(amount_status='verified' if complete else 'partial',
                              reconciliation_status='matched' if known == total else 'partial')
    return result


__all__ = ["PARSER_VERSION", "parse_dividend_decision_document", "parse_dividend_payment_components"]
