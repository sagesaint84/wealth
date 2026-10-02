from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEALTH_JS = ROOT / "app" / "static" / "wealth.js"
LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


def patch_wealth_js(source: str) -> str:
    if "broker.includes('토스') || broker.includes('toss')" not in source:
        old_accounts = """function populateWtsAccounts() {
  const select = document.getElementById('wtsDestinationAccount');
  if (!select) return;
  const accounts = (dashboard && dashboard.accounts) || [];
  const currentVal = select.value;
  select.innerHTML = '<option value=\"\">귀속할 Wealth 계좌를 선택하세요</option>' +
    accounts.map(acc => {
      const broker = acc.broker || '기타';
      const name = maskAccountDisplayLabel(acc.account_name || acc.name || '계좌');
      const owner = acc.owner ? ` (${acc.owner})` : '';
      return `<option value=\"${html(acc.id)}\">${html(broker)} - ${html(name)}${html(owner)}</option>`;
    }).join('');
  if (currentVal && accounts.some(a => String(a.id) === currentVal)) {
    select.value = currentVal;
  }
}"""

        new_accounts = """function populateWtsAccounts() {
  const select = document.getElementById('wtsDestinationAccount');
  if (!select) return;
  const accounts = ((dashboard && dashboard.accounts) || []).filter(account => {
    const broker = String(account.broker || '').trim().toLowerCase();
    return broker.includes('토스') || broker.includes('toss');
  });
  const currentVal = select.value;
  select.innerHTML = '<option value=\"\">토스증권 계좌를 선택하세요</option>' +
    accounts.map(acc => {
      const broker = acc.broker || '토스증권';
      const name = maskAccountDisplayLabel(acc.account_name || acc.name || '계좌');
      const owner = acc.owner ? ` (${acc.owner})` : '';
      return `<option value=\"${html(acc.id)}\">${html(broker)} - ${html(name)}${html(owner)}</option>`;
    }).join('');
  if (currentVal && accounts.some(a => String(a.id) === currentVal)) {
    select.value = currentVal;
  } else if (accounts.length === 1) {
    select.value = String(accounts[0].id || '');
  }
}"""
        source = replace_once(source, old_accounts, new_accounts, "populateWtsAccounts")

    helper_marker = "function brokerImportPnlPresentation(candidate, value) {"
    render_marker = "function renderBrokerImportPreviewDetails(data, overlayId) {"
    if helper_marker not in source:
        helper = """function brokerImportPnlPresentation(candidate, value) {
  const numeric = Number(value ?? 0);
  const amount = Number.isFinite(numeric) ? numeric : 0;
  const market = String(candidate?.market_type || candidate?.market || '').trim().toUpperCase();
  const currency = String(
    candidate?.currency || (market === 'US' || market === 'OVERSEAS' ? 'USD' : 'KRW')
  ).trim().toUpperCase();

  const sign = amount > 0 ? '+' : (amount < 0 ? '-' : '');
  const absolute = Math.abs(amount);
  const text = currency === 'USD'
    ? `${sign}$${number(absolute, 2)}`
    : `${sign}₩${money(absolute)}`;
  const toneClass = amount > 0
    ? 'pnl-positive'
    : (amount < 0 ? 'pnl-negative' : '');
  return { text, toneClass };
}

"""
        if source.count(render_marker) != 1:
            raise SystemExit(f"renderBrokerImportPreviewDetails: expected 1 marker, found {source.count(render_marker)}")
        source = source.replace(render_marker, helper + render_marker, 1)

    old_name = "`<strong>${html(itemName)}</strong>` +"
    new_name = "`<strong class=\"broker-import-item-name\">${html(itemName)}</strong>` +"
    if 'class="broker-import-item-name"' not in source:
        source = replace_once(source, old_name, new_name, "broker import item name")

    if "const providerPnl = brokerImportPnlPresentation(candidate, choice.provider_realized_pnl" not in source:
        old_candidate = """    const candidate = item.candidate || {};
    const itemName = candidate.name || candidate.prdt_name || candidate.code || `선택 항목 ${item.index + 1}`;
    const itemDate = candidate.date || '';
"""
        new_candidate = """    const candidate = item.candidate || {};
    const itemName = candidate.name || candidate.prdt_name || candidate.code || `선택 항목 ${item.index + 1}`;
    const itemDate = candidate.date || '';
    const providerPnl = brokerImportPnlPresentation(candidate, choice.provider_realized_pnl ?? candidate.pnl ?? 0);
    const finalPnl = brokerImportPnlPresentation(candidate, choice.final_wealth_pnl ?? choice.provider_realized_pnl ?? candidate.pnl ?? 0);
"""
        source = replace_once(source, old_candidate, new_candidate, "broker import preview pnl presentation")

    old_ipo = """          `제공사 손익 ${html(Number(choice.provider_realized_pnl || 0).toLocaleString('ko-KR'))} · 최종 Wealth 손익 <strong style=\"color:var(--text-color);\">${html(Number(choice.final_wealth_pnl || 0).toLocaleString('ko-KR'))}</strong>` +"""
    new_ipo = """          `제공사 손익 <strong class=\"broker-import-pnl ${providerPnl.toneClass}\">${html(providerPnl.text)}</strong> · 최종 Wealth 손익 <strong class=\"broker-import-pnl ${finalPnl.toneClass}\">${html(finalPnl.text)}</strong>` +"""
    if 'class="broker-import-pnl ${providerPnl.toneClass}"' not in source:
        source = replace_once(source, old_ipo, new_ipo, "IPO preview pnl")

    old_general = """          `유형: <strong>일반주식</strong> · 최종 Wealth 손익 <strong style=\"color:var(--text-color);\">${html(Number(choice.final_wealth_pnl || choice.provider_realized_pnl || 0).toLocaleString('ko-KR'))}</strong>` +"""
    new_general = """          `유형: <strong>일반주식</strong> · 최종 Wealth 손익 <strong class=\"broker-import-pnl ${finalPnl.toneClass}\">${html(finalPnl.text)}</strong>` +"""
    if source.count('class="broker-import-pnl ${finalPnl.toneClass}"') < 2:
        source = replace_once(source, old_general, new_general, "general preview pnl")

    required = [
        ".filter(account => {",
        "broker.includes('토스') || broker.includes('toss')",
        "토스증권 계좌를 선택하세요",
        "accounts.length === 1",
        helper_marker,
        "candidate?.currency",
        "currency === 'USD'",
        'class="broker-import-item-name"',
        "brokerImportPnlPresentation(candidate, choice.provider_realized_pnl",
        "brokerImportPnlPresentation(candidate, choice.final_wealth_pnl",
        'class="broker-import-pnl ${providerPnl.toneClass}"',
        'class="broker-import-pnl ${finalPnl.toneClass}"',
    ]
    missing = [marker for marker in required if marker not in source]
    if missing:
        raise SystemExit(f"wealth.js post-patch verification failed: {missing}")
    return source


def patch_layout_css(source: str) -> str:
    if ".broker-import-item-name {" not in source:
        source = source.rstrip() + """

/* Broker realized import preview readability */
.broker-import-item-name {
  font-size: 15px !important;
  line-height: 1.35;
  font-weight: 700;
}
.broker-import-pnl {
  font-variant-numeric: tabular-nums;
}
.broker-import-pnl.pnl-positive {
  color: var(--red, #ff718c) !important;
}
.broker-import-pnl.pnl-negative {
  color: var(--blue, #54a8ff) !important;
}
"""
    required = [
        ".broker-import-item-name",
        "font-size: 15px",
        ".broker-import-pnl.pnl-positive",
        "var(--red",
        ".broker-import-pnl.pnl-negative",
        "var(--blue",
    ]
    missing = [marker for marker in required if marker not in source]
    if missing:
        raise SystemExit(f"wealth-layout.css post-patch verification failed: {missing}")
    return source


def main() -> None:
    js_before = WEALTH_JS.read_text(encoding="utf-8")
    css_before = LAYOUT_CSS.read_text(encoding="utf-8")
    js_after = patch_wealth_js(js_before)
    css_after = patch_layout_css(css_before)

    WEALTH_JS.write_text(js_after, encoding="utf-8")
    LAYOUT_CSS.write_text(css_after, encoding="utf-8")

    print("PR77_PATCH_APPLIED")
    print(f"wealth.js changed={js_after != js_before}")
    print(f"wealth-layout.css changed={css_after != css_before}")


if __name__ == "__main__":
    main()
