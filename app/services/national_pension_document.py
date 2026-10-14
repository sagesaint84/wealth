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
    from PIL import Image, ImageOps
    from app.services.national_pension_import import MAX_PAGES, MAX_PIXELS, parse_text
    Image.MAX_IMAGE_PIXELS=MAX_PIXELS
    directory=path.parent

    def ocr(image_path):
        with Image.open(image_path) as image:
            if image.format not in {'PNG','JPEG'} or image.width*image.height>MAX_PIXELS or getattr(image,'n_frames',1)!=1:
                raise ValueError('Image limit')
            image=ImageOps.exif_transpose(image).convert('L')
            image.thumbnail((3200,3200))
            image=ImageOps.autocontrast(image)
            prepared=directory/'prepared.png';image.save(prepared);os.chmod(prepared,0o600)
        # Orientation detection is optional (short documents can lack enough text).
        try:
            orientation=command(['tesseract',str(prepared),'stdout','-l','osd','--psm','0'],5).decode('utf-8')
            rotation=re.search(r'Rotate:\s*(90|180|270)',orientation)
            if rotation:
                with Image.open(prepared) as image: image.rotate(-int(rotation[1]),expand=True).save(directory/'rotated.png')
                prepared=directory/'rotated.png';os.chmod(prepared,0o600)
        except subprocess.CalledProcessError: pass
        # PSM 6 performs line finding/limited skew handling. Severe perspective skew requires manual correction.
        return command(['tesseract',str(prepared),'stdout','-l','kor+eng','--psm','6'],20).decode('utf-8')

    if kind!='pdf': return parse_text(ocr(path),ocr=True,document_type=document_type)
    info=command(['pdfinfo',str(path)]).decode('utf-8',errors='replace')
    pages=re.search(r'^Pages:\s*(\d+)',info,re.M)
    if not pages or not 1<=int(pages[1])<=MAX_PAGES or re.search(r'^Encrypted:\s*yes',info,re.M): raise ValueError('PDF limit')
    parts=[];used_ocr=False
    for page in range(1,int(pages[1])+1):
        output=directory/'page.txt'
        command(['pdftotext','-f',str(page),'-l',str(page),'-layout','-enc','UTF-8',str(path),str(output)])
        os.chmod(output,0o600)
        if output.stat().st_size>200_000: raise ValueError('Text limit')
        text=output.read_text(encoding='utf-8')
        if len(re.findall(r'[가-힣]',text))<20:
            prefix=directory/'page'
            command(['pdftoppm','-f',str(page),'-l',str(page),'-singlefile','-scale-to','3200','-png',str(path),str(prefix)])
            image=directory/'page.png';os.chmod(image,0o600);text=ocr(image);used_ocr=True
        parts.append(text)
    return parse_text('\n'.join(parts),ocr=used_ocr,document_type=document_type)


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
