"""Native dialog geometry and role hierarchy with synthetic, read-only data."""
import base64
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_savings_contributions_chrome import BOOT
from tests.test_settings_surface_chrome import FRAMES, click, no_overflow, start


SIZES = {
    'compact': 'accountCashDialog ledgerCardPayDialog familyManagerDialog forcePasswordModal changePasswordModal'.split(),
    'wide': 'ipoHistoricalImportDialog accountImportDialog importDialog accountEditDialog insuranceAccountDialog realEstateDialog ledgerCardsDialog ledgerExcelDialog pnlImportDialog adminUsersModal'.split(),
    'xwide': ['stockChartDialog'],
    'standard': 'holdingDialog dividendImportDialog assetRecordDialog accountAddDialog bankAccountDialog savingAccountDialog savingContributionsDialog nationalPensionHistoryDialog loanAccountDialog realEstateSellDialog ledgerTxDialog ledgerRecurringDialog dividendRecordDialog pnlRecordDialog ipoManualSaleDialog wealth-history-dialog'.split(),
}
WIDTHS = {'compact': 500, 'standard': 620, 'wide': 760, 'xwide': 900}
GUARD = r'''
window.__dialogProbe={mutations:[],charts:[],emptyChart:false};
const dialogFetch=window.fetch;
window.fetch=async function(url,options={}){
 const address=new URL(String(url),location.href),method=(options.method||'GET').toUpperCase();
 if(address.origin!==location.origin)throw new Error('External request prohibited');
 if(!['GET','HEAD'].includes(method)){
  __dialogProbe.mutations.push({url:String(url),method});
  if(address.pathname==='/api/refresh-prices')return {ok:false,status:503,json:async()=>({detail:'Read-only synthetic preview'})};
  throw new Error('Mutation prohibited');
 }
 if(address.pathname.startsWith('/api/stock-chart/')){
  __dialogProbe.charts.push(address.search);
  const candles=__dialogProbe.emptyChart?[]:Array.from({length:20},(_,i)=>({date:`2026-10-${String(i+1).padStart(2,'0')}`,close:10000+i*100,volume:1000+i*10}));
  return {ok:true,status:200,json:async()=>({candles})};
 }
 if(address.pathname==='/api/auth/me'&&__dialogProbe.forcePassword){
  const response=await dialogFetch.apply(this,arguments),data=await response.json();
  return {ok:true,status:200,json:async()=>({...data,must_change_password:true})};
 }
 return dialogFetch.apply(this,arguments);
};
'''
MEASURE = r'''(()=>{
const box=e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};};
const d=document.querySelector('dialog[open]'),h=d.querySelector('.dialog-head h2'),c=d.querySelector('.dialog-head .close');
const localScroll=e=>{for(let p=e.parentElement;p&&p!==d;p=p.parentElement)if(['auto','scroll'].includes(getComputedStyle(p).overflowX))return true;return false;};
const overflow=[...d.querySelectorAll('input,select,textarea,button,p,h2,h3,h4,.form-grid,.admin-table-wrap')]
 .filter(e=>e.getClientRects().length&&!localScroll(e)).filter(e=>{const r=e.getBoundingClientRect(),b=box(d);return r.left<b.left-1||r.right>b.right+1;})
 .map(e=>e.id||e.className||e.tagName);
const roles={};for(const [name,selector] of Object.entries({description:'.dialog-description,.ipo-manual-sale-note',subheading:'.dialog-subheading',empty:'.dialog-empty,#ledgerCardsList .empty,#ledgerRecurringList .empty,.admin-empty-cell'})){
 roles[name]=[...d.querySelectorAll(selector)].filter(e=>e.getClientRects().length).map(e=>({font:parseFloat(getComputedStyle(e).fontSize),line:getComputedStyle(e).lineHeight,color:getComputedStyle(e).color}));}
return {id:d.id||'wealth-history-dialog',className:d.className,box:box(d),title:h&&box(h),titleFont:h&&getComputedStyle(h).fontSize,
close:c&&box(c),closeName:c&&(c.getAttribute('aria-label')||c.textContent),scroll:d.scrollWidth,client:d.clientWidth,overflow,roles,
controls:[...d.querySelectorAll('input,select,textarea')].filter(e=>e.getClientRects().length).map(e=>({id:e.id,width:box(e).width,height:box(e).height,font:getComputedStyle(e).fontSize}))};
})()'''


def screenshot(call, path):
    path.write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format': 'png'})['data']))


def fits(row, width):
    assert row['box']['left'] >= -1, row
    assert row['box']['right'] <= width + 1, row
    assert row['scroll'] <= row['client'] + 1, row
    assert not row['overflow'], row
    if row['close']:
        close, title, bounds = row['close'], row['title'], row['box']
        assert 40 <= close['width'] <= 46 and 40 <= close['height'] <= 46, row
        assert bounds['left'] <= close['left'] < close['right'] <= bounds['right'], row
        assert bounds['top'] <= close['top'] < close['bottom'] <= bounds['bottom'], row
        assert title['right'] <= close['left'] + 1, row
        assert row['closeName'] != '×', row
    else:
        assert row['id'] == 'forcePasswordModal', row


@pytest.mark.parametrize('width', [1280, 390])
@pytest.mark.parametrize('theme', ['purple', 'white', 'oled'])
def test_all_dialog_roles_geometry_and_readonly_lifecycle(chrome_preview, width, theme, tmp_path):
    call, evaluate = start(chrome_preview, width, BOOT + GUARD)
    call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 844 if width == 390 else 900,
         'deviceScaleFactor': 1, 'mobile': width == 390})
    wait_for(evaluate, "document.querySelectorAll('dialog').length===32&&!!window.WealthSavingsContributions")
    # Authentication's existing price-refresh POST is synthetic in GUARD. Measure
    # dialog actions separately from that initial page bootstrap request.
    evaluate('window.bootstrapMutations=__dialogProbe.mutations.splice(0)')
    assert all(item['url'] == '/api/refresh-prices' for item in evaluate('bootstrapMutations'))
    evaluate("document.querySelector('.toast')?.classList.remove('show')")
    evaluate(f"document.documentElement.dataset.theme={json.dumps(theme)}")
    evaluate("currentOwner='모두';renderSavings(__contributions.savings,__contributions.banks,[],'모두');WealthSavingsContributions.open('housing')")
    evaluate("document.getElementById('savingContributionsDialog').close();renderLedgerCardsList([]);openLedgerRecurringModal();document.getElementById('ledgerRecurringDialog').close()")
    evaluate("document.getElementById('adminUserListTbody').innerHTML='<tr><td class=admin-empty-cell colspan=4>등록된 사용자가 없습니다.</td></tr>'")
    evaluate("openStockChart('SYN','가상 종목',10000,'KRW')")
    wait_for(evaluate, "!!document.querySelector('#stockChartContainer svg')")
    evaluate("document.getElementById('stockChartDialog').close()")
    evaluate("window.dialogSheet=[...document.styleSheets].find(s=>s.href&&s.href.includes('wealth-dialog-system.css'))")
    # Width/header changes must preserve form-control typography and dimensions.
    form_styles = r'''[...document.querySelectorAll('dialog label,dialog input,dialog select,dialog textarea,dialog .button')]
      .filter(e=>!e.matches('.close')).map(e=>{const s=getComputedStyle(e);return [e.id,e.name,s.fontSize,s.fontWeight,s.lineHeight,s.padding,s.height];})'''
    evaluate('dialogSheet.disabled=true')
    old_styles = evaluate(form_styles)
    old_titles = evaluate("""(()=>{const fonts={};for(const d of document.querySelectorAll('dialog')){
      d.showModal();fonts[d.id||'wealth-history-dialog']=getComputedStyle(d.querySelector('.dialog-head h2')).fontSize;d.close();}return fonts;})()""")
    evaluate('dialogSheet.disabled=false')
    assert evaluate(form_styles) == old_styles
    rows = []
    representatives = {'familyManagerDialog', 'savingContributionsDialog', 'ledgerCardsDialog', 'stockChartDialog', 'adminUsersModal'}
    for size, ids in SIZES.items():
        for dialog_id in ids:
            selector = '.wealth-history-dialog' if dialog_id == 'wealth-history-dialog' else '#' + dialog_id
            evaluate(f"document.querySelector({json.dumps(selector)}).showModal()")
            evaluate(FRAMES)
            row = evaluate(MEASURE)
            rows.append(row)
            fits(row, width)
            assert row['box']['width'] == (366 if width == 390 else WIDTHS[size]), row
            assert row['titleFont'] == old_titles[dialog_id], row
            for role in row['roles']['description']:
                assert role['font'] == 12, row
            for role in row['roles']['subheading']:
                assert role['font'] == (15 if dialog_id == 'savingContributionsDialog' else 14), row
            for role in row['roles']['empty']:
                assert role['font'] == 12, row
            if dialog_id == 'adminUsersModal':
                assert evaluate("document.querySelector('#adminUsersModal .admin-empty-cell').getBoundingClientRect().width<=document.querySelector('#adminUsersModal .admin-table-wrap').clientWidth+1")
            if dialog_id in representatives:
                screenshot(call, tmp_path / f'{dialog_id}-{width}-{theme}.png')
            evaluate(f"document.querySelector({json.dumps(selector)}).close()")
    (tmp_path / 'dialog-matrix.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    # Data tables keep their intentional local scroll; only empty tables shrink.
    evaluate("document.getElementById('adminUserListTbody').innerHTML='<tr><td>synthetic</td><td>일반 사용자</td><td>활성</td><td>관리</td></tr>';document.getElementById('adminUsersModal').showModal()")
    fits(evaluate(MEASURE), width)
    if width == 390:
        assert evaluate("document.querySelector('#adminUsersModal .admin-table-wrap').scrollWidth>document.querySelector('#adminUsersModal .admin-table-wrap').clientWidth")
    evaluate("document.getElementById('adminUsersModal').close()")
    # A long Korean title exercises wrapping independently of existing short titles.
    for dialog_id in ('familyManagerDialog', 'holdingDialog', 'adminUsersModal', 'stockChartDialog'):
        evaluate(f"window.longDialog=document.getElementById({json.dumps(dialog_id)});window.longTitle=longDialog.querySelector('.dialog-head h2');window.oldTitle=longTitle.innerHTML;longTitle.textContent='매우 긴 예·적금 상품 및 자동이체 납입 내역 관리';longDialog.showModal()")
        evaluate(FRAMES)
        fits(evaluate(MEASURE), width)
        evaluate('longDialog.close();longTitle.innerHTML=oldTitle')
    # Real close delegation and Escape remain usable; forced-password stays mandatory.
    evaluate("document.getElementById('holdingDialog').showModal()")
    click(call, evaluate, '#holdingDialog .close')
    assert not evaluate("document.getElementById('holdingDialog').open")
    evaluate("document.getElementById('holdingDialog').showModal()")
    call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Escape', 'code': 'Escape', 'windowsVirtualKeyCode': 27})
    call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Escape', 'code': 'Escape', 'windowsVirtualKeyCode': 27})
    evaluate(FRAMES)
    assert not evaluate("document.getElementById('holdingDialog').open")
    evaluate("openStockChart('SYN','가상 종목',10000,'KRW')")
    wait_for(evaluate, "!!document.querySelector('#stockChartContainer svg')")
    click(call, evaluate, '#stockChartPeriodTabs [data-period="1W"]')
    wait_for(evaluate, "document.querySelector('#stockChartPeriodTabs [data-period=\"1W\"]').classList.contains('active')&&document.getElementById('stockChartContainer').textContent.includes('60분봉')")
    assert '?period=1W' in evaluate('__dialogProbe.charts')
    for resized in (390, 1280, width):
        call('Emulation.setDeviceMetricsOverride', {'width': resized, 'height': 900, 'deviceScaleFactor': 1, 'mobile': resized == 390})
        evaluate(FRAMES)
        fits(evaluate(MEASURE), resized)
        assert evaluate("document.querySelector('#stockChartContainer svg').getBoundingClientRect().width<=document.getElementById('stockChartContainer').clientWidth+1")
    evaluate("document.getElementById('stockChartDialog').close()")
    no_overflow(evaluate, width)
    evaluate('__dialogProbe.forcePassword=true;initAuthSession()')
    wait_for(evaluate, "document.getElementById('forcePasswordModal').open")
    call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Escape', 'code': 'Escape', 'windowsVirtualKeyCode': 27})
    call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Escape', 'code': 'Escape', 'windowsVirtualKeyCode': 27})
    evaluate(FRAMES)
    assert evaluate("document.getElementById('forcePasswordModal').open")
    evaluate("document.getElementById('forcePasswordModal').close()")
    assert evaluate('__dialogProbe.mutations') == []
    assert evaluate('__contributions.writes') == []
    assert evaluate('__settingsProbe.errors') == []


@pytest.mark.parametrize('width', [1280, 390])
def test_global_actions_and_split_date_inputs(chrome_preview, width):
    call, evaluate = start(chrome_preview, width, BOOT + GUARD + r"""
const guardedFetch = window.fetch;
window.__permissionFailures = [];
window.__dividendPreviewRequests = [];
window.fetch = async function(input, options) {
  const address = new URL(input instanceof Request ? input.url : String(input), location.href);
  const method = (options?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
  if (address.origin === location.origin && address.pathname === '/api/actual-dividends/estimate' &&
      !address.search && method === 'POST') {
    __dividendPreviewRequests.push({path: address.pathname, method});
    return Response.json({tax_type_label: '합성 세금', estimated: true, gross_amount: 0, tax: 0});
  }
  const response = await guardedFetch.apply(this, arguments);
  if ([401, 403].includes(response.status)) __permissionFailures.push(response.status);
  return response;
};
""")
    wait_for(evaluate, "WealthStartup.canRead() && !loadAssetDataForUser.pending")
    assert evaluate("typeof WealthGlobalActionController.bind === 'function' && typeof setupAutoAdvancingDateInput === 'function'")
    startup = evaluate('__dialogProbe.mutations.splice(0)')
    assert all(item['url'] == '/api/refresh-prices' for item in startup)

    def route(name, ready):
        evaluate(f"location.hash={json.dumps(name)}")
        wait_for(evaluate, ready)

    def open_and_close(button, dialog):
        count = evaluate('__settingsProbe.dialogs')
        click(call, evaluate, button)
        wait_for(evaluate, f"document.getElementById('{dialog}').open")
        assert evaluate('__settingsProbe.dialogs') == count + 1
        click(call, evaluate, f'#{dialog} .close')
        assert not evaluate(f"document.getElementById('{dialog}').open")

    route('assets', "document.querySelector('.wealth-workspace').dataset.activeView === 'assets'")
    click(call, evaluate, '#topbarFamilyTabs [data-owner="아빠"]')
    assert evaluate("currentOwner === '아빠'")
    for category, button, dialog in [
        ('securities', '#addAccountBtn', 'accountAddDialog'),
        ('banking', '#addBankIntegratedBtn', 'bankAccountDialog'),
        ('real_estate', '#addRealEstateBtn', 'realEstateDialog'),
    ]:
        click(call, evaluate, f'.account-cat-tab[data-cat="{category}"]')
        assert evaluate('WealthAssetCategoryState.current()') == category
        open_and_close(button, dialog)

    for tab, button, dialog in [
        ('pnl', '#addPnlBtn', 'pnlRecordDialog'),
        ('dividend', '#addDividendBtn', 'dividendRecordDialog'),
    ]:
        route(tab, f"document.querySelector('.wealth-workspace').dataset.incomeTab === '{tab}'")
        open_and_close(button, dialog)
    evaluate('__settingsProbe.confirmAllowed=false')
    confirm_count = evaluate('__settingsProbe.confirms.length')
    click(call, evaluate, '#clearAllDividendBtn')
    assert evaluate('__settingsProbe.confirms.length') == confirm_count + 1
    assert evaluate('__dialogProbe.mutations') == []
    assert evaluate('__permissionFailures') == []
    assert evaluate('__settingsProbe.errors') == []
    print(f'GLOBAL_ACTION_{width}=PASS', flush=True)

    callers = {
        'pnlSplitDateWrap': 'pnlRecordDialog',
        'divSplitDateWrap': 'dividendRecordDialog',
        'ledgerTxSplitDateWrap': 'ledgerTxDialog',
        'ledgerPaySplitDateWrap': 'ledgerCardPayDialog',
    }

    def show_date_fields(wrapper, dialog):
        evaluate(f"""
        (() => {{
          document.getElementById('{dialog}').showModal();
          const wrap = document.getElementById('{wrapper}');
          window.__dateParts = [...wrap.querySelectorAll('.date-part')];
          window.__dateNative = wrap.querySelector('input[type=date]');
        }})()
        """)

    def close_date_fields(dialog):
        evaluate(f"document.getElementById('{dialog}').close()")

    def type_text(text):
        call('Input.insertText', {'text': text})

    for wrapper, dialog in callers.items():
        show_date_fields(wrapper, dialog)
        assert evaluate(f"document.getElementById('{wrapper}').dataset.autoAdvancingInit") == 'true'
        evaluate("""
        __dateNative.value='2025-04-03';
        """)
        assert evaluate('__dateParts.map(part => part.value)') == ['2025', '04', '03']
        assert evaluate(f"""
        (() => {{
          const original = document.getElementById('{wrapper}')._syncFromNative;
          setupAutoAdvancingDateInput('#{wrapper}');
          setupAutoAdvancingDateInput('#{wrapper}');
          return original === document.getElementById('{wrapper}')._syncFromNative;
        }})()
        """), wrapper
        evaluate("""
        window.__nativeDateEvents = [];
        for (const kind of ['input', 'change']) {
          __dateNative.addEventListener(kind, event => __nativeDateEvents.push([event.type, event.target.value]));
        }
        __dateParts.forEach(part => { part.value=''; });
        __dateParts[0].focus();
        """)
        type_text('2024')
        assert evaluate('document.activeElement === __dateParts[1]'), wrapper
        type_text('2')
        assert evaluate('document.activeElement === __dateParts[2]'), wrapper
        type_text('29')
        assert evaluate('__dateNative.value') == '2024-02-29', wrapper
        assert evaluate('__nativeDateEvents') == [['input', '2024-02-29'], ['change', '2024-02-29']], wrapper

        evaluate("""
        (() => {
          const clipboardData = new DataTransfer();
          clipboardData.setData('text/plain', '2025/4/1');
          __dateParts[0].focus();
          __dateParts[0].dispatchEvent(new ClipboardEvent('paste', {clipboardData, bubbles: true, cancelable: true}));
        })()
        """)
        assert evaluate('__dateNative.value') == '2025-04-01', wrapper
        assert evaluate('document.activeElement === __dateParts[2]'), wrapper
        evaluate('__dateParts[2].select()')
        type_text('31')
        assert evaluate('__dateNative.value') == '2025-04-30', wrapper
        assert evaluate('__dateParts[2].value') == '30', wrapper
        close_date_fields(dialog)
        print(f'{width}px {wrapper}: focus, native value/events, paste, leap day, month end and repeat bind PASS', flush=True)

    for wrapper, dialog in callers.items():
        show_date_fields(wrapper, dialog)
        evaluate("""
        __dateNative.value='2024-02-29';
        window.__composition = [];
        __dateParts[2].addEventListener('input', event => {
          if (event.isComposing) __composition.push(event.data);
        });
        __dateParts[2].focus();
        __dateParts[2].setSelectionRange(0, 2);
        """)
        call('Input.imeSetComposition', {'text': '한', 'selectionStart': 1, 'selectionEnd': 1})
        assert evaluate('__composition') == ['한'], wrapper
        assert evaluate('__dateNative.value') == '2024-02-29', wrapper
        assert evaluate('document.activeElement === __dateParts[2]'), wrapper
        assert evaluate('__dateParts[2].value') == '한', f'{wrapper}: composing text was overwritten'
        call('Input.imeSetComposition', {'text': '', 'selectionStart': 0, 'selectionEnd': 0})
        close_date_fields(dialog)

    for wrapper, dialog in callers.items():
        show_date_fields(wrapper, dialog)
        for index, committed, expected, next_focus in [
            (0, '2025', '2025-04-15', 1),
            (1, '6', '2024-06-15', 2),
            (2, '30', '2024-04-30', 2),
        ]:
            for text, final_date in [('한', '2024-04-15'), (committed, expected)]:
                evaluate(f"""
                __dateNative.value='2024-04-15';
                __nativeDateEvents.length=0;
                window.__imePart=__dateParts[{index}];
                __imePart.focus();
                __imePart.select();
                """)
                end = len(text)
                call('Input.imeSetComposition', {'text': text, 'selectionStart': end, 'selectionEnd': end})
                assert evaluate('__imePart.value') == text, (wrapper, index, text)
                assert evaluate('document.activeElement === __imePart'), (wrapper, index)
                assert evaluate('__dateNative.value') == '2024-04-15', (wrapper, index)
                assert evaluate('__nativeDateEvents') == [], (wrapper, index)
                type_text(text)
                assert evaluate('__dateNative.value') == final_date, (wrapper, index, text)
                if text == '한':
                    assert evaluate('__imePart.value') == '', (wrapper, index)
                    assert evaluate('document.activeElement === __imePart'), (wrapper, index)
                    assert evaluate('__nativeDateEvents') == [], (wrapper, index)
                else:
                    assert evaluate(f'document.activeElement === __dateParts[{next_focus}]'), (wrapper, index)
                    assert evaluate('__imePart.value') == final_date.split('-')[index], (wrapper, index)
                    events = [['input', final_date], ['change', final_date]]
                    assert evaluate('__nativeDateEvents') == events, (wrapper, index)
                    evaluate("__imePart.dispatchEvent(new InputEvent('input', {inputType:'insertCompositionText', bubbles:true}))")
                    assert evaluate('__nativeDateEvents') == events, (wrapper, index)
        close_date_fields(dialog)
    assert evaluate('__dialogProbe.mutations') == []
    assert evaluate('__permissionFailures') == []
    assert evaluate('__settingsProbe.errors') == []
    assert not [event for event in evaluate.load_errors if event.get('method') == 'Runtime.exceptionThrown']
    wait_for(evaluate, '__dividendPreviewRequests.length > 0')
    preview_requests = evaluate('__dividendPreviewRequests')
    assert all(request == {'path': '/api/actual-dividends/estimate', 'method': 'POST'} for request in preview_requests)
    assert evaluate('__dialogProbe.mutations') == []
    print(f'READONLY_PREVIEW_POST_{width}={len(preview_requests)} MUTATION_REQUESTS_{width}=0', flush=True)
    print(f'SPLIT_DATE_{width}=PASS', flush=True)
