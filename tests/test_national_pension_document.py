"""No external tools: synthetic images and mocked Poppler/Tesseract output."""
from pathlib import Path
import json
import subprocess

import pytest

from app.services import national_pension_document as worker
from tests.test_national_pension_import import HISTORY


@pytest.mark.parametrize('kind,format', [('png','PNG'),('jpeg','JPEG')])
def test_offline_image_ocr_exif_preprocessing_and_no_personal_payload(tmp_path,monkeypatch,kind,format):
    from PIL import Image
    path=tmp_path/('synthetic.'+kind);Image.new('RGB',(800,500),'white').save(path,format=format)
    calls=[]
    def command(args,timeout=12):
        calls.append(args)
        return b'Rotate: 90' if '--psm' in args and args[-1]=='0' else HISTORY.encode()
    monkeypatch.setattr(worker,'command',command)
    result=worker.extract(path,kind,'auto')
    assert result['document_type']=='history'
    assert all(row['status']=='OCR 확인 필요' for row in result['fields'])
    assert any('kor+eng' in args for args in calls)
    assert (tmp_path/'rotated.png').exists()


@pytest.mark.parametrize('scanned', [False,True])
def test_pdf_layout_extraction_then_only_if_needed_ocr(tmp_path,monkeypatch,scanned):
    from PIL import Image
    path=tmp_path/'synthetic.pdf';path.write_bytes(b'%PDF-synthetic')
    calls=[]
    def command(args,timeout=12):
        calls.append(args)
        if args[0]=='pdfinfo':return b'Pages: 1\nEncrypted: no\n'
        if args[0]=='pdftotext':Path(args[-1]).write_text('' if scanned else HISTORY,encoding='utf-8');return b''
        if args[0]=='pdftoppm':Image.new('RGB',(1000,1000),'white').save(args[-1]+'.png');return b''
        if args[-1]=='0':raise subprocess.CalledProcessError(1,args)
        return HISTORY.encode()
    monkeypatch.setattr(worker,'command',command)
    result=worker.extract(path,'pdf','auto')
    assert result['fields'][0]['value']==9000000
    decoded=json.loads(worker.encode_result(result))
    assert decoded==result
    assert {row['key']:row['value'] for row in decoded['fields']
            if row['key'] in {'query_date','pension_start'}}=={'query_date':'2026-10-14','pension_start':'2045-01-01'}
    assert any(args[0]=='tesseract' for args in calls)==scanned
    assert '-layout' in next(args for args in calls if args[0]=='pdftotext')


@pytest.mark.parametrize('info',[b'Pages: 9\nEncrypted: no',b'Pages: 1\nEncrypted: yes',b'broken'])
def test_pdf_page_encryption_and_corruption_limits(tmp_path,monkeypatch,info):
    monkeypatch.setattr(worker,'command',lambda *args,**kwargs:info)
    with pytest.raises(ValueError):worker.extract(tmp_path/'synthetic.pdf','pdf','auto')


def test_image_pixels_rejected_before_ocr(tmp_path,monkeypatch):
    from PIL import Image
    path=tmp_path/'synthetic.png';Image.new('1',(4100,4100)).save(path)
    monkeypatch.setattr(worker,'command',lambda *args,**kwargs:pytest.fail('Oversized image must not reach OCR'))
    with pytest.raises(ValueError):worker.extract(path,'png','auto')
