"""Isolated experiment worker. Never imported by Wealth or its API.

Only stdlib imports precede RLIMIT_AS; output is fixed codes/booleans/metrics.
"""
import argparse
from collections import Counter
import contextlib
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))


def merge_boxes(entries):
    """Experimental geometry adapter; never repair text/digits or join syllables."""
    groups=[]
    for entry in sorted(entries, key=lambda e:e[2][1]+e[2][3]/2):
        center=entry[2][1]+entry[2][3]/2
        match=next((g for g in groups if abs(center-g[0][2][1]-g[0][2][3]/2)
                    < min(entry[2][3],g[0][2][3])*.5),None)
        if match is None:groups.append([entry])
        else:match.append(entry)
    lines=[]
    for group in groups:
        group.sort(key=lambda e:e[2][0])
        x=min(e[2][0] for e in group); y=min(e[2][1] for e in group)
        lines.append({'text':' '.join(e[0] for e in group), 'confidence':min(e[1] for e in group),
                      'bbox':[x,y,max(e[2][0]+e[2][2] for e in group)-x,max(e[2][1]+e[2][3] for e in group)-y], 'reasons':[]})
    return lines


def apply_geometry(lines, width, height):
    for line in lines:
        x,y,w,h=line['bbox']
        if width<320:line['reasons'].append('image_low_resolution')
        if h<12:line['reasons'].append('text_too_small')
        if x<=1 or y<=1 or x+w>=width-1 or y+h>=height-1:line['reasons'].append('row_clipped')
    return lines


def ocr_metrics(lines, expected):
    # Whitespace normalization is comparison ONLY, never parser input/repair.
    compact=lambda s:re.sub(r'\s+','',s)
    observed=[line['text'] for line in lines]
    numeric=lambda items:Counter(token for line in items for token in re.findall(r'(?<![\d,.])([+\-]?\d[\d,]*)\s*원',line))
    actual=numeric(observed); wanted=numeric(expected)
    dates=[s for s in expected if re.fullmatch(r'\d+월\s*\d+일',s)]
    parties=[s for s in expected if s.startswith('가상')]
    return {'numeric_exact':actual==wanted, 'numeric_expected':sum(wanted.values()),
            'numeric_matched':sum((actual&wanted).values()),
            'party_exact':sum(s in observed for s in parties),'party_expected':len(parties),
            'date_exact':sum(any(compact(s)==compact(v) for v in observed) for s in dates),
            'date_expected':len(dates)}


def ledger_checks(result, case):
    rows=result['rows']; bank=case['kind']=='bank'; variant=case.get('variant')
    parties=['가상입금처','가상출금처'] if bank else ['가상카페','가상서점']
    amounts=['1234567','234567'] if bank else ['12345','23456']
    days=[14,13]
    if variant=='duplicate':parties=['가상카페']*2;amounts=['12345']*2;days=[14,14]
    if variant in ('cancel','refund'):parties[0]='가상카페 '+('취소' if variant=='cancel' else '환불')
    checks={'row_count':len(rows)==2,'review':all(r['review_status']=='review_required' for r in rows),
            'owner_null':all(r['owner'] is None and r['account_id'] is None for r in rows),
            'year_null':all(r['transaction_date'] is None and r['transaction_date_parts']['year'] is None for r in rows)}
    checks['party']=len(rows)==2 and all(r['counterparty' if bank else 'merchant']==p for r,p in zip(rows,parties))
    checks['amount']=len(rows)==2 and all(r['amount']==a for r,a in zip(rows,amounts))
    checks['dates']=len(rows)==2 and all(r['transaction_date_parts']=={'year':None,'month':10,'day':d} for r,d in zip(rows,days))
    checks['sign']=not bank or (len(rows)==2 and [r['direction'] for r in rows]==['inflow','outflow'])
    checks['balance']=not bank or (len(rows)==2 and [r['balance_after'] for r in rows]==['11234567','11000000'])
    if variant in ('cancel','refund'):
        checks['semantics']=bool(rows) and rows[0]['transaction_type_candidate']==('card_cancellation' if variant=='cancel' else 'refund')
    # Low-resolution raw errors must never become accepted financial values.
    if case['width']<320:
        checks['safe_rejection']=all(r['amount'] is None and r['balance_after'] is None
                                     and r['counterparty'] is None and r['merchant'] is None for r in rows)
        required=('review','owner_null','year_null','safe_rejection')
    else:required=tuple(checks)
    return checks, all(checks[key] for key in required)


def pension_checks(result, kind, page_texts, multi):
    fields={r['key']:r for r in result['fields']}
    checks={'document_type':result['document_type']==kind and result['detected_type']==kind}
    for key, value in [('total_paid_amount',1200000),('paid_months',12),('query_date','2026-10-14')]:
        checks[key]=key in fields and fields[key]['value']==value
        checks[key+'_review']=key in fields and fields[key]['status']=='OCR 확인 필요'
    checks['json']=json.loads(json.dumps(result,allow_nan=False))==result
    checks['page_order']=not multi or (len(page_texts)==2 and '2026.10.14' in page_texts[0] and '2026.10.15' in page_texts[1])
    return checks,all(checks.values())


def verify_models(bundle):
    for row in json.loads((HERE/'models.json').read_text())['models']:
        if hashlib.sha256((bundle/'models'/row['name']).read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('MODEL_CHECKSUM_FAIL')


def memory_snapshot():
    import resource
    values={}
    for line in Path('/proc/self/status').read_text().splitlines():
        key,_,value=line.partition(':')
        if key in ('VmRSS','VmSize','VmPeak'):
            values[key+'_kib']=int(value.split()[0])
    values['peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return values


def guard_finance():
    import app.services.financial_json as financial
    import app.services.secure_files as secure
    calls=[]
    def forbidden(*args,**kwargs):
        calls.append(True); raise RuntimeError('FINANCE_WRITE_DETECTED')
    for name in ('write_financial_json','ensure_financial_json','read_financial_json','financial_rmw'):
        # financial_rmw is also used as a decorator. Importing a decorated
        # function is harmless; executing any decorated mutation must fail.
        if name=='financial_rmw':
            def decorate(*args,**kwargs):
                if len(args)==1 and callable(args[0]):return forbidden
                return lambda function:forbidden
            setattr(financial,name,decorate)
        else:setattr(financial,name,forbidden)
    for name in ('atomic_write_private_json','atomic_write_private_bytes'):
        if hasattr(secure,name):setattr(secure,name,forbidden)
    return calls


def execute(bundle, case, machine):
    stage='DEPENDENCY_FAIL'; metrics={}; checks={}
    started=time.monotonic(); deadline=started+55
    try:
        if platform.system()!='Linux' or platform.machine()!=machine:
            raise ValueError('UNSUPPORTED_PLATFORM')
        def no_network(*a,**k):raise RuntimeError('OFFLINE_FAIL')
        socket.socket.connect=no_network; socket.create_connection=no_network
        for package,version in [('rapidocr','3.9.2'),('onnxruntime','1.24.3')]:
            if importlib.metadata.version(package)!=version:raise ValueError('DEPENDENCY_FAIL')
        before=time.monotonic()
        from PIL import Image
        import cv2
        from rapidocr import RapidOCR
        from rapidocr.utils.typings import OCRVersion,ModelType,LangRec
        cv2.setNumThreads(1)
        metrics['import_seconds']=time.monotonic()-before
        metrics['after_import']=memory_snapshot()
        stage='MODEL_CHECKSUM_FAIL';verify_models(bundle); checks['model_checksum']=True
        stage='MODEL_LOAD_FAIL';before=time.monotonic()
        engine=RapidOCR(params={
            'Det.model_path':str(bundle/'models/ch_PP-OCRv5_det_mobile.onnx'),
            'Det.ocr_version':OCRVersion.PPOCRV5,'Det.model_type':ModelType.MOBILE,
            'Rec.model_path':str(bundle/'models/korean_PP-OCRv5_rec_mobile.onnx'),
            'Rec.lang_type':LangRec.KOREAN,'Rec.ocr_version':OCRVersion.PPOCRV5,'Rec.model_type':ModelType.MOBILE,
            'Cls.model_path':str(bundle/'models/ch_ppocr_mobile_v2.0_cls_mobile.onnx'),
            'Global.use_cls':True,'Global.log_level':'critical',
            'EngineConfig.onnxruntime.intra_op_num_threads':1,'EngineConfig.onnxruntime.inter_op_num_threads':1})
        metrics['load_seconds']=time.monotonic()-before; checks['model_loaded']=True
        metrics['after_load']=memory_snapshot()
        calls=guard_finance()
        stage='OCR_VALUE_MISMATCH'
        with tempfile.TemporaryDirectory(prefix='rapidocr-case-') as temp:
            work=Path(temp); source=bundle/'fixtures'/case['path']
            if source.stat().st_size>10*1024*1024:raise ValueError('INPUT_LIMIT_FAIL')
            images=[source]
            if source.suffix=='.pdf':
                info=subprocess.run(['pdfinfo',str(source)],capture_output=True,check=True,timeout=10).stdout.decode()
                pages=re.search(r'^Pages:\s*(\d+)',info,re.M)
                if not pages or not 1<=int(pages[1])<=8:raise ValueError('INPUT_LIMIT_FAIL')
                text=subprocess.run(['pdftotext',str(source),'-'],capture_output=True,check=True,timeout=10).stdout
                checks['scanned_pdf']=not text.strip(b'\x0c \r\n\t')
                subprocess.run(['pdftoppm','-scale-to','1800','-png',str(source),str(work/'page')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=min(20,max(.1,deadline-time.monotonic())))
                images=sorted(work.glob('page-*.png'),key=lambda p:int(p.stem.split('-')[-1]))
                checks['pdf_pages']=len(images)==int(pages[1])
            pages=[];page_texts=[];all_lines=[]
            for page_number,path in enumerate(images,1):
                with Image.open(path) as im:
                    width,height=im.size
                    if width*height>16_000_000:raise ValueError('INPUT_LIMIT_FAIL')
                samples=[]
                for repetition in range(3):
                    if time.monotonic()>deadline:raise TimeoutError()
                    before=time.monotonic();output=engine(str(path));samples.append(time.monotonic()-before)
                    if time.monotonic()>deadline:raise TimeoutError()
                metrics['cold_seconds']=metrics.get('cold_seconds',0)+samples[0]
                metrics['warm_seconds']=metrics.get('warm_seconds',0)+sum(samples[1:])/2
                entries=[]
                if output.txts:
                    for text,score,box in zip(output.txts,output.scores,output.boxes):
                        xs=[float(p[0]) for p in box];ys=[float(p[1]) for p in box]
                        entries.append((text,float(score)*100,[min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)]))
                lines=apply_geometry(merge_boxes(entries),width,height)
                page_text='\n'.join(l['text'] for l in lines);page_texts.append(page_text);all_lines+=lines
                pages.append({'page':page_number,'text':page_text,'method':'ocr_tsv','ocr_lines':lines})
            metrics.update(ocr_metrics(all_lines,case['lines']))
            stage='PARSER_MISMATCH'
            if case['kind'] in ('bank','card'):
                from app.services.ledger_document import parse_pages
                extra,ok=ledger_checks(parse_pages(pages,case['kind']+'_transactions'),case)
            else:
                from app.services.national_pension_import import parse_text
                extra,ok=pension_checks(parse_text('\n'.join(page_texts),ocr=True),case['kind'],page_texts,case.get('multipage',False))
            checks.update(extra)
            checks['finance_writes_zero']=not calls and not Path('/tmp/finance').exists()
            checks['offline']=True  # Docker network none is independently required by runner.
            temp_path=work
        checks['cleanup']=not temp_path.exists()
        ok=ok and all(checks.get(k,False) for k in ('finance_writes_zero','cleanup','model_checksum','model_loaded'))
        ok=ok and checks.get('scanned_pdf',True) and checks.get('pdf_pages',True)
        return {'status':'PASS' if ok else 'FAIL','code':'OK' if ok else 'PARSER_MISMATCH','checks':checks,'metrics':metrics}
    except MemoryError:
        return {'status':'FAIL','code':'RLIMIT_AS_FAIL','stage':stage,'metrics':metrics,'checks':checks}
    except (TimeoutError,subprocess.TimeoutExpired):
        return {'status':'FAIL','code':'CPU_TIMEOUT','stage':stage,'metrics':metrics,'checks':checks}
    except Exception as error:
        allowed={'MODEL_CHECKSUM_FAIL','DEPENDENCY_FAIL','OFFLINE_FAIL','UNSUPPORTED_PLATFORM','FINANCE_WRITE_DETECTED','INPUT_LIMIT_FAIL'}
        code=str(error) if str(error) in allowed else stage
        return {'status':'FAIL','code':code,'stage':stage,'metrics':metrics,'checks':checks}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--case',required=True);parser.add_argument('--machine',required=True)
    parser.add_argument('--limit-mib',type=int,required=True);args=parser.parse_args()
    import resource
    limit=args.limit_mib*1024*1024
    resource.setrlimit(resource.RLIMIT_AS,(limit,limit));resource.setrlimit(resource.RLIMIT_CPU,(60,60))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(20*1024*1024,)*2)
    os.umask(0o077);logging.disable(logging.CRITICAL)
    cases=json.loads((args.bundle/'cases.json').read_text(encoding='utf-8'))
    case=next(row for row in cases if row['id']==args.case)
    # Suppress native/Python diagnostic text. Only the allowlisted report leaves.
    with open(os.devnull,'w') as sink, contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
        result=execute(args.bundle,case,args.machine)
    result.update(id=args.case,limit_mib=args.limit_mib,
                  peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    print(json.dumps(result,allow_nan=False),flush=True)


if __name__=='__main__':main()
