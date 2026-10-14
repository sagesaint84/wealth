"""Synthetic in-context import and five asset tabs; existing native Chrome harness only."""
import json
import pytest
from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_defaults_interest_chrome import prepare
from tests.test_workflow_ux_chrome import FRAMES, click


def geometry_diagnostics(evaluate):
    return evaluate(r'''(()=>{
      const identify=e=>e.id?`#${e.id}`:`${e.tagName.toLowerCase()}.${[...e.classList].join('.')}`;
      const basic=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
        return {element:identify(e),left:r.left,right:r.right,width:r.width,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,
          minWidth:s.minWidth,maxWidth:s.maxWidth,flexShrink:s.flexShrink,whiteSpace:s.whiteSpace,display:s.display,
          gridColumns:s.gridTemplateColumns,flexWrap:s.flexWrap,overflowX:s.overflowX};};
      const measure=e=>{let scroller=e.parentElement;
        while(scroller&&!(['auto','scroll'].includes(getComputedStyle(scroller).overflowX)&&scroller.scrollWidth>scroller.clientWidth))scroller=scroller.parentElement;
        const parents=[];let parent=e.parentElement;
        while(parent&&parents.length<6){parents.push(basic(parent));parent=parent.parentElement;}
        return {...basic(e),parents,children:[...e.children].slice(0,8).map(basic),scrollAncestor:scroller?identify(scroller):null};};
      const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
      const suspects=[...document.body.querySelectorAll('*')].filter(e=>visible(e)&&(e.getBoundingClientRect().right>innerWidth+1||e.getBoundingClientRect().left< -1));
      return {viewport:innerWidth,pageWidth:document.documentElement.scrollWidth,category:document.documentElement.dataset.wealthAssetCategory,
        firstOverflow:suspects.length?measure(suspects[0]):null,suspects:suspects.slice(0,45).map(measure),
        targets:[...document.querySelectorAll('#assetCategoryTabs,#accountsPanel,.account-panel-head-row,.toolbar,#securitiesActions,#realEstateActions,#catPanelRealEstate,#realEstateGrid,#catPanelRealEstate .saving-card-details,#catPanelRealEstate .saving-detail-row,#catPanelTax,.np-card-actions,#nationalPensionHistoryDialog,#npImportPanel,#npImportFile,#npImportReview,#npImportApply')].filter(visible).map(measure)};
    })()''')


def no_overflow(evaluate,width):
    actual=evaluate('document.documentElement.scrollWidth')
    assert actual<=width, geometry_diagnostics(evaluate)


def assert_pension_actions_inside(evaluate):
    geometry=evaluate(r'''(()=>{
      return [...document.querySelectorAll('.np-card-actions > button')].map(button=>{
        const r=button.getBoundingClientRect(),parent=button.parentElement.getBoundingClientRect();
        const text=document.createRange();text.selectNodeContents(button);
        return {label:button.textContent,inside:r.left>=parent.left-1&&r.right<=parent.right+1,
          textInside:[...text.getClientRects()].every(t=>t.left>=r.left-1&&t.right<=r.right+1&&t.top>=r.top-1&&t.bottom<=r.bottom+1),
          width:r.width,height:r.height,whiteSpace:getComputedStyle(button).whiteSpace};
      });
    })()''')
    assert len(geometry)==3,geometry
    assert all(row['inside'] and row['textInside'] for row in geometry),geometry


def assert_real_estate_details_inside(evaluate,width):
    geometry=evaluate(r'''(()=>{
      const inside=(child,parent)=>{const r=child.getBoundingClientRect(),p=parent.getBoundingClientRect();
        return r.left>=p.left-1&&r.right<=p.right+1;};
      return [...document.querySelectorAll('#catPanelRealEstate .saving-detail-row')].map(row=>{
        const range=document.createRange();range.selectNodeContents(row);const r=row.getBoundingClientRect();
        return {inside:inside(row,row.parentElement),childrenInside:[...row.children].every(child=>inside(child,row)),
          textInside:[...range.getClientRects()].every(text=>text.left>=r.left-1&&text.right<=r.right+1),
          width:r.width,scrollWidth:row.scrollWidth,clientWidth:row.clientWidth};
      });
    })()''')
    assert geometry,geometry_diagnostics(evaluate)
    assert all(row['inside'] and row['childrenInside'] and row['textInside'] for row in geometry),geometry_diagnostics(evaluate)
    # Exact synthetic fixture values: layout must never change the financial display.
    assert evaluate("[...document.querySelectorAll('#catPanelRealEstate .saving-detail-label')].some(e=>e.textContent==='매수가 (취득가)')")
    assert evaluate("[...document.querySelectorAll('#catPanelRealEstate .saving-detail-label')].some(e=>e.textContent==='현재 시세')")
    assert evaluate("[...document.querySelectorAll('#catPanelRealEstate .saving-detail-val')].some(e=>e.textContent.trim()==='₩400,000,000')")
    assert evaluate("[...document.querySelectorAll('#catPanelRealEstate .saving-detail-val')].some(e=>e.textContent.trim()==='₩420,000,000')")
    assert evaluate("[...document.querySelectorAll('#catPanelRealEstate .saving-detail-val')].some(e=>e.textContent.includes('+₩20,000,000 (+5.0%)'))")
    if width==320:
        assert evaluate("getComputedStyle(document.querySelector('#catPanelRealEstate .saving-card-details')).gridTemplateColumns.split(' ').length")==1


def assert_real_estate_buttons_hittable(call,evaluate):
    evaluate(FRAMES)  # Allow the existing MutationObserver to wrap delete menus.
    menu_count=evaluate(r'''(()=>{
      const menus=[...document.querySelectorAll('#catPanelRealEstate .wealth-row-more')].filter(menu=>{
        const summary=menu.querySelector(':scope > summary');
        return summary?.getClientRects().length&&getComputedStyle(summary).visibility==='visible';
      });
      window.__estateMenus=menus.map((menu,index)=>({menu,wasOpen:menu.open}));
      menus.forEach((menu,index)=>menu.querySelector(':scope > summary').dataset.pensionHitMenu=String(index));
      return menus.length;
    })()''')
    for index in range(menu_count):
        if not evaluate(f'__estateMenus[{index}].menu.open'):
            # Make delete visible through the real disclosure control, not CSS/DOM forcing.
            click(call,evaluate,f'[data-pension-hit-menu="{index}"]')
            assert evaluate(f'__estateMenus[{index}].menu.open')
    count=evaluate(r'''(()=>{
      const visible=button=>{
        if(!button.getClientRects().length||button.closest('[hidden],details:not([open])'))return false;
        for(let e=button;e;e=e.parentElement){const s=getComputedStyle(e);
          if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse')return false;}
        return true;
      };
      window.__estateHitButtons=[...document.querySelectorAll('#catPanelRealEstate button,#realEstateActions button')].filter(visible);
      __estateHitButtons.forEach((button,index)=>button.dataset.pensionHitTarget=String(index));
      return __estateHitButtons.length;
    })()''')
    assert count>0
    assert evaluate("__estateHitButtons.some(button=>button.matches('[data-re-del-id]'))")
    for index in range(count):
        evaluate(f"__estateHitButtons[{index}].scrollIntoView({{block:'center',inline:'nearest',behavior:'instant'}})")
        evaluate(FRAMES)
        geometry=evaluate(f'''(()=>{{
          const button=__estateHitButtons[{index}],r=button.getBoundingClientRect(),s=getComputedStyle(button);
          const rect=e=>{{if(!e)return null;const p=e.getBoundingClientRect();return {{left:p.left,right:p.right,top:p.top,bottom:p.bottom,width:p.width,height:p.height}};}};
          const identity=e=>e?{{tag:e.tagName,id:e.id,class:e.className}}:null;
          const x=r.x+r.width/2,y=r.y+r.height/2,hit=document.elementFromPoint(x,y);
          const actions=button.closest('.saving-card-actions,#realEstateActions'),card=button.closest('.real-estate-card');
          const kinds=['reEditId','reDelId','reSellId','reRefreshKbId','reSubtab'];
          const kind=kinds.find(key=>key in button.dataset)||button.id||'panel-button';
          const ancestors=[];for(let e=button;e&&ancestors.length<8;e=e.parentElement){{const cs=getComputedStyle(e);ancestors.push({{...identity(e),rect:rect(e),display:cs.display,visibility:cs.visibility,pointerEvents:cs.pointerEvents,overflowX:cs.overflowX,overflowY:cs.overflowY,contentVisibility:cs.contentVisibility,closedDetails:e.tagName==='DETAILS'&&!e.open}});}}
          return {{index:{index},selector:'[data-pension-hit-target="{index}"]',kind,
            card:card?'synthetic-real-estate-card-'+[...document.querySelectorAll('#catPanelRealEstate .real-estate-card')].indexOf(card):null,
            viewport:{{width:innerWidth,height:innerHeight,clientWidth:document.documentElement.clientWidth}},
            rect:rect(button),cardRect:rect(card),actionRect:rect(actions),documentScrollWidth:document.documentElement.scrollWidth,
            documentClientWidth:document.documentElement.clientWidth,display:s.display,visibility:s.visibility,pointerEvents:s.pointerEvents,
            connected:button.isConnected,sameTarget:document.querySelector('[data-pension-hit-target="{index}"]')===button,
            center:{{x,y,inside:x>=0&&x<document.documentElement.clientWidth&&y>=0&&y<innerHeight}},
            hit:!!hit&&button.contains(hit),hitTarget:identity(hit),occluded:!!hit&&!button.contains(hit),ancestors,
            inside:r.left>=0&&r.right<=document.documentElement.clientWidth&&r.top>=0&&r.bottom<=innerHeight,
            category:document.documentElement.dataset.wealthAssetCategory}};
        }})()''')
        message='REAL_ESTATE_HIT_TEST\n'+'\n'.join(f'{key}={json.dumps(value,ensure_ascii=False)}' for key,value in geometry.items())
        if not (geometry['inside'] and geometry['hit'] and geometry['connected'] and geometry['sameTarget']):
            print(message,flush=True)  # Captured stdout retains explicit lines if pytest truncates an assertion dict.
        assert geometry['connected'] and geometry['sameTarget'],message
        assert geometry['inside'] and geometry['hit'],message
    # Restore only menus that this test opened, through native clicks.
    for index in range(menu_count):
        if not evaluate(f'__estateMenus[{index}].wasOpen'):
            click(call,evaluate,f'[data-pension-hit-menu="{index}"]')
            assert not evaluate(f'__estateMenus[{index}].menu.open')


def real_estate_form_diagnostics(evaluate):
    return evaluate(r'''(()=>{
      const dialog=document.getElementById('realEstateDialog'),form=document.getElementById('realEstateForm'),grid=form.querySelector('.form-grid');
      const measure=e=>{if(!e)return null;const r=e.getBoundingClientRect(),s=getComputedStyle(e);
        return {selector:e.id?'#'+e.id:e.tagName.toLowerCase()+'.'+[...e.classList].join('.'),
          left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,clientWidth:e.clientWidth,scrollWidth:e.scrollWidth,
          gridColumns:s.gridTemplateColumns,minWidth:s.minWidth,whiteSpace:s.whiteSpace,flexShrink:s.flexShrink,
          flexWrap:s.flexWrap,display:s.display,visibility:s.visibility};};
      const children=[...form.querySelectorAll('.form-grid,.form-grid > *,label,input,select,.re-price-controls,.re-ownership-head,.re-joint-row,#reJointRows,#rePreviewBox,.dialog-actions,button')]
        .filter(e=>e.getClientRects().length&&getComputedStyle(e).visibility==='visible');
      return {dialog:measure(dialog),form:measure(form),grid:measure(grid),
        elements:children.map(e=>({child:measure(e),parent:measure(e.parentElement)}))};
    })()''')


def assert_real_estate_form_usable(evaluate,width):
    diagnostics=real_estate_form_diagnostics(evaluate)
    message='REAL_ESTATE_FORM_LAYOUT\n'+'\n'.join(f'{key}={json.dumps(value,ensure_ascii=False)}' for key,value in diagnostics.items() if key!='elements')
    message+='\n'+'\n'.join(f'element[{index}]={json.dumps(value,ensure_ascii=False)}' for index,value in enumerate(diagnostics['elements']))
    if diagnostics['dialog']['scrollWidth']>diagnostics['dialog']['clientWidth']+1:
        print(message,flush=True)
    assert diagnostics['dialog']['scrollWidth']<=diagnostics['dialog']['clientWidth']+1,message
    assert diagnostics['form']['scrollWidth']<=diagnostics['form']['clientWidth']+1,message
    assert diagnostics['grid']['scrollWidth']<=diagnostics['grid']['clientWidth']+1,message
    assert len(diagnostics['grid']['gridColumns'].split())==(1 if width<=480 else 2),message
    selectors=evaluate(r'''(()=>{
      document.querySelectorAll('#realEstateForm [data-pension-form-hit]').forEach(e=>e.removeAttribute('data-pension-form-hit'));
      return [...document.querySelectorAll('#realEstateForm input:not([type=hidden]),#realEstateForm select,#reFetchKbBtn,#reAddJointRowBtn,#realEstateForm .dialog-actions button')]
        .filter(e=>e.getClientRects().length&&getComputedStyle(e).visibility==='visible')
        .map((e,index)=>{e.dataset.pensionFormHit=String(index);return '[data-pension-form-hit="'+index+'"]';});
    })()''')
    assert '#reFetchKbBtn' in [value['child']['selector'] for value in diagnostics['elements']],message
    for selector in selectors:
        evaluate(f'document.querySelector({json.dumps(selector)}).scrollIntoView({{block:"center",inline:"nearest",behavior:"instant"}})')
        evaluate(FRAMES)
        geometry=evaluate(f'''(()=>{{const e=document.querySelector({json.dumps(selector)}),r=e.getBoundingClientRect(),d=document.getElementById('realEstateDialog').getBoundingClientRect();
          const x=r.left+r.width/2,y=r.top+r.height/2,hit=document.elementFromPoint(x,y);
          return {{selector:{json.dumps(selector)},element:e.id||e.tagName,left:r.left,right:r.right,top:r.top,bottom:r.bottom,
            inside:r.left>=d.left&&r.right<=d.right&&r.top>=d.top&&r.bottom<=d.bottom,
            hit:!!hit&&e.contains(hit),hitElement:hit?{{id:hit.id,class:hit.className,tag:hit.tagName}}:null}};
        }})()''')
        hit_message='REAL_ESTATE_FORM_CONTROL\n'+'\n'.join(f'{key}={json.dumps(value,ensure_ascii=False)}' for key,value in geometry.items())
        if not (geometry['inside'] and geometry['hit']):
            print(hit_message,flush=True)
            print(message,flush=True)
        assert geometry['inside'] and geometry['hit'],hit_message+'\n'+message


@pytest.mark.parametrize('width',[1280,390,320])
@pytest.mark.parametrize('theme',['purple','white','oled'])
def test_review_partial_approval_draft_conflict_and_five_tab_geometry(chrome_preview,width,theme):
    call,evaluate=prepare(chrome_preview,width)
    wait_for(evaluate,"typeof window.WealthAssetCategoryState?.current==='function'")
    assert evaluate(r'''(()=>{
      const paths=[...document.scripts].map(script=>new URL(script.src||location.href).pathname);
      return paths.filter(path=>path==='/static/wealth-asset-category-state.js').length===1&&
        paths.indexOf('/static/wealth-asset-category-state.js')<paths.indexOf('/static/wealth-layout.js')&&
        paths.indexOf('/static/wealth-layout.js')<paths.indexOf('/static/wealth.js');
    })()''')
    evaluate(f'document.documentElement.dataset.theme={json.dumps(theme)}')
    evaluate(r'''(()=>{
      window.__importItem={id:'synthetic-np',owner:'아빠',insurance_type:'national_pension',product_name:'합성 국민연금',total_paid_amount:8000000,monthly_payout:100000,expected_amount:24000000,converted_total_asset:24000000,yearly_contributions:[]};
      window.__importWrites=[];window.__importConflict=false;window.__realEstateDeleteRequests=0;window.confirm=()=>true;
      const previous=window.fetch;
      window.fetch=async(url,options={})=>{
        const path=new URL(String(url),location.href).pathname;
        if(path==='/api/real-estates/demo-home'&&options.method==='DELETE')__realEstateDeleteRequests++;
        if(path.endsWith('/national-pension-analysis'))return {ok:true,status:200,json:async()=>({revision:0,analysis:{},history:structuredClone(__importItem.yearly_contributions),total_paid_amount:__importItem.total_paid_amount,monthly_payout:__importItem.monthly_payout})};
        if(path.endsWith('/national-pension-import/preview'))return {ok:true,status:200,json:async()=>({document_type:'history',fingerprint:'a'.repeat(64),expected:{synthetic:true},warnings:[],periods:[],monthly:[],annual:[{year:'2025',deposit:100000,status:'OCR 확인 필요'}],fields:[{key:'total_paid_amount',label:'실제 납부 보험료 총액',value:9000000,current:8000000,status:'OCR 확인 필요',comparison:'기존 값과 불일치'},{key:'monthly_payout',label:'예상 월 연금액',value:200000,current:100000,status:'OCR 확인 필요'}]})};
        if(path.endsWith('/national-pension-import/apply')){
          const body=JSON.parse(options.body);__importWrites.push(body);
          if(__importConflict)return {ok:false,status:409,json:async()=>({detail:'합성 충돌: 다시 가져와 주세요.'})};
          __importItem.yearly_contributions=body.annual;
          for(const key of ['total_paid_amount','monthly_payout'])if(key in body.metadata.fields)__importItem[key]=body.metadata.fields[key];
          return {ok:true,status:200,json:async()=>({item:structuredClone(__importItem)})};
        }
        if(path==='/api/dashboard')return {ok:true,status:200,json:async()=>({...rawDashboard,insurance_accounts:[structuredClone(__importItem)]})};
        return previous(url,options);
      };
      location.hash='assets';window.dispatchEvent(new Event('hashchange'));
      renderInsurance([__importItem],'아빠');switchAccountCategory('insurance');
    })()''')
    assert evaluate("document.querySelectorAll('#assetCategoryTabs [role=tab]').length")==5
    for category,panel in [('securities','catPanelSecurities'),('banking','catPanelBanking'),('insurance','catPanelInsurance'),('real_estate','catPanelRealEstate'),('tax','catPanelTax')]:
        evaluate(f"document.querySelector('[data-cat={category}]').click()")
        assert evaluate(f"WealthAssetCategoryState.current()==='{category}'")
        assert evaluate(f"getComputedStyle(document.getElementById('{panel}')).display!=='none'")
        assert evaluate(f"document.querySelector('[data-cat={category}]').getAttribute('aria-selected')")== 'true'
        if category=='tax':
            click(call,evaluate,'#assetCategoryTabs [data-cat=tax]')
            assert evaluate("window.WealthAssetCategoryState.current()")=='tax'
            assert evaluate("getComputedStyle(document.getElementById('catPanelSecurities')).display")=='none'
            assert evaluate("document.getElementById('catPanelTax').textContent.includes('국민연금')")
        if category=='insurance':
            assert_pension_actions_inside(evaluate)
        if category=='real_estate':
            assert_real_estate_details_inside(evaluate,width)
            assert_real_estate_buttons_hittable(call,evaluate)
            no_overflow(evaluate,width)
            original=evaluate('JSON.stringify(rawRealEstates)')
            click(call,evaluate,'#catPanelRealEstate [data-re-edit-id="demo-home"]')
            assert evaluate("document.getElementById('realEstateDialog').open")
            assert_real_estate_form_usable(evaluate,width)
            click(call,evaluate,'#reIsJointCheck')
            assert evaluate("document.getElementById('reIsJointCheck').checked")
            assert evaluate("document.querySelectorAll('#reJointRows .re-joint-row').length")>=2
            assert_real_estate_form_usable(evaluate,width)
            click(call,evaluate,'#realEstateDialog .dialog-actions [value=cancel]')
            assert not evaluate("document.getElementById('realEstateDialog').open")
            assert evaluate('JSON.stringify(rawRealEstates)')==original
            # Exercise the actual delete control, explicitly cancelling its confirmation.
            # The fixture is synthetic; no DELETE request should ever be sent.
            evaluate("window.__priorEstateConfirm=window.confirm;window.__estateDeletePrompts=0;window.confirm=()=>{__estateDeletePrompts++;return false;}")
            try:
                click(call,evaluate,'#catPanelRealEstate .wealth-row-more > summary')
                assert evaluate("document.querySelector('#catPanelRealEstate [data-re-del-id=\"demo-home\"]').closest('details').open")
                click(call,evaluate,'#catPanelRealEstate [data-re-del-id="demo-home"]')
                assert evaluate('__estateDeletePrompts')==1
                assert evaluate('__realEstateDeleteRequests')==0
                assert evaluate('JSON.stringify(rawRealEstates)')==original
                click(call,evaluate,'#catPanelRealEstate .wealth-row-more > summary')
            finally:
                evaluate('window.confirm=__priorEstateConfirm')
            # CDP pointer events + hit testing exercise the real action, not element.click().
            click(call,evaluate,'#addRealEstateBtn')
            assert evaluate("document.getElementById('realEstateDialog').open")
            assert evaluate("document.querySelectorAll('dialog[open]').length")==1
            assert_real_estate_form_usable(evaluate,width)
            evaluate("closeDialog('realEstateDialog')")
            click(call,evaluate,'#catPanelRealEstate .saving-card-details [data-re-sell-id]')
            assert evaluate("document.getElementById('realEstateSellDialog').open")
            assert evaluate("document.querySelectorAll('dialog[open]').length")==1
            assert evaluate("(()=>{const e=document.getElementById('realEstateSellDialog');return e.scrollWidth<=e.clientWidth+1;})()")
            evaluate("closeDialog('realEstateSellDialog')")
        no_overflow(evaluate,width)
    evaluate("switchAccountCategory('insurance')")
    click(call,evaluate,'.np-card-actions [data-national-import-id]')
    wait_for(evaluate,"!document.getElementById('npAnalysisFields').disabled")
    assert evaluate("document.querySelectorAll('dialog[open]').length")==1
    evaluate(r'''(()=>{const transfer=new DataTransfer();transfer.items.add(new File(['%PDF-synthetic'],'synthetic.pdf',{type:'application/pdf'}));document.getElementById('npImportFile').files=transfer.files;document.querySelector('#npImportFields>button').click();})()''')
    wait_for(evaluate,"document.querySelectorAll('.np-import-row').length===3")
    assert evaluate('__importWrites.length')==0
    assert evaluate("[...document.querySelectorAll('.np-import-row [data-approve]')].every(e=>!e.checked)")
    assert evaluate("document.getElementById('npImportReview').textContent.includes('기존 값과 불일치')")
    evaluate(FRAMES);no_overflow(evaluate,width)
    assert evaluate("(()=>{const e=document.getElementById('nationalPensionHistoryDialog');return e.scrollWidth<=e.clientWidth+1;})()")
    assert evaluate("[...document.querySelectorAll('#npImportFields label')].every(e=>!!document.getElementById(e.htmlFor))")
    # Only one annual amount, edited by the user. Original financial totals remain unselected.
    evaluate("document.querySelector('[data-kind=annual] [data-key=deposit]').value='123456';document.querySelector('[data-kind=annual] [data-approve]').checked=true;__importConflict=true;document.getElementById('npImportApply').click()")
    wait_for(evaluate,"document.getElementById('npImportStatus').textContent.includes('합성 충돌')")
    assert evaluate("document.querySelector('[data-kind=annual] [data-key=deposit]').value")=='123456'
    assert evaluate('__importWrites[0].metadata.fields')=={}
    assert evaluate('__importItem.total_paid_amount')==8000000
    # A dirty analysis must block import without discarding its row.
    evaluate("document.querySelector('[data-np-add=membership_periods]').click();document.getElementById('npImportApply').click()")
    assert evaluate("document.getElementById('npImportStatus').textContent.includes('저장하지 않은')")
    assert evaluate('__importWrites.length')==1
    evaluate("document.querySelector('[data-np-action=cancel]').click();__importConflict=false;document.getElementById('npImportApply').click()")
    wait_for(evaluate,"!document.getElementById('nationalPensionHistoryDialog').open")
    assert evaluate('__importWrites.length')==2
    assert evaluate('__importItem.yearly_contributions[0].deposit')==123456
    assert evaluate('__importItem.total_paid_amount')==8000000
    assert evaluate('__importItem.monthly_payout')==100000
    no_overflow(evaluate,width)
    # Basic-product draft must survive an attempted analysis navigation.
    evaluate("openInsuranceAccountDialog(__importItem);document.querySelector('#insuranceAccountForm [name=product_name]').value='합성 미저장 초안';document.querySelector('[data-np-edit-entry]').click()")
    assert evaluate("document.getElementById('insuranceAccountDialog').open")
    assert evaluate("document.querySelector('#insuranceAccountForm [name=product_name]').value")=='합성 미저장 초안'
    evaluate("closeDialog('insuranceAccountDialog');switchAccountCategory('tax')")
    assert evaluate("sessionStorage.getItem('wealth_asset_category')")=='tax'
    # readyState/rawDashboard/panel also describe the old document. Wait for
    # a marker installed only in the next document before checking restoration.
    token='pension-tax-restored-document'
    evaluate('delete window.__pensionReloadDocument')
    script=call('Page.addScriptToEvaluateOnNewDocument',{'source':f'window.__pensionReloadDocument={json.dumps(token)};'})
    try:
        call('Page.reload',{})
        wait_for(evaluate,f"window.__pensionReloadDocument==={json.dumps(token)}&&document.readyState==='complete'&&typeof window.WealthAssetCategoryState?.current==='function'&&typeof rawDashboard!=='undefined'&&!!rawDashboard&&!!document.getElementById('catPanelTax')")
    except (AssertionError,pytest.fail.Exception):
        pytest.fail(f'Reloaded pension preview did not initialize; load errors={evaluate.load_errors}; state='+str(evaluate("({ready:document.readyState,marker:window.__pensionReloadDocument,categoryModule:typeof window.WealthAssetCategoryState,scripts:[...document.scripts].map(s=>s.src)})")))
    finally:
        call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':script['identifier']})
    assert evaluate("window.WealthAssetCategoryState.current()")=='tax'
    assert evaluate("getComputedStyle(document.getElementById('catPanelTax')).display")=='block'
    assert evaluate("getComputedStyle(document.getElementById('catPanelSecurities')).display")=='none'
    assert evaluate("document.querySelector('[data-cat=tax]').getAttribute('aria-selected')")=='true'
    no_overflow(evaluate,width)
