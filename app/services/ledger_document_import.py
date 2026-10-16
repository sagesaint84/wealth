"""Disposable read-only preview: does not import financial services or resolve data paths."""
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from app.services.document_extraction import DECODE_SLOTS, MAX_BYTES, detect_file


def preview(data, mime, document_type='auto'):
    if document_type not in {'auto', 'bank_transactions', 'card_transactions'}:
        raise ValueError('자료 종류를 확인해 주세요.')
    kind = detect_file(data, mime)
    if not DECODE_SLOTS.acquire(blocking=False):
        raise ValueError('문서 분석이 진행 중입니다. 잠시 후 다시 시도해 주세요.')
    try:
        with tempfile.TemporaryDirectory(prefix='wealth-ledger-ocr-') as directory:
            os.chmod(directory, 0o700)
            path = Path(directory) / ('input.' + kind)
            with path.open('xb') as stream:
                os.chmod(path, 0o600); stream.write(data)
            process = subprocess.Popen([sys.executable, '-m', 'app.services.ledger_document',
                str(path), kind, document_type], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                start_new_session=os.name == 'posix')
            try:
                output, _ = process.communicate(timeout=75)
            except subprocess.TimeoutExpired:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.communicate()
                raise ValueError('분석 시간이 초과했습니다. 페이지를 줄이거나 수동 입력해 주세요.') from None
            if process.returncode or len(output) > 300_000:
                raise ValueError('오프라인 문서 분석을 완료하지 못했습니다. 도구 설치·파일 상태를 확인해 주세요.')
            result = json.loads(output)
            if (not isinstance(result, dict) or set(result) != {'document_type', 'status', 'rows', 'warnings'}
                    or result['status'] != 'review_required' or not isinstance(result['rows'], list)
                    or len(result['rows']) > 200 or not isinstance(result['warnings'], list)):
                raise ValueError('분석 결과 형식을 확인해 주세요.')
            return result
    except (OSError, subprocess.SubprocessError, UnicodeError, json.JSONDecodeError):
        raise ValueError('오프라인 분석 도구를 사용할 수 없습니다. 수동 입력해 주세요.') from None
    finally:
        DECODE_SLOTS.release()
