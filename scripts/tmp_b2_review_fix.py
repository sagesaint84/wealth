from pathlib import Path

path = Path("app/static/wealth-financial-income-what-if.js")
text = path.read_text(encoding="utf-8")

old = """      const rateText = Number.isFinite(Number(etf.estimated_withholding_rate))
        ? `${(Number(etf.estimated_withholding_rate) * 100).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%`
        : '확인 불가';
      html += `
"""
new = """      const rateText = Number.isFinite(Number(etf.estimated_withholding_rate))
        ? `${(Number(etf.estimated_withholding_rate) * 100).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%`
        : '확인 불가';
      const foreignTaxText = foreign.capital_gain_tax_calculated === false
        ? '금융소득 판정 미포함 · 양도세는 빠른 입력만으로 미계산'
        : '금융소득 판정 미포함';
      html += `
"""
if old not in text:
    raise SystemExit("trading result marker not found")
text = text.replace(old, new, 1)

old = "<small>금융소득 판정 미포함 · 양도세는 빠른 입력만으로 미계산</small>"
new = "<small>${foreignTaxText}</small>"
if old not in text:
    raise SystemExit("foreign trading message marker not found")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Phase 10.5B-2 UI review fix applied")
