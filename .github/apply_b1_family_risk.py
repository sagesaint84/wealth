from __future__ import annotations

from pathlib import Path
import re


MAIN = Path("app/main.py")
INDEX = Path("app/static/index.html")
STATE = Path("docs/PROJECT_STATE.md")
ROADMAP = Path("docs/ROADMAP.md")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing marker: {label}")
    return text.replace(old, new, 1)


main = MAIN.read_text(encoding="utf-8")
route = '''@app.get("/api/dividends/financial-income-family-risk")
async def financial_income_family_risk(request: Request) -> JSONResponse:
    """Return per-family-member financial-income screening risk."""
    username = get_current_username(request)
    from app.services.tax import (
        FamilyFinancialIncomeRiskError,
        get_family_financial_income_risk_for_user,
    )
    try:
        result = await get_family_financial_income_risk_for_user(username)
    except FamilyFinancialIncomeRiskError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": str(exc)},
            headers={"Cache-Control": "no-store"},
        ) from exc
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


'''
main = replace_once(
    main,
    '@app.post("/api/dividends/financial-income-simulation")',
    route + '@app.post("/api/dividends/financial-income-simulation")',
    "family risk API insertion point",
)
MAIN.write_text(main, encoding="utf-8")

index = INDEX.read_text(encoding="utf-8")
index = replace_once(
    index,
    '    <link rel="stylesheet" href="/static/wealth-financial-income-what-if.css?v=1.3.0" />',
    '    <link rel="stylesheet" href="/static/wealth-financial-income-what-if.css?v=1.3.0" />\n'
    '    <link rel="stylesheet" href="/static/wealth-family-financial-income-risk.css?v=1.3.0" />',
    "family risk stylesheet",
)
index = replace_once(
    index,
    '    <script src="/static/wealth-financial-income-what-if.js?v=1.3.0"></script>',
    '    <script src="/static/wealth-financial-income-what-if.js?v=1.3.0"></script>\n'
    '    <script src="/static/wealth-family-financial-income-risk.js?v=1.3.0"></script>',
    "family risk script",
)
INDEX.write_text(index, encoding="utf-8")

state = STATE.read_text(encoding="utf-8")
state, count = re.subn(
    r"## 1\. 현재 개발 상태\n.*?\n## 2\. Phase 10\.5 완료/진행 현황",
    '''## 1. 현재 개발 상태

현재 작업 단계는 **Phase 10.5B-1 — 가족 금융소득 위험 보기**입니다.

현재 작업:

- branch: `phase10-5b1-family-financial-income-risk`
- base: `main`
- 상태: 구현/검증 중
- 작업 시작 기준 main: `39ca928` (PR #25 merge)

B-1 목표:

1. `settings.family_members`에 등록된 구성원별 금융소득 projection을 독립 계산한다.
2. 1,000만원 product watch와 2,000만원 종합과세 screening을 개인별로만 표시한다.
3. 가족 전체 합계는 참고값으로만 제공하고 법정 2,000만원 기준을 가족 합계에 적용하지 않는다.
4. `모두` 또는 미등록 소유자의 보유자산/실제 금융소득 기록은 임의 배분하지 않고 미분류 상태로 표시한다.
5. 한 구성원의 forecast가 불가능하면 가족 projected 합계를 부분합으로 표시하지 않는다.
6. 기존 금융소득 projection·DART/KIND/Naver/Yahoo source 계층을 그대로 재사용한다.

## 2. Phase 10.5 완료/진행 현황''',
    state,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit("PROJECT_STATE current phase block not replaced")
state = replace_once(
    state,
    '- [ ] 10.5A-4.4 국내 ETF 분배금 공식 Source 개선 — 진행 중',
    '- [x] 10.5A-4.4 국내 ETF 분배금 공식 Source 개선 — PR #25 merge (`39ca928`)\n'
    '- [ ] 10.5B-1 가족 금융소득 위험 보기 — 진행 중',
    "PROJECT_STATE phase checklist",
)
if "### 가족 금융소득 위험 보기" not in state:
    state = replace_once(
        state,
        '### 개인 vs 가족법인 비교',
        '''### 가족 금융소득 위험 보기

- 법정 금융소득 종합과세 기준은 개인별 기준으로만 평가한다.
- 가족 합계는 자산배분 참고용이며 법정 threshold 판정값이 아니다.
- 가족 구성원은 `settings.family_members` 순서를 따른다.
- `모두`/미등록 소유자의 데이터는 구성원에게 임의 배분하지 않는다.
- 자동 미래 이자 forecast는 아직 없으며 B-1은 기존 projection 기본값(추가 이자 0원)을 사용한다.

### 개인 vs 가족법인 비교''',
        "PROJECT_STATE family principle",
    )
STATE.write_text(state, encoding="utf-8")

roadmap = ROADMAP.read_text(encoding="utf-8")
roadmap, count = re.subn(
    r"## 1\. 현재 우선순위\n.*?\n## 2\. 다음 단계",
    '''## 1. 현재 우선순위

### Phase 10.5B-1 — 가족 금융소득 위험 보기

상태: 구현/검증 중

A-4.4 국내 ETF 분배금 공식 Source 개선은 PR #25 (`39ca928`)로 완료되었습니다.

목표:

- 등록 가족 구성원별 실제 YTD + 미래 예상 배당 기반 금융소득 projection을 계산한다.
- 개인별 1,000만원 watch / 2,000만원 종합과세 screening 상태를 표시한다.
- 정확히 2,000만원은 `도달 · 초과 아님`, 2,000만원 초과는 `초과`로 구분한다.
- 가족 합계는 참고값으로만 제공하고 개인별 법정 threshold와 혼동하지 않는다.
- 미분류 소유자 데이터가 있으면 가족 참고 합계의 불완전성을 명시한다.
- 일부 구성원 forecast가 unavailable이면 projected 가족 합계를 부분합으로 표시하지 않는다.

완료 기준:

- 구성원 순서/소유자 scoping 테스트
- 정확히 2,000만원 경계 테스트
- 1,000만원 watch / 2,000만원 개인별 위험 집계 테스트
- 가족 합계에 statutory threshold를 적용하지 않는 guard
- 미분류 소유자/forecast unavailable completeness guard
- authenticated-user only API / `Cache-Control: no-store`
- 예상 탭 개인별 위험 UI 및 가족 참고 합계 경고
- 기존 financial-income projection/What-if 회귀 통과
- 전체 unittest suite 통과
- 사용자 로컬 검증 완료
- PR Ready → merge
- GHCR build success

## 2. 다음 단계''',
    roadmap,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit("ROADMAP priority block not replaced")
roadmap = replace_once(
    roadmap,
    '다음 제품 단계는 `Phase 10.5B-1 — 가족 금융소득 위험 보기`이며 아래 3절을 따른다.',
    '다음 제품 단계는 `Phase 10.5B-2 — 추가 배당/매매 What-if 확장`이며 아래 3절을 따른다.',
    "ROADMAP next phase",
)
roadmap, count = re.subn(
    r"### Phase 10\.5B-1 — 가족 금융소득 위험 보기\n.*?\n### Phase 10\.5B-2",
    '''### Phase 10.5B-1 — 가족 금융소득 위험 보기

상태: 진행 중. 상세 목표/완료 기준은 이 문서 1절을 따른다.

핵심 원칙:

- 본인/배우자/자녀 등 등록 소유자별 예상 금융소득
- 1,000만원 watch / 2,000만원 screening 상태는 개인별 판정
- 가족 전체 합계는 참고값으로만 제공
- 미분류 데이터는 임의 배분하지 않음

### Phase 10.5B-2''',
    roadmap,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit("ROADMAP B-1 section not replaced")
ROADMAP.write_text(roadmap, encoding="utf-8")
