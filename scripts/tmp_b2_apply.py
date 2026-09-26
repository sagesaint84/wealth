from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Service: financial-income what-if
# ---------------------------------------------------------------------------
what_if = ROOT / "app/services/tax/what_if.py"
replace_once(
    what_if,
    "from app.services.tax.investment_tax import compare_investment_tax_2026\n",
    "from app.services.tax.investment_tax import compare_investment_tax_2026\n"
    "from app.services.tax.investment_tax import rules_2026 as investment_rules\n",
)

marker = "\ndef build_financial_income_what_if(\n"
helper = '''\ndef _trading_impact(\n    *,\n    foreign_share_realized_gain_krw: float,\n    kr_listed_overseas_etf_taxable_gain_krw: float,\n) -> dict[str, Any]:\n    etf_withholding = (\n        kr_listed_overseas_etf_taxable_gain_krw\n        * investment_rules.GENERAL_DIVIDEND_WITHHOLDING_RATE\n    )\n    return {\n        "foreign_shares": {\n            "realized_gain_krw": _won(foreign_share_realized_gain_krw),\n            "financial_income_addition_krw": 0,\n            "included_in_financial_income_screening": False,\n            "capital_gain_tax_calculated": False,\n            "note": (\n                "해외주식 실현차익은 금융소득 종합과세 판정에 포함하지 않습니다. "\n                "이 빠른 입력만으로는 연간 순손익과 기본공제 사용상태를 확정할 수 없어 "\n                "양도소득세는 계산하지 않습니다."\n            ),\n        },\n        "kr_listed_overseas_etf": {\n            "taxable_gain_krw": _won(kr_listed_overseas_etf_taxable_gain_krw),\n            "financial_income_addition_krw": _won(\n                kr_listed_overseas_etf_taxable_gain_krw\n            ),\n            "included_in_financial_income_screening": True,\n            "estimated_withholding_rate": investment_rules.GENERAL_DIVIDEND_WITHHOLDING_RATE,\n            "estimated_withholding_krw": _won(etf_withholding),\n            "final_tax_calculated": False,\n        },\n        "screening_only": True,\n        "legal_tax_determination": False,\n    }\n\n\n'''
replace_once(what_if, marker, helper + marker)

replace_once(
    what_if,
    "    additional_interest_gross_krw: object = 0,\n    high_dividend_scenario: dict[str, Any] | None = None,\n",
    "    additional_interest_gross_krw: object = 0,\n"
    "    additional_foreign_share_realized_gain_krw: object = 0,\n"
    "    additional_kr_listed_overseas_etf_taxable_gain_krw: object = 0,\n"
    "    high_dividend_scenario: dict[str, Any] | None = None,\n",
)

replace_once(
    what_if,
    "    additional_interest = _nonnegative(\n"
    "        additional_interest_gross_krw,\n"
    "        \"FINANCIAL_INCOME_WHAT_IF_INTEREST_INVALID\",\n"
    "    )\n"
    "    scenario_addition = additional_dividend + additional_interest\n",
    "    additional_interest = _nonnegative(\n"
    "        additional_interest_gross_krw,\n"
    "        \"FINANCIAL_INCOME_WHAT_IF_INTEREST_INVALID\",\n"
    "    )\n"
    "    additional_foreign_share_gain = _nonnegative(\n"
    "        additional_foreign_share_realized_gain_krw,\n"
    "        \"FINANCIAL_INCOME_WHAT_IF_FOREIGN_SHARE_GAIN_INVALID\",\n"
    "    )\n"
    "    additional_kr_overseas_etf_gain = _nonnegative(\n"
    "        additional_kr_listed_overseas_etf_taxable_gain_krw,\n"
    "        \"FINANCIAL_INCOME_WHAT_IF_KR_OVERSEAS_ETF_GAIN_INVALID\",\n"
    "    )\n"
    "    scenario_addition = (\n"
    "        additional_dividend\n"
    "        + additional_interest\n"
    "        + additional_kr_overseas_etf_gain\n"
    "    )\n"
    "    trading_impact = _trading_impact(\n"
    "        foreign_share_realized_gain_krw=additional_foreign_share_gain,\n"
    "        kr_listed_overseas_etf_taxable_gain_krw=additional_kr_overseas_etf_gain,\n"
    "    )\n",
)

replace_once(
    what_if,
    "        \"additional_interest_gross_krw\": _won(additional_interest),\n"
    "        \"scenario_addition_gross_krw\": _won(scenario_addition),\n",
    "        \"additional_interest_gross_krw\": _won(additional_interest),\n"
    "        \"additional_foreign_share_realized_gain_krw\": _won(\n"
    "            additional_foreign_share_gain\n"
    "        ),\n"
    "        \"additional_kr_listed_overseas_etf_taxable_gain_krw\": _won(\n"
    "            additional_kr_overseas_etf_gain\n"
    "        ),\n"
    "        \"scenario_addition_gross_krw\": _won(scenario_addition),\n"
    "        \"trading_impact\": trading_impact,\n",
)

# Extend the user-scoped orchestration signature and build call.
needle = "    additional_interest_gross_krw: object = 0,\n    high_dividend_scenario: dict[str, Any] | None = None,\n    investment_scenario: dict[str, Any] | None = None,\n"
replacement = (
    "    additional_interest_gross_krw: object = 0,\n"
    "    additional_foreign_share_realized_gain_krw: object = 0,\n"
    "    additional_kr_listed_overseas_etf_taxable_gain_krw: object = 0,\n"
    "    high_dividend_scenario: dict[str, Any] | None = None,\n"
    "    investment_scenario: dict[str, Any] | None = None,\n"
)
# The build signature was already replaced above, so replace the next occurrence only.
text = what_if.read_text(encoding="utf-8")
first = text.find(needle)
second = text.find(needle, first + 1) if first >= 0 else -1
if second < 0:
    raise SystemExit("user scoped signature pattern not found")
text = text[:second] + text[second:].replace(needle, replacement, 1)
what_if.write_text(text, encoding="utf-8")

replace_once(
    what_if,
    "        additional_interest_gross_krw=additional_interest_gross_krw,\n"
    "        high_dividend_scenario=high_dividend_scenario,\n",
    "        additional_interest_gross_krw=additional_interest_gross_krw,\n"
    "        additional_foreign_share_realized_gain_krw=(\n"
    "            additional_foreign_share_realized_gain_krw\n"
    "        ),\n"
    "        additional_kr_listed_overseas_etf_taxable_gain_krw=(\n"
    "            additional_kr_listed_overseas_etf_taxable_gain_krw\n"
    "        ),\n"
    "        high_dividend_scenario=high_dividend_scenario,\n",
)

replace_once(
    what_if,
    "            \"server_scoped_from_authenticated_user\": True,\n"
    "        }\n",
    "            \"server_scoped_from_authenticated_user\": True,\n"
    "            \"quick_trading_inputs\": {\n"
    "                \"foreign_share_realized_gain_krw\": _won(\n"
    "                    _nonnegative(\n"
    "                        additional_foreign_share_realized_gain_krw,\n"
    "                        \"FINANCIAL_INCOME_WHAT_IF_FOREIGN_SHARE_GAIN_INVALID\",\n"
    "                    )\n"
    "                ),\n"
    "                \"kr_listed_overseas_etf_taxable_gain_krw\": _won(\n"
    "                    _nonnegative(\n"
    "                        additional_kr_listed_overseas_etf_taxable_gain_krw,\n"
    "                        \"FINANCIAL_INCOME_WHAT_IF_KR_OVERSEAS_ETF_GAIN_INVALID\",\n"
    "                    )\n"
    "                ),\n"
    "                \"server_auto_overwrite\": False,\n"
    "            },\n"
    "        }\n",
)

# ---------------------------------------------------------------------------
# API route: preserve legacy kwargs when new fields are absent.
# ---------------------------------------------------------------------------
main = ROOT / "app/main.py"
replace_once(
    main,
    "        \"additional_interest_gross_krw\",\n"
    "        \"high_dividend_scenario\",\n",
    "        \"additional_interest_gross_krw\",\n"
    "        \"additional_foreign_share_realized_gain_krw\",\n"
    "        \"additional_kr_listed_overseas_etf_taxable_gain_krw\",\n"
    "        \"high_dividend_scenario\",\n",
)
replace_once(
    main,
    "            additional_interest_gross_krw=body.get(\n"
    "                \"additional_interest_gross_krw\", 0.0\n"
    "            ),\n"
    "            investment_scenario=investment_scenario,\n",
    "            additional_interest_gross_krw=body.get(\n"
    "                \"additional_interest_gross_krw\", 0.0\n"
    "            ),\n"
    "            investment_scenario=investment_scenario,\n"
    "            **(\n"
    "                {\n"
    "                    \"additional_foreign_share_realized_gain_krw\": body.get(\n"
    "                        \"additional_foreign_share_realized_gain_krw\"\n"
    "                    )\n"
    "                }\n"
    "                if \"additional_foreign_share_realized_gain_krw\" in body\n"
    "                else {}\n"
    "            ),\n"
    "            **(\n"
    "                {\n"
    "                    \"additional_kr_listed_overseas_etf_taxable_gain_krw\": body.get(\n"
    "                        \"additional_kr_listed_overseas_etf_taxable_gain_krw\"\n"
    "                    )\n"
    "                }\n"
    "                if \"additional_kr_listed_overseas_etf_taxable_gain_krw\" in body\n"
    "                else {}\n"
    "            ),\n",
)

# ---------------------------------------------------------------------------
# UI: quick trading fields + comparison fallback + result details.
# ---------------------------------------------------------------------------
js = ROOT / "app/static/wealth-financial-income-what-if.js"
replace_once(
    js,
    "            </div>\n          </div>\n\n          <div class=\"fi-what-if-section\">\n            <label class=\"fi-what-if-toggle\">\n              <input id=\"fiWhatIfHighDividendEnabled\" type=\"checkbox\" />",
    "            </div>\n"
    "            <div class=\"fi-what-if-subhead\">추가 매매 가정</div>\n"
    "            <div class=\"fi-what-if-grid two\">\n"
    "              <label>\n"
    "                <span>해외주식 실현차익 가정</span>\n"
    "                <input id=\"fiWhatIfForeignShareGain\" type=\"number\" min=\"0\" step=\"10000\" value=\"0\" data-korean-currency />\n"
    "                <small>금융소득 2천만원 판정에는 포함하지 않음</small>\n"
    "              </label>\n"
    "              <label>\n"
    "                <span>국내상장 해외 ETF 과세기준금액</span>\n"
    "                <input id=\"fiWhatIfKrOverseasEtfTaxableGain\" type=\"number\" min=\"0\" step=\"10000\" value=\"0\" data-korean-currency />\n"
    "                <small>배당소득 성격의 screening 금액으로 금융소득에 포함</small>\n"
    "              </label>\n"
    "            </div>\n"
    "          </div>\n\n"
    "          <div class=\"fi-what-if-section\">\n"
    "            <label class=\"fi-what-if-toggle\">\n"
    "              <input id=\"fiWhatIfHighDividendEnabled\" type=\"checkbox\" />",
)

replace_once(
    js,
    "            <div id=\"fiWhatIfInvestmentFields\" class=\"fi-what-if-investment-fields\" hidden>\n"
    "              <div class=\"fi-what-if-grid three\">",
    "            <div id=\"fiWhatIfInvestmentFields\" class=\"fi-what-if-investment-fields\" hidden>\n"
    "              <label class=\"fi-check\">\n"
    "                <input id=\"fiWhatIfUseQuickTrading\" type=\"checkbox\" checked />\n"
    "                <span>빠른 매매 가정을 비교 입력의 보조값으로 사용</span>\n"
    "              </label>\n"
    "              <small>수동 매매차익이 0이거나 ETF 과세대상 매매이익이 빈칸일 때만 위 값을 사용합니다.</small>\n"
    "              <div class=\"fi-what-if-grid three\">",
)

replace_once(
    js,
    "    const etfInput = document.getElementById('fiWhatIfEtfTaxGain');\n"
    "    const scenario = {\n"
    "      asset_type: assetType,\n"
    "      annual_distribution_krw: numberValue('fiWhatIfDistribution'),\n"
    "      annual_realized_gain_krw: numberValue('fiWhatIfRealizedGain'),\n",
    "    const etfInput = document.getElementById('fiWhatIfEtfTaxGain');\n"
    "    const useQuickTrading = boolValue('fiWhatIfUseQuickTrading');\n"
    "    let realizedGain = numberValue('fiWhatIfRealizedGain');\n"
    "    if (useQuickTrading && assetType === 'us_direct' && realizedGain === 0) {\n"
    "      realizedGain = numberValue('fiWhatIfForeignShareGain');\n"
    "    }\n"
    "    const scenario = {\n"
    "      asset_type: assetType,\n"
    "      annual_distribution_krw: numberValue('fiWhatIfDistribution'),\n"
    "      annual_realized_gain_krw: realizedGain,\n",
)

replace_once(
    js,
    "    if (assetType === 'kr_listed_us_etf' && etfInput && etfInput.value !== '') {\n"
    "      scenario.taxable_etf_gain_krw = numberValue('fiWhatIfEtfTaxGain');\n"
    "    }\n",
    "    if (assetType === 'kr_listed_us_etf' && etfInput) {\n"
    "      if (etfInput.value !== '') {\n"
    "        scenario.taxable_etf_gain_krw = numberValue('fiWhatIfEtfTaxGain');\n"
    "      } else if (useQuickTrading) {\n"
    "        scenario.taxable_etf_gain_krw = numberValue('fiWhatIfKrOverseasEtfTaxableGain');\n"
    "      }\n"
    "    }\n",
)

replace_once(
    js,
    "      payload.additional_interest_gross_krw,\n"
    "    ];\n",
    "      payload.additional_interest_gross_krw,\n"
    "      payload.additional_foreign_share_realized_gain_krw,\n"
    "      payload.additional_kr_listed_overseas_etf_taxable_gain_krw,\n"
    "    ];\n",
)

replace_once(
    js,
    "      additional_interest_gross_krw: numberValue('fiWhatIfExtraInterest'),\n"
    "    };\n",
    "      additional_interest_gross_krw: numberValue('fiWhatIfExtraInterest'),\n"
    "      additional_foreign_share_realized_gain_krw: numberValue('fiWhatIfForeignShareGain'),\n"
    "      additional_kr_listed_overseas_etf_taxable_gain_krw: numberValue('fiWhatIfKrOverseasEtfTaxableGain'),\n"
    "    };\n",
)

replace_once(
    js,
    "    const highDividend = whatIf?.high_dividend_special_tax;\n",
    "    const tradingImpact = whatIf?.trading_impact;\n"
    "    if (tradingImpact) {\n"
    "      const foreign = tradingImpact.foreign_shares || {};\n"
    "      const etf = tradingImpact.kr_listed_overseas_etf || {};\n"
    "      const rateText = Number.isFinite(Number(etf.estimated_withholding_rate))\n"
    "        ? `${(Number(etf.estimated_withholding_rate) * 100).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%`\n"
    "        : '확인 불가';\n"
    "      html += `\n"
    "        <div class=\"fi-compare-block\">\n"
    "          <div class=\"fi-compare-title\">\n"
    "            <strong>추가 매매 영향</strong>\n"
    "            <span>금융소득과 양도소득 레이어를 구분합니다.</span>\n"
    "          </div>\n"
    "          <div class=\"fi-result-grid comparison\">\n"
    "            <div class=\"fi-result-card\">\n"
    "              <span>해외주식 실현차익</span>\n"
    "              <strong>${money(foreign.realized_gain_krw || 0)}</strong>\n"
    "              <small>금융소득 판정 미포함 · 양도세는 빠른 입력만으로 미계산</small>\n"
    "            </div>\n"
    "            <div class=\"fi-result-card\">\n"
    "              <span>국내상장 해외 ETF 과세기준금액</span>\n"
    "              <strong>${money(etf.taxable_gain_krw || 0)}</strong>\n"
    "              <small>금융소득에 포함</small>\n"
    "            </div>\n"
    "            <div class=\"fi-result-card\">\n"
    "              <span>ETF 예상 원천징수</span>\n"
    "              <strong>${money(etf.estimated_withholding_krw || 0)}</strong>\n"
    "              <small>${rateText} screening · 최종세액 아님</small>\n"
    "            </div>\n"
    "          </div>\n"
    "        </div>\n"
    "      `;\n"
    "    }\n\n"
    "    const highDividend = whatIf?.high_dividend_special_tax;\n",
)

replace_once(
    js,
    "        이 결과는 2026년 기준 사전 screening입니다. 고배당 특례는 공식 공시 확인과 신고 신청을 사용자가 가정한 경우에만 반영하며, 지방소득세·금융소득 종합과세 최종세액·건강보험료·급여/퇴직금 인출·증여/상속세는 포함하지 않습니다.\n",
    "        이 결과는 2026년 기준 사전 screening입니다. 해외주식 실현차익은 금융소득 판정과 분리하며 빠른 매매 입력만으로 양도소득세를 확정하지 않습니다. 고배당 특례는 공식 공시 확인과 신고 신청을 사용자가 가정한 경우에만 반영하며, 지방소득세·금융소득 종합과세 최종세액·건강보험료·급여/퇴직금 인출·증여/상속세는 포함하지 않습니다.\n",
)

# ---------------------------------------------------------------------------
# Source-of-truth docs: B-1 complete, B-2 current.
# ---------------------------------------------------------------------------
state = ROOT / "docs/PROJECT_STATE.md"
text = state.read_text(encoding="utf-8")
start = text.index("## 1. 현재 개발 상태")
end = text.index("## 2. Phase 10.5 완료/진행 현황")
section = '''## 1. 현재 개발 상태\n\n현재 작업 단계는 **Phase 10.5B-2 — 추가 배당/매매 What-if 확장**입니다.\n\n현재 작업:\n\n- branch: `phase10-5b2-whatif-trading-expansion`\n- base: `main`\n- 상태: 구현/검증 중\n- 작업 시작 기준 main: `a8883c2` (PR #26 merge)\n\nB-2 목표:\n\n1. 기존 추가 배당/이자 What-if에 해외주식 실현차익과 국내상장 해외 ETF 과세기준금액을 추가한다.\n2. 해외주식 실현차익은 금융소득 1천/2천만원 판정에서 분리한다.\n3. 국내상장 해외 ETF 과세기준금액은 금융소득 screening에 포함한다.\n4. 빠른 입력만으로 확정할 수 없는 해외주식 양도소득세는 임의 계산하지 않는다.\n5. 기존 개인 vs 가족법인 비교 입력은 수동값을 우선하고 빠른 매매 가정은 보조값으로만 연결한다.\n6. 모든 시나리오는 stateless이며 저장하지 않는다.\n\n'''
text = text[:start] + section + text[end:]
text = text.replace(
    "- [ ] 10.5B-1 가족 금융소득 위험 보기 — 진행 중",
    "- [x] 10.5B-1 가족 금융소득 위험 보기 — PR #26 merge (`a8883c2`)\n- [ ] 10.5B-2 추가 배당/매매 What-if 확장 — 진행 중",
)
state.write_text(text, encoding="utf-8")

roadmap = ROOT / "docs/ROADMAP.md"
text = roadmap.read_text(encoding="utf-8")
start = text.index("## 1. 현재 우선순위")
end = text.index("## 2. 다음 단계")
section = '''## 1. 현재 우선순위\n\n### Phase 10.5B-2 — 추가 배당/매매 What-if 확장\n\n상태: 구현/검증 중\n\nB-1 가족 금융소득 위험 보기는 PR #26 (`a8883c2`)로 완료되었습니다.\n\n목표:\n\n- 추가 배당/이자와 함께 해외주식 실현차익을 별도 매매 레이어로 표시\n- 국내상장 해외 ETF 과세기준금액을 금융소득 screening에 반영\n- 해외주식 실현차익은 금융소득 1천/2천만원 판정에서 제외\n- 빠른 매매 입력만으로 불충분한 해외주식 양도세는 미계산으로 명시\n- 개인 vs 가족법인 비교에서 수동 입력을 우선하고 빠른 매매 가정을 fallback으로 연결\n- 기존 What-if/high-dividend/family-risk 회귀 유지\n\n완료 기준:\n\n- ETF 과세기준금액 금융소득 포함 테스트\n- 해외주식 실현차익 금융소득 제외 테스트\n- 정확히 2천만원 경계 유지\n- 새 입력 validation/API no-store/legacy call contract 테스트\n- 투자비교 fallback이 수동값을 덮어쓰지 않는 static guard\n- JS 문법/Python compile/`git diff --check`\n- 전체 unittest suite 및 사용자 로컬 검증\n- PR Ready → merge → GHCR build success\n\n'''
text = text[:start] + section + text[end:]
text = text.replace(
    "다음 제품 단계는 `Phase 10.5B-2 — 추가 배당/매매 What-if 확장`이며 아래 3절을 따른다.",
    "다음 제품 단계는 `Phase 10.5B-3 — 배우자/자녀 분산 시뮬레이션`이며 아래 3절을 따른다.",
)
text = text.replace(
    "### Phase 10.5B-1 — 가족 금융소득 위험 보기\n\n상태: 진행 중. 상세 목표/완료 기준은 이 문서 1절을 따른다.",
    "### Phase 10.5B-1 — 가족 금융소득 위험 보기\n\n상태: 완료 — PR #26 (`a8883c2`).",
)
text = text.replace(
    "### Phase 10.5B-2 — 추가 배당/매매 What-if 확장\n\n- 추가 배당금",
    "### Phase 10.5B-2 — 추가 배당/매매 What-if 확장\n\n상태: 진행 중. 상세 목표/완료 기준은 이 문서 1절을 따른다.\n\n- 추가 배당금",
)
roadmap.write_text(text, encoding="utf-8")

print("Phase 10.5B-2 integration applied")
