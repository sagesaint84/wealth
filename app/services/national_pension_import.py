"""Offline, reviewed pension document import. Never infer personal expense or tax eligibility."""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
from copy import deepcopy
from pathlib import Path

from app.services import national_pension as np
from app.services.financial_json import financial_rmw, write_financial_json
from app.services.savings import validate_national_pension_history

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 8
MAX_PIXELS = 16_000_000
_slots = threading.BoundedSemaphore(2)
FIELDS = {
    'total_paid_amount': '실제 납부 보험료 총액', 'paid_months': '실제 납부 월수',
    'unpaid_amount': '미납 보험료', 'unpaid_months': '미납 월수',
    'scheduled_amount': '납입예정 보험료', 'scheduled_months': '납입예정 월수',
    'unpayable_amount': '납부할 수 없는 보험료', 'unpayable_months': '납부할 수 없는 월수',
    'monthly_payout': '예상 월 연금액', 'pension_start': '예상 연금 개시월',
    'future_total': '향후 총 예상 납부액', 'query_date': '조회일', 'issued_date': '발행일',
    'annual_total': '확인서 연간 합계', 'additional_amount': '추가 보험료',
    'pension_basis': '예상 연금액 기준',
}
SNAPSHOT_KEYS = ('yearly_contributions', 'national_pension_analysis', 'national_pension_import',
                 'total_paid_amount', 'monthly_payout', 'monthly_premium', 'maturity_date',
                 'expected_amount', 'converted_total_asset')


def snapshot(item):
    return {key: deepcopy(item.get(key)) for key in SNAPSHOT_KEYS}


def detect_file(data: bytes, mime: str) -> str:
    if not data or len(data) > MAX_BYTES:
        raise ValueError('파일은 10MB 이하로 선택해 주세요.')
    kind = ('pdf' if data.startswith(b'%PDF-') else 'png' if data.startswith(b'\x89PNG\r\n\x1a\n')
            else 'jpeg' if data.startswith(b'\xff\xd8\xff') else None)
    allowed = {'pdf': 'application/pdf', 'png': 'image/png', 'jpeg': 'image/jpeg'}
    if kind is None or mime not in (allowed[kind], 'application/octet-stream'):
        raise ValueError('PDF, PNG, JPG 파일 형식을 확인해 주세요.')
    return kind


def number(token):
    # Reject malformed OCR digits; never substitute O/I for 0/1.
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)', token):
        raise ValueError('금액의 숫자를 확인해 주세요.')
    value=int(token.replace(',', ''))
    np.money(value,optional=False)
    return value


def parse_text(text: str, *, ocr=False, document_type='auto') -> dict:
    if len(text) > 200_000:
        raise ValueError('문서 내용이 처리 제한을 초과했습니다.')
    has_history = '가입내역' in text
    has_certificate = '소득공제' in text and '납부확인' in text
    detected = 'history' if has_history and not has_certificate else 'certificate' if has_certificate and not has_history else 'unknown'
    if document_type not in {'auto', 'history', 'certificate'}:
        raise ValueError('자료 종류를 확인해 주세요.')
    kind = detected if document_type == 'auto' else document_type
    result = dict(document_type=kind, detected_type=detected, fields=[], periods=[], monthly=[], annual=[], warnings=[])
    if kind == 'unknown':
        result['warnings'].append('문서 종류를 선택한 뒤 다시 추출해 주세요.')
        return result
    # Only numerical/enum values from allowlisted labels leave this function.
    # Never return lines containing a name, workplace, issuing ID or raw source text.
    labels = {
        'total_paid_amount': ('납부한 보험료 총액', '납부 보험료 총액'),
        'paid_months': ('실제 납부 월수', '납부한 월수'),
        'unpaid_amount': ('미납 보험료',), 'unpaid_months': ('미납 월수',),
        'scheduled_amount': ('납입예정 금액',), 'scheduled_months': ('납입예정 월수',),
        'unpayable_amount': ('납부할 수 없는 보험료',), 'unpayable_months': ('납부할 수 없는 월수',),
        'monthly_payout': ('예상 월 연금액', '예상연금월액'),
        'future_total': ('향후 총 예상 납부액',), 'annual_total': ('연간 합계',),
        'additional_amount': ('추가 보험료',),
    }
    for key, aliases in labels.items():
        values=[]
        for label in aliases:
            for match in re.finditer(re.escape(label)+r'\s*[:：]?\s*([\d,OIl.\-]+)\s*(?:원|개월|월)?', text):
                try: values.append(number(match[1]))
                except ValueError: result['warnings'].append(FIELDS[key]+' 숫자 확인 필요')
        if values:
            unique=set(values)
            result['fields'].append(dict(key=key,label=FIELDS[key],value=values[0],
                status='OCR 확인 필요' if ocr else '정확히 추출됨' if len(unique)==1 else '자료 불일치',
                conflict=len(unique)>1))
    for key,label in [('query_date','조회일'),('issued_date','발행일'),('pension_start','예상 연금 개시월')]:
        match=re.search(label+r'\s*[:：]?\s*(\d{4})[년.\-/]\s*(\d{1,2})(?:[월.\-/]\s*(\d{1,2}))?',text)
        if match:
            if key!='pension_start' and match[3] is None:
                result['warnings'].append(label+'의 일자 확인 필요');continue
            try: value=np.iso_date(f'{int(match[1]):04d}-{int(match[2]):02d}-{int(match[3] or 1):02d}').isoformat()
            except ValueError: result['warnings'].append(label+' 확인 필요');continue
            result['fields'].append(dict(key=key,label=FIELDS[key],value=value,status='OCR 확인 필요' if ocr else '정확히 추출됨'))
    if '현재가치' in text or '미래 명목' in text:
        basis='unknown' if '현재가치' in text and '미래 명목' in text else 'current' if '현재가치' in text else 'future_nominal'
        result['fields'].append(dict(key='pension_basis',label=FIELDS['pension_basis'],value=basis,status='OCR 확인 필요' if ocr else '정확히 추출됨'))
    # Labelled period rows only. Unknown table layouts remain unsupported, not fabricated.
    period=re.compile(r'(\d{4})[.\-/](\d{1,2})\s*[~∼～]\s*(\d{4})[.\-/](\d{1,2})([^\n]*)')
    for match in period.finditer(text):
        tail=match[5]; row=dict(start=f'{int(match[1]):04d}-{int(match[2]):02d}',end=f'{int(match[3]):04d}-{int(match[4]):02d}',
                              membership='workplace' if '사업장' in tail else 'regional' if '지역' in tail else 'unknown',
                              workplace_role='unknown',personal_paid=None,status='OCR 확인 필요' if ocr else '연도별 배분 불가')
        try:
            np.iso_date(row['start']+'-01');np.iso_date(row['end']+'-01')
            if row['start']>row['end']: raise ValueError()
            for key,label in [('paid','실제납부'),('paid_months','납부월수'),('unpaid','미납금액'),('unpaid_months','미납월수'),('income_base','기준소득월액')]:
                value=re.search(label+r'\s*[:：]?\s*([\d,OIl.\-]+)',tail)
                row[key]=number(value[1]) if value else None
            result['periods'].append(row)
        except ValueError: result['warnings'].append('기간별 납부내역 확인 필요')
    # Flat, labelled table columns retained by pdftotext -layout. Multi-level or
    # collapsed headers are intentionally not guessed.
    header=None
    for line in text.splitlines():
        cells=re.split(r'\s{2,}',line.strip())
        if '기준소득월액' in cells and '실제 납부액' in cells:
            header=cells;continue
        if not header or len(cells)!=len(header): continue
        record=dict(zip(header,cells));interval=period.search(record.get('기간',''))
        if not interval: continue
        start=f'{int(interval[1]):04d}-{int(interval[2]):02d}';end=f'{int(interval[3]):04d}-{int(interval[4]):02d}'
        if any(row['start']==start and row['end']==end and row.get('paid') is not None for row in result['periods']):continue
        try:
            np.iso_date(start+'-01');np.iso_date(end+'-01')
            if start>end:raise ValueError()
            row=dict(start=start,end=end,membership='workplace' if record.get('가입종별')=='사업장' else 'regional' if record.get('가입종별')=='지역' else 'unknown',workplace_role='unknown',personal_paid=None,status='OCR 확인 필요' if ocr else '연도별 배분 불가')
            for key,label in [('income_base','기준소득월액'),('paid','실제 납부액'),('unpaid','미납액'),('paid_months','납부 월수'),('unpaid_months','미납 월수')]:
                row[key]=number(record[label].replace('원','').replace('개월','').strip()) if label in record else None
            result['periods']=[previous for previous in result['periods'] if (previous['start'],previous['end'])!=(start,end)]
            result['periods'].append(row)
        except ValueError:result['warnings'].append('기간 표 숫자·기간 확인 필요')
    year_match=re.search(r'귀속연도\s*[:：]?\s*(\d{4})',text)
    if kind=='certificate' and year_match:
        year=int(year_match[1])
        for match in re.finditer(r'(?m)^\s*(\d{1,2})월\s+(사업장 고지금액|지역 납부금액)\s*[:：]?\s*([\d,OIl.\-]+)',text):
            try:
                month=np.integer(int(match[1]),1,12)
                result['monthly'].append(dict(year=year,month=month,kind='billed' if '사업장' in match[2] else 'paid',
                    amount=number(match[3]),status='실제 납부 여부 미확인' if '사업장' in match[2] else 'OCR 확인 필요' if ocr else '정확히 추출됨'))
            except ValueError: result['warnings'].append('월별 숫자 확인 필요')
        header=None
        for line in text.splitlines():
            cells=re.split(r'\s{2,}',line.strip())
            if '월' in cells and any(label in cells for label in ('사업장 고지금액','지역 납부금액')):
                header=cells;continue
            if not header or len(cells)!=len(header):continue
            record=dict(zip(header,cells))
            try:
                month=np.integer(int(record['월'].replace('월','')),1,12)
                for label,role in [('사업장 고지금액','billed'),('지역 납부금액','paid')]:
                    if label not in record or record[label] in {'','-','미확인'}:continue
                    result['monthly'].append(dict(year=year,month=month,kind=role,amount=number(record[label].replace('원','').strip()),status='실제 납부 여부 미확인' if role=='billed' else 'OCR 확인 필요' if ocr else '정확히 추출됨'))
            except (ValueError,KeyError):result['warnings'].append('월별 표 숫자 확인 필요')
        total=next((row['value'] for row in result['fields'] if row['key']=='annual_total'),None)
        seen=[(row['year'],row['month'],row['kind']) for row in result['monthly']]
        if len(seen)!=len(set(seen)): result['warnings'].append('중복 월별 기록: 적용 전 확인 필요')
        if total is not None and result['monthly'] and sum(row['amount'] for row in result['monthly'])!=total:
            result['warnings'].append('월별 합계와 연간 합계 불일치: 자동 연도 반영 제외')
    # Explicit annual actual-payment rows only; monthly billed sums are never promoted.
    for match in re.finditer(r'(?m)^\s*(\d{4})년\s+실제 납부액\s*[:：]?\s*([\d,OIl.\-]+)',text):
        try:
            row=validate_national_pension_history([dict(year=match[1],deposit=number(match[2]))])[0]
            result['annual'].append({**row,'status':'OCR 확인 필요' if ocr else '정확히 추출됨'})
        except ValueError: result['warnings'].append('연도별 실제 납부액 확인 필요')
    if not any(result[key] for key in ('fields','periods','monthly','annual')):
        result['warnings'].append('지원하는 항목을 찾지 못했습니다. 수동 입력하거나 명확한 자료로 다시 시도해 주세요.')
    if result['periods']: result['warnings'].append('기간별 총액은 연도별·본인 부담액으로 자동 배분하지 않습니다.')
    total=next((row['value'] for row in result['fields'] if row['key']=='total_paid_amount'),None)
    if total is not None and result['periods'] and all(row.get('paid') is not None for row in result['periods']):
        if sum(row['paid'] for row in result['periods'])!=total:
            result['warnings'].append('추출 기간별 실제 납부 합계와 총액이 다릅니다. 누락 기간·추납·원문을 확인하세요.')
    return result


def preview(item_id, username, data, mime, document_type='auto'):
    if not _slots.acquire(blocking=False):
        raise ValueError('자료 분석이 진행 중입니다. 잠시 후 다시 시도해 주세요.')
    try:
        return _preview(item_id,username,data,mime,document_type)
    except (OSError,subprocess.SubprocessError):
        raise ValueError('오프라인 분석 도구를 사용할 수 없습니다. 수동 입력해 주세요.') from None
    finally:
        _slots.release()


def _preview(item_id, username, data, mime, document_type):
    _, current=np.read_state(username); item=np.find_item(current,item_id)
    kind=detect_file(data,mime)
    with tempfile.TemporaryDirectory(prefix='wealth-np-') as directory:
        os.chmod(directory,0o700)
        path=Path(directory)/('input.'+kind)
        with path.open('xb') as stream:
            os.chmod(path,0o600);stream.write(data)
        # Worker owns all untrusted decoding, with Linux resource limits and bounded tools.
        process=subprocess.Popen([sys.executable,'-m','app.services.national_pension_document',str(path),kind,document_type],
                                 stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=os.name=='posix')
        try:
            output,_=process.communicate(timeout=75)
        except subprocess.TimeoutExpired:
            if os.name=='posix': os.killpg(process.pid,signal.SIGKILL)
            else: process.kill()
            process.communicate()
            raise ValueError('자료 분석 시간이 초과했습니다. 수동 입력하거나 페이지를 줄여 주세요.') from None
        if process.returncode or len(output)>300_000:
            raise ValueError('자료 분석을 완료하지 못했습니다. OCR 설치·파일 상태를 확인하거나 수동 입력해 주세요.')
        try: extracted=json.loads(output)
        except (ValueError,UnicodeError): raise ValueError('자료 분석 결과를 확인할 수 없습니다.') from None
        if not isinstance(extracted,dict) or any(not isinstance(extracted.get(key),list) for key in ('fields','periods','monthly','annual','warnings')):
            raise ValueError('자료 분석 결과 형식을 확인할 수 없습니다.')
    extracted.update(fingerprint=hashlib.sha256(data).hexdigest(),expected=snapshot(item))
    for row in extracted['fields']:
        row['current']=item.get(row['key']) if row['key'] in {'total_paid_amount','monthly_payout'} else item.get('national_pension_import',{}).get('fields',{}).get(row['key'])
        if row['key'] in {'total_paid_amount','monthly_payout'} and row['current'] is not None:
            row['comparison']='기존 값과 일치' if row['current']==row['value'] else '기존 값과 불일치'
    return extracted


def clean_metadata(payload, *, check_total=True):
    if not isinstance(payload,dict) or set(payload)-{'document_type','fields','periods','monthly'}:
        raise ValueError('가져오기 검토 형식을 확인해 주세요.')
    kind=np.choice(payload.get('document_type'),{'history','certificate'})
    fields={}
    if not isinstance(payload.get('fields',{}),dict): raise ValueError('적용 항목을 확인해 주세요.')
    for key,value in payload.get('fields',{}).items():
        if key not in FIELDS: raise ValueError('지원하지 않는 적용 항목입니다.')
        fields[key]=np.iso_date(value).isoformat() if key in {'query_date','issued_date','pension_start'} else np.choice(value,{'unknown','current','future_nominal'}) if key=='pension_basis' else np.money(value,optional=False)
        if key.endswith('months'): fields[key]=np.integer(value,0,2000)
    periods=[]
    for row in np.rows(payload.get('periods',[])):
        start,end=row.get('start'),row.get('end')
        if not isinstance(start,str) or not isinstance(end,str) or not re.fullmatch(r'\d{4}-\d{2}',start) or not re.fullmatch(r'\d{4}-\d{2}',end): raise ValueError('기간을 확인해 주세요.')
        np.iso_date(start+'-01');np.iso_date(end+'-01')
        if start>end or any(start<=previous['end'] and previous['start']<=end for previous in periods): raise ValueError('중복 또는 역전 기간입니다.')
        clean=dict(start=start,end=end,membership=np.choice(row.get('membership'),{'unknown','workplace','regional'}),workplace_role='unknown',personal_paid=None)
        for key in ('paid','unpaid','income_base','paid_months','unpaid_months'):
            clean[key]=np.money(row.get(key))
        span=(int(end[:4])-int(start[:4]))*12+int(end[5:])-int(start[5:])+1
        for key in ('paid_months','unpaid_months'):
            if clean[key] is not None: clean[key]=np.integer(row[key],0,span)
        periods.append(clean)
    monthly=[]; seen=set()
    for row in np.rows(payload.get('monthly',[])):
        year=np.integer(row.get('year'),1988,np.date.today().year);month=np.integer(row.get('month'),1,12)
        role=np.choice(row.get('kind'),{'paid','billed'});identity=(year,month,role)
        if identity in seen: raise ValueError('중복 월별 기록입니다.')
        seen.add(identity);monthly.append(dict(year=year,month=month,kind=role,amount=np.money(row.get('amount'),optional=False)))
    if check_total and 'annual_total' in fields and monthly and sum(row['amount'] for row in monthly)!=fields['annual_total']:
        raise ValueError('월별 합계와 연간 합계가 다릅니다. 검토 초안을 수정해 주세요.')
    return dict(document_type=kind,fields=fields,periods=periods,monthly=monthly)


@financial_rmw('portfolio.json')
def apply(item_id,username,payload):
    if not isinstance(payload,dict): raise ValueError('검토 입력은 객체여야 합니다.')
    fingerprint=payload.get('fingerprint')
    if not isinstance(fingerprint,str) or not re.fullmatch(r'[0-9a-f]{64}',fingerprint): raise ValueError('자료 식별값을 확인해 주세요.')
    clean=clean_metadata(payload.get('metadata'))
    annual=validate_national_pension_history(payload.get('annual',[]))
    path,data=np.read_state(username);item=np.find_item(data,item_id)
    if payload.get('expected')!=snapshot(item): raise np.PensionConflict('국민연금 정보가 변경되었습니다. 다시 가져와 검토해 주세요.')
    stored=item.get('national_pension_import',{})
    if not isinstance(stored,dict): raise ValueError('기존 가져오기 자료를 확인해 주세요.')
    if stored:
        # Validate the canonical lists before dictionary merging: corrupt duplicates
        # must not be silently collapsed into a successful save.
        clean_metadata({key:stored.get(key,{} if key=='fields' else [] if key in {'periods','monthly'} else None)
                        for key in ('document_type','fields','periods','monthly')},check_total=False)
    # Approving one item must not erase previously reviewed, unselected metadata.
    periods={ (row['start'],row['end']): row for row in stored.get('periods',[]) }
    periods.update({(row['start'],row['end']):row for row in clean['periods']})
    months={ (row['year'],row['month'],row['kind']):row for row in stored.get('monthly',[]) }
    months.update({(row['year'],row['month'],row['kind']):row for row in clean['monthly']})
    clean=clean_metadata(dict(document_type=clean['document_type'],
        fields={**stored.get('fields',{}),**clean['fields']},periods=list(periods.values()),monthly=list(months.values())),check_total=False)
    if not payload['metadata'].get('fields') and not payload['metadata'].get('periods') and not payload['metadata'].get('monthly') and not annual:
        raise ValueError('적용할 항목을 선택해 주세요.')
    history=validate_national_pension_history(item.get('yearly_contributions',[]))
    by_year={row['year']:row for row in history}
    for row in annual: by_year[row['year']]=row  # replacement, never sum duplicate periods/files
    # Metadata is a reviewed snapshot. Re-import replaces it, preserving unknown fields only in original financial data.
    item['national_pension_import']={**clean,'fingerprint':fingerprint,'revision':np.integer(stored.get('revision',0),0,2**53-2)+1}
    if annual: item['yearly_contributions']=list(by_year.values())
    for key in ('total_paid_amount','monthly_payout'):
        if key in payload['metadata'].get('fields',{}): item[key]=clean['fields'][key]
    write_financial_json(path,data)
    return dict(item=deepcopy(item),expected=snapshot(item))
