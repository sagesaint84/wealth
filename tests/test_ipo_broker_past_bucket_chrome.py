"""Native Chrome display regressions using only synthetic snapshots/portfolios."""
import pytest

from tests.test_workflow_ux_chrome import chrome_preview, start, click, no_overflow, FRAMES, attach_broker_metadata


@pytest.mark.parametrize('width', [1280, 390])
def test_normalized_brokers_all_period_past_and_month_restoration(chrome_preview, width):
    call, evaluate = start(chrome_preview, width, 'ipo')
    evaluate(r'''(()=>{
      const row=(id,managers,date,status='PAST')=>({ipo_id:id,company_name:id,lead_managers:managers,filter_group:status,presentation_sort_date:date,subscription_start:date});
      __rows=[
        row('samsung-new',['삼성증권'],'2026-09-20'),row('samsung-old',['삼성증권(주)'],'2026-03-12'),
        row('mira-new',['미래에셋증권'],'2026-09-21'),row('mira-old',['미래에셋증권 주식회사'],'2026-04-12'),
        row('multi',['삼성증권(주)','미래에셋증권 주식회사'],'2026-08-15'),
        row('daishin',['대신증권'],'2026-09-01'),row('daishin-legal',['대신증권(주)'],'2026-05-01'),
        row('leading',['주식회사 상상인증권'],'2026-06-01'),
        row('branch',['골드만삭스증권 서울지점'],'2026-07-01'),
        row('yu-short',['유진증권'],'2026-07-01'),row('yu-full',['유진투자증권'],'2026-07-02'),
        row('future',['삼성증권(주)'],'2026-10-12','UPCOMING'),row('active',['삼성증권'],'2026-10-08','ACTIVE'),
        row('nodate',['삼성증권(주)'],'')
      ];
      __raw=JSON.stringify(__rows);
      WealthIpoState.setMarketIpos(__rows);WealthIpoState.setFilterGroup('ALL');
      WealthIpoState.setHistoryYear(2026);WealthIpoState.setHistoryMonth(10);WealthIpoState.setMonthExplicitlySelected(true);WealthIpoState.renderIpoList();
      __options=()=>[...document.querySelector('#ipoBrokerFilter').options].map(o=>o.textContent);
      __choose=name=>{const s=document.getElementById('ipoBrokerFilter');s.value=[...s.options].find(o=>o.textContent===name).value;s.dispatchEvent(new Event('change',{bubbles:true}))};
      __ids=()=>[...document.querySelectorAll('.ipo-card')].map(c=>c.dataset.ipoId);
    })()''')
    attach_broker_metadata(evaluate, '__rows')
    evaluate('__raw=JSON.stringify(__rows)')
    options = evaluate('__options()')
    for name in ['삼성증권', '미래에셋증권', '대신증권', '상상인증권', '골드만삭스증권']:
        assert options.count(name) == 1
    assert '유진증권' not in options and options.count('유진투자증권') == 1
    assert all('(주)' not in value and '주식회사' not in value and '서울지점' not in value for value in options)
    evaluate("__choose('삼성증권')")
    assert evaluate("document.getElementById('ipoBrokerFilter').value") == 'samsung'
    click(call, evaluate, '[data-filter-group="PAST"]')
    assert evaluate('__ids()') == ['samsung-new', 'multi', 'samsung-old', 'nodate']
    assert evaluate("document.querySelector('.ipo-month-control')===null")
    assert evaluate("['ipoPrevMonthBtn','ipoNextMonthBtn','ipoTodayMonthBtn','ipoMonthPicker'].every(id=>!document.getElementById(id))")
    assert evaluate("document.getElementById('ipoListWrapper').textContent.includes('선택한 월')") is False
    assert evaluate("document.querySelector('[data-filter-group=PAST]').textContent") == '과거 4'
    assert evaluate('[WealthIpoState.getHistoryYear(),WealthIpoState.getHistoryMonth()]') == [2026, 10]
    evaluate("__choose('미래에셋증권')")
    assert evaluate("document.getElementById('ipoBrokerFilter').value") == 'mirae'
    assert evaluate('__ids()') == ['mira-new', 'multi', 'mira-old']
    evaluate("__choose('유진투자증권')")
    assert evaluate("document.getElementById('ipoBrokerFilter').value") == 'eugene'
    assert evaluate('__ids()') == ['yu-full', 'yu-short']
    evaluate("__choose('삼성증권')")
    for group, expected in [('ALL', ['active', 'future', 'nodate']), ('UPCOMING', ['future']), ('ACTIVE', ['active'])]:
        click(call, evaluate, f'[data-filter-group="{group}"]')
        assert evaluate("document.getElementById('ipoMonthPicker').value") == '2026-10'
        assert evaluate('__ids()') == expected
        assert evaluate("document.getElementById('ipoBrokerFilter').value") == 'samsung'
        click(call, evaluate, '[data-filter-group="PAST"]')
    assert evaluate('__raw===JSON.stringify(WealthIpoState.getCanonicalMarketIpos())')
    no_overflow(evaluate, width)
    evaluate("__rows=[{...__rows[0],lead_managers:['(주)비엔케이투자증권']}]")
    attach_broker_metadata(evaluate, '__rows')
    assert evaluate('__options()') == ['전체 증권사', 'BNK투자증권']
    assert evaluate("document.getElementById('ipoBrokerFilter').value") == ''
    assert evaluate('__ids()') == ['samsung-new']
    no_overflow(evaluate, width)


@pytest.mark.parametrize('width', [1280, 390])
def test_compact_bucket_details_typography_badges_toggle_and_owner(chrome_preview, width):
    call, evaluate = start(chrome_preview, width, 'invest')
    click(call, evaluate, '[data-invest="buckets"]')
    evaluate("__view.holdings[0].name='KoAct 미국나스닥성장기업액티브 아주 긴 종목명';window.dispatchEvent(new CustomEvent('wealth:portfolio',{detail:__view}))")
    evaluate(FRAMES)
    assert evaluate("document.querySelector('.wealth-bucket-contents [role=status]').textContent") == '5건 · 합계 1,800원'
    styles = evaluate(r'''(()=>{
      const css=s=>getComputedStyle(document.querySelector(s));
      return {title:css('.wealth-bucket-contents > h4').fontSize,weight:css('.wealth-bucket-contents > h4').fontWeight,
        status:css('.wealth-bucket-contents > [role=status]').fontSize,row:css('.wealth-bucket-constituent').fontSize,
        name:css('.wealth-bucket-holding').fontSize,value:css('.wealth-bucket-value').fontSize,
        align:css('.wealth-bucket-value').textAlign,numbers:css('.wealth-bucket-value').fontVariantNumeric,
        badge:css('.wealth-bucket-badge').fontSize,padding:css('.wealth-bucket-constituent').paddingTop,
        columns:css('.wealth-bucket-constituent').gridTemplateColumns.split(' ').length};
    })()''')
    assert styles == {'title': '15px', 'weight': '600', 'status': '12px', 'row': '12px', 'name': '13px',
                      'value': '13px', 'align': 'right', 'numbers': 'tabular-nums', 'badge': '11px', 'padding': '8px',
                      'columns': 2 if width == 390 else 4}
    for theme in ['purple', 'white', 'oled']:
        evaluate(f"document.documentElement.dataset.theme='{theme}'")
        colors = evaluate("[...document.querySelectorAll('.wealth-bucket-badge')].map(e=>getComputedStyle(e).getPropertyValue('--bucket-color').trim())")
        assert colors == ['#A78BFA', '#FB7185', '#FB7185', '#A78BFA', '#697386']
        no_overflow(evaluate, width)
    if width == 390:
        assert evaluate("(()=>{const r=document.querySelectorAll('.wealth-bucket-constituent')[2];return r.querySelector('.wealth-bucket-value').getBoundingClientRect().top>=r.querySelector('.wealth-bucket-holding').getBoundingClientRect().bottom})()")
        assert evaluate("getComputedStyle(document.querySelector('.wealth-bucket-holding')).textOverflow") != 'ellipsis'
    click(call, evaluate, '[data-bucket-filter="growth"]')
    assert evaluate("document.querySelector('.wealth-bucket-contents [role=status]').textContent") == '2건 · 합계 700원'
    assert evaluate("[...document.querySelectorAll('.wealth-bucket-constituent')].every(r=>r.dataset.bucketId==='growth')")
    click(call, evaluate, '[data-bucket-filter="growth"]')
    assert evaluate("document.querySelectorAll('.wealth-bucket-constituent').length") == 5
    click(call, evaluate, '[data-bucket-filter="core"]')
    evaluate("window.dispatchEvent(new CustomEvent('wealth:portfolio',{detail:{...__view,owner:'엄마',accounts:[__view.accounts[1]]}}))")
    assert evaluate("document.querySelector('.wealth-bucket-contents [role=status]').textContent") == '2건 · 합계 900원'
    assert evaluate("document.querySelectorAll('[data-bucket-filter][aria-pressed=true]').length") == 0
    assert evaluate('__requests.length') == 0
    no_overflow(evaluate, width)
