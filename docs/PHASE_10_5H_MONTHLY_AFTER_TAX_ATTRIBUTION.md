# Phase 10.5H — Monthly after-known-tax attribution precision

## 목적

Phase 10.5G는 연간 알려진 세금 후 배당 현금을 기존 forecast 지급월에 배분해 월배당 목표를 비교했다. 운영 browser smoke에서 연간 세후 계산 coverage는 100%였지만 일부 연간 forecast에 안전한 지급월이 없어 `목표 비교 보류`가 표시됐다.

10.5H의 목적은 이 상태를 임의 월 추정으로 숨기지 않고 다음 두 층으로 분리하는 것이다.

1. **연간 알려진 세금 후 총액** — 기존 검증된 `portfolio_after_tax` 결과를 authoritative 값으로 유지
2. **월별 안전 귀속액** — 기존 `monthly_schedule`에 실제 존재하는 종목/통화별 gross 금액에 한해서만 알려진 세금 후 현금을 비례 귀속

## 월별 귀속 계약

종목별 기존 값을 다음과 같이 사용한다.

- 연간 gross: 기존 `gross_annual_dividend_krw`
- 연간 알려진 세금 후 현금: 기존 `after_known_tax_cash_krw`
- 월별 gross: 기존 `monthly_schedule.items[].payout_krw`
- identity: normalized `code + currency`

새 세율이나 세금 계산은 만들지 않는다.

### 완전한 지급월 schedule

종목의 월별 gross 합계가 연간 gross와 반올림 허용오차 내에서 일치하면 기존 연간 알려진 세금 후 현금 전체를 해당 월별 gross 비중으로 배분한다.

### 부분 지급월 schedule

월별 gross 합계가 연간 gross보다 작으면 월별로 확인 가능한 gross 비율만큼의 알려진 세금 후 현금만 배분한다.

예:

```text
연간 gross       1,000,000
월별 schedule      600,000
연간 known cash    850,000

월 귀속 가능 cash = 850,000 × 60% = 510,000
월 미정 cash      = 340,000
```

### 지급월 없음

연간 forecast가 존재하지만 기존 forecast에 지급월이 없으면 해당 종목의 알려진 세금 후 현금 전액을 `월 미정`으로 유지한다.

### 월 schedule가 연간 gross를 초과

반올림 오차를 넘어 월별 gross가 연간 gross보다 크면 해당 종목 월 귀속은 fail-closed 처리한다. 초과분을 축소하거나 다른 월에 재배분하지 않는다.

## 반올림

기존 monthly schedule item은 원 단위로 반올림돼 있으므로 월 item 개수에 비례한 최소 반올림 허용오차만 사용한다. 이 허용오차는 지급월을 새로 만들거나 경제적 금액을 fuzzy matching하는 데 사용하지 않는다.

## 월 목표 의미

연간 `portfolio_after_tax` 계산이 complete이고 residual이 0이며 종목별 annual cash 합계와 reconciliation되면 **연간 총액 비교는 가능**하다.

월별 attribution이 일부 미완료인 경우:

- 안전하게 귀속된 금액만으로 이미 목표를 넘은 월은 `최소 충족`으로 표시
- 목표 미만인 월은 `판정 대기`로 표시
- `최소 X개월 충족 · Y개월 판정 대기` 제공
- 연간 목표(`월 목표 × 12`) 대비 부족/초과는 canonical 연간 known-after-tax 총액으로 표시
- 월 미정 known-after-tax 현금을 별도로 표시

월별 attribution이 100%인 경우에만 기존 `X / 12개월 충족`을 확정 표시한다.

연간 after-known-tax 계산 자체가 불완전하면 기존처럼 `목표 비교 보류`로 fail-closed한다.

## UX

10.5G 현금흐름 block을 유지하면서 다음을 명확히 표시한다.

- 월평균 예상 수령 = canonical 연간 알려진 세금 후 총액 ÷ 12
- `월 귀속 XX.XX% · 월 미정 ₩...`
- 월 카드 금액은 `귀속 하한`임을 표시
- 부분 귀속 시 최대/최소 월 및 편중은 `귀속분 기준` / `연간 총액 대비 귀속 하한`으로 표시
- 월 미정 금액이 큰 종목을 펼쳐볼 수 있음
- residual과 월 미정 금액을 특정 월·종목에 임의 배분하지 않음

## 변경하지 않는 계약

- canonical gross forecast 변경 없음
- `monthly_schedule`의 지급월 생성/수정 없음
- official event identity/dedup 변경 없음
- record-date entitlement 추론 없음
- 새로운 세율/threshold 없음
- 고배당기업 자격/세제특례 자동 적용 없음
- 서버 금융데이터 persistence 변경 없음
- C-7 가족별 배당 분산 UX는 계속 보류

## 완료 조건

1. 부분 schedule에 연간 known-after-tax 현금 전액을 과다 배분하지 않는다.
2. 지급월이 없는 연간 배당은 월 미정으로 남는다.
3. 월 schedule가 연간 gross를 초과하면 fail-closed한다.
4. 월평균은 annual canonical known-after-tax 총액 기준으로 표시한다.
5. 부분 귀속에서도 최소 충족 월과 연간 목표 부족/초과를 안전하게 제공한다.
6. residual/month-unknown을 임의 배분하지 않는다.
7. targeted/related/full unittest, JS syntax, diff/status gate를 통과한다.
8. exact-head merge, GHCR, 운영 배포 및 browser smoke를 완료한다.
