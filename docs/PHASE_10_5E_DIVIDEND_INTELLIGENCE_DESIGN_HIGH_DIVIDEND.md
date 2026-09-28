# Phase 10.5E — Dividend Intelligence design refresh + 고배당기업 공식 자격

마지막 갱신: 2026-09-28

## 목표

Phase 10.5D에서 통합한 배당 신뢰도·세후 기여도·알림·point-in-time 정확도를 유지하면서 화면의 정보 위계를 단순화하고, 국내 상장주식의 2026 고배당기업 여부를 **회사가 제출한 공식 공시의 명시값**으로만 확인한다.

이 단계는 새로운 세율 또는 새로운 고배당기업 법정 요건 계산기를 만들지 않는다. 기존 `app/services/tax/high_dividend_2026.py`와 `rules_2026.py`의 verified rule contract를 변경하지 않으며, 자동 자격 확인 결과만 Dividend Intelligence에 추가한다.

## 10.5D 마감 상태

- PR #50 merge: `e18408d6d23be031c03c0d8e44e349f09cee239d`
- GHCR Build and Publish Docker Image run #119 성공
- 운영 컨테이너 기동 및 `/ -> /login` 307 확인
- 브라우저 smoke 확인 완료
  - 알려진 세금 후 예상 현금/수익률/coverage 표시
  - 공식 근거/추정/residual 표시
  - point-in-time snapshot 누적 상태 표시
  - 배당·금융소득 알림 기본 OFF 표시
  - 월별 예상 배당 및 종목 drill-down 표시

## UI 변경 범위

### 배당 예상 근거

기존의 긴 문장형 source banner를 다음 compact chip 중심 구조로 바꾼다.

- 공식 근거 종목 수
- 확정금액 반영 종목 수
- 이력·시장 추정 종목 수
- OpenDART / KIND 공식 링크
- 상세 source breakdown과 확정금액 반영 원칙은 `<details>`에 둔다.

### Dividend Intelligence

정보를 다음 순서로 정리한다.

1. **핵심 현금흐름**
   - 알려진 세금 후 예상 현금
   - 알려진 세금
   - 평가금액 기준 세후 배당수익률
   - 세후 계산 coverage
2. **신뢰도 요약**
   - 공식 근거
   - 확정금액 반영
   - 추정
   - 미귀속 residual
3. **고배당기업 공식 자격**
   - 공식 해당
   - 공식 미해당
   - 확인 대기
   - 공식 조회 불가
   - 대상 아님
4. **운영/설정**
   - point-in-time 정확도 상태
   - 배당·금융소득 opt-in 알림
5. **상세 근거**
   - 종목/계좌별 예상 근거
   - 종목별 고배당기업 공식 자격과 원문
   - 세전/알려진 세금/예상 수령 및 기여도

## 고배당기업 자격 source contract

### 공식 근거

2026-09-28 재확인 기준:

- 국가법령정보센터 `조세특례제한법 제104조의27`
  - 고배당기업 요건과 공시 의무를 규정한다.
  - 고배당기업은 정기주주총회에서 이익배당을 결의한 날의 다음 날까지 요건 충족 사실을 공시해야 한다.
- 국가법령정보센터 `조세특례제한법 시행령 제104조의24`
  - 특례배당소득 및 배당성향 등 세부사항을 규정한다.
- 한국거래소 KIND `고배당기업 현황`
  - 상장법인이 제출한 `기업가치 제고 계획` 공시의 `조세특례제한법 제104조의27에 따른 고배당기업 여부` 항목을 기준으로 제공한다.
  - 가장 최근 공시에서 해당 항목이 `해당`인 기업만 목록에 표시되고 이후 `미해당`으로 정정·변경되면 목록에서 제외된다고 명시한다.
- 한국거래소 2026.2 `기업가치 제고 계획 가이드라인 해설서`
  - 공시 양식에 `조세특례제한법 제104조의27에 따른 고배당기업 여부` 필드가 존재한다.
  - 해당 여부는 **기업의 자체적인 판단**임을 명시한다.

공식 reference:

- https://www.law.go.kr/법령/조세특례제한법/제104조의27
- https://www.law.go.kr/법령/조세특례제한법시행령/제104조의24
- https://kind.krx.co.kr/valueup/dividend.do?method=valueupHighDividendMain
- https://kind.krx.co.kr/external/dst/valueupReference/11664/%282026%EB%85%842%EC%9B%94%29%EA%B8%B0%EC%97%85%EA%B0%80%EC%B9%98%20%EC%A0%9C%EA%B3%A0%20%EA%B3%84%ED%9A%8D%20%EA%B0%80%EC%9D%B4%EB%93%9C%EB%9D%BC%EC%9D%B8%20%ED%95%B4%EC%84%A4%EC%84%9C.pdf

### 판정 원칙

Wealth는 회사 자격을 재계산하거나 시장자료로 추정하지 않는다.

- 공식 공시에서 구조적으로 `고배당기업 여부 = 해당` 확인 → `official_qualified`
- 공식 공시에서 구조적으로 `고배당기업 여부 = 미해당` 확인 → `official_not_qualified`
- 관련 공시/필드를 확인하지 못함 → `not_confirmed`
- credential/network/upstream failure → `source_unavailable`
- 해외주식/국내 ETF 등 현재 계약의 비대상 자산 → `not_applicable`

`not_confirmed`는 `미해당`이 아니다. 목록 부재나 공시 부재를 법적 미충족으로 바꾸지 않는다.

### 세금 적용 원칙

- 공식 자격 상태가 `official_qualified`여도 10.5E가 분리과세를 자동 적용하지 않는다.
- 사용자 자산의 특정 배당이 실제 `특례배당소득`인지 자동 확정하지 않는다.
- 기존 10.5A-4 rule engine의 `high_dividend_company_confirmed` / `separate_taxation_requested` 계약을 우회하지 않는다.
- 고배당기업으로 공식 확인된 종목의 **현재 예상 gross 배당 합계/비중**은 자산관리 참고값일 뿐 특례배당소득 확정액이 아니다.
- 새 세율/threshold/client-side tax constant를 추가하지 않는다.

## 데이터 연결

- Phase 10.5D `dividend_intelligence.instruments`를 그대로 사용한다.
- 국내 배당주만 공식 자격 조회 대상으로 삼는다.
- OpenDART/KIND 공식 filing 근거를 사용하고 구조적으로 명시된 해당/미해당 값만 채택한다.
- 실패 시 기존 forecast, C-5 알려진 세금 후 계산, C-4/C-4.1 identity/snapshot 계약은 그대로 유지한다.

## 완료 조건

- source banner가 compact summary + collapsible detail 구조로 변경
- Dividend Intelligence 핵심 KPI/신뢰도/운영 상태의 시각적 우선순위 정리
- 국내 배당주별 공식 고배당기업 상태 및 원문 link 표시
- 목록/공시 부재를 `미해당`으로 추론하지 않음
- 세제특례 자동 적용 없음
- 기존 C-4/C-4.1/C-5/C-6/10.5D 계약 회귀 없음
- targeted + related regression + full unittest + compile + JS syntax + diff/status gate 통과
- PR merge / GHCR / 운영 browser smoke 확인
