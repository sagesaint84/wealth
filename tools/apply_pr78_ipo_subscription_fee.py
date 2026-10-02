from __future__ import annotations

from pathlib import Path


PATH = Path("app/static/wealth-ipo-sale-bridge.js")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    return source.replace(old, new, 1)


source = PATH.read_text(encoding="utf-8")

fee_label = "\uacf5\ubaa8\uccad\uc57d\ube44"
fee_memo = "\uacf5\ubaa8\uc218\uc218\ub8cc"
base_memo = "\uacf5\ubaa8\uc8fc \ubc30\uc815 \ub9e4\ub3c4 \uc2e4\ud604\uc190\uc775"
invalid_fee_message = "\uacf5\ubaa8\uccad\uc57d\ube44\ub294 0\uc6d0 \uc774\uc0c1\uc758 \uc815\uc218\ub85c \uc785\ub825\ud574 \uc8fc\uc138\uc694."

old_form = '''          <label class="ipo-manual-sale-wide">\uc2e4\ud604\uc190\uc775 (KRW \u00b7 \uc99d\uad8c\uc0ac \ud655\uc778 \uae08\uc561)\n            <input name="pnl_krw" type="number" step="1" required placeholder="\uc608: 125000" />\n          </label>\n          <label>\ub9e4\ub3c4\uae08\uc561 (\uc120\ud0dd)'''
new_form = f'''          <label class="ipo-manual-sale-wide">\uc2e4\ud604\uc190\uc775 (KRW \u00b7 \uc99d\uad8c\uc0ac \ud655\uc778 \uae08\uc561)\n            <input name="pnl_krw" type="number" step="1" required placeholder="\uc608: 125000" />\n          </label>\n          <label>{fee_label}\n            <input name="ipo_subscription_fee_krw" type="number" min="0" step="1" value="2000" required />\n          </label>\n          <label>\ub9e4\ub3c4\uae08\uc561 (\uc120\ud0dd)'''
source = replace_once(source, old_form, new_form, "FORM_FEE_FIELD")

old_pnl = "    const pnlKrw = Number(form.elements.pnl_krw.value);\n"
new_pnl = (
    old_pnl
    + "    const ipoSubscriptionFeeKrw = Number(form.elements.ipo_subscription_fee_krw.value);\n"
)
source = replace_once(source, old_pnl, new_pnl, "FEE_VALUE_READ")

saving_marker = "\n    saving = true;\n"
if source.count(saving_marker) != 1:
    raise SystemExit(f"FEE_VALIDATION_INSERT: expected 1 marker, found {source.count(saving_marker)}")
calculation = f'''\n    if (!Number.isInteger(ipoSubscriptionFeeKrw) || ipoSubscriptionFeeKrw < 0) {{\n      setDialogStatus('{invalid_fee_message}', true);\n      return;\n    }}\n    const finalWealthPnlKrw = pnlKrw - ipoSubscriptionFeeKrw;\n    const subscriptionFeeMemo = ipoSubscriptionFeeKrw === 2000\n      ? '{fee_memo} 2\ucc9c\uc6d0 \ucc28\uac10'\n      : `{fee_memo} ${{ipoSubscriptionFeeKrw.toLocaleString('ko-KR')}}\uc6d0 \ucc28\uac10`;\n'''
source = source.replace(saving_marker, calculation + saving_marker, 1)

old_payload = "        pnl: pnlKrw,\n        pnl_krw: pnlKrw,\n"
new_payload = (
    "        pnl: finalWealthPnlKrw,\n"
    "        pnl_krw: finalWealthPnlKrw,\n"
    "        provider_realized_pnl: pnlKrw,\n"
    "        ipo_subscription_fee_krw: ipoSubscriptionFeeKrw,\n"
)
source = replace_once(source, old_payload, new_payload, "FINAL_PNL_PAYLOAD")

old_memo = f"        memo: '{base_memo}',\n"
new_memo = f"        memo: `{base_memo} \u00b7 ${{subscriptionFeeMemo}}`,\n"
source = replace_once(source, old_memo, new_memo, "FEE_MEMO")

PATH.write_text(source, encoding="utf-8")

written = PATH.read_text(encoding="utf-8")
required = [
    fee_label,
    'name="ipo_subscription_fee_krw"',
    'value="2000"',
    "const ipoSubscriptionFeeKrw = Number(form.elements.ipo_subscription_fee_krw.value)",
    "Number.isInteger(ipoSubscriptionFeeKrw)",
    "const finalWealthPnlKrw = pnlKrw - ipoSubscriptionFeeKrw",
    "provider_realized_pnl: pnlKrw",
    "ipo_subscription_fee_krw: ipoSubscriptionFeeKrw",
    "pnl: finalWealthPnlKrw",
    "pnl_krw: finalWealthPnlKrw",
    fee_memo,
]
for marker in required:
    if marker not in written:
        raise SystemExit(f"POST_WRITE_VERIFY_FAILED: {marker!r}")

print("PR78_IPO_SUBSCRIPTION_FEE_PATCHED")
