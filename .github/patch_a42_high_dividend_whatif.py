from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) What-if service: integrate the existing 2026 high-dividend special rule.
replace_once(
    "app/services/tax/what_if.py",
    "from app.services.tax.financial_income import get_financial_income_projection_for_user\nfrom app.services.tax.investment_tax import compare_investment_tax_2026\n",
    "from app.services.tax.financial_income import get_financial_income_projection_for_user\nfrom app.services.tax.high_dividend_2026 import calculate_high_dividend_separate_tax_2026\nfrom app.services.tax.investment_tax import compare_investment_tax_2026\n",
)

replace_once(
    "app/services/tax/what_if.py",
    "def build_financial_income_what_if(\n    baseline_projection: dict[str, Any],\n    *,\n    additional_dividend_gross_krw: object = 0,\n    additional_interest_gross_krw: object = 0,\n) -> dict[str, Any]:\n",
    "_HIGH_DIVIDEND_SCENARIO_FIELDS = frozenset(\n    {\n        \"special_dividend_income_krw\",\n        \"high_dividend_company_confirmed\",\n        \"separate_taxation_requested\",\n    }\n)\n\n\ndef _high_dividend_special_result(\n    scenario: dict[str, Any] | None,\n    *,\n    additional_dividend_gross_krw: float,\n) -> dict[str, Any] | None:\n    if scenario is None:\n        return None\n    if not isinstance(scenario, dict) or set(scenario) - _HIGH_DIVIDEND_SCENARIO_FIELDS:\n        raise FinancialIncomeWhatIfError(\n            \"FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_SCENARIO_INVALID\"\n        )\n    amount = _nonnegative(\n        scenario.get(\"special_dividend_income_krw\", 0),\n        \"FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_AMOUNT_INVALID\",\n    )\n    if amount > additional_dividend_gross_krw:\n        raise FinancialIncomeWhatIfError(\n            \"FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_EXCEEDS_ADDITIONAL_DIVIDEND\"\n        )\n    return calculate_high_dividend_separate_tax_2026(\n        amount,\n        high_dividend_company_confirmed=scenario.get(\n            \"high_dividend_company_confirmed\", False\n        ),\n        separate_taxation_requested=scenario.get(\n            \"separate_taxation_requested\", False\n        ),\n    )\n\n\ndef build_financial_income_what_if(\n    baseline_projection: dict[str, Any],\n    *,\n    additional_dividend_gross_krw: object = 0,\n    additional_interest_gross_krw: object = 0,\n    high_dividend_scenario: dict[str, Any] | None = None,\n) -> dict[str, Any]:\n",
)

replace_once(
    "app/services/tax/what_if.py",
    "    scenario_addition = additional_dividend + additional_interest\n\n    try:\n",
    "    scenario_addition = additional_dividend + additional_interest\n    high_dividend_special = _high_dividend_special_result(\n        high_dividend_scenario,\n        additional_dividend_gross_krw=additional_dividend,\n    )\n    excluded_from_comprehensive = (\n        int(high_dividend_special.get(\"excluded_from_comprehensive_tax_threshold_krw\", 0))\n        if high_dividend_special\n        else 0\n    )\n\n    try:\n",
)

replace_once(
    "app/services/tax/what_if.py",
    "        scenario_projected = _won(baseline_projected + scenario_addition)\n\n    watch_baseline = _threshold_state(\n",
    "        scenario_projected = _won(baseline_projected + scenario_addition)\n\n    scenario_comprehensive_amount = (\n        None\n        if scenario_projected is None\n        else max(scenario_projected - excluded_from_comprehensive, 0)\n    )\n\n    watch_baseline = _threshold_state(\n",
)

replace_once(
    "app/services/tax/what_if.py",
    "    comprehensive_scenario = _threshold_state(\n        scenario_projected, FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW\n    )\n",
    "    comprehensive_scenario = _threshold_state(\n        scenario_comprehensive_amount, FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW\n    )\n",
)

replace_once(
    "app/services/tax/what_if.py",
    "        \"scenario_projected_gross_screening_income_krw\": scenario_projected,\n        \"thresholds\": {\n",
    "        \"scenario_projected_gross_screening_income_krw\": scenario_projected,\n        \"scenario_comprehensive_tax_screening_income_krw\": scenario_comprehensive_amount,\n        \"high_dividend_special_tax\": high_dividend_special,\n        \"thresholds\": {\n",
)

replace_once(
    "app/services/tax/what_if.py",
    "    additional_interest_gross_krw: object = 0,\n    investment_scenario: dict[str, Any] | None = None,\n) -> dict[str, Any]:\n",
    "    additional_interest_gross_krw: object = 0,\n    high_dividend_scenario: dict[str, Any] | None = None,\n    investment_scenario: dict[str, Any] | None = None,\n) -> dict[str, Any]:\n",
)

replace_once(
    "app/services/tax/what_if.py",
    "        additional_dividend_gross_krw=additional_dividend_gross_krw,\n        additional_interest_gross_krw=additional_interest_gross_krw,\n    )\n",
    "        additional_dividend_gross_krw=additional_dividend_gross_krw,\n        additional_interest_gross_krw=additional_interest_gross_krw,\n        high_dividend_scenario=high_dividend_scenario,\n    )\n",
)

# 2) API allowlist/validation and forwarding.
replace_once(
    "app/main.py",
    '        "additional_interest_gross_krw",\n        "investment_scenario",\n',
    '        "additional_interest_gross_krw",\n        "high_dividend_scenario",\n        "investment_scenario",\n',
)

replace_once(
    "app/main.py",
    "    investment_scenario = body.get(\"investment_scenario\")\n",
    "    high_dividend_scenario = body.get(\"high_dividend_scenario\")\n    if high_dividend_scenario is not None:\n        if not isinstance(high_dividend_scenario, dict):\n            raise HTTPException(\n                status_code=400,\n                detail={\"code\": \"FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID\"},\n                headers={\"Cache-Control\": \"no-store\"},\n            )\n        allowed_high_dividend_fields = {\n            \"special_dividend_income_krw\",\n            \"high_dividend_company_confirmed\",\n            \"separate_taxation_requested\",\n        }\n        if set(high_dividend_scenario) - allowed_high_dividend_fields:\n            raise HTTPException(\n                status_code=400,\n                detail={\"code\": \"FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID\"},\n                headers={\"Cache-Control\": \"no-store\"},\n            )\n\n    investment_scenario = body.get(\"investment_scenario\")\n",
)

replace_once(
    "app/main.py",
    "        FinancialIncomeWhatIfError,\n        InvestmentTaxComparisonError,\n",
    "        FinancialIncomeWhatIfError,\n        HighDividendSpecialTaxError,\n        InvestmentTaxComparisonError,\n",
)

replace_once(
    "app/main.py",
    "            additional_interest_gross_krw=body.get(\n                \"additional_interest_gross_krw\", 0.0\n            ),\n            investment_scenario=investment_scenario,\n",
    "            additional_interest_gross_krw=body.get(\n                \"additional_interest_gross_krw\", 0.0\n            ),\n            high_dividend_scenario=high_dividend_scenario,\n            investment_scenario=investment_scenario,\n",
)

replace_once(
    "app/main.py",
    "        FinancialIncomeWhatIfError,\n        InvestmentTaxComparisonError,\n    ) as exc:\n",
    "        FinancialIncomeWhatIfError,\n        HighDividendSpecialTaxError,\n        InvestmentTaxComparisonError,\n    ) as exc:\n",
)

# 3) UI: explicit official-confirmation and filing-assumption controls.
replace_once(
    "app/static/wealth-financial-income-what-if.js",
    "          <div class=\"fi-what-if-section\">\n            <label class=\"fi-what-if-toggle\">\n              <input id=\"fiWhatIfInvestmentEnabled\" type=\"checkbox\" />\n",
    "          <div class=\"fi-what-if-section\">\n            <label class=\"fi-what-if-toggle\">\n              <input id=\"fiWhatIfHighDividendEnabled\" type=\"checkbox\" />\n              <span>\n                <strong>2026 고배당기업 분리과세 특례 가정</strong>\n                <small>공식 공시 확인과 실제 신고 시 신청 가정을 별도로 입력합니다.</small>\n              </span>\n            </label>\n            <div id=\"fiWhatIfHighDividendFields\" class=\"fi-what-if-investment-fields\" hidden>\n              <div class=\"fi-what-if-grid three\">\n                <label>\n                  <span>특례 배당금액</span>\n                  <input id=\"fiWhatIfHighDividendAmount\" type=\"number\" min=\"0\" step=\"10000\" value=\"0\" data-korean-currency />\n                  <small>위 추가 배당 가정 중 특례 대상이라고 가정할 금액</small>\n                </label>\n                <label class=\"fi-check\">\n                  <input id=\"fiWhatIfHighDividendConfirmed\" type=\"checkbox\" />\n                  <span>공식 공시에서 고배당기업 확인함</span>\n                </label>\n                <label class=\"fi-check\">\n                  <input id=\"fiWhatIfHighDividendRequested\" type=\"checkbox\" />\n                  <span>신고 시 분리과세 신청 가정</span>\n                </label>\n              </div>\n              <small>앱이 배당수익률로 적격 여부를 추정하지 않습니다. 공식 공시 확인이 전제이며 지방소득세·최종 신고세액은 별도입니다.</small>\n            </div>\n          </div>\n\n          <div class=\"fi-what-if-section\">\n            <label class=\"fi-what-if-toggle\">\n              <input id=\"fiWhatIfInvestmentEnabled\" type=\"checkbox\" />\n",
)

replace_once(
    "app/static/wealth-financial-income-what-if.js",
    "    document.getElementById('fiWhatIfInvestmentEnabled')?.addEventListener('change', syncInvestmentFields);\n",
    "    document.getElementById('fiWhatIfHighDividendEnabled')?.addEventListener('change', syncHighDividendFields);\n    document.getElementById('fiWhatIfInvestmentEnabled')?.addEventListener('change', syncInvestmentFields);\n",
)

replace_once(
    "app/static/wealth-financial-income-what-if.js",
    "    syncInvestmentFields();\n    syncVisibility();\n  }\n\n  function syncInvestmentFields() {\n",
    "    syncHighDividendFields();\n    syncInvestmentFields();\n    syncVisibility();\n  }\n\n  function syncHighDividendFields() {\n    const enabled = boolValue('fiWhatIfHighDividendEnabled');\n    const fields = document.getElementById('fiWhatIfHighDividendFields');\n    if (fields) fields.hidden = !enabled;\n  }\n\n  function syncInvestmentFields() {\n",
)

replace_once(
    "app/static/wealth-financial-income-what-if.js",
    "  function buildInvestmentScenario() {\n",
    "  function buildHighDividendScenario() {\n    if (!boolValue('fiWhatIfHighDividendEnabled')) return null;\n    return {\n      special_dividend_income_krw: numberValue('fiWhatIfHighDividendAmount'),\n      high_dividend_company_confirmed: boolValue('fiWhatIfHighDividendConfirmed'),\n      separate_taxation_requested: boolValue('fiWhatIfHighDividendRequested'),\n    };\n  }\n\n  function buildInvestmentScenario() {\n",
)

replace_once(
    "app/static/wealth-financial-income-what-if.js",
    "    if (payload.investment_scenario) {\n",
    "    if (payload.high_dividend_scenario) {\n      values.push(payload.high_dividend_scenario.special_dividend_income_krw);\n    }\n    if (payload.investment_scenario) {\n",
)

replace_once(
    "app/static/wealth-financial-income-what-if.js",
    "    const investmentScenario = buildInvestmentScenario();\n",
    "    const highDividendScenario = buildHighDividendScenario();\n    if (highDividendScenario) payload.high_dividend_scenario = highDividendScenario;\n    const investmentScenario = buildInvestmentScenario();\n",
)

replace_once(
    "app/static/wealth-financial-income-what-if.js",
    "    const projected = whatIf.scenario_projected_gross_screening_income_krw;\n    const baseline = whatIf.baseline_projected_gross_screening_income_krw;\n",
    "    const projected = whatIf.scenario_projected_gross_screening_income_krw;\n    const comprehensiveProjected = whatIf.scenario_comprehensive_tax_screening_income_krw;\n    const baseline = whatIf.baseline_projected_gross_screening_income_krw;\n",
)

replace_once(
    "app/static/wealth-financial-income-what-if.js",
    "          <strong>${money(projected)}</strong>\n          <small>추가 가정 ${money(whatIf.scenario_addition_gross_krw || 0)}</small>\n",
    "          <strong>${money(projected)}</strong>\n          <small>추가 가정 ${money(whatIf.scenario_addition_gross_krw || 0)} · 종합과세 판정대상 ${money(comprehensiveProjected)}</small>\n",
)

replace_once(
    "app/static/wealth-financial-income-what-if.js",
    "    const comparison = data?.investment_comparison;\n",
    "    const highDividend = whatIf?.high_dividend_special_tax;\n    if (highDividend) {\n      const applied = highDividend.special_rule_applied === true;\n      const confirmed = highDividend.high_dividend_company_confirmed_by_user === true;\n      const requested = highDividend.separate_taxation_requested === true;\n      html += `\n        <div class=\"fi-compare-block\">\n          <div class=\"fi-compare-title\">\n            <strong>2026 고배당기업 분리과세 특례</strong>\n            <span>${applied ? '특례 적용 가정' : '특례 미적용'} · screening-only</span>\n          </div>\n          <div class=\"fi-result-grid comparison\">\n            <div class=\"fi-result-card\">\n              <span>공식 공시 확인</span>\n              <strong>${confirmed ? '확인함' : '미확인'}</strong>\n              <small>앱 자동 적격판정 아님</small>\n            </div>\n            <div class=\"fi-result-card\">\n              <span>2천만원 판정 제외액</span>\n              <strong>${money(highDividend.excluded_from_comprehensive_tax_threshold_krw || 0)}</strong>\n              <small>${requested ? '분리과세 신청 가정' : '신청 가정 없음'}</small>\n            </div>\n            <div class=\"fi-result-card\">\n              <span>특례 국세 예상액</span>\n              <strong>${money(highDividend.national_income_tax_krw)}</strong>\n              <small>지방소득세·최종 신고세액 미포함</small>\n            </div>\n          </div>\n        </div>\n      `;\n    }\n\n    const comparison = data?.investment_comparison;\n",
)

replace_once(
    "app/static/wealth-financial-income-what-if.js",
    "        이 결과는 2026년 기준 사전 screening입니다. 금융소득 종합과세 최종세액, 고배당 특례, 건강보험료, 급여·퇴직금 인출, 증여·상속세는 포함하지 않습니다.\n",
    "        이 결과는 2026년 기준 사전 screening입니다. 고배당 특례는 공식 공시 확인과 신고 신청을 사용자가 가정한 경우에만 반영하며, 지방소득세·금융소득 종합과세 최종세액·건강보험료·급여/퇴직금 인출·증여/상속세는 포함하지 않습니다.\n",
)

# 4) Focused tests for A-4.2.
Path("tests/test_high_dividend_what_if.py").write_text(
    '''from __future__ import annotations\n\nimport unittest\n\nfrom app.services.tax.high_dividend_2026 import HighDividendSpecialTaxError\nfrom app.services.tax.what_if import (\n    FinancialIncomeWhatIfError,\n    build_financial_income_what_if,\n)\n\n\nBASELINE = {\n    "known_gross_screening_income_krw": 10_000_000,\n    "projected_gross_screening_income_krw": 19_000_000,\n}\n\n\nclass HighDividendWhatIfTests(unittest.TestCase):\n    def test_no_special_scenario_preserves_existing_screening(self):\n        result = build_financial_income_what_if(\n            BASELINE, additional_dividend_gross_krw=2_000_000\n        )\n        self.assertEqual(result["scenario_projected_gross_screening_income_krw"], 21_000_000)\n        self.assertEqual(result["scenario_comprehensive_tax_screening_income_krw"], 21_000_000)\n        self.assertTrue(result["thresholds"]["comprehensive_tax"]["scenario"]["exceeded"])\n        self.assertIsNone(result["high_dividend_special_tax"])\n\n    def test_applied_special_dividend_reduces_only_comprehensive_screening(self):\n        result = build_financial_income_what_if(\n            BASELINE,\n            additional_dividend_gross_krw=2_000_000,\n            high_dividend_scenario={\n                "special_dividend_income_krw": 2_000_000,\n                "high_dividend_company_confirmed": True,\n                "separate_taxation_requested": True,\n            },\n        )\n        self.assertEqual(result["scenario_projected_gross_screening_income_krw"], 21_000_000)\n        self.assertEqual(result["scenario_comprehensive_tax_screening_income_krw"], 19_000_000)\n        self.assertFalse(result["thresholds"]["comprehensive_tax"]["scenario"]["exceeded"])\n        self.assertTrue(result["thresholds"]["watch"]["scenario"]["at_or_above"])\n        special = result["high_dividend_special_tax"]\n        self.assertTrue(special["special_rule_applied"])\n        self.assertEqual(special["excluded_from_comprehensive_tax_threshold_krw"], 2_000_000)\n        self.assertEqual(special["national_income_tax_krw"], 280_000)\n\n    def test_not_requested_preserves_comprehensive_screening(self):\n        result = build_financial_income_what_if(\n            BASELINE,\n            additional_dividend_gross_krw=2_000_000,\n            high_dividend_scenario={\n                "special_dividend_income_krw": 2_000_000,\n                "high_dividend_company_confirmed": True,\n                "separate_taxation_requested": False,\n            },\n        )\n        self.assertEqual(result["scenario_comprehensive_tax_screening_income_krw"], 21_000_000)\n        self.assertFalse(result["high_dividend_special_tax"]["special_rule_applied"])\n\n    def test_requested_without_official_confirmation_fails_closed(self):\n        with self.assertRaisesRegex(\n            HighDividendSpecialTaxError, "HIGH_DIVIDEND_COMPANY_CONFIRMATION_REQUIRED"\n        ):\n            build_financial_income_what_if(\n                BASELINE,\n                additional_dividend_gross_krw=1_000_000,\n                high_dividend_scenario={\n                    "special_dividend_income_krw": 1_000_000,\n                    "high_dividend_company_confirmed": False,\n                    "separate_taxation_requested": True,\n                },\n            )\n\n    def test_special_amount_cannot_exceed_additional_dividend(self):\n        with self.assertRaisesRegex(\n            FinancialIncomeWhatIfError,\n            "FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_EXCEEDS_ADDITIONAL_DIVIDEND",\n        ):\n            build_financial_income_what_if(\n                BASELINE,\n                additional_dividend_gross_krw=500_000,\n                high_dividend_scenario={\n                    "special_dividend_income_krw": 500_001,\n                    "high_dividend_company_confirmed": True,\n                    "separate_taxation_requested": True,\n                },\n            )\n\n    def test_unknown_special_field_is_rejected(self):\n        with self.assertRaisesRegex(\n            FinancialIncomeWhatIfError,\n            "FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_SCENARIO_INVALID",\n        ):\n            build_financial_income_what_if(\n                BASELINE,\n                high_dividend_scenario={"save": True},\n            )\n\n    def test_unavailable_projection_stays_unknown_after_special_rule(self):\n        result = build_financial_income_what_if(\n            {\n                "known_gross_screening_income_krw": 10_000_000,\n                "projected_gross_screening_income_krw": None,\n            },\n            additional_dividend_gross_krw=1_000_000,\n            high_dividend_scenario={\n                "special_dividend_income_krw": 1_000_000,\n                "high_dividend_company_confirmed": True,\n                "separate_taxation_requested": True,\n            },\n        )\n        self.assertIsNone(result["scenario_projected_gross_screening_income_krw"])\n        self.assertIsNone(result["scenario_comprehensive_tax_screening_income_krw"])\n        self.assertIsNone(result["thresholds"]["comprehensive_tax"]["scenario"]["exceeded"])\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

Path("tests/test_high_dividend_what_if_static.py").write_text(
    '''from __future__ import annotations\n\nfrom pathlib import Path\nimport unittest\n\nROOT = Path(__file__).resolve().parents[1]\n\n\nclass HighDividendWhatIfStaticTests(unittest.TestCase):\n    def test_api_accepts_only_explicit_high_dividend_scenario_fields(self):\n        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")\n        self.assertIn('"high_dividend_scenario"', source)\n        self.assertIn('"special_dividend_income_krw"', source)\n        self.assertIn('"high_dividend_company_confirmed"', source)\n        self.assertIn('"separate_taxation_requested"', source)\n        self.assertIn("HighDividendSpecialTaxError", source)\n\n    def test_ui_separates_official_confirmation_from_filing_assumption(self):\n        source = (ROOT / "app" / "static" / "wealth-financial-income-what-if.js").read_text(encoding="utf-8")\n        self.assertIn("fiWhatIfHighDividendConfirmed", source)\n        self.assertIn("fiWhatIfHighDividendRequested", source)\n        self.assertIn("공식 공시에서 고배당기업 확인함", source)\n        self.assertIn("신고 시 분리과세 신청 가정", source)\n        self.assertIn("high_dividend_scenario", source)\n        self.assertIn("scenario_comprehensive_tax_screening_income_krw", source)\n        self.assertNotIn("고배당 특례, 건강보험료", source)\n\n    def test_ui_does_not_claim_automatic_eligibility(self):\n        source = (ROOT / "app" / "static" / "wealth-financial-income-what-if.js").read_text(encoding="utf-8")\n        self.assertIn("앱이 배당수익률로 적격 여부를 추정하지 않습니다", source)\n        self.assertIn("앱 자동 적격판정 아님", source)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

# 5) Update continuity docs for phase transition.
replace_once(
    "docs/PROJECT_STATE.md",
    "현재 작업 단계는 **Phase 10.5A-4.1 — 공식 공시 기반 배당예상 Source 계층**입니다.\n\n현재 PR:\n\n- PR: `#22`\n- branch: `phase10-5a41-official-dividend-forecast`\n- base: `main`\n- 상태: Draft\n- 작업 시작 기준 main: `6c0f8a3`\n- 이 문서 추가 직전 기능 HEAD: `2d38657` (`fix: reuse user-scoped DART credentials`)\n\nPR #22의 목표:\n\n1. 기존 Naver/Yahoo 배당 예상을 유지한다.\n2. 국내 종목에 OpenDART 공식 자료를 추가한다.\n3. 기존 국내 예상 DPS가 없을 때만 직전 사업연도 OpenDART 공식 DPS로 보정한다.\n4. 최근 배당결정 공시가 존재해도 구조적으로 금액을 검증하지 못한 경우 `confirmed_amount=false`를 유지한다.\n5. DART 장애 또는 미설정 상태에서도 기존 예상은 계속 동작한다.\n6. 사용자별 DART 인증정보를 기존 OpenAPI 저장소에서 재사용한다.\n",
    "현재 작업 단계는 **Phase 10.5A-4.2 — 고배당 분리과세 What-if 연결**입니다.\n\n현재 작업:\n\n- branch: `phase10-5a42-high-dividend-whatif`\n- base: `main`\n- 상태: 구현/검증 중\n- 작업 시작 기준 main: `19b0af2` (PR #22 merge)\n\nA-4.2 목표:\n\n1. A-4 고배당 분리과세 규칙 엔진을 A-3 What-if에 연결한다.\n2. 공식 공시 확인 상태와 사용자의 신고 시 특례 신청 가정을 분리한다.\n3. 특례 적용 시 2,000만원 종합과세 screening 대상 금액에서 적격 특례배당만 제외한다.\n4. 1,000만원 제품 watch는 총 금융소득 기준을 유지한다.\n5. 공식 확인 없이 특례를 요청하면 fail-closed로 거부한다.\n6. 결과는 screening-only이며 지방소득세/최종 신고세액을 확정하지 않는다.\n",
)

replace_once(
    "docs/PROJECT_STATE.md",
    "- [ ] 10.5A-4.1 공식 공시 기반 배당예상 Source 계층 — PR #22 진행 중\n",
    "- [x] 10.5A-4.1 공식 공시 기반 배당예상 Source 계층 — PR #22 merge (`19b0af2`)\n- [ ] 10.5A-4.2 고배당 분리과세 What-if 연결 — 진행 중\n",
)

replace_once(
    "docs/ROADMAP.md",
    "### Phase 10.5A-4.1 — 공식 공시 기반 배당예상 Source 계층\n\n상태: 진행 중 / PR #22\n",
    "### Phase 10.5A-4.2 — 고배당 분리과세 What-if 연결\n\n상태: 진행 중\n\nA-4.1 공식 공시 기반 배당예상 Source 계층은 PR #22 (`19b0af2`)로 완료되었습니다.\n",
)
