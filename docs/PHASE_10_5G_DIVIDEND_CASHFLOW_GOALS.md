# Phase 10.5G — Dividend cashflow goals

마지막 갱신: 2026-09-29

## 배경

Phase 10.5F는 PR #52 merge `ed10883728a97fca71baa29ad8c28f41cb4b4298`, GHCR Build and Publish Docker Image run #135 성공 후 운영/browser smoke까지 확인했다.

운영 smoke에서 확인한 10.5F 상태:

- USD 예수금 `type=number` raw value는 유지하면서 `$15,929.62 · 약 ₩22,052,807` 보조표시 정상
- Dividend Intelligence 상세 내부 상태가 `calculated` 대신 `계산 완료`로 표시
- ETF·해외자산의 고배당기업 `대상 아님` 상태에서는 불필요한 `공식 근거` 링크가 표시되지 않음

## 목표

새 세법·세율·forecast source를 추가하지 않고 기존 10.5D~F 결과를 실제 배당 현금흐름 의사결정에 연결한다.

1. 선택 연도의 1~12월 **알려진 세금 후 예상 현금흐름**을 월별로 보여준다.
2. 월평균 예상 수령액, 최대/최소 배당월, 최대월 편중도를 보여준다.
3. 사용자가 **알려진 세금 후 월배당 목표**를 입력하면 목표 충족 월 수와 연간 부족/초과 금액을 보여준다.
4. 알려진 세금 후 예상 현금 기여 상위 종목을 보여준다.
5. monthly attribution이 완전하지 않으면 목표 판정을 fail-closed 한다.

## 월별 알려진 세금 후 배분 계약

- 월별 세전 forecast는 기존 `monthly_schedule`을 그대로 사용한다.
- 세금 계산은 새로 하지 않는다.
- 종목별 연간 `after_known_tax_cash_krw`는 기존 C-5 / Dividend Intelligence 계산 결과만 재사용한다.
- 같은 종목의 연간 알려진 세금 후 예상 현금을 기존 monthly schedule의 종목별 세전 예상 비중으로 월별 배분한다.
- 월별 배분은 자산관리용 projection이며 record-date entitlement 또는 실제 입금일 확정이 아니다.
- `portfolio_after_tax.calculation_status != complete`, 종목 매칭 실패, 계산 제외 종목, residual 등이 있으면 월 목표 충족 여부를 확정 표시하지 않는다.
- residual은 특정 월이나 종목에 임의 배분하지 않는다.
- 완전 계산 상태에서는 월별 알려진 세금 후 예상 현금 합계가 기존 canonical 연간 `after_known_tax_cash_krw`와 일치해야 한다.

## 월배당 목표 계약

- 목표는 법정 기준이나 세금 threshold가 아니라 사용자가 직접 정하는 자산관리 목표다.
- 기본 목표값을 하드코딩하지 않는다.
- 목표 입력은 KRW native numeric input을 유지한다.
- 목표값은 서버 금융데이터에 저장하지 않고 현재 브라우저 `localStorage`에 owner별로만 저장한다.
- 목표가 없으면 월별 현금흐름만 표시한다.
- 월별 알려진 세금 후 attribution이 불완전하면 `목표 비교 보류`로 표시한다.

## 화면

Dividend Intelligence 안에서 다음 순서로 표시한다.

- 기존 알려진 세금 후 연간 KPI
- 신뢰도/근거 chip
- **선택 연도 12개월 배당 현금흐름**
  - 월 목표 입력
  - 월평균 예상 수령
  - 최대/최소 월
  - 최대월 편중
  - 목표 충족 월 / 연간 부족·초과
  - 1~12월 compact cashflow cards
  - 상위 예상 수령 기여 종목
  - 계산 범위 설명
- 고배당기업 공식 자격
- 정확도 / 알림
- 종목·계좌별 상세

기존 월별 세전 배당 차트는 유지한다. 10.5G 영역은 그 차트를 대체하지 않고 **알려진 세금 후 의사결정 레이어**를 추가한다.

## 비범위

- 새로운 세율·세법·금융소득 threshold 추가 없음
- rolling 12개월 forecast 신규 생성 없음: 현재 선택 연도의 1~12월 schedule을 사용
- 실제 배당 entitlement 추론 없음
- forecast event identity / dedup 변경 없음
- 고배당기업 공식 자격 판정 변경 없음
- 배당·금융소득 알림 변경 없음
- C-7 가족별 배당 분산 UI 변경 없음
- 서버측 목표값 persistence 추가 없음

## 검증

- `tests.test_dividend_cashflow_goal_frontend`
- 기존 Dividend Intelligence / after-tax frontend regression
- 기존 money-input regression
- full unittest
- `node --check app/static/wealth-dividend-source.js`
- Python compile
- `git diff --check`
- clean status
- PR final review → exact-head merge → main SHA verify → GHCR → 운영/browser smoke

## 운영 smoke 항목

- 월별 알려진 세금 후 카드 12개 표시
- 현재 100% coverage 포트폴리오에서 월별 합계가 연간 알려진 세금 후 예상 현금과 일치
- 월 목표 입력 후 충족 월 수 / 연간 부족 또는 초과 표시
- 목표 입력 삭제 시 `월 목표 미설정` 복귀
- owner 전환 시 owner별 목표 분리
- 기존 gross 월별 차트 / 고배당기업 / 정확도 / 알림 / 종목 상세 회귀 없음
