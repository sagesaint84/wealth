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
