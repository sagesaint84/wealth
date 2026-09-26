from pathlib import Path

path = Path("app/static/index.html")
text = path.read_text(encoding="utf-8")
needle = '    <script src="/static/wealth.js?v=1.3.0"></script>'
addition = '    <script src="/static/wealth-dividend-source.js?v=1.3.0"></script>'
if addition not in text:
    if needle not in text:
        raise SystemExit("wealth.js script tag not found")
    text = text.replace(needle, needle + "\n" + addition, 1)
    path.write_text(text, encoding="utf-8")
