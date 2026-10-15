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
        saveControls:[...panel.querySelectorAll('button')].filter(node=>/저장|등록|적용/.test(node.textContent)).length,
        hit:hit===button||button.contains(hit),visible:getComputedStyle(panel).display!=='none'};
    })()""")
    assert result['page']<=width and result['dialogScroll']<=result['dialogClient']+1,json.dumps(result,ensure_ascii=True)
    assert result['readOnly'] and result['exactMoney'] and result['saveControls']==0,result
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
    for path in ('/api/ledger/transactions','/api/ledger/import-file','/apply','/commit'):
        assert path not in js
    assert 'BigInt(row.amount)' in js


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
        balance:review.textContent.includes('₩11,234,567'),readOnly:review.textContent.includes('저장 기능 없음'),
        save:document.querySelectorAll('#ledgerOcrPanel [data-save], #ledgerOcrPanel button[type="submit"]').length,
        calls:__o11Calls};
    })()""")
    assert result['page']<=width and result['scroll']<=result['client']+1,result
    assert all(result[key] for key in ('partialDate','yearReason','transfer','amount','balance','readOnly')),result
    assert result['save']==0 and result['calls']==[{'path':'/api/ledger/document-import/preview','method':'POST'}]
