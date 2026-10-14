"""Generate public, synthetic OCR inputs on the CI runner; no user documents."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    args = parser.parse_args()
    if not args.font.is_file():
        raise SystemExit('Required public Korean system font is missing')
    args.output.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(args.font), 64)
    image = Image.new('RGB', (1800, 1000), 'white')
    draw = ImageDraw.Draw(image)
    lines = (
        '국민연금 납부내역 확인',
        '국민연금 가입내역조회',
        '납부한 보험료 총액 1200000원',
        '실제 납부 월수 12개월',
        '조회일 2026.10.14',
    )
    for index, line in enumerate(lines):
        box = draw.textbbox((0, 0), line, font=font)
        if box[2] - box[0] > 1600:
            raise SystemExit('Synthetic text does not fit the fixture')
        draw.text((100, 100 + index * 150), line, font=font, fill='black')
    image.save(args.output / 'synthetic.png')
    # Scanned/image PDF deliberately exercises Poppler and the OCR fallback,
    # rather than an embedded text layer that would bypass OCR.
    image.save(args.output / 'synthetic.pdf', 'PDF', resolution=150.0)
    print('Created public synthetic PNG and scanned PDF')


if __name__ == '__main__':
    main()
