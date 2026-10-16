"""Native Chrome read-only UI; synthetic preview responses, no OCR or financial writes."""
import json
from pathlib import Path

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_ledger_document_import import BANK, page, partial_bank
from app.services.ledger_document import parse_pages


@pytest.mark.parametrize('width', [320,390,1280])
@pytest.mark.parametrize('theme', ['purple','white','oled'])
def test_read_only_ocr_preview_no_save_theme_geometry(chrome_preview,width,theme):
    call,evaluate,port=chrome_preview
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<=430})
    call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#ledger'})
    wait_for(evaluate,"document.readyState==='complete' && typeof openLedgerExcelModal==='function' && !!document.getElementById('ledgerOcrAnalyze')")
    data=json.dumps(parse_pages([page(BANK)]),ensure_ascii=True)
    evaluate(f"""(()=>{{
      document.documentElement.dataset.theme={json.dumps(theme)};
      window.__ocrCalls=[];
      const original=window.fetch;
      window.fetch=async(url,options={{}})=>{{
        const path=new URL(String(url),location.href).pathname;
        if(path==='/api/ledger/document-import/preview'){{
          __ocrCalls.push({{path,method:options.method,credentials:options.credentials}});
          return {{ok:true,json:async()=>({data})}};
        }}
        return original(url,options);
      }};
      openLedgerExcelModal();document.getElementById('ledgerOcrPanel').open=true;
      const transfer=new DataTransfer();transfer.items.add(new File(['synthetic-only'],'synthetic.png',{{type:'image/png'}}));
      document.getElementById('ledgerOcrFile').files=transfer.files;
      document.getElementById('ledgerOcrAnalyze').click();
    }})()""")
    wait_for(evaluate,"document.querySelectorAll('#ledgerOcrReview .ledger-ocr-row').length===2")
    result=evaluate("""(()=>{
      const panel=document.getElementById('ledgerOcrPanel'),dialog=document.getElementById('ledgerExcelDialog');
      const button=document.getElementById('ledgerOcrAnalyze');button.scrollIntoView({block:'center'});
      const r=button.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
      return {page:document.documentElement.scrollWidth,dialogScroll:dialog.scrollWidth,dialogClient:dialog.clientWidth,
        scrollers:[...document.querySelectorAll('body,body *')].filter(node=>node.getClientRects().length&&node.scrollWidth>node.clientWidth+1).slice(0,12).map(node=>({id:node.id,tag:node.tagName,class:node.className,scroll:node.scrollWidth,client:node.clientWidth,right:node.getBoundingClientRect().right,overflow:getComputedStyle(node).overflowX})),
        overflowElements:[...document.querySelectorAll('body *')].filter(node=>{
          if(!node.getClientRects().length||node.getBoundingClientRect().right<=innerWidth+1)return false;
          for(let parent=node.parentElement;parent&&parent!==document.body;parent=parent.parentElement){if(['auto','scroll'].includes(getComputedStyle(parent).overflowX)&&parent.scrollWidth>parent.clientWidth)return false;}
          return true;
        }).slice(0,12).map(node=>({id:node.id,tag:node.tagName,class:node.className,right:node.getBoundingClientRect().right})),
        calls:__ocrCalls,readOnly:panel.textContent.includes('읽기 전용'),
        exactMoney:panel.textContent.includes('+₩1,234,567'),
        saveDisabled:document.getElementById('ledgerOcrSave').disabled,
        hit:hit===button||button.contains(hit),visible:getComputedStyle(panel).display!=='none'};
    })()""")
    assert result['page']<=width and result['dialogScroll']<=result['dialogClient']+1,json.dumps(result,ensure_ascii=True)
    assert result['readOnly'] and result['exactMoney'] and result['saveDisabled'],result
    assert result['hit'] and result['visible'],result
    assert result['calls']==[{'path':'/api/ledger/document-import/preview','method':'POST','credentials':'same-origin'}]
    evaluate("document.getElementById('ledgerExcelDialog').close()")
    wait_for(evaluate,"!document.getElementById('ledgerOcrReview').children.length && !document.getElementById('ledgerOcrFile').value")
    assert evaluate("!document.getElementById('ledgerOcrReview').children.length && !document.getElementById('ledgerOcrFile').value")


def test_closing_dialog_ignores_late_preview_and_keeps_existing_import(chrome_preview):
    call,evaluate,port=chrome_preview
    call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#ledger'})
    wait_for(evaluate,"document.readyState==='complete' && typeof openLedgerExcelModal==='function'")
    result=evaluate("""(async()=>{
      const original=window.fetch;let finish;
      window.fetch=(url,options)=>new URL(String(url),location.href).pathname==='/api/ledger/document-import/preview'
        ?new Promise(resolve=>finish=resolve):original(url,options);
      openLedgerExcelModal();document.getElementById('ledgerOcrPanel').open=true;
      const transfer=new DataTransfer();transfer.items.add(new File(['synthetic'],'synthetic.pdf',{type:'application/pdf'}));
      document.getElementById('ledgerOcrFile').files=transfer.files;document.getElementById('ledgerOcrAnalyze').click();
      document.getElementById('ledgerExcelDialog').close();
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      finish({ok:true,json:async()=>({document_type:'unknown',status:'review_required',rows:[],warnings:[]})});
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      return {empty:!document.getElementById('ledgerOcrReview').children.length,
        status:document.getElementById('ledgerOcrStatus').textContent,
        enabled:!document.getElementById('ledgerOcrAnalyze').disabled,
        existing:!!document.getElementById('ledgerFileInput')&&typeof uploadLedgerFile==='function'&&typeof processLedgerTextImport==='function'};
    })()""")
    assert result=={'empty':True,'status':'','enabled':True,'existing':True}


def test_ocr_static_read_only_contract():
    root=Path(__file__).resolve().parents[1]
    js=(root/'app/static/wealth-ledger-ocr.js').read_text(encoding='utf-8')
    assert '/api/ledger/document-import/preview' in js
    assert 'textContent' in js and 'innerHTML' not in js
    for path in ('/api/ledger/transactions','/api/ledger/import-file','/apply'):
        assert path not in js
    assert 'BigInt(value)' in js
    assert "request('review',{rows:rows.map(payload)})" in js
    assert "request('commit',body)" in js
    assert 'request_id:crypto.randomUUID()' not in js and '!confirmed.checked' in js
    assert 'if(busy || pending || !checked' in js
    assert '저장 내역 다시 조회' in js and '자동 재저장은 하지 않습니다' in js


@pytest.mark.parametrize('width', [320,390,1280])
@pytest.mark.parametrize('theme', ['purple','white','oled'])
def test_o11_year_missing_preview_is_visible_without_save_or_layout_overflow(chrome_preview,width,theme):
    call,evaluate,port=chrome_preview
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<=430})
    call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#ledger'})
    wait_for(evaluate,"document.readyState==='complete' && typeof openLedgerExcelModal==='function' && !!document.getElementById('ledgerOcrAnalyze')")
    data=json.dumps(parse_pages([page(partial_bank())]),ensure_ascii=True)
    evaluate(f"""(()=>{{
      document.documentElement.dataset.theme={json.dumps(theme)};
      const original=window.fetch;window.__o11Calls=[];
      window.fetch=async(url,options={{}})=>{{
        const path=new URL(String(url),location.href).pathname;
        if(path==='/api/ledger/document-import/preview'){{
          __o11Calls.push({{path,method:options.method}});
          return {{ok:true,json:async()=>({data})}};
        }}
        return original(url,options);
      }};
      openLedgerExcelModal();document.getElementById('ledgerOcrPanel').open=true;
      const transfer=new DataTransfer();transfer.items.add(new File(['synthetic-only'],'synthetic.png',{{type:'image/png'}}));
      document.getElementById('ledgerOcrFile').files=transfer.files;document.getElementById('ledgerOcrAnalyze').click();
    }})()""")
    wait_for(evaluate,"document.querySelectorAll('#ledgerOcrReview .ledger-ocr-row').length===2")
    result=evaluate("""(()=>{
      const dialog=document.getElementById('ledgerExcelDialog'),review=document.getElementById('ledgerOcrReview');
      return {page:document.documentElement.scrollWidth,scroll:dialog.scrollWidth,client:dialog.clientWidth,
        partialDate:review.textContent.includes('10월 14일 · 연도 미확인'),
        yearReason:review.textContent.includes('현재 연도로 채우지 않습니다'),
        transfer:review.textContent.includes('이체 후보'),amount:review.textContent.includes('+₩1,234,567'),
        balance:review.textContent.includes('₩11,234,567'),readOnly:document.getElementById('ledgerOcrSave').disabled,
        save:document.querySelectorAll('#ledgerOcrPanel [data-save], #ledgerOcrPanel button[type="submit"]').length,
        calls:__o11Calls};
    })()""")
    assert result['page']<=width and result['scroll']<=result['client']+1,result
    assert all(result[key] for key in ('partialDate','yearReason','transfer','amount','balance','readOnly')),result
    assert result['save']==0 and result['calls']==[{'path':'/api/ledger/document-import/preview','method':'POST'}]

REVIEW_BOOT = r"""
window.__reviewFlow={reviews:[],commits:[],previewFail:false,saveMode:'success'};
window.__fillOcr=(index,values)=>{
  for(const [key,value] of Object.entries(values)){
    const control=document.querySelectorAll('#ledgerOcrReview .ledger-ocr-row')[index].querySelector(`[data-field="${key}"]`);
    if(control.type==='checkbox')control.checked=value;else control.value=value;
    control.dispatchEvent(new Event(control.tagName==='SELECT'||control.type==='checkbox'?'change':'input',{bubbles:true}));
  }
};
const nativeFetch=window.fetch;
window.fetch=async(url,options={})=>{
  const path=new URL(String(url),location.href).pathname;
  const answer=(data,status=200)=>({ok:status===200,status,json:async()=>structuredClone(data)});
  if(path==='/api/ledger/document-import/options')return answer({owners:['아빠','엄마','모두'],categories:{income:['급여/상여'],expense:['식비/외식'],transfer:['계좌이체/저축']}});
  if(path==='/api/ledger/document-import/preview')return __reviewFlow.previewFail?answer({detail:'합성 OCR 실패'},400):answer(window.__syntheticOcr);
  if(path==='/api/ledger/document-import/review'){
    const body=JSON.parse(options.body);__reviewFlow.reviews.push(body);
    return answer({revision:'synthetic-revision',review_token:'synthetic-review-token',count:body.rows.length,total:body.rows.reduce((sum,row)=>sum+BigInt(row.amount),0n).toString(),duplicates:body.rows.map(()=>!!__reviewFlow.duplicateMode)});
  }
  if(path==='/api/ledger/document-import/commit'){
    const body=JSON.parse(options.body);__reviewFlow.commits.push(body);
    if(__reviewFlow.saveMode==='uncertain'&&__reviewFlow.commits.length===1)throw new Error('합성 응답 유실');
    if(__reviewFlow.saveMode==='conflict')return answer({detail:'합성 재검토 필요'},409);
    return answer({count:body.rows.length});
  }
  return nativeFetch(url,options);
};
window.__ledgerReloads=0;window.loadLedger=async()=>{__ledgerReloads++;};
openLedgerExcelModal();document.getElementById('ledgerOcrPanel').open=true;
"""


def open_review_ui(chrome_preview,width):
    call,evaluate,port=chrome_preview
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<=430})
    call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#ledger'})
    wait_for(evaluate,"document.readyState==='complete' && typeof openLedgerExcelModal==='function' && !!document.getElementById('ledgerOcrAdd')")
    data=json.dumps(parse_pages([page(BANK)]),ensure_ascii=True)
    evaluate('window.__syntheticOcr='+data+';'+REVIEW_BOOT)
    wait_for(evaluate,"document.getElementById('ledgerOcrAdd') && !document.getElementById('ledgerOcrAdd').disabled")
    return evaluate


@pytest.mark.parametrize('width',[320,390,1280])
def test_confirmed_ocr_edit_selection_and_uncertain_save_requires_read_only_review(chrome_preview,width):
    evaluate=open_review_ui(chrome_preview,width)
    evaluate("""(()=>{
      const transfer=new DataTransfer();transfer.items.add(new File(['synthetic-only'],'synthetic.png',{type:'image/png'}));
      document.getElementById('ledgerOcrFile').files=transfer.files;document.getElementById('ledgerOcrAnalyze').click();
    })()""")
    wait_for(evaluate,"document.querySelectorAll('#ledgerOcrReview .ledger-ocr-row').length===2")
    wait_for(evaluate,"!document.getElementById('ledgerOcrAnalyze').disabled")
    evaluate("__fillOcr(0,{date:'2026-10-14',amount:'12345',type:'expense',owner:'아빠',category:'식비/외식',direction:'outflow',merchant:'수정한합성상점',source_kind:'normal',selected:true});document.getElementById('ledgerOcrCheck').click()")
    wait_for(evaluate,"!document.getElementById('ledgerOcrConfirmation').hidden")
    assert evaluate("document.getElementById('ledgerOcrSave').disabled && __reviewFlow.commits.length===0")
    assert evaluate("__reviewFlow.reviews.length===1 && __reviewFlow.reviews[0].rows.length===1 && __reviewFlow.reviews[0].rows[0].merchant==='수정한합성상점'")
    evaluate("__reviewFlow.saveMode='uncertain';document.getElementById('ledgerOcrConfirmed').click();document.getElementById('ledgerOcrSave').click()")
    wait_for(evaluate,"document.getElementById('ledgerOcrStatus').textContent.includes('저장 여부가 미확인') && document.getElementById('ledgerOcrSave').disabled")
    assert evaluate("document.querySelectorAll('#ledgerOcrReview .ledger-ocr-row').length===2 && !document.querySelector('#ledgerOcrReview [data-field=amount]').disabled")
    evaluate("document.getElementById('ledgerOcrSave').click()")
    assert evaluate("__reviewFlow.commits.length===1 && !('request_id' in __reviewFlow.commits[0])")
    evaluate("__reviewFlow.duplicateMode=true;document.getElementById('ledgerOcrCheck').click()")
    wait_for(evaluate,"__reviewFlow.reviews.length===2 && __ledgerReloads===1")
    assert evaluate("__reviewFlow.commits.length===1 && document.getElementById('ledgerOcrSave').disabled && !document.getElementById('ledgerOcrConfirmed').checked")
    assert evaluate("document.querySelectorAll('#ledgerOcrReview .ledger-ocr-row').length===2 && !document.querySelector('#ledgerOcrReview [data-field=duplicate_confirmed]').checked")
    assert evaluate("__reviewFlow.commits[0].rows.length===1 && !('balance_after' in __reviewFlow.commits[0].rows[0]) && !('account_id' in __reviewFlow.commits[0].rows[0])")


@pytest.mark.parametrize('width',[320,390,1280])
def test_manual_fallback_preserves_edits_and_conflict_draft(chrome_preview,width):
    evaluate=open_review_ui(chrome_preview,width)
    evaluate("document.getElementById('ledgerOcrAdd').click()")
    wait_for(evaluate,"document.querySelector('#ledgerOcrReview [data-field=owner] option[value=아빠]')!==null")
    evaluate("__fillOcr(0,{merchant:'편집유지합성상점',selected:true});document.getElementById('ledgerOcrCheck').click()")
    assert evaluate("__reviewFlow.reviews.length===0 && document.getElementById('ledgerOcrStatus').textContent.includes('필수값')")
    evaluate("""(()=>{
      __reviewFlow.previewFail=true;
      const transfer=new DataTransfer();transfer.items.add(new File(['synthetic'],'synthetic.png',{type:'image/png'}));
      document.getElementById('ledgerOcrFile').files=transfer.files;document.getElementById('ledgerOcrAnalyze').click();
    })()""")
    wait_for(evaluate,"document.getElementById('ledgerOcrStatus').textContent.includes('OCR 실패')")
    assert evaluate("document.querySelector('#ledgerOcrReview [data-field=merchant]').value==='편집유지합성상점' && !document.getElementById('ledgerOcrAdd').disabled")
    evaluate("__fillOcr(0,{date:'2026-10-14',amount:'12345',type:'transfer',owner:'아빠',category:'계좌이체/저축',direction:'outflow',source_kind:'bank_transfer'});document.getElementById('ledgerOcrCheck').click()")
    wait_for(evaluate,"!document.getElementById('ledgerOcrConfirmation').hidden")
    evaluate("__reviewFlow.saveMode='conflict';document.getElementById('ledgerOcrConfirmed').click();document.getElementById('ledgerOcrSave').click()")
    wait_for(evaluate,"document.getElementById('ledgerOcrStatus').textContent.includes('재검토')")
    assert evaluate("document.querySelector('#ledgerOcrReview [data-field=merchant]').value==='편집유지합성상점' && document.getElementById('ledgerOcrSave').disabled")
    geometry=evaluate("""(()=>{
      const dialog=document.getElementById('ledgerExcelDialog');
      return {page:document.documentElement.scrollWidth,scroll:dialog.scrollWidth,client:dialog.clientWidth,
        labels:[...document.querySelectorAll('#ledgerOcrReview input,#ledgerOcrReview select')].every(input=>!!input.closest('label'))};
    })()""")
    assert geometry['page']<=width and geometry['scroll']<=geometry['client']+1 and geometry['labels'],geometry
    evaluate("document.querySelector('#ledgerOcrReview [data-field=merchant]').focus()")
    call=chrome_preview[0];call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Tab','code':'Tab','windowsVirtualKeyCode':9})
    assert evaluate("document.activeElement!==document.querySelector('#ledgerOcrReview [data-field=merchant]')")


def test_cancellation_unselected_and_user_confirmation_required(chrome_preview):
    evaluate=open_review_ui(chrome_preview,390)
    evaluate("__syntheticOcr.rows[0].transaction_type_candidate='refund';document.getElementById('ledgerOcrAdd').click();__fillOcr(0,{source_kind:'refund'})")
    assert evaluate("!document.querySelector('#ledgerOcrReview [data-field=selected]').checked && document.querySelector('#ledgerOcrReview [data-errors]').textContent.includes('취소·환불')")
    evaluate("__fillOcr(0,{date:'2026-10-14',amount:'12345',type:'income',owner:'아빠',category:'급여/상여',direction:'inflow',selected:true});document.getElementById('ledgerOcrCheck').click()")
    assert evaluate("__reviewFlow.reviews.length===0")
    evaluate("__fillOcr(0,{special_confirmed:true});document.getElementById('ledgerOcrCheck').click()")
    wait_for(evaluate,"__reviewFlow.reviews.length===1")
    assert evaluate("__reviewFlow.reviews[0].rows[0].special_confirmed===true")


def test_duplicate_warning_requires_explicit_ack_and_fresh_review(chrome_preview):
    evaluate=open_review_ui(chrome_preview,390)
    evaluate("document.getElementById('ledgerOcrAdd').click()")
    wait_for(evaluate,"document.querySelector('#ledgerOcrReview [data-field=owner] option[value=아빠]')!==null")
    evaluate("__reviewFlow.duplicateMode=true;__fillOcr(0,{date:'2026-10-14',amount:'12345',type:'expense',owner:'아빠',category:'식비/외식',direction:'outflow',source_kind:'normal',selected:true});document.getElementById('ledgerOcrCheck').click()")
    wait_for(evaluate,"document.querySelector('#ledgerOcrReview [data-field=duplicate_confirmed]')!==null")
    evaluate("document.getElementById('ledgerOcrConfirmed').click()")
    assert evaluate("document.getElementById('ledgerOcrSave').disabled && __reviewFlow.commits.length===0")
    evaluate("__fillOcr(0,{duplicate_confirmed:true})")
    assert evaluate("document.getElementById('ledgerOcrSave').disabled && document.getElementById('ledgerOcrConfirmation').hidden")
    evaluate("document.getElementById('ledgerOcrCheck').click()")
    wait_for(evaluate,"__reviewFlow.reviews.length===2 && !document.getElementById('ledgerOcrConfirmation').hidden")
    evaluate("document.getElementById('ledgerOcrConfirmed').click();document.getElementById('ledgerOcrSave').click()")
    wait_for(evaluate,"document.getElementById('ledgerOcrStatus').textContent.includes('추가 완료')")
    assert evaluate("__reviewFlow.commits.length===1 && __reviewFlow.commits[0].rows[0].duplicate_confirmed===true")


def test_unknown_document_keeps_manual_input_available(chrome_preview):
    evaluate=open_review_ui(chrome_preview,320)
    evaluate("""(()=>{
      __syntheticOcr={document_type:'unknown',status:'review_required',rows:[],warnings:[]};
      const transfer=new DataTransfer();transfer.items.add(new File(['synthetic-only'],'synthetic.pdf',{type:'application/pdf'}));
      document.getElementById('ledgerOcrFile').files=transfer.files;document.getElementById('ledgerOcrAnalyze').click();
    })()""")
    wait_for(evaluate,"document.getElementById('ledgerOcrStatus').textContent.includes('읽은 거래가 없습니다')")
    assert evaluate("!document.getElementById('ledgerOcrAdd').disabled && __reviewFlow.commits.length===0")
    evaluate("document.getElementById('ledgerOcrAdd').click()")
    assert evaluate("document.querySelectorAll('#ledgerOcrReview .ledger-ocr-row').length===1 && !document.querySelector('#ledgerOcrReview [data-field=date]').value && document.querySelector('#ledgerOcrReview [data-field=amount]').value==='0' && document.getElementById('ledgerOcrReview').textContent.includes('0원(미확인)') && !document.querySelector('#ledgerOcrReview [data-field=type]').value")


def test_confirmation_total_keeps_exact_large_integer_digits(chrome_preview):
    evaluate=open_review_ui(chrome_preview,390)
    evaluate("document.getElementById('ledgerOcrAdd').click();document.getElementById('ledgerOcrAdd').click()")
    wait_for(evaluate,"document.querySelector('#ledgerOcrReview [data-field=owner] option[value=아빠]')!==null")
    evaluate("__fillOcr(0,{date:'2026-10-14',amount:'9007199254740991',type:'expense',owner:'아빠',category:'식비/외식',direction:'outflow',selected:true});__fillOcr(1,{date:'2026-10-13',amount:'9007199254740991',type:'expense',owner:'아빠',category:'식비/외식',direction:'outflow',selected:true});document.getElementById('ledgerOcrCheck').click()")
    wait_for(evaluate,"!document.getElementById('ledgerOcrConfirmation').hidden")
    assert evaluate("document.getElementById('ledgerOcrTotal').textContent.includes('18,014,398,509,481,982') && __reviewFlow.commits.length===0")


def test_accountinfo_unknown_zero_duplicate_and_brokerage_cash_contract(chrome_preview):
    evaluate=open_review_ui(chrome_preview,320)
    source=(Path(__file__).resolve().parents[1]/'app/static/wealth-accountinfo-import.js').read_text(encoding='utf-8')
    evaluate(source)
    result=evaluate("""(()=>{
      const api=window.WealthAccountInfoImport;
      const raw={source_row:1,tokens:['합성은행','987654321012','가상입출금','2020-01-01','활동성']};
      const missing=api.parseRowTokens(raw);
      const zero=api.parseRowTokens({...raw,tokens:[...raw.tokens,'0원']});
      const unknown=api.decorateRows({rows:[missing]},'합성소유자',{})[0];
      const existing=api.decorateRows({rows:[missing]},'합성소유자',{
        bankAccounts:[{bank_name:'합성은행',account_number:'987654321012',owner:'합성소유자'}]})[0];
      const broker={...missing,institution:'합성증권',reported_balance_krw:777777,product:'일반'};
      const csv=api.brokerageCsv(api.decorateRows({rows:[broker]},'합성소유자',{}),'합성소유자');
      return {unknown:missing.reported_balance_krw===null,zero:zero.reported_balance_krw===0,
        placeholder:unknown.import_balance_krw==='0',unselected:!unknown.default_selected,
        review:unknown.import_status==='review',duplicate:existing.import_status==='duplicate'&&!existing.default_selected,
        noBrokerBalance:!csv.includes('777777'),zeroCash:csv.includes(',0,0,미적용,')};
    })()""")
    assert all(result.values()),result
