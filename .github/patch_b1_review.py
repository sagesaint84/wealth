from pathlib import Path

service = Path("app/services/tax/family_financial_income.py")
text = service.read_text(encoding="utf-8")
text = text.replace(
    "from app.services.tax.financial_income import (\n    FinancialIncomeProjectionError,\n    _filter_holdings_for_owner,\n    build_financial_income_projection,\n)",
    "from app.services.tax.financial_income import (\n    FinancialIncomeProjectionError,\n    build_financial_income_projection,\n)",
)
old = '''def _effective_holding_owner(\n    holding: dict[str, Any], account_owners: dict[str, str]\n) -> str:\n    direct = str(holding.get("owner") or "").strip()\n    if direct and direct != "모두":\n        return direct\n    account_owner = account_owners.get(str(holding.get("account_id")), "모두")\n    return account_owner if account_owner else "모두"\n'''
new = '''def _holding_owner_resolution(\n    holding: dict[str, Any], account_owners: dict[str, str]\n) -> tuple[str, bool]:\n    """Resolve one family owner without allowing double attribution.\n\n    A named holding owner takes precedence only when it agrees with the named\n    account owner. Conflicting named owners are treated as ambiguous and are\n    excluded from every member projection until the data is corrected.\n    """\n    direct = str(holding.get("owner") or "").strip()\n    account_owner = account_owners.get(str(holding.get("account_id")), "모두")\n    direct_named = direct if direct and direct != "모두" else ""\n    account_named = account_owner if account_owner and account_owner != "모두" else ""\n    if direct_named and account_named and direct_named != account_named:\n        return "소유자 충돌", True\n    return direct_named or account_named or "모두", False\n\n\ndef _scoped_holdings_for_member(\n    holdings: list[dict[str, Any]],\n    accounts: list[dict[str, Any]],\n    owner: str,\n) -> list[dict[str, Any]]:\n    account_owners = _account_owner_map(accounts)\n    scoped: list[dict[str, Any]] = []\n    for holding in holdings:\n        if not isinstance(holding, dict):\n            continue\n        resolved, conflict = _holding_owner_resolution(holding, account_owners)\n        if not conflict and resolved == owner:\n            scoped.append(holding)\n    return scoped\n'''
if old not in text:
    raise SystemExit("owner helper marker missing")
text = text.replace(old, new, 1)
text = text.replace(
    '''    holding_count = 0\n    record_count = 0\n    labels: set[str] = set()\n\n    for holding in holdings:\n        if not isinstance(holding, dict):\n            continue\n        owner = _effective_holding_owner(holding, account_owners)\n        if owner not in allowed:\n            holding_count += 1\n            labels.add(owner or "모두")\n''',
    '''    holding_count = 0\n    ownership_conflict_count = 0\n    record_count = 0\n    labels: set[str] = set()\n\n    for holding in holdings:\n        if not isinstance(holding, dict):\n            continue\n        owner, conflict = _holding_owner_resolution(holding, account_owners)\n        if conflict:\n            holding_count += 1\n            ownership_conflict_count += 1\n            labels.add("소유자 충돌")\n        elif owner not in allowed:\n            holding_count += 1\n            labels.add(owner or "모두")\n''',
    1,
)
text = text.replace(
    '''        "holding_count": holding_count,\n        "actual_record_count": record_count,\n''',
    '''        "holding_count": holding_count,\n        "ownership_conflict_count": ownership_conflict_count,\n        "actual_record_count": record_count,\n''',
    1,
)
text = text.replace(
    "    family_reference_complete = projected_complete and not has_unassigned\n",
    "    family_reference_complete = bool(rows) and projected_complete and not has_unassigned\n",
    1,
)
text = text.replace(
    "        scoped_holdings = _filter_holdings_for_owner(holdings, accounts, owner)\n",
    "        scoped_holdings = _scoped_holdings_for_member(holdings, accounts, owner)\n",
    1,
)
service.write_text(text, encoding="utf-8")

ui = Path("app/static/wealth-family-financial-income-risk.js")
text = ui.read_text(encoding="utf-8")
old_ui = "소유자 미분류 보유자산 ${Number(unassigned.holding_count || 0).toLocaleString('ko-KR')}건 · 올해 실제 금융소득 기록 ${Number(unassigned.actual_record_count || 0).toLocaleString('ko-KR')}건을 확인하세요."
new_ui = "소유자 미분류 보유자산 ${Number(unassigned.holding_count || 0).toLocaleString('ko-KR')}건(소유자 충돌 ${Number(unassigned.ownership_conflict_count || 0).toLocaleString('ko-KR')}건 포함) · 올해 실제 금융소득 기록 ${Number(unassigned.actual_record_count || 0).toLocaleString('ko-KR')}건을 확인하세요."
if old_ui not in text:
    raise SystemExit("UI warning marker missing")
ui.write_text(text.replace(old_ui, new_ui, 1), encoding="utf-8")

test = Path("tests/test_family_financial_income_risk.py")
text = test.read_text(encoding="utf-8")
text = text.replace(
    '''                {"code": "CCC", "account_id": "a3", "quantity": 1},\n            ],''',
    '''                {"code": "CCC", "account_id": "a3", "quantity": 1},\n                {"code": "DDD", "account_id": "a1", "owner": "아빠", "quantity": 1},\n            ],''',
    1,
)
text = text.replace(
    '''        self.assertEqual(result["unassigned"]["holding_count"], 1)\n        self.assertEqual(result["unassigned"]["actual_record_count"], 1)''',
    '''        self.assertEqual(result["unassigned"]["holding_count"], 2)\n        self.assertEqual(result["unassigned"]["ownership_conflict_count"], 1)\n        self.assertEqual(result["unassigned"]["actual_record_count"], 1)''',
    1,
)
insert = '''\n    def test_no_members_is_not_a_complete_family_reference(self):\n        result = build_family_financial_income_risk([], as_of="2026-09-26")\n        self.assertFalse(result["family_reference"]["reference_complete"])\n        self.assertEqual(result["member_count"], 0)\n'''
marker = "\n\nclass FamilyFinancialIncomeRiskOrchestrationTests"
if marker not in text:
    raise SystemExit("test insertion marker missing")
text = text.replace(marker, insert + marker, 1)
test.write_text(text, encoding="utf-8")
