# Phase 10.5D — Dividend Intelligence

상태: 통합 구현 및 검증 진행 중

Phase 10.5D는 다음 네 작업을 하나의 increment와 하나의 PR로 묶는다.

1. 배당 예상 신뢰도·근거 UX 강화
2. 종목/계좌별 알려진 세금 후 배당 기여도
3. 배당·금융소득 opt-in 알림
4. 배당예측 point-in-time 정확도 화면

## 재사용 계약

새 세율, 새로운 금융소득 threshold, 새로운 배당 event matching 규칙을 만들지 않는다.

- C-4의 official dividend event identity / dedup 계약을 그대로 사용한다.
- C-4.1 `dividend_forecast_snapshots.json`과 기존 evaluator만 정확도 측정에 사용한다.
- C-5 `portfolio_after_tax`를 세전/알려진 세금 후 현금의 canonical tax-attribution 계층으로 재사용한다.
- B-1 가족 금융소득 위험 보기의 **개인별** threshold 결과만 금융소득 알림에 사용한다.
- 가족 합계에는 1천만원/2천만원 법정 screening 기준을 적용하지 않는다.

## 신뢰도·공식 근거

종목별 forecast source는 현재 저장된 공식자료 metadata를 해석해 다음 수준으로 표시한다.

- 공식 확정금액 반영
- 공식 확정 근거 있으나 숫자 미반영
- 공식 근거 확인
- 공식 과거이력 기반 추정
- 최근 배당이력 기반 추정
- 시장 데이터 기반 추정
- 휴리스틱 추정

공시 원문 링크는 저장된 `https://` 공식 evidence URL이 있을 때만 노출한다.
공시 존재와 미래 지급액 확정은 계속 구분한다.

## 종목/계좌별 기여도

포트폴리오 gross total은 계속 `summary.total_annual_dividend_krw`가 authoritative하다.
종목별 C-5 attribution 합계와 canonical total의 차이인 residual은 특정 종목이나 계좌에 임의 귀속하지 않는다.

동일 종목이 여러 계좌에 있을 때 계좌별 금액은 현재 보유수량 비율로만 나누는 **자산관리 추정치**다.
이는 record-date 보유 또는 배당 권리(entitlement) 확정이 아니다.

## 배당·금융소득 알림

알림은 기본 OFF이며 `automation.dividend_intelligence_alerts.enabled=true`로 사용자가 명시적으로 켠 경우에만 동작한다.

scheduled daily-close forecast snapshot에서:

- 새 official 배당/ETF distribution event identity
- 새 배당결정 공시 존재

를 deterministic event key로 중복 방지해 알린다.

금융소득 알림은 B-1의 각 등록 가족 구성원별 projection을 다시 사용해:

- 1천만원 watch 도달
- 2천만원 도달
- 2천만원 초과

상태를 개인별로만 알린다. `모두` 또는 가족 reference total은 threshold 대상으로 사용하지 않는다.
알림 실패는 daily-close snapshot 저장을 실패시키지 않는다.

## 배당예측 정확도

정확도 화면은 저장된 point-in-time snapshot과 actual record만 사용한다.
과거 예측을 현재 holdings/source로 재생성하지 않는다.
현재 진행 중인 월은 제외한다.

기존 evaluator가 amount comparison을 완전하다고 판정할 때만 MAE/WAPE를 표시한다.
비교 가능한 gross actual 또는 forecast attribution이 불완전하면 금액 정확도를 억지로 계산하지 않는다.
충분한 평가 horizon이 없으면 `측정 데이터 누적 중`으로 표시한다.

## C-7

가족별 배당 분산 보기 단순화(C-7)는 기존 Family Risk / Allocation Simulation과 기능 중복이 크므로 추후 UX 정리 후보로 계속 보류한다.
