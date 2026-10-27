"""Panel collapse is absent, not CSS-hidden; tabs/details/lazy work survive."""
import json
from pathlib import Path

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_home_three_tabs_chrome import BOOT as HOME
from tests.test_ledger_single_renderer_chrome import BOOT as LEDGER
from tests.test_static_transport_chrome import PROFILE, transport_server

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'app/static'
OLD_KEY='collapsed_sections'
OLD_KEYS=['summary','records','heatmap','dividend','pnl','market','accounts','holdings','ledger','calendar','ipo']


def test_panel_collapse_code_markup_and_styles_are_really_removed():
    forbidden=['section-collapse-btn','section-collapsible-content','is-collapsed',
               'SECTION_MAP','getCollapsedSections','saveCollapsedSections','toggleSection',
               'applySectionCollapsedState','initCollapsedSections',OLD_KEY]
    for path in STATIC.iterdir():
        if path.suffix not in {'.js','.css','.html'}:continue
        source=path.read_text(encoding='utf-8')
        assert not any(token in source for token in forbidden),path.name


def test_functional_details_tabs_and_ledger_wrapper_are_retained():
    html=(STATIC/'index.html').read_text(encoding='utf-8')
    for marker in ['id="ledgerSectionContent"','id="ledgerOcrPanel"','id="npAnalysis-annual_details"',
                   'id="homeTabs"','id="adminSystemTab"','id="adminUpdatePermissionApproval"']:
        assert marker in html,marker
    assert '<details' in html and '<summary>① 납부 현황' in html
    layout=(STATIC/'wealth-layout.js').read_text(encoding='utf-8')
    assert "disclosure.className = 'wealth-danger-zone'" in layout
    assert "disclosure.append(danger)" in layout


def probe(theme,seed):
    return f"""
    window.__expanded={{storage:[],badFrames:0,heatmaps:0}};
    const expGet=Storage.prototype.getItem,expSet=Storage.prototype.setItem,expRemove=Storage.prototype.removeItem;
    expSet.call(localStorage,{json.dumps(OLD_KEY)},{json.dumps(seed)});
    expSet.call(localStorage,'app_theme',{json.dumps(theme)});
    __expanded.readOld=()=>expGet.call(localStorage,{json.dumps(OLD_KEY)});
    for(const [name,original] of [['getItem',expGet],['setItem',expSet],['removeItem',expRemove]]){{
      Storage.prototype[name]=function(key,...args){{
        if(key==={json.dumps(OLD_KEY)})__expanded.storage.push(name);
        return original.call(this,key,...args);
      }};
    }}
    const expFrame=()=>{{if(document.querySelector('.section-collapse-btn,.panel.is-collapsed'))__expanded.badFrames++;requestAnimationFrame(expFrame);}};
    requestAnimationFrame(expFrame);
    """


def ready(evaluate):
    wait_for(evaluate,"typeof startupIncomeReuse!=='undefined' && startupIncomeReuse===false && !!window.WealthUnifiedTimeseries && WealthStartup.canRead() && __transport.pending===0")


def visible(evaluate,selector):
    wait_for(evaluate,f"!!document.querySelector({json.dumps(selector)})?.getClientRects().length")


def route(evaluate,hash_value,selector):
    evaluate(f'location.hash={json.dumps(hash_value)}')
    visible(evaluate,selector)


@pytest.mark.parametrize('width',[320,360,390,768,1280])
@pytest.mark.parametrize('theme',['purple','white','oled'])
def test_old_storage_cannot_collapse_routes_and_resize_stays_lazy(chrome_preview,width,theme):
    call,evaluate,_=chrome_preview
    seed='not-json' if theme=='white' else json.dumps(OLD_KEYS+['obsolete'])
    call('Page.addScriptToEvaluateOnNewDocument',{'source':probe(theme,seed)+PROFILE+LEDGER+HOME})
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<500})
    with transport_server(True) as port:
        call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home'})
        ready(evaluate)
        assert evaluate("document.getElementById('wealthAssetNetWorth').textContent")=='397,000,000원'
        assert evaluate("document.getElementById('classificationList').children.length")==0
        assert evaluate("document.getElementById('holdingsBody').children.length")==0
        assert evaluate('__tabs.markets')==0
        assert evaluate('__ledgerCalls.length')==0
        for path in ['/api/refresh-prices','/api/dashboard','/api/planning/snapshot-all']:
            assert evaluate(f'__transport.api.filter(r=>r.path==={json.dumps(path)}).length')==1,path
        route(evaluate,'home/history','#wealthHistoryPlot svg')
        route(evaluate,'home/markets','#marketGrid')
        wait_for(evaluate,'__tabs.markets===1')
        route(evaluate,'invest','#summaryPanel')
        evaluate("document.querySelector('[data-invest=heatmap]').click()")
        visible(evaluate,'#assetHeatmapContainer .heatmap-tile')
        evaluate('window.__expRender=renderHeatmaps;renderHeatmaps=function(...args){__expanded.heatmaps++;return __expRender.apply(this,args)}')
        new_width=390 if width==1280 else 1280
        call('Emulation.setDeviceMetricsOverride',{'width':new_width,'height':900,'deviceScaleFactor':1,'mobile':new_width<500})
        evaluate("window.dispatchEvent(new Event('resize'))")
        wait_for(evaluate,'heatmapResizeTimer===null && __expanded.heatmaps>0')
        assert evaluate("(()=>{const c=document.getElementById('assetHeatmapContainer'),r=c.getBoundingClientRect();return [...c.querySelectorAll('.heatmap-tile')].every(t=>t.getBoundingClientRect().right<=r.right+2)})()")
        evaluate("document.querySelector('#assetHeatmapContainer .heatmap-tile').click()")
        assert evaluate("document.getElementById('searchInput').value.trim().length")>0
        evaluate("document.querySelector('[data-invest=holdings]').click()")
        visible(evaluate,'#holdingsBody tr')
        evaluate("__expanded.heatmaps=0;window.dispatchEvent(new Event('resize'))")
        wait_for(evaluate,'heatmapResizeTimer===null')
        assert evaluate('__expanded.heatmaps')==0
        evaluate("document.querySelector('[data-invest=records]').click()")
        visible(evaluate,'#recordsPanel .records-grid')
        route(evaluate,'assets','#accountsPanel')
        evaluate("document.querySelector('#assetCategoryTabs [data-cat=banking]').click()")
        visible(evaluate,'#catPanelBanking')
        route(evaluate,'pnl','#realizedPnlPanel')
        route(evaluate,'dividend','#dividendPanel')
        route(evaluate,'ledger','#ledgerSectionContent')
        route(evaluate,'ipo','#ipoPanel')
        route(evaluate,'calendar','#calendarPanel')
        route(evaluate,'home','#wealthAssetNetWorth')
        # Observe completion of the actual debounce, not an arbitrary sleep.
        evaluate("__expanded.heatmaps=0;window.dispatchEvent(new Event('resize'))")
        wait_for(evaluate,'heatmapResizeTimer===null')
        assert evaluate('__expanded.heatmaps')==0
        assert evaluate('__expanded.storage')==[]
        assert evaluate('__expanded.readOld()')==seed
        assert evaluate('__expanded.badFrames')==0
        assert evaluate("document.querySelectorAll('.panel.is-collapsed,.section-collapse-btn').length")==0
        assert evaluate("(()=>{const ids=[...document.querySelectorAll('[id]')].map(n=>n.id);return new Set(ids).size===ids.length})()")
        assert evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        assert evaluate('__tabs.errors')==[]
        assert evaluate('__transport.errors')==[]
        previous=evaluate('performance.timeOrigin')
        call('Page.reload',{'ignoreCache':True})
        wait_for(evaluate,f'performance.timeOrigin!=={previous!r} && document.readyState==="complete"')
        ready(evaluate)
        visible(evaluate,'#wealthAssetNetWorth')
        assert evaluate('__expanded.storage')==[]
        assert evaluate('__expanded.readOld()')==seed
        assert evaluate('__tabs.markets')==0
