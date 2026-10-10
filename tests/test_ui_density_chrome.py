"""Phase 1 geometry and typography, using only synthetic native Chrome preview."""
import base64
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_savings_contributions_chrome import prepare
from tests.test_settings_surface_chrome import FRAMES, no_overflow


def sample(evaluate, selector):
    return evaluate(f"""(()=>{{const e=document.querySelector({json.dumps(selector)});
      const s=getComputedStyle(e),r=e.getBoundingClientRect();return {{font:parseFloat(s.fontSize),
      width:r.width,height:r.height,left:r.left,right:r.right,top:r.top,bottom:r.bottom,
      columns:s.gridTemplateColumns.split(' ').length,color:s.color,
      padding:s.padding,scroll:e.scrollWidth,client:e.clientWidth}};}})()""")


def screenshot(call, path):
    path.write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format': 'png'})['data']))


def unchanged_styles(evaluate):
    return evaluate("""[...document.querySelectorAll(`#settingsSurface input,#settingsSurface button,
      #settingsSurface h3,#settingsSurface strong,#settingsSurface .settings-help,
      #settingsSurface .openapi-badge,#settingsSurface label`)]
      .filter(e=>!e.matches('#openapiKrxSection .form-grid>label'))
      .map(e=>({id:e.id,text:e.textContent,font:getComputedStyle(e).fontSize}))""")


def dialog_baselines(evaluate):
    return evaluate("""(()=>{const out=[];for(const d of document.querySelectorAll('dialog')){
      d.showModal();const h=d.querySelector('.dialog-head h2'),c=d.querySelector('.close');
      out.push({id:d.id,width:d.getBoundingClientRect().width,
        title:h&&getComputedStyle(h).fontSize,close:c&&[c.getBoundingClientRect().width,c.getBoundingClientRect().height]});
      d.close();}return out;})()""")


@pytest.mark.parametrize('width', [1280, 390])
@pytest.mark.parametrize('theme', ['purple', 'white', 'oled'])
def test_phase1_scoped_typography_and_geometry(chrome_preview, width, theme, tmp_path):
    call, evaluate = prepare(chrome_preview, width)
    call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 844 if width == 390 else 900,
         'deviceScaleFactor': 1, 'mobile': width == 390})
    evaluate(f"document.documentElement.dataset.theme={json.dumps(theme)}")
    wait_for(evaluate, "!![...document.styleSheets].find(s=>s.href&&s.href.includes('wealth-ui-density.css'))")
    evaluate("window.densitySheet=[...document.styleSheets].find(s=>s.href&&s.href.includes('wealth-ui-density.css'));densitySheet.disabled=true")
    old_dialogs = dialog_baselines(evaluate)
    old_settings = unchanged_styles(evaluate)
    old_asset = sample(evaluate, '#savingsGrid')
    old_card = sample(evaluate, '.saving-card')
    old_krx = sample(evaluate, '#openapiKrxSection .form-grid > label')
    evaluate('WealthSavingsContributions.open("housing")')
    old_summary = sample(evaluate, '#savingContributionSummary')
    old_savings = sample(evaluate, '#savingContributionsDialog')
    evaluate("document.getElementById('savingContributionsDialog').close();densitySheet.disabled=false")
    assert dialog_baselines(evaluate) == old_dialogs
    assert unchanged_styles(evaluate) == old_settings
    for selector in ('#openapiKrxSection .form-grid > label', '#openapiKrxPassword'):
        label_selector = selector if 'label' in selector else '#openapiKrxSection .form-grid > label:last-child'
        assert sample(evaluate, label_selector)['font'] == 11.5
    assert sample(evaluate, '#settingsSurface .openapi-label')['font'] == 11.5
    evaluate("location.hash='settings';window.dispatchEvent(new Event('hashchange'));document.getElementById('settingsApiTab').click()")
    evaluate(FRAMES)
    no_overflow(evaluate, width)
    screenshot(call, tmp_path / 'settings.png')

    evaluate("location.hash='assets';window.dispatchEvent(new Event('hashchange'));switchAccountCategory('banking')")
    evaluate(FRAMES)
    asset, card = sample(evaluate, '#savingsGrid'), sample(evaluate, '.saving-card')
    assert asset['width'] <= evaluate("document.getElementById('savingsGrid').parentElement.clientWidth") + 1
    if width == 390:
        assert card['width'] <= asset['width'] + 1
        # All four affected grids must shrink their tracks inside a narrow container.
        assert evaluate("['savingsGrid','loansGrid','insuranceGrid','realEstateGrid'].every(id=>getComputedStyle(document.getElementById(id)).gridTemplateColumns!=='360px')")
    else:
        assert asset['width'] == old_asset['width']
        assert asset['columns'] == old_asset['columns']
        assert card['width'] == old_card['width']
    no_overflow(evaluate, width)
    screenshot(call, tmp_path / 'assets.png')
    evaluate("""renderSavings(__contributions.savings,__contributions.banks,
      [{id:'loan-ui',owner:'아빠',bank_name:'가상은행',product_name:'가상 대출',current_balance:120000000,interest_rate:4.2}],'모두');
      renderInsurance([{id:'insurance-ui',owner:'아빠',insurance_type:'pension',company:'가상 보험',product_name:'가상 연금',monthly_premium:100000,total_paid_amount:8000000}],'모두');
      renderRealEstate([{id:'estate-ui',owner:'아빠',name:'가상 아파트',property_type:'apartment',current_value:300000000,purchase_price:250000000}],'모두',[]);""")
    asset_grids = {}
    for category, grid_id in [('banking', 'savingsGrid'), ('banking', 'loansGrid'),
                              ('insurance', 'insuranceGrid'), ('real_estate', 'realEstateGrid')]:
        evaluate(f'switchAccountCategory({json.dumps(category)})')
        evaluate(FRAMES)
        root_selector = '#' + grid_id
        evaluate('densitySheet.disabled=true')
        before_grid = sample(evaluate, root_selector)
        before_card = sample(evaluate, root_selector + ' .saving-card')
        evaluate('densitySheet.disabled=false')
        after_grid = sample(evaluate, root_selector)
        after_card = sample(evaluate, root_selector + ' .saving-card')
        assert after_grid['width'] > 0
        if width == 390:
            assert after_grid['width'] <= evaluate(f'document.getElementById({json.dumps(grid_id)}).parentElement.clientWidth') + 1
            assert after_card['width'] <= after_grid['width'] + 1
            assert after_card['scroll'] <= after_card['client'] + 1
        else:
            assert after_grid['width'] == before_grid['width']
            assert after_grid['columns'] == before_grid['columns']
            assert after_card['width'] == before_card['width']
        asset_grids[grid_id] = dict(before=before_grid, after=after_grid, card=after_card)
        no_overflow(evaluate, width)
    evaluate("switchAccountCategory('banking')")

    evaluate('WealthSavingsContributions.open("housing")')
    evaluate(FRAMES)
    fonts = {
        '#savingContributionsTitle': 17.5,
        '#savingContributionsDialog > p': 12,
        '#savingContributionSummary > div': 11,
        '#savingContributionSummary strong': 16,
        '#savingContributionsDialog h3': 15,
        '#savingContributionHistory .empty': 12,
        '#savingContributionForm label': 11,
        '#savingContributionForm input': 13,
        '#savingContributionSave': 12,
    }
    for selector, expected in fonts.items():
        assert sample(evaluate, selector)['font'] == expected, selector
    summary = sample(evaluate, '#savingContributionSummary')
    assert summary['columns'] == 3
    assert summary['height'] < 80
    assert sample(evaluate, '#savingContributionForm')['columns'] == (1 if width == 390 else 2)
    savings = sample(evaluate, '#savingContributionsDialog')
    assert savings['height'] < old_savings['height']
    assert savings['scroll'] <= savings['client'] + 1
    screenshot(call, tmp_path / 'savings-empty.png')
    evaluate("document.querySelectorAll('#savingContributionSummary strong')[2].textContent='₩123,456,789'")
    assert evaluate("[...document.querySelectorAll('#savingContributionSummary>div')].every(e=>e.scrollWidth<=e.clientWidth+1)")
    assert evaluate("[...document.querySelectorAll('#savingContributionSummary>div')].every(e=>{const r=e.getBoundingClientRect(),d=e.closest('dialog').getBoundingClientRect();return r.left>=d.left&&r.right<=d.right+1})")
    evaluate("""document.getElementById('savingContributionsDialog').close();
      const s=__contributions.savings.find(s=>s.id==='housing');s.contribution_opening_amount=8000000;
      s.contributions=[{id:'manual-ui',date:'2026-10-04',amount:100000,source:'manual',
        withdraw_account_name:'가상 출금통장',memo:'납입 메모',created_at:'2026-10-04'}];
      s.current_paid_amount=8100000;WealthSavingsContributions.open('housing');""")
    assert sample(evaluate, '.saving-contribution-source')['font'] == 10
    assert sample(evaluate, '.saving-contribution-row > strong')['font'] == 14
    assert sample(evaluate, '.saving-contribution-reference')['font'] == 12
    screenshot(call, tmp_path / 'savings-history.png')
    evaluate("document.getElementById('savingContributionsDialog').close();location.hash='pnl';window.dispatchEvent(new Event('hashchange'))")
    evaluate(FRAMES)
    pnl_selector = '#realizedPnlPanel .dividend-summary-cards'
    evaluate('densitySheet.disabled=true')
    old_pnl = sample(evaluate, pnl_selector)
    evaluate('densitySheet.disabled=false')
    pnl = sample(evaluate, pnl_selector)
    assert pnl['columns'] == (2 if width == 390 else 4)
    if width == 390:
        assert 150 <= pnl['height'] <= 240
        assert evaluate("(()=>{const r=[...document.querySelectorAll('#realizedPnlPanel .div-summary-card')].map(e=>e.getBoundingClientRect());return r[0].top===r[1].top&&r[2].top===r[3].top&&r[2].top>r[0].top})()")
    else:
        assert pnl['width'] == old_pnl['width']
        assert pnl['height'] == old_pnl['height']
    evaluate("document.getElementById('pnlTotalWin').textContent='+₩123,456,789';document.getElementById('pnlTotalLoss').textContent='-₩123,456,789'")
    assert evaluate("[...document.querySelectorAll('#realizedPnlPanel .div-summary-card')].every(e=>e.scrollWidth<=e.clientWidth+1)")
    no_overflow(evaluate, width)
    screenshot(call, tmp_path / 'pnl-long-values.png')
    assert evaluate('__settingsProbe.errors') == []
    assert evaluate('__contributions.writes.length') == 0
    (tmp_path / 'measurements.json').write_text(json.dumps(dict(width=width, theme=theme,
        savings_before=old_savings, savings_after=savings, summary_before=old_summary,
        summary_after=summary, krx_before=old_krx, krx_after=sample(evaluate, '#openapiKrxSection .form-grid > label'),
        asset_before=old_asset, asset_after=asset, card_before=old_card, card_after=card,
        pnl_before=old_pnl, pnl_after=pnl, asset_grids=asset_grids,
        global_dialogs=old_dialogs), indent=2), encoding='utf-8')
