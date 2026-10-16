"""Offline native-image OCR smoke. Never loads a portfolio or saves an import."""
import argparse
from contextlib import contextmanager
import ast
import hashlib
import inspect
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


def command(args, timeout=30):
    # Do not print raw decoder output, even though these fixtures are synthetic.
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=False)
    if result.returncode:
        raise SmokeCheckError('Required offline command failed: ' + Path(args[0]).name)
    return result.stdout.decode('utf-8', errors='strict')


class SmokeCheckError(RuntimeError):
    """An explicit failed smoke assertion, rather than an unknown exception."""


def require(condition, message):
    if not condition:
        raise SmokeCheckError(message)


class SmokeSafetyError(RuntimeError):
    """Integrity or cleanup cannot be proved; never continue to another input."""


class LedgerOCRError(RuntimeError):
    """Expected OCR/validation failure after safety checks have completed."""


@contextmanager
def ledger_workspace(prefix='wealth-ledger-smoke-'):
    manager = tempfile.TemporaryDirectory(prefix=prefix)
    directory = manager.__enter__()
    try:
        yield directory
    finally:
        try:
            manager.__exit__(None, None, None)
            if Path(directory).exists() or Path(directory).is_symlink():
                raise SmokeSafetyError('Ledger workspace cleanup failed')
        except Exception:
            raise SmokeSafetyError('Ledger workspace cleanup failed') from None


def check_ledger_integrity(data, inputs, sentinels):
    # Inspect without repairing/deleting evidence. Inspect both independent
    # boundaries even if one fails; never disclose exception/path contents.
    failed = False
    try:
        if data.is_symlink() or not data.is_dir():
            failed = True
        else:
            failed |= set(data.iterdir()) != set(sentinels)
            failed |= any(path.is_symlink() or not path.is_file() or path.read_bytes() != content
                          for path, content in sentinels.items())
    except Exception:
        failed = True
    try:
        failed |= inputs.is_symlink() or not inputs.is_dir() or bool(list(inputs.iterdir()))
    except Exception:
        failed = True
    if failed:
        raise SmokeSafetyError('Ledger integrity or worker cleanup failed')


def recognize(path):
    text = command(['tesseract', str(path), 'stdout', '-l', 'kor+eng', '--psm', '6'])
    require('국민연금납부내역확인' in re.sub(r'\s+', '', text),
            'Synthetic Korean phrase was not recognized')


def validate_ledger_result(result, document_type):
    """Compare exact fictional source values, never a normalized OCR mistake."""
    require(isinstance(result, dict) and
            set(result) == {'document_type', 'status', 'rows', 'warnings'},
            'Ledger preview response contract failed')
    require(result['document_type'] == document_type,
            'Ledger document type failed (unknown=' + str(result['document_type'] == 'unknown') + ')')
    require(result['status'] == 'review_required', 'Ledger review status failed')
    require(isinstance(result['rows'], list) and len(result['rows']) == 2,
            'Ledger must contain exactly two transactions, excluding headers/totals')
    expected = (
        (('가상입금처', '1234567', 'inflow', '11234567', '09:10'),
         ('가상출금처', '234567', 'outflow', '11000000', '10:20'))
        if document_type == 'bank_transactions' else
        (('가상카페', '12345', 'unknown', None, None),
         ('가상서점', '23456', 'unknown', None, None))
    )
    seen_ids = set()
    for row, values, day in zip(result['rows'], expected, (14, 13)):
        party, amount, direction, balance, clock = values
        label = 'counterparty' if document_type == 'bank_transactions' else 'merchant'
        require(row.get(label) == party, 'Synthetic Korean ledger party extraction failed')
        require(row.get('amount') == amount, 'Synthetic ledger amount extraction failed')
        require(row.get('direction') == direction, 'Synthetic ledger direction failed')
        require(row.get('balance_after') == balance, 'Synthetic ledger balance separation failed')
        require(row.get('transaction_time') == clock, 'Synthetic ledger time extraction failed')
        require(row.get('transaction_date') is None and row.get('transaction_date_parts') ==
                {'year': None, 'month': 10, 'day': day}, 'Ledger must not invent a transaction year')
        require('year_missing' in row.get('review_reasons', []) and
                row.get('review_status') == 'review_required', 'Ledger human review contract failed')
        require(row.get('owner') is None and row.get('account_id') is None,
                'Ledger must not infer an owner/account')
        location = row.get('source_location') or {}
        require(location.get('method') == 'ocr_tsv' and location.get('page') == 1 and
                location.get('bbox'), 'Ledger must use actual image OCR, including scanned PDFs')
        require(row.get('row_id') and row['row_id'] not in seen_ids,
                'Ledger candidate IDs must be distinct')
        seen_ids.add(row['row_id'])
        require(not {'raw_text', 'original_filename', 'storage_path'} & set(row),
                'Ledger preview must not expose raw document data')
        if document_type == 'card_transactions':
            require(row.get('transaction_type_candidate') == 'card_approval_candidate' and
                    row.get('payment_method_candidate') == 'card', 'Card approval candidate contract failed')


def diagnose_ledger_evidence(target, kind):
    """Only the disposable PUBLIC synthetic smoke; never print OCR/preview text."""
    probe = '''import json, sys
from pathlib import Path
from app.services.document_extraction import extract_pages, set_worker_limits
from app.services.ledger_document import classification_evidence, needs_ocr
set_worker_limits()
pages = extract_pages(Path(sys.argv[1]), sys.argv[2], needs_ocr=needs_ocr, tsv=True)
print(json.dumps(classification_evidence(pages)))
'''
    evidence = json.loads(command([sys.executable, '-c', probe, str(target), kind], timeout=75))
    keys = ('date', 'money', 'bank_header', 'card_header', 'tsv_lines')
    require(isinstance(evidence, dict) and set(evidence) == set(keys) and
            all(type(evidence[key]) is bool for key in keys), 'Ledger diagnostic contract failed')
    print('DIAG: ledger ' + ' '.join(key + '=' + str(evidence[key]) for key in keys))


PARTY_BOOL_FIELDS = ('original_candidate_exists', 'original_split', 'bbox_present',
    'image_geometry_ok', 'source_quality_ok', 'source_reasons_allowed', 'bbox_valid', 'overlap', 'refine_called',
    'txt_created', 'tsv_created', 'output_checks_ok', 'output_geometry_ok',
    'txt_nonempty', 'txt_one_line', 'tsv_one_line', 'txt_split', 'reread_tsv_split',
    'txt_tsv_equal', 'txt_tsv_spacing_differs', 'party_format_ok', 'accepted', 'final_party_null',
    'final_party_exact', 'review_reasons_allowed', 'observer_supported')
PARTY_BUCKETS = {'unknown', 'under30', '30to79', '80to89', '90plus'}
PARTY_SOURCE_REASONS = {'unknown','none','multiple','text_too_small','image_low_resolution',
                        'row_clipped','ocr_geometry_missing'}
CI_BANK_FIXTURE = Path('/fixtures/bank.png')
PARTY_REJECTS = {'unknown', 'not_candidate', 'summary_excluded', 'date_excluded',
    'ambiguous_numeric', 'image_geometry_guard', 'source_quality_guard', 'bbox_guard',
    'overlap_guard', 'output_read_guard', 'output_format_guard', 'reread_initial_guard',
    'txt_tsv_guard', 'party_format_guard', 'numeric_guard', 'final_guard', 'accepted'}


def confidence_bucket(value):
    if type(value) not in (int, float) or not 0 <= value <= 100:
        return 'unknown'
    return 'under30' if value < 30 else '30to79' if value < 80 else '80to89' if value < 90 else '90plus'


def empty_party_evidence():
    return {**dict.fromkeys(PARTY_BOOL_FIELDS), 'original_confidence_bucket':'unknown',
            'reread_confidence_bucket':'unknown', 'refine_calls':None, 'reject_code':'unknown',
            'source_reason_code':'unknown'}


class PartyObserver:
    """Read actual Python execution, ONLY in the disposable synthetic probe.

    AST anchors refer to executed statements, not a duplicate OCR algorithm.
    Raw text/coordinates/frame locals are never serialized. Missing anchors or
    observation errors invalidate the trace instead of inventing rejection codes.
    """
    def __init__(self, ledger):
        self.ledger = ledger
        self.refine = ledger.LineRecognizer.refine.__code__
        self.parse = ledger.parse_pages.__code__
        self.read = ledger.read_line_output.__code__
        self.records, self.active, self.pending, self.rows = {}, {}, {}, []
        self.captured_rows = set()
        self.supported = True
        self.anchors = {}
        self._anchors(ledger.LineRecognizer.refine, True)
        self._anchors(ledger.parse_pages, False)
        required = {'prepare','start','role','quality_pass','bbox_pass','overlap',
                    'outputs','initial','compare','party_check','final','party_source','row'}
        self.supported = required <= {tag for tags in self.anchors.values() for tag in tags}

    def _add(self, function, start, node, tag):
        self.anchors.setdefault((function.__code__, start+node.lineno-1), []).append(tag)

    def _anchors(self, function, refine):
        source, start = inspect.getsourcelines(function)
        tree = ast.parse(textwrap.dedent(''.join(source)))
        for node in ast.walk(tree):
            if refine and isinstance(node, ast.With):
                self._add(function,start,node,'prepare')
            if isinstance(node, ast.Assign):
                names = {n.id for target in node.targets for n in ast.walk(target) if isinstance(n,ast.Name)}
                used = {n.id for n in ast.walk(node.value) if isinstance(n,ast.Name)}
                if refine:
                    for name, tag in (('content','start'),('crop_box','bbox_pass'),
                                      ('candidates','outputs'),('replacement','compare')):
                        if name in names:self._add(function,start,node,tag)
                    if {'x','y','w','h'} <= names:self._add(function,start,node,'quality_pass')
                    if 'valid' in names and 'fullmatch' in {n.attr for n in ast.walk(node.value) if isinstance(n,ast.Attribute)}:
                        self._add(function,start,node,'party_check')
                    if 'valid' in names and 'numeric_signature' in used:self._add(function,start,node,'numeric_check')
                else:
                    if 'party' in names and 'safe_label' in used:self._add(function,start,node,'party_source')
                    if 'party' in names and isinstance(node.value,ast.Constant) and node.value.value is None:
                        self._add(function,start,node,'clear_party')
            if not refine and isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id=='reason':
                self._add(function,start,node,'row')
            if not refine or not isinstance(node,ast.If):continue
            used = {n.id for n in ast.walk(node.test) if isinstance(n,ast.Name)}
            if used=={'numeric','party'}:self._add(function,start,node,'role')
            if isinstance(node.test,ast.Name) and node.test.id=='overlaps':
                self._add(function,start,node,'overlap')
            if isinstance(node.test,ast.Name) and node.test.id=='valid':
                tag = 'final' if isinstance(node.body[0],ast.Assign) and isinstance(node.body[0].targets[0],ast.Subscript) else 'initial'
                self._add(function,start,node,tag)
            if {'width','height','tsv_size'} <= used:
                for child in ast.walk(node):
                    if isinstance(child,ast.Return):self._add(function,start,child,'reject:image_geometry_guard')
            code = ('summary_excluded' if 'SUMMARY_LABELS' in used else
                    'date_excluded' if 'date_marker' in used and 'TIME' in used else
                    'not_candidate' if used=={'numeric','party'} else
                    'ambiguous_numeric' if {'numeric','MONEY','re'} <= used else
                    'source_quality_guard' if {'box','line'} <= used else
                    'bbox_guard' if {'w','h','x','y','width','height'} <= used else
                    'overlap_guard' if used=={'overlaps'} else None)
            if code:
                for child in node.body:
                    if isinstance(child,ast.Continue):self._add(function,start,child,'reject:'+code)
            for child in node.body:
                if isinstance(child,ast.Raise) and 'output format' in ast.unparse(child):
                    self._add(function,start,child,'reject:output_format_guard')

    def observe(self, callback):
        previous = sys.gettrace()
        sys.settrace(self.trace)
        try:return callback()
        finally:sys.settrace(previous)

    def trace(self, frame, event, arg):
        try:return self._trace(frame,event,arg)
        except SmokeSafetyError:raise
        except Exception:
            raise SmokeSafetyError('Diagnostic observation failed') from None

    def _trace(self, frame, event, arg):
        parent = frame.f_back
        # Observe the REAL callback invocation/return without replacing it.
        if parent and parent.f_code==self.refine and frame.f_code==getattr(parent.f_locals.get('run'),'__code__',None):
            record = self.active.get(id(parent))
            if record is not None:
                if event=='call':
                    record['refine_called']=True;record['refine_calls']+=1
                elif event=='return':
                    for key in ('txt','tsv'):
                        path=parent.f_locals.get(key+'_path')
                        record[key+'_created']=path.is_file() if isinstance(path,Path) else None
            return self.trace
        if frame.f_code==self.read and parent and parent.f_code==self.refine:
            if event=='exception':
                record=self.active.get(id(parent))
                if record is not None:
                    record.update(output_checks_ok=False,accepted=False,reject_code='output_read_guard')
            return self.trace
        if frame.f_code not in (self.refine,self.parse):return None
        if event!='line':return self.trace
        values=frame.f_locals
        for tag in self.anchors.get((frame.f_code,frame.f_lineno),[]):
            if tag=='prepare':
                for line in values.get('lines',[]):
                    if id(line) in self.records:continue  # `with` exit can revisit its source line.
                    reasons=set(line['reasons'])
                    allowed=reasons <= PARTY_SOURCE_REASONS-{'unknown','none','multiple'}
                    self.records[id(line)]={**empty_party_evidence(),
                        'original_split':bool(self.ledger.SPLIT_HANGUL.search(line['text'])),
                        'original_confidence_bucket':confidence_bucket(line['confidence']),
                        'bbox_present':line['bbox'] is not None, 'refine_called':False, 'refine_calls':0,
                        'source_reasons_allowed':allowed,
                        'source_reason_code':('unknown' if not allowed else 'none' if not reasons else
                                              next(iter(reasons)) if len(reasons)==1 else 'multiple')}
            if tag=='start':
                record=self.records.get(id(values.get('line')))
                self.active[id(frame)]=record
                if record is not None:record['image_geometry_ok']=True
            record=self.active.get(id(frame))
            if frame.f_code==self.parse:
                if tag=='party_source':self.pending[id(frame)]=self.records.get(id(values.get('line')))
                elif tag=='clear_party':self.pending[id(frame)]=None
                elif tag=='row' and isinstance(values.get('row'),dict) and id(values['row']) not in self.captured_rows:
                    self.captured_rows.add(id(values['row']))
                    self.rows.append(self.pending.get(id(frame)))
                    self.pending[id(frame)]=None
                continue
            if tag=='reject:image_geometry_guard':
                for line in values.get('lines',[]):
                    item=self.records.get(id(line))
                    if item is not None:item.update(image_geometry_ok=False,accepted=False,reject_code='image_geometry_guard')
            if record is None:continue
            if tag=='role':record['original_candidate_exists']=bool(values.get('party'))
            elif tag=='quality_pass':record['source_quality_ok']=True
            elif tag=='bbox_pass':record['bbox_valid']=True
            elif tag=='overlap':record['overlap']=bool(values.get('overlaps'))
            elif tag=='outputs':record['output_checks_ok']=True
            elif tag=='initial':
                candidates=values.get('candidates',[])
                txt=values.get('txt')
                record['txt_nonempty']=bool(txt) if isinstance(txt,str) else None
                record['txt_one_line']=(bool(txt) and len(txt.splitlines())==1) if isinstance(txt,str) else None
                record['txt_split']=bool(self.ledger.SPLIT_HANGUL.search(txt)) if isinstance(txt,str) else None
                record['tsv_one_line']=len(candidates)==1
                record['reread_tsv_split']=bool(self.ledger.SPLIT_HANGUL.search(candidates[0]['text'])) if len(candidates)==1 else None
                record['reread_confidence_bucket']=confidence_bucket(candidates[0]['confidence']) if len(candidates)==1 else 'unknown'
                record['output_geometry_ok']=values.get('output_size_matches')
                record['_initial']=bool(values.get('valid'))
            elif tag=='compare' and record.get('_initial'):
                record['txt_tsv_equal']=bool(values.get('valid'))
                if record['txt_tsv_equal']:
                    record['txt_tsv_spacing_differs']=values['txt']!=values['candidates'][0]['text']
            elif tag=='party_check':record['_party_check']=True
            elif tag=='numeric_check':record['_numeric_check']=True
            elif tag=='final':
                valid=bool(values.get('valid'));record['accepted']=valid
                if record.get('_party_check'):record['party_format_ok']=valid
                record['reject_code']=('accepted' if valid else
                    'reread_initial_guard' if not record.get('_initial') else
                    'txt_tsv_guard' if record.get('txt_tsv_equal') is False else
                    'party_format_guard' if record.get('_party_check') else
                    'numeric_guard' if record.get('_numeric_check') else 'final_guard')
            elif tag.startswith('reject:'):
                code=tag.split(':',1)[1];record.update(accepted=False,reject_code=code)
                if code=='source_quality_guard':record['source_quality_ok']=False
                if code=='bbox_guard':record['bbox_valid']=False
        return self.trace


def party_report(result, observer):
    rows=result.get('rows',[]) if isinstance(result,dict) else []
    report=[]
    for index,expected in enumerate(('가상입금처','가상출금처')):
        observed=observer.rows[index] if index<len(observer.rows) else None
        evidence=empty_party_evidence()
        if observer.supported and observed is not None:
            evidence.update({key:observed[key] for key in evidence})
        evidence['observer_supported']=observer.supported
        if index<len(rows) and isinstance(rows[index],dict):
            row=rows[index]
            evidence['final_party_null']=row.get('counterparty') is None
            evidence['final_party_exact']=row.get('counterparty')==expected
            reasons=row.get('review_reasons')
            evidence['review_reasons_allowed']=(isinstance(reasons,list) and
                all(isinstance(code,str) and code in observer.ledger.REASONS for code in reasons))
        report.append(evidence)
    return report


def emit_party_report(rows, preview):
    keys=set(empty_party_evidence())
    require(isinstance(rows,list) and len(rows)==2,'Party diagnostic schema failed')
    for row in rows:
        require(isinstance(row,dict) and set(row)==keys,'Party diagnostic schema failed')
        require(all(row[key] is None or type(row[key]) is bool for key in PARTY_BOOL_FIELDS),'Party diagnostic boolean failed')
        require(row['refine_calls'] is None or (type(row['refine_calls']) is int and 0<=row['refine_calls']<=8),'Party diagnostic count failed')
        require(row['reject_code'] in PARTY_REJECTS and
            row['source_reason_code'] in PARTY_SOURCE_REASONS and
            row['original_confidence_bucket'] in PARTY_BUCKETS and row['reread_confidence_bucket'] in PARTY_BUCKETS,
            'Party diagnostic code failed')
    source=preview.get('rows',[]) if isinstance(preview,dict) else []
    for index,row in enumerate(rows):
        values=dict(row)
        original=source[index] if index<len(source) and isinstance(source[index],dict) else None
        values['preview_party_null']=original.get('counterparty') is None if original is not None else None
        values['preview_party_exact']=original.get('counterparty')==('가상입금처','가상출금처')[index] if original is not None else None
        def safe(value):return 'unknown' if value is None else str(value).lower() if type(value) is bool else str(value)
        print('DIAG bank.png row='+str(index+1)+' '+' '.join(key+'='+safe(value) for key,value in values.items()))


def party_probe(path):
    root=str(Path(__file__).resolve().parents[2])
    if root not in sys.path:sys.path.insert(0,root)
    from app.services import ledger_document as ledger
    require(sys.platform=='linux' and os.environ.get('WEALTH_ENV')=='test' and
        path.name=='bank.png' and path.parent.name.startswith('wealth-party-probe-'), 'Party probe input denied')
    ledger.set_worker_limits()
    observer=PartyObserver(ledger)
    try:result=observer.observe(lambda:ledger.extract(path,'png','bank_transactions'))
    except SmokeSafetyError:raise
    except (ValueError, SmokeCheckError, subprocess.TimeoutExpired):result=None  # No exception text or local variables in output.
    return party_report(result,observer)


def diagnose_bank_parties(source, preview):
    # This CLI-only replay accepts the public read-only CI fixture, never a
    # user-selected/API document. It does not modify production code or output.
    require(sys.platform=='linux' and not source.is_symlink() and
            source.resolve()==CI_BANK_FIXTURE, 'Party diagnostic input denied')
    with ledger_workspace(prefix='wealth-party-probe-') as directory:
        work=Path(directory);os.chmod(work,0o700)
        target=work/'bank.png';shutil.copyfile(source,target);os.chmod(target,0o600)
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--party-probe',str(target)],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
        try:output,_=process.communicate(timeout=75)
        except subprocess.TimeoutExpired:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.communicate()
            raise SmokeCheckError('Party diagnostic timeout') from None
        if process.returncode in (2, 3):raise SmokeSafetyError('Diagnostic safety or execution check failed')
        require(process.returncode==0 and len(output)<=20_000,'Party diagnostic subprocess failed')
        rows=json.loads(output)
    require(not work.exists(),'Party diagnostic cleanup failed')
    emit_party_report(rows,preview)


FOCUS_BOOL_FIELDS = ('source_quality_ok','bbox_valid','overlap','refine_called',
    'output_checks_ok','output_geometry_ok','txt_nonempty','txt_one_line','tsv_one_line',
    'txt_tsv_equal','accepted','expanded_crop_used','reread_confidence_ok',
    'reread_row_clipped','reread_text_too_small','reread_other_risks','txt_printable',
    'old_numeric_valid','new_numeric_valid','numeric_values_equal',
    'numeric_sign_equal','numeric_context_equal','numeric_tsv_equal',
    'parser_row_seen','document_type_matches')
FOCUS_KINDS = {'bank_amount','bank_balance','card_row'}
CI_LEDGER_INPUTS = {'bank.png':('png','bank_transactions'),
    'bank.pdf':('pdf','bank_transactions'),'card.jpg':('jpeg','card_transactions'),
    'card.pdf':('pdf','card_transactions')}


class FocusObserver(PartyObserver):
    """Synthetic smoke only: observe the same guards for amounts/balances/cards.

    Raw frame text/coordinates stay private. No production callback is replaced.
    The existing party diagnostic schema is deliberately unchanged.
    """
    def __init__(self, ledger):
        super().__init__(ledger)
        self.amount_rows=[]

    def _trace(self, frame, event, arg):
        result=super()._trace(frame,event,arg)
        if event!='line' or frame.f_code not in (self.refine,self.parse):return result
        values=frame.f_locals
        tags=self.anchors.get((frame.f_code,frame.f_lineno),[])
        if 'prepare' in tags:
            for number,line in enumerate(values.get('lines',[]),1):
                record=self.records.get(id(line))
                if record is not None:
                    record.setdefault('_source_line',number)
                    # Comparison/classification only, never parser text repair.
                    compact=re.sub(r'\s+','',line['text'])
                    record.setdefault('_balance',compact.startswith(('거래후잔액','잔액')))
                    record.setdefault('_detail',dict.fromkeys(FOCUS_BOOL_FIELDS))
        if frame.f_code==self.parse:
            if 'row' in tags:
                row=values.get('row')
                if isinstance(row,dict) and not any(item[0] is row for item in self.amount_rows):
                    self.amount_rows.append((row,self.records.get(id(values.get('line')))))
            return result
        record=self.active.get(id(frame))
        if record is None:return result
        detail=record.setdefault('_detail',dict.fromkeys(FOCUS_BOOL_FIELDS))
        if 'role' in tags:
            record['_numeric']=bool(values.get('numeric'))
        if 'initial' in tags:
            candidates=values.get('candidates',[]);txt=values.get('txt')
            one=len(candidates)==1
            reasons=set(values.get('candidate_risks',[]))
            detail.update(reread_confidence_ok=(candidates[0]['confidence'] is not None
                and candidates[0]['confidence']>=90) if one else None,
                reread_row_clipped='row_clipped' in reasons,
                reread_text_too_small='text_too_small' in reasons,
                reread_other_risks=bool(reasons-{'row_clipped','text_too_small'}),
                txt_printable=txt.isprintable() if isinstance(txt,str) else None)
            crop=values.get('crop_box');box=values.get('box')
            if crop is not None and box is not None:
                detail['expanded_crop_used']=crop[0]==box[0]-12 and crop[1]==box[1]-12
        if 'numeric_check' in tags:
            previous,current=values.get('previous'),values.get('current')
            old_sign,new_sign=values.get('old_sign'),values.get('new_sign')
            candidates=values.get('candidates',[])
            detail.update(old_numeric_valid=previous is not None,new_numeric_valid=current is not None,
                numeric_values_equal=previous==current if previous is not None and current is not None else None,
                numeric_sign_equal=(old_sign.group() if old_sign else None)==(new_sign.group() if new_sign else None),
                numeric_context_equal=values.get('context_matches'),
                numeric_tsv_equal=self.ledger.numeric_signature(candidates[0]['text'])==current if len(candidates)==1 and current is not None else None)
        return result


def focus_report(observer, document_type, result=None):
    selected=[('bank_amount' if document_type=='bank_transactions' else 'card_row',record)
              for _,record in observer.amount_rows[:6]]
    if not selected:
        # Classification can fail before any parser row exists. Still report
        # the actually visited numeric source guards, not invented rows.
        selected=[('bank_amount' if document_type=='bank_transactions' else 'card_row',record)
                  for record in observer.records.values() if record.get('_numeric') and not record.get('_balance')][:6]
    if document_type=='bank_transactions':
        selected += [('bank_balance',record) for record in observer.records.values() if record.get('_balance')][:4]
    report=[]
    for position,(kind,record) in enumerate(selected,1):
        values={**dict.fromkeys(FOCUS_BOOL_FIELDS),'kind':kind,'position':position,'source_line':None,
                'refine_calls':None,'original_confidence_bucket':'unknown',
                'reread_confidence_bucket':'unknown','reject_code':'unknown','source_reason_code':'unknown'}
        if observer.supported and record is not None:
            values.update({key:record.get(key) for key in FOCUS_BOOL_FIELDS if key in record})
            values.update({key:value for key,value in record.get('_detail',{}).items() if value is not None})
            values.update(source_line=record.get('_source_line'),refine_calls=record.get('refine_calls'),
                original_confidence_bucket=record.get('original_confidence_bucket','unknown'),
                reread_confidence_bucket=record.get('reread_confidence_bucket','unknown'),
                reject_code=record.get('reject_code','unknown'),
                source_reason_code=record.get('source_reason_code','unknown'))
            values['parser_row_seen']=any(item is record for _,item in observer.amount_rows)
        values['document_type_matches']=result.get('document_type')==document_type if isinstance(result,dict) else None
        report.append(values)
    return report


def emit_focus_report(rows, name):
    require(name in CI_LEDGER_INPUTS and isinstance(rows,list) and 0<len(rows)<=10,'Focused diagnostic schema failed')
    keys=set(FOCUS_BOOL_FIELDS)|{'kind','position','source_line','refine_calls',
        'original_confidence_bucket','reread_confidence_bucket','reject_code','source_reason_code'}
    # Validate ALL rows before emitting any output, including unexpected keys.
    for row in rows:
        require(isinstance(row,dict) and set(row)==keys,'Focused diagnostic schema failed')
        require(all(row[k] is None or type(row[k]) is bool for k in FOCUS_BOOL_FIELDS),'Focused diagnostic boolean failed')
        require(row['kind'] in FOCUS_KINDS and row['reject_code'] in PARTY_REJECTS and
                row['source_reason_code'] in PARTY_SOURCE_REASONS and
                row['original_confidence_bucket'] in PARTY_BUCKETS and row['reread_confidence_bucket'] in PARTY_BUCKETS,
                'Focused diagnostic code failed')
        for key,limit in [('position',10),('source_line',10000),('refine_calls',8)]:
            require(row[key] is None or type(row[key]) is int and 0<=row[key]<=limit,'Focused diagnostic count failed')
    for row in rows:
        safe=lambda v:'unknown' if v is None else str(v).lower() if type(v) is bool else str(v)
        print('DIAG '+name+' '+' '.join(key+'='+safe(value) for key,value in row.items()))


def focus_probe(path):
    root=str(Path(__file__).resolve().parents[2])
    if root not in sys.path:sys.path.insert(0,root)
    from app.services import ledger_document as ledger
    require(sys.platform=='linux' and os.environ.get('WEALTH_ENV')=='test' and
        path.name in CI_LEDGER_INPUTS and path.parent.name.startswith('wealth-focus-probe-'),
        'Focused diagnostic input denied')
    public=Path('/fixtures')/path.name
    require(not path.is_symlink() and not public.is_symlink() and
        hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(public.read_bytes()).digest(),
        'Focused diagnostic input denied')
    ledger.set_worker_limits()
    kind,document_type=CI_LEDGER_INPUTS[path.name]
    observer=FocusObserver(ledger)
    try:result=observer.observe(lambda:ledger.extract(path,kind,document_type))
    except SmokeSafetyError:raise
    except (ValueError, SmokeCheckError, subprocess.TimeoutExpired):result=None  # No exception text or raw frames in report.
    return focus_report(observer,document_type,result)


def is_public_ledger_fixture(source):
    return (sys.platform=='linux' and source.name in CI_LEDGER_INPUTS and not source.is_symlink()
            and source.resolve()==Path('/fixtures')/source.name)


def diagnose_ledger_rejections(source):
    require(is_public_ledger_fixture(source),'Focused diagnostic input denied')
    with ledger_workspace(prefix='wealth-focus-probe-') as directory:
        work=Path(directory);os.chmod(work,0o700)
        target=work/source.name;shutil.copyfile(source,target);os.chmod(target,0o600)
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--focus-probe',str(target)],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
        try:output,_=process.communicate(timeout=75)
        except subprocess.TimeoutExpired:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.communicate()
            raise SmokeCheckError('Focused diagnostic timeout') from None
        if process.returncode in (2, 3):raise SmokeSafetyError('Diagnostic safety or execution check failed')
        require(process.returncode==0 and len(output)<=40000,'Focused diagnostic subprocess failed')
        try:rows=json.loads(output)
        except (ValueError,UnicodeError):raise SmokeCheckError('Focused diagnostic output failed') from None
    emit_focus_report(rows,source.name)


def run_ledger_case(fixtures, name, kind, document_type):
    # Exercise the real preview coordinator AND the production worker. It owns
    # its process group timeout and private input cleanup; no finance API runs.
    # This file runs as /app/ops/pension-ocr/smoke.py, not with `python -m`.
    application_root = str(Path(__file__).resolve().parents[2])
    if application_root not in sys.path:
        sys.path.insert(0, application_root)
    from app.services.ledger_document_import import preview
    keys = ('WEALTH_ENV', 'WEALTH_DISABLE_ENV_FILE', 'WEALTH_DATA_DIR', 'DATA_DIR', 'TMPDIR')
    saved_env = {key: os.environ.get(key) for key in keys}
    saved_tempdir = tempfile.tempdir
    with ledger_workspace() as directory:
        work = Path(directory)
        os.chmod(work, 0o700)
        data = work / 'synthetic-data'; data.mkdir(mode=0o700)
        inputs = work / 'ocr-inputs'; inputs.mkdir(mode=0o700)
        sentinels = {data / 'ledger.json': b'{"transactions":[],"synthetic_only":true}',
                     data / 'portfolio.json': b'{"cash":12345,"synthetic_only":true}'}
        for path, content in sentinels.items():
            path.write_bytes(content); os.chmod(path, 0o600)
        source = fixtures / name
        require(source.is_file(), 'Synthetic ledger fixture missing')
        target = work / name
        shutil.copyfile(source, target); os.chmod(target, 0o600)
        if kind == 'pdf':
            info = command(['pdfinfo', str(target)])
            require(re.search(r'^Pages:\s*1\s*$', info, re.M) is not None,
                    'Synthetic ledger PDF must contain exactly one page')
            require(not command(['pdftotext', '-enc', 'UTF-8', str(target), '-']).strip(),
                    'Synthetic ledger PDF must have no text layer')
        try:
            os.environ.update(WEALTH_ENV='test', WEALTH_DISABLE_ENV_FILE='1',
                              WEALTH_DATA_DIR=str(data), DATA_DIR=str(data), TMPDIR=str(inputs))
            # Only this single-threaded smoke process: scope all preview temp
            # directories so their disappearance is observable without mocks.
            tempfile.tempdir = str(inputs)
            mime = {'png': 'image/png', 'jpeg': 'image/jpeg', 'pdf': 'application/pdf'}[kind]
            try:
                result = preview(target.read_bytes(), mime, document_type)
            except (ValueError, subprocess.TimeoutExpired):
                raise LedgerOCRError('Ledger OCR worker failed') from None
            if isinstance(result, dict) and result.get('document_type') != document_type:
                diagnose_ledger_evidence(target, kind)
            if name=='bank.png' and document_type=='bank_transactions' and isinstance(result,dict):
                rows=result.get('rows',[])
                if isinstance(rows,list) and any(index>=len(rows) or not isinstance(rows[index],dict) or
                    rows[index].get('counterparty')!=expected for index,expected in enumerate(('가상입금처','가상출금처'))):
                    try:diagnose_bank_parties(source,result)
                    except SmokeSafetyError:raise
                    except (SmokeCheckError, ValueError, subprocess.TimeoutExpired):print('DIAG bank.png probe_status=unavailable')
            try:validate_ledger_result(result, document_type)
            except SmokeSafetyError:raise
            except SmokeCheckError as validation_error:
                if is_public_ledger_fixture(source):
                    try:diagnose_ledger_rejections(source)
                    except SmokeSafetyError:raise
                    except (SmokeCheckError, ValueError, subprocess.TimeoutExpired):print('DIAG '+name+' focus_probe_status=unavailable')
                raise LedgerOCRError(str(validation_error)) from None
        finally:
            # Restore process scope even when integrity inspection itself fails.
            try:
                check_ledger_integrity(data, inputs, sentinels)
            finally:
                tempfile.tempdir = saved_tempdir
                for key, value in saved_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
    print('PASS: synthetic ledger OCR, exact values, review, no writes and cleanup ('
          + document_type + ', ' + kind + ')')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-machine', required=True)
    parser.add_argument('--fixtures', type=Path, default=Path('/fixtures'))
    args = parser.parse_args()
    require(sys.platform == 'linux' and platform.machine() == args.expected_machine,
            'Image runtime architecture does not match the native runner')
    for tool in ('tesseract', 'pdfinfo', 'pdftoppm', 'pdftotext'):
        require(shutil.which(tool) is not None, 'Missing required offline tool: ' + tool)
    version=command(['tesseract', '--version'])
    require('tesseract' in version.lower(),
            'Tesseract version check failed')
    matched=re.match(r'tesseract\s+(\d+\.\d+\.\d+)(?:\s|$)',version)
    print('DIAG runtime tesseract_version='+(matched[1] if matched else 'unknown'))
    languages = set(command(['tesseract', '--list-langs']).splitlines())
    require({'kor', 'eng', 'osd'} <= languages, 'Required Tesseract language data missing')
    command(['pdfinfo', '-v'])
    command(['pdftoppm', '-v'])
    print('PASS: native architecture, OCR binaries and kor/eng/osd language data')

    # The production worker writes intermediates beside the input. Copy only
    # synthetic read-only fixtures to private container-local temporary storage.
    with tempfile.TemporaryDirectory(prefix='wealth-ocr-smoke-') as directory:
        work = Path(directory)
        os.chmod(work, 0o700)
        for suffix in ('png', 'pdf'):
            source = args.fixtures / ('synthetic.' + suffix)
            require(source.is_file(), 'Synthetic input missing')
            target = work / source.name
            shutil.copyfile(source, target)
            os.chmod(target, 0o600)
        recognize(work / 'synthetic.png')
        info = command(['pdfinfo', str(work / 'synthetic.pdf')])
        require(re.search(r'^Pages:\s*1\s*$', info, re.M) is not None,
                'Synthetic PDF must contain exactly one page')
        command(['pdftoppm', '-f', '1', '-l', '1', '-singlefile', '-scale-to',
                 '3200', '-png', str(work / 'synthetic.pdf'), str(work / 'raster')])
        recognize(work / 'raster.png')
        print('PASS: Korean PNG OCR and Poppler PDF rasterization/Korean OCR')
        for kind in ('png', 'pdf'):
            output = command([sys.executable, '-m', 'app.services.national_pension_document',
                              str(work / ('synthetic.' + kind)), kind, 'auto'], timeout=75)
            result = json.loads(output)
            require(result.get('document_type') == 'history' and
                    result.get('detected_type') == 'history', 'Document type extraction failed')
            fields = {row['key']: row for row in result['fields']}
            for key, expected in (('total_paid_amount', 1200000), ('paid_months', 12),
                                  ('query_date', '2026-10-14')):
                require(key in fields and fields[key]['value'] == expected,
                        'Synthetic document field extraction failed: ' + key)
                require(fields[key]['status'] == 'OCR 확인 필요',
                        'OCR result must still require human review')
            print('PASS: production document worker, strict JSON and review contract (' + kind + ')')

    ledger_failures=[]
    for name, kind, document_type in (
        ('bank.png', 'png', 'bank_transactions'),
        ('bank.pdf', 'pdf', 'bank_transactions'),
        ('card.jpg', 'jpeg', 'card_transactions'),
        ('card.pdf', 'pdf', 'card_transactions'),
    ):
        try:run_ledger_case(args.fixtures, name, kind, document_type)
        except LedgerOCRError:
            ledger_failures.append(name)
            print('FAIL: synthetic ledger exact-value check ('+name+')')
    require(not ledger_failures,'Ledger OCR smoke exact-value checks failed')


if __name__ == '__main__':
    try:
        if len(sys.argv)==3 and sys.argv[1]=='--party-probe':
            print(json.dumps(party_probe(Path(sys.argv[2])),allow_nan=False))
        elif len(sys.argv)==3 and sys.argv[1]=='--focus-probe':
            print(json.dumps(focus_probe(Path(sys.argv[2])),allow_nan=False))
        else:main()
    except SmokeSafetyError:
        print('FAIL: OCR smoke safety check failed', file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        # Only fixed diagnostic messages; subprocess stdout/stderr remain private.
        if isinstance(exc, (SmokeCheckError, LedgerOCRError)):
            print('FAIL: ' + str(exc), file=sys.stderr)
        else:
            print('FAIL: offline OCR smoke could not complete', file=sys.stderr)
            sys.exit(3)
        sys.exit(1)
