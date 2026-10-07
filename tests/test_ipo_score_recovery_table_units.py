"""Production parser + temporary persistence: percentage units in table headers."""
from contextlib import nullcontext
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.services.ipo import refresh_adapter as adapter, store
from app.services.ipo.dart_parser import DartSemanticParser
from tests.test_ipo_pre_subscription_score_recovery import company, dart_client


TABLE = '''<TABLE><TR><TH>구분</TH><TH>주식수(주)</TH><TH>비율(%)</TH></TR>
<TR><TD>상장 직후 유통가능 주식</TD><TD>2,333,000</TD><TD>23.33</TD></TR>
<TR><TD>상장 3개월 후 유통가능 주식</TD><TD>5,000,000</TD><TD>50.00</TD></TR>
</TABLE>'''
MSBIO = (Path(__file__).parent / 'fixtures/ipo/msbio_20261007000328_float.html').read_text(encoding='utf-8')


@pytest.mark.parametrize('document', [TABLE, MSBIO])
def test_interactive_header_unit_ratio_is_persisted_and_recomputes_score(monkeypatch, tmp_path, document):
    monkeypatch.setattr(store, 'DATA_DIR', tmp_path / 'ipo')
    row = company()
    assert row['score']['coverage'] == 60
    assert row['score']['core_missing'] == ['tradable_share_ratio']
    assert row['score']['score'] is None
    row.update(corp_code='01749559', stock_code='0013Y0')
    store.write_market_store({'schema_version':1,'ipos':[row]})
    dart = dart_client()
    dart.get_filing_list.return_value = {'list':[
        {'rcept_no':'20261007000328','rcept_dt':'20261007','report_nm':'[기재정정]투자설명서'},
        {'rcept_no':'20261008000328','rcept_dt':'20261008','report_nm':'[기재정정]투자설명서'},
    ]}
    zipped = BytesIO()
    with ZipFile(zipped, 'w') as archive:
        archive.writestr('registration.xml', document)
    dart.download_document_zip.return_value = zipped.getvalue()
    monkeypatch.setattr(adapter, 'DartClient', lambda **kwargs:dart)
    monkeypatch.setattr(adapter, '_BASE_REFRESH_MARKET', lambda **kwargs:{'status':'ok'})
    monkeypatch.setattr(adapter._base, '_refresh_file_lock', nullcontext)
    monkeypatch.setattr(adapter, 'discover_and_merge_primary_sources', lambda **kwargs:{})
    monkeypatch.setattr(adapter, 'refresh_missing_metalogos_references', lambda **kwargs:{'status':'ok'})
    result = adapter.refresh_ipo_market(username='synthetic-user', target_date_str='2026-10-07')
    assert result['targeted_dart']['candidates'] == 1
    assert result['targeted_dart']['enriched'] == 1
    dart.download_document_zip.assert_called_once_with('20261007000328')
    saved = store.read_market_store()['ipos'][0]
    feature = saved['features']['tradable_share_ratio']
    assert feature['value'] == 23.33, f'extraction/persistence stage: {feature}; score: {saved["score"]}'
    assert feature['status'] == 'ok'
    assert feature['source'] == 'dart_document'
    assert feature['source_date'] == '20261007'
    assert feature['rcept_no'] == '20261007000328'
    assert saved['score']['score'] is not None
    assert saved['score']['score'] != 86
    assert saved['score']['is_calculating'] is False
    assert saved['score']['coverage'] == 75
    assert saved['score']['core_missing'] == []
    assert saved['sources']['metalogos160'] == row['sources']['metalogos160']


@pytest.mark.parametrize('document', [TABLE, TABLE.replace('23.33</TD>', '23.33%</TD>')])
def test_ratio_unit_header_and_explicit_percent_are_equivalent(document):
    assert DartSemanticParser().extract_tradable_share_ratio(document) == 23.33


@pytest.mark.parametrize('document', [
    TABLE.replace('상장 직후 유통가능 주식','상장 1개월 후 유통가능 주식'),
    TABLE.replace('비율(%)','공모가(원)'),
    TABLE.replace('23.33</TD>','2333000</TD>'),
    TABLE.replace('23.33</TD>','-23.33</TD>'),
    TABLE.replace('23.33</TD>','101</TD>'),
    TABLE.replace('23.33</TD>','23.33 또는 25</TD>'),
])
def test_unit_header_does_not_promote_future_float_prices_or_invalid_values(document):
    assert DartSemanticParser().extract_tradable_share_ratio(document) is None


def test_corrected_unit_header_ratio_preserves_amendment_priority():
    document = '<P>정정 후</P>' + TABLE + '<P>정정 전</P>' + TABLE.replace('23.33</TD>','30.00</TD>')
    assert DartSemanticParser().extract_tradable_share_ratio(document) == 23.33


@pytest.mark.parametrize('suffix', ['', '%'])
def test_conflicting_immediate_float_rows_fail_closed(suffix):
    document = TABLE.replace('23.33</TD>', f'23.33{suffix}</TD>')
    document = document.replace('</TABLE>', f'<TR><TD>상장 직후 유통가능 주식</TD><TD>2,500,000</TD><TD>25{suffix}</TD></TR></TABLE>')
    assert DartSemanticParser().extract_tradable_share_ratio(document) is None


@pytest.mark.parametrize('section', ['table','prose','whole'])
def test_actual_ms_bio_filing_layout(section):
    table = MSBIO[MSBIO.index('<TABLE'):MSBIO.index('</TABLE>')+len('</TABLE>')]
    prose = MSBIO[MSBIO.rindex('<P>'):]
    document = {'table':table,'prose':prose,'whole':MSBIO}[section]
    feature = DartSemanticParser().parse_document(document, '20261007000328', '20261007')['tradable_share_ratio']
    assert feature['value'] == 23.33
    assert feature['source'] == 'dart_document'


@pytest.mark.parametrize('document', [
    MSBIO[:MSBIO.rindex('<P>')].replace('상장일 유통가능','상장 후 1개월 유통가능'),
    MSBIO[:MSBIO.rindex('<P>')].replace('공모 후 기준','알 수 없는 기준'),
    MSBIO[:MSBIO.rindex('<P>')].replace('공모 후 기준','완전희석 기준'),
    '<P>신청 기관의 23.33%는 시장 참여자입니다. 상장 후 3개월에 유통가능합니다.</P>',
])
def test_actual_layout_requires_immediate_row_and_unambiguous_post_offer_basis(document):
    assert DartSemanticParser().extract_tradable_share_ratio(document) is None


def test_actual_layout_uses_header_basis_not_column_order():
    table = MSBIO[MSBIO.index('<TABLE'):MSBIO.index('</TABLE>')+len('</TABLE>')]
    table = table.replace('공모 후 기준', 'TEMP').replace(
        '주식매수선택권 및<BR/>신주인수권 행사 시', '공모 후 기준'
    ).replace('TEMP', '주식매수선택권 및 신주인수권 행사 시')
    assert DartSemanticParser().extract_tradable_share_ratio(table) == 22.86
