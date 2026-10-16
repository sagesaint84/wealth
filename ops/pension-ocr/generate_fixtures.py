"""Generate public, synthetic OCR inputs on the CI runner; no user documents."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


BANK_LINES = (
    '은행 입출금 거래내역',
    '현재 잔액 11,000,000원',
    '10월 14일',
    '가상입금처',
    '09:10',
    '+1,234,567 원',
    '거래 후 잔액 11,234,567원',
    '10월 13일',
    '가상출금처',
    '10:20',
    '-234,567 원',
    '거래 후 잔액 11,000,000원',
)
CARD_LINES = (
    '카드 이용내역',
    '총 사용금액 35,801원',
    '10월 14일',
    '가상카페',
    '승인금액 12,345 원',
    '10월 13일',
    '가상서점',
    '승인금액 23,456 원',
)


def generate_ledger_fixtures(output, font):
    """Fictional screens, with generous margins and no date/year inference."""
    for name, lines, background, foreground, suffix in (
        ('bank', BANK_LINES, '#111827', 'white', 'png'),
        ('card', CARD_LINES, 'white', '#111827', 'jpg'),
    ):
        image = Image.new('RGB', (1800, 200 + len(lines)*132), background)
        draw = ImageDraw.Draw(image)
        for index, line in enumerate(lines):
            box = draw.textbbox((0, 0), line, font=font)
            if box[2]-box[0] > 1600 or box[3]-box[1] > 110:
                raise SystemExit('Synthetic ledger text does not fit the fixture')
            draw.text((100, 100+index*132), line, font=font, fill=foreground)
        image.save(output / (name+'.'+suffix), quality=95, subsampling=0)
        # Image-only PDF: the native smoke must check that no text layer exists.
        image.save(output / (name+'.pdf'), 'PDF', resolution=150.0, quality=95)
        for extension in (suffix, 'pdf'):
            # Public synthetic fixtures only. The container uses UID 65534.
            (output / (name+'.'+extension)).chmod(0o644)


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
    # Same public font family, heavier/larger ledger glyphs to reduce OCR
    # syllable segmentation and confusion between the final digit and 원.
    # Fail if the CI's public font package lacks the required face.
    ledger_face = args.font.with_name(args.font.stem + 'Bold' + args.font.suffix)
    if not ledger_face.is_file():
        raise SystemExit('Required public Korean bold font is missing')
    generate_ledger_fixtures(args.output, ImageFont.truetype(str(ledger_face), 80))
    print('Created public synthetic bank/card images and scanned PDFs')


if __name__ == '__main__':
    main()
