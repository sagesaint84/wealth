"""Offline native-image OCR smoke. Never loads a portfolio or saves an import."""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def command(args, timeout=30):
    # Do not print raw decoder output, even though these fixtures are synthetic.
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError('Required offline command failed: ' + Path(args[0]).name)
    return result.stdout.decode('utf-8', errors='strict')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def recognize(path):
    text = command(['tesseract', str(path), 'stdout', '-l', 'kor+eng', '--psm', '6'])
    require('국민연금납부내역확인' in re.sub(r'\s+', '', text),
            'Synthetic Korean phrase was not recognized')


def validate_ledger_result(result, document_type):
    """Compare exact fictional source values, never a normalized OCR mistake."""
    require(isinstance(result, dict) and
            set(result) == {'document_type', 'status', 'rows', 'warnings'},
            'Ledger preview response contract failed')
    require(result['document_type'] == document_type and result['status'] == 'review_required',
            'Ledger document type/review status failed')
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
    with tempfile.TemporaryDirectory(prefix='wealth-ledger-smoke-') as directory:
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
            result = preview(target.read_bytes(), mime, document_type)
            validate_ledger_result(result, document_type)
            require(not list(inputs.iterdir()), 'Ledger worker private inputs were not cleaned up')
            require(set(data.iterdir()) == set(sentinels), 'Ledger created unexpected financial/user paths')
            require(all(not path.is_symlink() and path.read_bytes() == content
                        for path, content in sentinels.items()), 'Ledger changed synthetic financial files')
        finally:
            tempfile.tempdir = saved_tempdir
            for key, value in saved_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    require(not work.exists(), 'Ledger smoke temporary copies were not cleaned up')
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
    require('tesseract' in command(['tesseract', '--version']).lower(),
            'Tesseract version check failed')
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

    for name, kind, document_type in (
        ('bank.png', 'png', 'bank_transactions'),
        ('bank.pdf', 'pdf', 'bank_transactions'),
        ('card.jpg', 'jpeg', 'card_transactions'),
        ('card.pdf', 'pdf', 'card_transactions'),
    ):
        run_ledger_case(args.fixtures, name, kind, document_type)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Only fixed diagnostic messages; subprocess stdout/stderr remain private.
        if isinstance(exc, RuntimeError):
            print('FAIL: ' + str(exc), file=sys.stderr)
        else:
            print('FAIL: offline OCR smoke could not complete', file=sys.stderr)
        sys.exit(1)
