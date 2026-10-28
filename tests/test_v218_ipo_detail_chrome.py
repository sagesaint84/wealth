"""Shared calendar IPO detail, in-memory account/allocation/link API only."""
import pytest
from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_ipo_calendar_ui_chrome import BOOT, ui_chrome_preview, open_calendar

DETAIL = r"""
window.__detail={revision:0,quantity:4,sold:0,pnl:12345,writes:[],fail:false};
const detailFetch=fetch;
window.fetch=async function(url,options={}){
 const address=new URL(String(url),location.href),path=address.pathname;
 const reply=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
 if(path==='/api/realized-pnl')return reply({records:[{id:'synthetic-sale',owner:'아빠',date:'2026-10-29',name:'가상기업',code:'123456',quantity:2,is_ipo:true,pnl:12345,pnl_krw:12345,currency:'KRW'}]});
 if(path==='/api/ipo/applications')return reply({revision:__detail.revision,applications:__uiApps,family_members:['아빠','엄마','자녀']});
 if(/^\/api\/ipo\/applications\/[^/]+$/.test(path)&&options.method==='PUT'){
   const body=JSON.parse(options.body),id=decodeURIComponent(path.split('/').pop());__detail.writes.push({path,body,method:'PUT'});
   if(body.revision!==__detail.revision)return reply({detail:'revision conflict'},409);
   __uiApps[id].applied_owners=body.applied_owners;__detail.revision++;return reply({...__uiApps[id],revision:__detail.revision});
 }
 if(path.startsWith('/api/ipo/applications/')&&path.includes('/applicants/')){
   if(options.method && options.method!=='GET'){
     const body=JSON.parse(options.body);__detail.writes.push({path,body,method:options.method});
     if(__detail.fail||body.revision!==__detail.revision)return reply({detail:'revision conflict'},409);
     if(path.endsWith('/allocation'))__detail.quantity=Number(body.quantity);
     else if(options.method==='DELETE')__detail.sold=0;
     else if(path.endsWith('/links'))__detail.sold=Number(body.matched_quantity);
     __detail.revision++;return reply({revision:__detail.revision});
   }
   if(path.endsWith('/sale-candidates'))return reply({candidates:[{pnl_record_id:'synthetic-sale',date:'2026-10-29',available_quantity:2}]});
   if(path.endsWith('/allocation'))return reply({allocation:{quantity:__detail.quantity,sold_quantity:__detail.sold,remaining_quantity:__detail.quantity-__detail.sold,realized_pnl_krw:__detail.sold?__detail.pnl:0},links:__detail.sold?[{pnl_record_id:'synthetic-sale',date:'2026-10-29',matched_quantity:__detail.sold}]:[]});
 }
 if(path.endsWith('/broker-options'))return reply({brokers:[{broker_id:'synthetic',display_name:'가상증권'}]});
 if(path.endsWith('/account-candidates'))return reply({candidates:[{account_id:'synthetic-father',owner:'아빠',account_name:'합성 계좌'}],auto_selected_account_id:'synthetic-father',broker_id:'synthetic',resolution_status:'MAPPED'});
 return detailFetch(url,options);
};
for(const app of Object.values(__uiApps))app.applicants={아빠:{broker_id:'synthetic',account_id:'synthetic-father'}};
"""

@pytest.mark.parametrize('width',[320,360,390,768,1280])
@pytest.mark.parametrize('theme',['purple','white','oled'])
def test_calendar_shares_account_allocation_link_and_failure_inputs(ui_chrome_preview,width,theme):
    call,evaluate,port=ui_chrome_preview
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<500})
    call('Page.addScriptToEvaluateOnNewDocument',{'source':f"localStorage.setItem('app_theme',{theme!r});"+BOOT+DETAIL})
    call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#calendar'})
    wait_for(evaluate,'!!window.WealthCalendar && !!window.WealthIpoDetail')
    open_calendar(evaluate)
    evaluate('document.querySelector(".cal-ipo-details[data-ipo=long]").click()')
    wait_for(evaluate,'!!document.querySelector("#ipoSharedDetailDialog .ipo-allocation-quantity:not(:disabled)")')
    assert evaluate('document.querySelector("#ipoSharedDetailDialog .ipo-applicant-account").dataset.ipo')=='long'
    assert evaluate('document.querySelector("#ipoSharedDetailDialog .ipo-applicant-account-select").value')=='synthetic-father'
    evaluate('document.querySelector("#ipoSharedDetailDialog .ipo-allocation-quantity").value="5";document.querySelector("#ipoSharedDetailDialog .ipo-allocation-save").click()')
    wait_for(evaluate,'document.querySelector("#ipoSharedDetailDialog .ipo-allocation-quantity")?.value==="5" && !document.querySelector("#ipoSharedDetailDialog .ipo-applicant-account").inert && document.querySelector("#ipoSharedDetailDialog .ipo-sale-link-save")?.disabled===false')
    assert evaluate('__detail.quantity')==5
    evaluate('document.querySelector("#ipoSharedDetailDialog .ipo-sale-candidate").value="synthetic-sale";document.querySelector("#ipoSharedDetailDialog .ipo-sale-match-quantity").value="2";document.querySelector("#ipoSharedDetailDialog .ipo-sale-link-save").click()')
    wait_for(evaluate,'document.querySelector("#ipoSharedDetailDialog .ipo-allocation-summary")?.textContent.includes("12,345")')
    assert evaluate('__detail.sold')==2
    assert evaluate('__detail.pnl')==12345
    evaluate('document.querySelector("#ipoSharedDetailDialog .ipo-pnl-detail").click()')
    wait_for(evaluate,'document.getElementById("pnlRecordDialog").open && document.getElementById("pnlRecordForm").dataset.recordId==="synthetic-sale"')
    evaluate('document.getElementById("pnlRecordDialog").close()')
    evaluate('(async()=>{await WealthIpoDetail.open("long");return true;})()')
    evaluate('window.confirm=()=>true;document.querySelector("#ipoSharedDetailDialog .ipo-sale-unlink").click()')
    wait_for(evaluate,'document.querySelector("#ipoSharedDetailDialog .ipo-allocation-summary")?.textContent.includes("매도 0주")')
    assert evaluate('__detail.pnl')==12345
    evaluate('__detail.fail=true;document.querySelector("#ipoSharedDetailDialog .ipo-allocation-quantity").value="6";document.querySelector("#ipoSharedDetailDialog .ipo-allocation-save").click()')
    wait_for(evaluate,'document.querySelector("#ipoSharedDetailDialog .ipo-allocation-summary").textContent.includes("실패")')
    assert evaluate('document.querySelector("#ipoSharedDetailDialog .ipo-allocation-quantity").value')=='6'
    assert evaluate('__detail.quantity')==5
    assert evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert evaluate('document.getElementById("ipoSharedDetailDialog").getBoundingClientRect().right<=innerWidth')
    evaluate('document.querySelector("#ipoSharedDetailDialog [data-close-ipo]").click()')
    assert evaluate('document.querySelector(".cal-day-cell.is-selected")!==null')
    assert evaluate('__uiErrors')==[]

def test_application_uses_card_revision_after_other_detail_refresh(ui_chrome_preview):
    call,evaluate,port=ui_chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOT+DETAIL+'window.alert=message=>window.__appAlert=message;'})
    call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#ipo'})
    wait_for(evaluate,'!!window.WealthIpoDetail && !!window.WealthIpoState && WealthStartup.canRead() && !loadAssetDataForUser.pending && !window.setIncomeTab.pendingTarget')
    evaluate('(async()=>{await loadAssetDataForUser.supplementary;return true;})()')
    evaluate('(async()=>{await loadIpoSchedule();WealthIpoState.setFilterGroup("ALL");WealthIpoState.setHistoryYear(2026);WealthIpoState.setHistoryMonth(10);WealthIpoState.setMonthExplicitlySelected(true);WealthIpoState.renderIpoList();window.__staleCard=document.querySelector("#ipoListWrapper .ipo-card[data-ipo-id=long]");__detail.revision=1;__uiApps.long.applied_owners=["엄마"];await WealthIpoDetail.open("listing");return true;})()')
    assert evaluate('document.querySelector("#ipoSharedDetailDialog .ipo-card").dataset.applicationRevision')=='1'
    assert evaluate('__staleCard.isConnected')
    assert evaluate('__staleCard.dataset.applicationRevision')=='0'
    evaluate('document.getElementById("ipoSharedDetailDialog").close();__staleCard.querySelector(".ipo-member-chk[data-member=자녀]").click()')
    wait_for(evaluate,'!!window.__appAlert')
    assert evaluate('__detail.writes.at(-1).body.revision')==0
    assert evaluate('__uiApps.long.applied_owners')==['엄마']
