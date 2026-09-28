# Phase 10.5F — Dividend detail UX polish + USD amount helper

마지막 갱신: 2026-09-29

## 상태

Phase 10.5E는 PR #51 merge `3d23a50425f3321942713192557bc546a8397b58`, GHCR Build and Publish Docker Image run #120 성공, 운영 기동 및 browser smoke까지 완료했다.

운영 browser smoke에서 확인한 10.5E 상태:

- compact `배당 예상 근거` chip과 상세 펼쳐보기 정상
- Dividend Intelligence가 배당 요약 카드 바로 아래 배치
- 알려진 세금 후 예상 현금 / 알려진 세금 / 세후 배당수익률 / coverage 정상
- 고배당기업 공식 자격 대상 국내주식 14종목은 `공식 해당 0 / 공식 미해당 0 / 확인 대기 14 / 조회 불가 0`
- `확인 대기`는 source 장애가 아니라 공식 `해당/미해당` 값을 구조적으로 확인하지 못한 fail-closed 상태
- ETF·해외자산은 `대상 아님`
- point-in-time snapshot 2개 누적 확인
- 배당·금융소득 알림 기본 OFF 확인

## 목표

10.5E의 계산/공식 source 계약은 변경하지 않고 운영 화면에서 확인된 작은 UX 마찰만 정리한다.

1. Dividend Intelligence 상세 표의 내부 상태값 `calculated`를 사용자 문구 `계산 완료`로 표시한다.
2. 고배당기업 자격 `대상 아님`인 ETF·해외자산에는 고배당기업 `공식 근거` 링크를 표시하지 않는다.
3. 기존 native number input 계약을 유지하면서 USD 예수금 입력에 `$12,345.67` 형태의 천 단위 보조표시와 현재 portfolio `fx_rates.USD` 기준 원화 환산 보조값을 표시한다.

## USD 입력 계약

- input 자체의 `type=number`와 raw value는 변경하지 않는다.
- 기존 저장/API payload의 숫자 의미를 변경하지 않는다.
- `input.value`를 포맷된 문자열로 덮어쓰지 않는다.
- `cash_usd` 입력과 명시적 `data-auto-usd-preview` opt-in 필드만 대상으로 한다.
- 원화 환산은 dashboard가 이미 수신한 `data.fx_rates.USD`를 `wealth:portfolio` event의 `fxRates.USD`에서 재사용한다.
- 환율을 새로 조회하거나 client에 환율 상수를 하드코딩하지 않는다.
- 현재 환율이 없으면 숫자를 추정하지 않고 `원화 환산 대기`로 표시한다.
- 기존 KRW 금액 보조표시 계약과 동작은 유지한다.

## Dividend detail UX 계약

- backend `calculation_status` 값 자체는 변경하지 않고 frontend display label만 한글화한다.
- `calculated` → `계산 완료`
- `unsupported` → `계산 제외`
- `unavailable` → `확인 불가`
- `partial` → `부분 계산`
- 고배당기업 `not_applicable`은 상태 badge만 표시하고 고배당기업 공식 근거 링크를 숨긴다.
- `official_qualified`, `official_not_qualified`, `not_confirmed`, `source_unavailable`의 기존 공식 근거 링크 계약은 유지한다.

## 비범위

- 세율·세법·threshold 변경 없음
- 고배당기업 자격 판정 로직 변경 없음
- 고배당기업 상태 변경 알림 추가 없음
- C-7 가족별 배당 분산 UI 변경 없음
- 실제 입력값 persistence 방식 변경 없음
- 새로운 FX API 호출 없음

## 완료 조건

- USD 예수금 입력의 포맷/원화 환산 helper 동작
- live `fx_rates.USD` 미존재 시 fail-closed 표시
- 기존 KRW money-input 회귀 없음
- Dividend Intelligence 상세 상태 한글화
- `대상 아님` 자산에서 불필요한 고배당 공식 링크 제거
- targeted + related regression + full unittest 통과
- JS `node --check`, Python compile, `git diff --check`, clean status 통과
- PR final review → exact-head merge → main SHA verify → GHCR → 운영/browser smoke
