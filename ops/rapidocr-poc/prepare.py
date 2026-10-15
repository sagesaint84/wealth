"""Network-enabled preparation of PUBLIC synthetic inputs, before inference."""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
import urllib.request

HERE = Path(__file__).resolve().parent


def verify_models(directory):
    manifest = json.loads((HERE / 'models.json').read_text())
    return all(hashlib.sha256((directory / row['name']).read_bytes()).hexdigest() == row['sha256']
               for row in manifest['models'])


def prepare(output, font):
    from PIL import Image, ImageDraw, ImageFont
    output.mkdir(parents=True, exist_ok=False)
    models = output / 'models'; models.mkdir()
    for row in json.loads((HERE / 'models.json').read_text())['models']:
        if not row['url'].startswith('https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/'):
            raise ValueError('MODEL_SOURCE_FAIL')
        with urllib.request.urlopen(row['url'], timeout=90) as response:
            data = response.read(64 * 1024 * 1024 + 1)
        if len(data) > 64 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('MODEL_CHECKSUM_FAIL')
        (models / row['name']).write_bytes(data)
    spec = importlib.util.spec_from_file_location('public_fixtures', HERE.parent / 'pension-ocr/generate_fixtures.py')
    fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
    images = output / 'fixtures'; images.mkdir()
    face = ImageFont.truetype(str(font.with_name('NanumGothicBold.ttf')), 80)
    fixture.generate_ledger_fixtures(images, face)
    cases = []
    for name, lines, kind in [('bank', fixture.BANK_LINES, 'bank'), ('card', fixture.CARD_LINES, 'card')]:
        suffix = 'png' if name == 'bank' else 'jpg'
        cases.append(dict(id=name + '_pdf', path=name+'.pdf', kind=kind, width=1800, lines=list(lines)))
        with Image.open(images / (name+'.'+suffix)) as original:
            for width in (1800, 390, 221, 135):
                resized = original.resize((width, round(original.height * width / original.width)), Image.Resampling.LANCZOS)
                filename = f'{name}-{width}.{suffix}'
                if width==1800:shutil.copyfile(images/(name+'.'+suffix),images/filename)
                else:resized.save(images / filename, quality=95, subsampling=0)
                cases.append(dict(id=f'{name}_{width}', path=filename, kind=kind, width=width, lines=list(lines)))
    pension_lines = {
        'history': ['국민연금 납부내역 확인', '국민연금 가입내역조회', '납부한 보험료 총액 1200000원', '실제 납부 월수 12개월', '조회일 2026.10.14'],
        'certificate': ['국민연금 소득공제 납부확인', '납부한 보험료 총액 1200000원', '실제 납부 월수 12개월', '조회일 2026.10.14'],
    }
    for kind, lines in pension_lines.items():
        im = Image.new('RGB', (1800, 1000), 'white'); draw = ImageDraw.Draw(im)
        normal = ImageFont.truetype(str(font), 64)
        for index, line in enumerate(lines):
            draw.text((100, 100+index*150), line, font=normal, fill='black')
        for suffix in ('png', 'pdf'):
            filename=f'pension-{kind}.{suffix}'; im.save(images / filename, resolution=150.0)
            cases.append(dict(id=f'pension_{kind}_{suffix}', path=filename, kind=kind, width=1800, lines=lines))
        # Second page has a distinct, allowed date: verify page order separately.
        second=Image.new('RGB', (1800, 1000), 'white')
        ImageDraw.Draw(second).text((100,100), '조회일 2026.10.15', font=normal, fill='black')
        filename=f'pension-{kind}-multi.pdf'
        im.save(images / filename, save_all=True, append_images=[second], resolution=150.0)
        cases.append(dict(id=f'pension_{kind}_multi', path=filename, kind=kind, width=1800, lines=lines, multipage=True))
    # Additional semantic cases use fictional parties; no production mutation.
    for variant, label in [('cancel', '가상카페 취소'), ('refund', '가상카페 환불')]:
        lines=list(fixture.CARD_LINES); lines[3]=label
        im=Image.new('RGB',(1800,1256),'white'); draw=ImageDraw.Draw(im)
        for index,line in enumerate(lines):draw.text((100,100+index*132),line,font=face,fill='#111827')
        filename=f'card-{variant}.png'; im.save(images/filename)
        cases.append(dict(id='card_'+variant,path=filename,kind='card',width=1800,lines=lines,variant=variant))
    lines=list(fixture.CARD_LINES); lines[5:]=lines[2:5]  # identical-looking rows must remain two.
    im=Image.new('RGB',(1800,1256),'white'); draw=ImageDraw.Draw(im)
    for index,line in enumerate(lines):draw.text((100,100+index*132),line,font=face,fill='#111827')
    im.save(images/'card-duplicate.png')
    cases.append(dict(id='card_duplicate',path='card-duplicate.png',kind='card',width=1800,lines=lines,variant='duplicate'))
    (output / 'cases.json').write_text(json.dumps(cases, ensure_ascii=False), encoding='utf-8')
    for path in output.rglob('*'):
        os.chmod(path, 0o755 if path.is_dir() else 0o644)
    os.chmod(output, 0o755)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--font', type=Path, default=Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf'))
    args=parser.parse_args()
    try:
        prepare(args.output,args.font)
        print('PREPARE_PASS')
    except Exception:
        print('PREPARE_FAIL'); raise SystemExit(1)
