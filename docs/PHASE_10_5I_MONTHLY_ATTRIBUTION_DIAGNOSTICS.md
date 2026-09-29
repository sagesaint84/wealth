# Phase 10.5I — Monthly attribution diagnostics & compact goal UX

## 목적

Phase 10.5H는 월별 알려진 세금 후 현금 귀속을 안전한 하한값과 `월 미정` 금액으로 분리했다. 운영 browser smoke에서 월 귀속 70.59%, 월 미정 ₩3,149,547가 확인됐고, 월 목표 판단은 `최소 1개월 충족 · 11개월 판정 대기`로 안전하게 동작했다.

10.5I는 이 `월 미정` 금액을 임의 월에 배분하지 않고 **왜 미정인지 사용자가 바로 이해할 수 있게 진단 UX를 추가**한다. 동시에 10~12월처럼 좁은 월 카드에서 상태 문구가 줄바꿈되는 문제를 compact badge로 정리한다.

## 범위

- 기존 10.5H `unassignedInstruments`를 그대로 재사용
- 월 미정 사유를 사용자 문구로 매핑
  - `monthly_schedule_missing` → `지급월 없음`
  - `partial_monthly_schedule` → `일부 지급월만 연결`
  - `monthly_schedule_exceeds_annual` → `월별 합계 불일치`
  - `rounding_remainder` → `반올림 잔액`
- 월 미정 종목별로 다음 정보를 표시
  - 종목명 / 코드 / 통화
  - 사유
  - 지급월 schedule coverage
  - 연결된 월별 gross 합계 / 연간 gross
  - 월 미정 알려진 세금 후 현금
- 사유별 종목 수 요약
- 월 카드 상태를 `최소 ✓` / `대기` compact badge로 표시하고 원래 의미는 title로 보존

## 변경하지 않는 계약

- annual gross / after-known-tax canonical 값 변경 없음
- monthly schedule 생성/수정 없음
- 지급월 추정 없음
- residual / 월 미정 금액 임의 배분 없음
- 세율/threshold 추가 없음
- dividend identity/dedup 변경 없음
- entitlement 추론 없음
- 서버 persistence 변경 없음

## 완료 조건

1. 월 미정 사유와 schedule coverage를 화면에서 확인할 수 있다.
2. monthly schedule이 없는 경우를 지급월 추정으로 보완하지 않는다.
3. 월별 합계 불일치도 별도 사유로 노출하고 fail-closed 상태를 유지한다.
4. 월 카드 상태 badge가 좁은 폭에서도 줄바꿈 없이 읽힌다.
5. targeted / related / full unittest, JS syntax, diff/status exact-head gate를 통과한다.
6. exact-head merge, GHCR, 운영 배포 및 browser smoke를 완료한다.
