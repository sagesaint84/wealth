"""Disposable offline decoder worker; stdout contains only allowlisted numeric metadata."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def command(args, timeout=12):
    return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                          timeout=timeout,env={**os.environ,'OMP_THREAD_LIMIT':'1'}).stdout


def encode_result(result):
    """Strict JSON boundary: dates must already be ISO strings, never default=str."""
    return json.dumps(result,ensure_ascii=True,allow_nan=False)


def extract(path,kind,document_type):
    from app.services.document_extraction import extract_pages
    from app.services.national_pension_import import parse_text
    pages = extract_pages(path,kind,run=command,
                          needs_ocr=lambda text: len(re.findall(r'[가-힣]',text))<20)
    return parse_text('\n'.join(page['text'] for page in pages),
                      ocr=any(page['method']=='ocr' for page in pages),document_type=document_type)


if __name__=='__main__':
    try:
        if os.name=='posix':
            import resource
            resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
            resource.setrlimit(resource.RLIMIT_CPU,(60,60))
            resource.setrlimit(resource.RLIMIT_FSIZE,(20*1024*1024,20*1024*1024))
            resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        os.umask(0o077)
        result=extract(Path(sys.argv[1]),sys.argv[2],sys.argv[3])
        sys.stdout.write(encode_result(result))
    except Exception:
        # No decoder error, path, text, filename or personal value in logs/error output.
        sys.exit(1)
