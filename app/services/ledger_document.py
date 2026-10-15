"""Read-only ledger candidate parser and disposable offline decoder entrypoint."""
import csv
import io
import json
import math
import os
import re
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.services.document_extraction import command, extract_pages, set_worker_limits

DATE = re.compile(r'(?<!\d)(20\d{2})[./-](\d{1,2})[./-](\d{1,2})(?!\d)')
KOREAN_DATE = re.compile(r'(?<!\d)(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일')
MONTH_DAY = re.compile(r'^\s*(\d{1,2})[ \t]*월[ \t]*(\d{1,2})[ \t]*일(?:[ \t]*\(?[월화수목금토일](?:요일)?\)?)?[ \t]*$')
METADATA_DATE = re.compile(r'^(?:발급|발행|작성|출력|촬영|조회)\s*(?:일자|일|날짜|연도)(?:\s|[:：]|$)')
TIME = re.compile(r'(?<!\d)([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?(?!\d)')
# Capture malformed numeric tokens WHOLE instead of accepting a valid suffix.
MONEY = re.compile(r'([^\s가-힣]+(?:[ \t]+[^\s가-힣]+)*)[ \t]*원')
MAX_ROWS = 200
SUMMARY_LABELS = ('현재 잔액', '현재잔액', '총 잔액', '총잔액', '사용합계',
    '사용 합계', '이용합계', '이용 합계', '총 이용', '총이용', '총 사용', '총사용', '합계금액', '합계 금액')
SPLIT_HANGUL = re.compile(r'(?<![가-힣])[가-힣](?:[ \t]+[가-힣]){2,}(?![가-힣])')
REASONS = {
    'year_missing': '거래 연도가 없습니다. 촬영일이나 현재 연도로 채우지 않습니다.',
    'date_invalid': '날짜를 확인해 주세요.',
    'date_missing': '거래일이 미확인입니다. 페이지 간 날짜를 이어 붙이지 않습니다.',
    'date_outside_period': '날짜가 명시된 조회 기간과 일치하지 않습니다.',
    'ocr_low_confidence': 'OCR 신뢰도가 낮습니다.',
    'image_low_resolution': '이미지 폭이 작아 금액·거래처를 확인할 수 없습니다.',
    'text_too_small': 'OCR 글자 높이가 작아 금액·거래처를 확인할 수 없습니다.',
    'row_clipped': '화면 가장자리의 잘린 행일 수 있습니다.',
    'ocr_geometry_missing': 'OCR 이미지 크기 근거가 없어 잘림 여부를 확인할 수 없습니다.',
    'amount_invalid': '금액 또는 숫자 자리를 확인해 주세요.',
    'direction_unknown': '입출금 부호가 미확인입니다.',
    'unlabeled_amount_ambiguous': '추가 금액이 거래금액인지 잔액인지 불명확하여 별도 거래로 만들지 않았습니다.',
    'balance_ambiguous': '거래 후 잔액을 확인해 주세요.',
    'party_unverified': '거래처가 잘렸거나 불명확합니다. 임의로 복원하지 않습니다.',
    'card_classification_unconfirmed': '카드 승인·취소·환불·대금 납부는 저장 단계에서 구분해야 합니다.',
    'transfer_not_income_expense': '이체를 수입·지출로 확정하지 않습니다.',
    'transaction_type_ambiguous': '취소·환불 등 거래 종류의 의미를 확인해 주세요.',
    'ocr_line_conflict': '행 재인식 결과가 충돌하거나 불명확합니다. 원본을 확인해 주세요.',
}


def needs_ocr(text):
    # Date/numeric evidence works for Latin/numeric PDFs too; never count Hangul.
    return ('\ufffd' in text or '\x00' in text or len(text.strip()) < 12
            or not (DATE.search(text) or KOREAN_DATE.search(text)
                    or any(MONTH_DAY.fullmatch(line) for line in text.splitlines()))
            or MONEY.search(text) is None)


def amount(value):
    text = value.strip()
    sign = text[:1] if text[:1] in {'+', '-'} else None
    digits = text[1:].strip() if sign else text
    if len(digits) > 18 or not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)', digits):
        return None, 'unknown'
    number = Decimal(digits.replace(',', ''))
    return format(number, 'f'), ('inflow' if sign == '+' else 'outflow' if sign == '-' else 'unknown')


def lines_for_page(page):
    if page['method'] == 'ocr_tsv' and 'ocr_lines' in page:
        return page['ocr_lines']
    if page['method'] != 'ocr_tsv':
        return [{'text': line.strip(), 'confidence': None, 'bbox': None, 'reasons': []}
                for line in page['text'].splitlines() if line.strip()]
    records = list(csv.DictReader(io.StringIO(page['text']), delimiter='\t'))
    sizes = {}
    for record in records:
        if record.get('level') == '1':
            try:
                width, height = int(record['width']), int(record['height'])
                if width > 0 and height > 0:
                    sizes[record.get('page_num')] = (width, height)
            except (ValueError, KeyError):
                pass
    grouped = {}
    for word in records:
        if word.get('level') != '5' or not (word.get('text') or '').strip():
            continue
        try:
            confidence = float(word['conf'])
            bounds = [int(word[key]) for key in ('left', 'top', 'width', 'height')]
            if not math.isfinite(confidence) or not 0 <= confidence <= 100 or any(n < 0 for n in bounds):
                raise ValueError()
        except (ValueError, KeyError):
            confidence, bounds = 0, None
        key = tuple(word.get(name) for name in ('page_num', 'block_num', 'par_num', 'line_num'))
        line = grouped.setdefault(key, {'words': [], 'confidence': 100, 'bounds': [], 'reasons': []})
        line['words'].append(word['text'].strip())
        line['confidence'] = min(line['confidence'], confidence)
        if bounds:
            line['bounds'].append(bounds)
            if bounds[3] < 12:
                line['reasons'].append('text_too_small')
            size = sizes.get(word.get('page_num'))
            if size:
                if size[0] < 320:
                    line['reasons'].append('image_low_resolution')
                if (bounds[0] <= 1 or bounds[1] <= 1 or bounds[0]+bounds[2] >= size[0]-1
                        or bounds[1]+bounds[3] >= size[1]-1):
                    line['reasons'].append('row_clipped')
            else:
                line['reasons'].append('ocr_geometry_missing')
    result = []
    for line in grouped.values():
        bounds = line['bounds']
        bbox = None
        if bounds:
            left, top = min(b[0] for b in bounds), min(b[1] for b in bounds)
            bbox = [left, top, max(b[0] + b[2] for b in bounds) - left,
                    max(b[1] + b[3] for b in bounds) - top]
        result.append({'text': ' '.join(line['words']), 'confidence': line['confidence'], 'bbox': bbox,
                       'reasons': list(dict.fromkeys(line['reasons']))})
    return result


def unsafe_line(line):
    reasons = list(line['reasons'])
    if line['confidence'] is not None and line['confidence'] < 80:
        reasons.append('ocr_low_confidence')
    return [reason for reason in reasons if reason != 'ocr_geometry_missing']


def numeric_signature(text):
    matches = list(MONEY.finditer(text))
    if len(matches) != 1:
        return None
    value, direction = amount(matches[0][1])
    return (value, direction) if value is not None else None


def tsv_size(text):
    pages = [row for row in csv.DictReader(io.StringIO(text), delimiter='\t') if row.get('level') == '1']
    try:
        return (int(pages[0]['width']), int(pages[0]['height'])) if len(pages) == 1 else None
    except (KeyError, ValueError):
        return None


class LineRecognizer:
    """Ledger-only, bounded pixel re-reading. Never repairs OCR strings."""
    MAX_CALLS = 8
    MAX_SECONDS = 12

    def __init__(self):
        self.calls = 0
        self.elapsed = 0.0

    def refine(self, text, image_path, run):
        from PIL import Image
        lines = lines_for_page({'method': 'ocr_tsv', 'text': text})
        with Image.open(image_path) as image:
            width, height = image.size
            if width < 320 or width*height > 16_000_000 or tsv_size(text) != image.size:
                for line in lines:
                    line['reasons'].append('ocr_line_conflict')
                return lines
            for index, line in enumerate(lines):
                content = line['text']
                if any(label in content for label in SUMMARY_LABELS):
                    continue
                # Combined date/time-and-amount rows retain the established
                # parser path. Their punctuation is not a damaged money sign.
                if date_marker(content, None) is not None or TIME.search(content):
                    continue
                numeric = MONEY.search(content) is not None or re.fullmatch(r'[+\-−]?[\d, .]+', content) is not None
                following = lines[index+1:index+3]
                amount_follows = bool(following) and (MONEY.search(following[0]['text']) is not None or
                    (TIME.fullmatch(following[0]['text']) and len(following) == 2 and
                     MONEY.search(following[1]['text']) is not None))
                party = bool(SPLIT_HANGUL.search(content)) or bool(
                    amount_follows and not numeric and re.search(r'[가-힣]', content)
                    and date_marker(content, None) is None and not TIME.search(content)
                    and not re.search(r'계좌번호|카드번호|예금주|고객명|거래내역|입출금|카드\s*(?:이용|사용)|조회|거래\s*연도', content))
                if not numeric and not party:
                    continue
                if numeric and (len(list(MONEY.finditer(content))) > 1 or
                                len(re.findall(r'[+\-−]', content)) > 1 or '−' in content):
                    line['reasons'].append('ocr_line_conflict')
                    continue
                box = line['bbox']
                # Geometry must be present, unclipped, and isolated from every
                # other TSV line; low resolution/invalid word geometry cannot
                # be rescued by running another recognizer.
                if (not box or line['reasons'] or line['confidence'] is None
                        or line['confidence'] < 30):
                    line['reasons'].append('ocr_line_conflict')
                    continue
                x, y, w, h = box
                if (not 0 < w <= 3000 or not 12 <= h <= 220 or x < 10 or y < 10 or x+w+10 >= width
                        or y+h+10 >= height):
                    line['reasons'].append('ocr_line_conflict')
                    continue
                crop_box = (x-8, y-8, x+w+8, y+h+8)
                overlaps = [other for n, other in enumerate(lines) if other['bbox'] and index != n and
                            other['bbox'][0] < crop_box[2] and other['bbox'][0]+other['bbox'][2] > crop_box[0] and
                            other['bbox'][1] < crop_box[3] and other['bbox'][1]+other['bbox'][3] > crop_box[1]]
                if overlaps:
                    line['reasons'].append('ocr_line_conflict')
                    for other in overlaps:
                        other['reasons'].append('ocr_line_conflict')
                    continue
                remaining = self.MAX_SECONDS - self.elapsed
                if self.calls >= self.MAX_CALLS or remaining <= 0:
                    raise ValueError('Line OCR budget exceeded')
                crop_path = image_path.parent / ('line-' + str(self.calls) + '.png')
                started = time.monotonic()
                try:
                    image.crop(crop_box).save(crop_path)
                    os.chmod(crop_path, 0o600)
                    self.calls += 1
                    output = run(['tesseract', str(crop_path), 'stdout', '-l', 'kor+eng',
                                  '--psm', '7', 'tsv'], min(3, remaining))
                    if len(output) > 20_000:
                        raise ValueError('Line OCR output limit')
                    candidates = lines_for_page({'method':'ocr_tsv', 'text':output.decode('utf-8')})
                    crop_size = (crop_box[2]-crop_box[0], crop_box[3]-crop_box[1])
                    output_size_matches = tsv_size(output.decode('utf-8')) == crop_size
                finally:
                    self.elapsed += time.monotonic() - started
                    crop_path.unlink(missing_ok=True)
                # A single-line crop may not become a second transaction or a
                # differently labelled balance. Unclear/conflicting reads keep
                # the original evidence but invalidate its candidate value.
                # The crop is intentionally narrow. Original-page resolution
                # was checked above; cropped width is not original resolution.
                candidate_risks = ([r for r in candidates[0]['reasons'] if r != 'image_low_resolution']
                                   if len(candidates) == 1 else ['ocr_line_conflict'])
                valid = (output_size_matches and len(candidates) == 1
                         and candidates[0]['confidence'] is not None
                         and candidates[0]['confidence'] >= 90 and not candidate_risks)
                replacement = candidates[0]['text'] if valid else ''
                if numeric and valid:
                    previous, current = numeric_signature(content), numeric_signature(replacement)
                    old_sign = re.search(r'[+\-−]', content)
                    new_sign = re.search(r'[+\-−]', replacement)
                    old_context = MONEY.sub('', content).strip()
                    new_context = MONEY.sub('', replacement).strip()
                    # Only amount tokens may differ after a fresh pixel read;
                    # a merchant/approval/cancellation label cannot be swapped.
                    context_matches = (old_context == new_context if previous else
                        not new_context or ('잔액' in content and new_context in {'잔액','거래 후 잔액'}))
                    valid = (current is not None and (previous is None or previous == current)
                             and bool('잔액' in content) == bool('잔액' in replacement)
                             and (old_sign.group() if old_sign else None) == (new_sign.group() if new_sign else None)
                             and context_matches and not any(label in replacement for label in SUMMARY_LABELS))
                elif party and valid:
                    valid = (not SPLIT_HANGUL.search(replacement) and not re.search(r'[\d?…□]', replacement)
                             and not MONEY.search(replacement) and len(replacement) <= 100)
                if valid:
                    line['text'] = replacement
                    line['confidence'] = candidates[0]['confidence']
                else:
                    line['reasons'].append('ocr_line_conflict')
        return lines


def period_for_page(lines):
    """Only explicitly labelled transaction year/range; never EXIF/current year."""
    periods = []
    for line in lines:
        text = line['text']
        if unsafe_line(line):
            continue
        year = re.fullmatch(r'(?:거래\s*연도|조회\s*연도)\s*[:：]?\s*(20\d{2})년?', text)
        if year:
            periods.append((date(int(year[1]), 1, 1), date(int(year[1]), 12, 31)))
        elif re.match(r'^(?:조회|거래)\s*기간\s*[:：]?', text):
            markers = list(DATE.finditer(text)) or list(KOREAN_DATE.finditer(text))
            if len(markers) == 2:
                try:
                    start, end = (date(*map(int, marker.groups())) for marker in markers)
                    if start <= end:
                        periods.append((start, end))
                except ValueError:
                    pass
    # Conflicting headers do not authorize selecting a convenient year.
    return periods[0] if periods and len(set(periods)) == 1 else None


def date_marker(text, period):
    if METADATA_DATE.match(text):
        return None
    full = DATE.search(text) or KOREAN_DATE.search(text)
    partial = MONTH_DAY.fullmatch(text)
    if not full and not partial:
        return None
    parts = {'year': None, 'month': None, 'day': None}
    reasons = []
    try:
        if full:
            year, month, day = map(int, full.groups())
            value = date(year, month, day)
            parts = {'year': year, 'month': month, 'day': day}
            if period and not period[0] <= value <= period[1]:
                reasons.append('date_outside_period')
            return value.isoformat(), parts, reasons
        month, day = map(int, partial.groups())
        date(2000, month, day)  # Validate partial leap-day without inventing a year.
        parts.update(month=month, day=day)
        candidates = []
        if period:
            for year in range(period[0].year, period[1].year+1):
                try:
                    candidate = date(year, month, day)
                    if period[0] <= candidate <= period[1]:
                        candidates.append(candidate)
                except ValueError:
                    continue
        if len(candidates) == 1:
            parts['year'] = candidates[0].year
            return candidates[0].isoformat(), parts, reasons
        return None, parts, ['year_missing']
    except ValueError:
        return None, parts, ['date_invalid']


def add_reason(row, reason):
    if reason not in row['review_reasons']:
        row['review_reasons'].append(reason)
        row['warnings'].append(REASONS[reason])


def safe_label(text):
    text = ''.join(c for c in text if c.isprintable())
    text = re.sub(r'\b\d{2,}(?:[- ]\d{2,}){1,}\b|\b\d{8,}\b', '[번호 생략]', text)
    return text.strip()[:100]


def classification_evidence(pages):
    """Boolean-only structural evidence, also usable by synthetic smoke diagnostics."""
    lines = [line for page in pages for line in lines_for_page(page)]
    return {
        'date': any(date_marker(line['text'], None) is not None for line in lines),
        'money': any(MONEY.search(line['text']) is not None for line in lines),
        'bank_header': any(re.match(r'^(?:은행\s*)?입출금(?:\s|$)|^은행\s*거래내역', line['text']) is not None
                           for line in lines),
        'card_header': any(re.match(r'^(?:신용|체크)?카드\s*(?:이용|사용|승인)(?:내역|\s|$)', line['text']) is not None
                           for line in lines),
        'tsv_lines': any(page['method'] == 'ocr_tsv' and bool(lines_for_page(page)) for page in pages),
    }


def parse_pages(pages, document_type='auto'):
    if document_type not in {'auto', 'bank_transactions', 'card_transactions'}:
        raise ValueError('자료 종류를 확인해 주세요.')
    decoded = [(page, lines_for_page(page)) for page in pages]
    # A user-selected type cannot turn an unrelated/ambiguous document into transactions.
    evidence = classification_evidence(pages)
    bank = evidence['date'] and evidence['money'] and evidence['bank_header']
    card = evidence['date'] and evidence['money'] and evidence['card_header']
    detected = 'bank_transactions' if bank and not card else 'card_transactions' if card and not bank else 'unknown'
    kind = detected if document_type == 'auto' else document_type
    if detected == 'unknown' or kind != detected:
        return {'document_type': 'unknown', 'status': 'review_required', 'rows': [],
                'warnings': ['화면 종류가 불명확합니다. 종류를 확인하거나 수동 입력해 주세요.']}
    result, warnings = [], []
    seen = set()
    for page, lines in decoded:
        period = period_for_page(lines)
        date_parts = {'year': None, 'month': None, 'day': None}; date_reasons = ['date_missing']
        current_date = None; current_time = None; party = None; last = None
        party_reasons = []
        for index, line in enumerate(lines):
            text = line['text']
            risk = unsafe_line(line)
            if len(text) > 500:
                warnings.append('긴 설명 행은 거래로 해석하지 않았습니다.'); party = None; continue
            if any(label in text for label in SUMMARY_LABELS):
                continue
            if any(label in text for label in ('계좌번호', '카드번호', '예금주', '고객명')):
                continue
            if METADATA_DATE.match(text) and not re.match(r'^조회\s*연도', text):
                continue
            if re.match(r'^(?:조회|거래)\s*(?:기간|연도)', text):
                continue
            day = date_marker(text, period)
            if day is not None:
                current_date, date_parts, date_reasons = day
                current_time = None; party = None; party_reasons = []; last = None
                if risk:
                    current_date = None; date_parts = {'year': None, 'month': None, 'day': None}
                    date_reasons = risk + ['date_missing']
            clock = TIME.search(text)
            if clock:
                current_time = clock.group(0) if not risk else None
            numeric_text = KOREAN_DATE.sub('', DATE.sub('', TIME.sub('', text)))
            money = list(MONEY.finditer(numeric_text))
            if '잔액' in text:
                if last is not None and party is None and not party_reasons and index - last['_line'] <= 3 and len(money) == 1:
                    value, balance_direction = amount(money[0][1])
                    if value is not None and balance_direction == 'outflow':
                        value = '-' + value
                    last['balance_after'] = value if not risk else None
                    if last['balance_after'] is None:
                        add_reason(last, 'balance_ambiguous')
                elif money:
                    warnings.append('잔액 행의 연결을 확인하지 못했습니다. 별도 거래로 만들지 않습니다.')
                continue
            if not money:
                if '원' in text and any(label in text for label in ('금액', '승인', '입금', '출금')):
                    warnings.append('금액이 불명확한 행이 있습니다.')
                elif day is None and not clock and not any(label in text for label in ('거래내역', '입출금', '카드 이용', '카드 사용')):
                    # Do not join OCR-separated syllables into an invented merchant.
                    split_hangul = SPLIT_HANGUL.search(text)
                    party = safe_label(text) if not risk and not re.search(r'[?…□]', text) and not split_hangul else None
                    party_reasons = risk + (['party_unverified'] if party is None else [])
                continue
            value, direction = amount(money[0][1]) if len(money) == 1 else (None, 'unknown')
            # Unsigned amount after a transaction, without a new merchant/date,
            # may be a small unlabelled balance. Do not fabricate a second row.
            if (kind == 'bank_transactions' and last is not None and party is None and not party_reasons
                    and direction == 'unknown' and not re.search(r'거래\s*금액|입금액|출금액', text)):
                add_reason(last, 'unlabeled_amount_ambiguous'); continue
            row_reasons = list(date_reasons) + list(line['reasons']) + party_reasons
            if value is None:
                row_reasons.append('amount_invalid')
            if risk or party_reasons:
                value, direction = None, 'unknown'; row_reasons.extend(risk)
            remainder = MONEY.sub('', KOREAN_DATE.sub('', DATE.sub('', TIME.sub('', text)))).strip(' :·')
            for label in ('승인금액', '승인 금액', '거래금액', '거래 금액', '입금액', '출금액'):
                remainder = remainder.replace(label, '')
            label = None if risk or party_reasons else party or safe_label(remainder) or None
            type_candidate = 'unknown'
            if kind == 'card_transactions':
                direction = 'unknown'
                context = text + ' ' + (party or '')
                type_candidate = ('unknown' if '취소' in context and '환불' in context
                                  else 'card_cancellation' if '취소' in context else 'refund' if '환불' in context
                                  else 'card_bill' if '대금' in context or '납부' in context else 'card_approval_candidate')
                row_reasons.append('card_classification_unconfirmed')
                if type_candidate == 'unknown':
                    row_reasons.append('transaction_type_ambiguous')
            else:
                if '이체' in text + ' ' + (party or ''):
                    type_candidate = 'bank_transfer'; row_reasons.append('transfer_not_income_expense')
                if direction == 'unknown':
                    row_reasons.append('direction_unknown')
            row = {'row_id': f'preview-{len(result)+1}', 'transaction_date': current_date,
                   'transaction_date_parts': dict(date_parts),
                   'transaction_time': current_time, 'counterparty': label if kind == 'bank_transactions' else None,
                   'merchant': label if kind == 'card_transactions' else None, 'amount': value,
                   'direction': direction, 'balance_after': None, 'transaction_type_candidate': type_candidate,
                   'payment_method_candidate': 'card' if kind == 'card_transactions' else None,
                   'owner': None, 'account_id': None, 'review_status': 'review_required',
                   'source_location': {'page': page['page'], 'line': index+1, 'bbox': line['bbox'], 'method': page['method']},
                   'warnings': [], 'review_reasons': [], '_line': index}
            for reason in dict.fromkeys(row_reasons):
                add_reason(row, reason)
            identity = (kind, tuple(date_parts.values()), current_date, current_time, label, value, direction)
            if identity in seen:
                row['warnings'].append('동일 후보가 반복됩니다. 중복 또는 별도 거래인지 확인해 주세요.')
            seen.add(identity); result.append(row); last = row
            party = None; party_reasons = []; current_time = None
            if len(result) >= MAX_ROWS:
                warnings.append('미리보기는 200행으로 제한됩니다.'); break
        if len(result) >= MAX_ROWS:
            break
    for row in result:
        row.pop('_line')
    if not result:
        warnings.append('지원하는 거래행을 찾지 못했습니다. 양식 지원 또는 인식 성공을 보장하지 않습니다.')
    return {'document_type': kind, 'status': 'review_required', 'rows': result,
            'warnings': list(dict.fromkeys(warnings))[:20]}


def extract(path, kind, document_type):
    deadline = time.monotonic() + 55
    def bounded_run(args, timeout=12):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('Document OCR budget exceeded')
        return command(args, min(timeout, remaining))
    recognizer = LineRecognizer()
    return parse_pages(extract_pages(path, kind, run=bounded_run, needs_ocr=needs_ocr,
                                    tsv=True, refine_tsv=recognizer.refine), document_type)


if __name__ == '__main__':
    try:
        set_worker_limits()
        sys.stdout.write(json.dumps(extract(Path(sys.argv[1]), sys.argv[2], sys.argv[3]),
                                    ensure_ascii=True, allow_nan=False))
    except Exception:
        sys.exit(1)  # No raw text, file name or decoder stderr in errors/logs.
