# Wealth Roadmap

> 현재 작업 상태는 `docs/PROJECT_STATE.md`를 먼저 읽습니다.
> 이 문서는 앞으로 진행할 기능의 우선순위와 완료 기준을 기록합니다.

마지막 갱신: 2026-09-29

## 1. 현재 우선순위

### Phase 10.5C — 배당 자산관리 의사결정

Wealth의 세금 기능은 **종합소득세 신고서 완성**이 아니라 **배당 자산관리 의사결정**을 우선한다.

완료:

- 10.5B-4.9 납세조합공제 선행 세액공제 — PR #40 merge (`7d97cd4a`)
- 10.5C-1 배당 세금 대시보드 — PR #41 merge (`f046f22d`), 운영 배포 확인
- 10.5C-2 세후 배당 현금흐름 보기 — PR #42 merge (`fcf14ba`)
- 10.5C-3 일간 가격손익과 평가액 변화 분리 — PR #43 merge (`89ad76a`)
- 10.5C-4 Dividend event identity & high-confidence actual/forecast dedup — PR #44 merge (`b235934d`)
- 10.5C-4.1 Dividend forecast point-in-time measurement foundation — PR #45 merge (`5edb9388`), 운영 배포 및 최초 snapshot 생성 확인
- 10.5C-5 포트폴리오 알려진 세금 후 배당수익률 — PR #46 merge (`b5e8cbaa`)
- 세금 도구 전용 `🧾 세금` workspace 이동 — PR #47 merge (`8f490c0`)
- 10.5C-6 2천만원 접근 What-if 개선 — PR #48, 운영 확인 완료 (`0d87fd9c`)

### Phase 10.5D — Dividend Intelligence

상태: **완료** — PR #50 merge (`e18408d6`), 운영 배포 및 browser smoke 확인.

통합 increment로 다음 네 항목을 한 번에 구현했다.

1. 배당 예상 신뢰도·근거 UX 강화
2. 종목/계좌별 알려진 세금 후 배당 기여도
3. 배당·금융소득 opt-in 알림
4. 배당예측 point-in-time 정확도 화면

핵심 원칙:

- C-4의 official event identity/dedup 계약을 변경하지 않는다.
- C-4.1 저장 snapshot과 actual record만 정확도 평가에 사용하고 과거 예측을 현재 source/holdings로 재생성하지 않는다.
- C-5 `portfolio_after_tax`를 알려진 세금 후 현금의 canonical tax-attribution 계층으로 재사용한다.
- 포트폴리오 gross total은 계속 `summary.total_annual_dividend_krw`가 authoritative하며 residual을 종목/계좌에 임의 귀속하지 않는다.
- 계좌별 배당 기여는 현재 보유수량 비례 자산관리 추정이며 record-date entitlement 확정이 아니다.
- 금융소득 알림은 B-1의 **개인별** threshold 결과만 재사용하고 가족 합계에는 법정 threshold를 적용하지 않는다.
- 알림은 기본 OFF이며 사용자가 명시적으로 켠 경우에만 daily close와 연결한다.
- 새 세율, 새로운 threshold 숫자, fuzzy dividend matching 규칙을 추가하지 않는다.

### Phase 10.5E — Dividend Intelligence 디자인 / 고배당기업 공식 자격

상태: **완료** — PR #51 merge (`3d23a504`), GHCR #120, 운영 배포 및 browser smoke 확인.

완료 내용:

- 배당 source/evidence 정보를 compact chip + 상세 펼쳐보기 구조로 단순화
- 알려진 세금 후 예상 현금, 알려진 세금, 세후 수익률, 계산 coverage를 우선 KPI로 재배치
- 국내 배당주의 고배당기업 여부는 회사의 최신 공식 `기업가치 제고 계획` 공시에 기재된 `해당 / 미해당` 값만 구조적으로 확인
- 공식 공시 부재는 `not_confirmed`, credential/network/upstream 실패는 `source_unavailable`로 fail-closed 처리
- 공식 자격을 확인해도 기존 10.5A-4 분리과세 규칙은 자동 적용하지 않음
- browser smoke에서 국내 대상 14종목은 `공식 해당 0 / 공식 미해당 0 / 확인 대기 14 / 조회 불가 0`, ETF·해외자산은 `대상 아님` 확인

검증:

- exact validated head: `adaeb2317e7fe1e50433fcb2e582aed403a26037`
- full unittest: `Ran 2395 tests in 130.581s` / `OK`
- `python -m py_compile`, `node --check`, `git diff --check`, clean status 통과
- merge SHA: `3d23a50425f3321942713192557bc546a8397b58`

### Phase 10.5F — Dividend detail UX polish + USD amount helper

상태: **완료** — PR #52 merge (`ed10883728a97fca71baa29ad8c28f41cb4b4298`), GHCR #135, 운영 배포 및 browser smoke 확인.

완료 내용:

- Dividend Intelligence 종목 상세의 내부 상태 `calculated`를 `계산 완료` 등 사용자 문구로 표시
- 고배당기업 `대상 아님`인 ETF·해외자산에서 불필요한 고배당기업 공식 근거 링크 제거
- 기존 `type=number` / raw value / payload 계약을 유지하면서 `cash_usd`에 `$12,345.67` 형태 보조표시 제공
- 원화 환산은 이미 dashboard가 받은 `data.fx_rates.USD`를 재사용하고 환율 상수를 하드코딩하지 않음
- 현재 환율이 없으면 추정하지 않고 `원화 환산 대기`로 fail-closed
- 기존 KRW 금액 helper와 저장/API 계약 유지

### Phase 10.5G — 배당 현금흐름 목표/의사결정

현재 increment: **선택 연도 12개월 알려진 세금 후 현금흐름 + 사용자 월배당 목표 비교**.

목표:

- 기존 `monthly_schedule`의 월별 gross forecast를 그대로 재사용
- 기존 종목별 `after_known_tax_cash_krw`를 각 종목의 월별 gross 비중으로 배분해 월별 알려진 세금 후 예상 현금 계산
- 월평균 예상 수령, 최대/최소 월, 최대월 편중, 상위 예상수령 기여 종목 표시
- owner별 사용자 월배당 목표를 browser localStorage에만 보관하고 12개월 충족 수와 연간 부족/초과 표시
- 기존 세후 계산 complete + residual 0 + 월별 attribution 100% + 연간 reconciliation 일치 조건에서만 목표 판단 확정
- 불완전하면 `목표 비교 보류`로 fail-closed
- 새 세율, 새 threshold, 새 지급월 추론, residual 임의 배분 없음

C-7 가족별 배당 분산 보기 단순화는 기존 Family Financial Income Risk / Family Allocation Simulation과 기능 중복이 커서 **추후 진행 후보**로 계속 보류한다.

## 2. 다음 단계

Phase 10.5G는 exact-head 로컬 검증을 완료했으며 PR #53 final review → Ready → exact-head merge → GHCR → 운영/browser smoke 순서로 마감한다.

추후 후보:

- **예측 정확도 고도화** — point-in-time snapshot과 actual 비교 데이터가 충분히 누적된 뒤 source별 accuracy/편향을 의사결정에 연결
- **고배당기업 공식 자격 상태 변경 알림** — 실제 공식 상태 변화 데이터가 쌓인 뒤 기존 opt-in alert/dedup 계약 재사용 여부 검토
- **C-7 가족별 배당 분산 보기 단순화** — 기존 두 family 패널을 단순 통합할 필요성이 다시 커질 때 진행

종합소득세 신고서 완성을 위한 다음 항목들은 **현재 제품 우선순위에서 보류**한다.

- 토지등 매매차익 예정신고세액
- 수시부과세액
- 가산세·추가납부세액
- 국세/지방세 최종 납부·환급액 완성
- 외국납부세액공제 연도별 이월 구조 완성

필요성이 명확해질 때만 별도 세무 phase로 재개한다.

## 3. 금융소득/가족 세금 확장

### Phase 10.5B-1 — 가족 금융소득 위험 보기

상태: 완료 — PR #26 (`a8883c2`).

핵심 원칙:

- 본인/배우자/자녀 등 등록 소유자별 예상 금융소득
- 1,000만원 watch / 2,000만원 screening 상태는 개인별 판정
- 가족 전체 합계는 참고값으로만 제공
- 미분류 데이터는 임의 배분하지 않음

### Phase 10.5B-2 — 추가 배당/매매 What-if 확장

상태: 완료 — PR #27 merge (`404059a`).

- 추가 배당금
- 추가 이자
- 추가 해외주식 실현차익
- 국내상장 해외 ETF 과세기준금액
- 개인 vs 가족법인 비교와 연결

### Phase 10.5B-3 — 배우자/자녀 분산 시뮬레이션

상태: 완료 — PR #28 merge (`6d71cc2`).

- 자산 또는 미래 투자금 배분 시 개인별 금융소득 변화
- 단순 세금 절감 추천이 아니라 결과 비교 중심
- 증여세/명의신탁/실질귀속 등 법적 쟁점은 계산 범위에서 별도 표시
- 실제 증여세 계산은 별도 규칙 엔진 없이는 자동 확정하지 않음

### Phase 10.5B-4 — 개인 종합과세 정밀화

상태:

- first increment 완료 — PR #29 merge (`2a98442`)
- B-4.1 비교산출세액 완료 — PR #30 merge (`c65afa9`)
- B-4.2 배당세액공제 완료 — PR #31 merge (`90867ae`)
- B-4.3 금융소득 기납부 원천징수세액 완료 — PR #32 merge (`4281a31`)
- B-4.4 개인지방소득세 비교산출세액 완료 — PR #33 merge (`9cd0d83`)
- B-4.4.1 개인지방소득세 배당세액공제 완료 — PR #34 merge (`78499b09`)
- B-4.4.2 금융소득 지방 특별징수 기납부세액 완료 — PR #35 merge (`22c40a9b`)
- B-4.5 국세 외국납부세액공제 완료 — PR #36 merge (`28607378`)
- B-4.6 개인지방소득세 외국납부세액공제 완료 — PR #37 merge (`e6232566`)
- B-4.7 국세 중간예납세액 반영 완료 — PR #38 merge (`91407565`)
- B-4.8 다른 종합소득 원천징수·납세조합 징수 기납부세액 완료 — PR #39 merge (`ee893fc9`)
- B-4.9 납세조합공제 선행 세액공제 완료 — PR #40 merge (`7d97cd4a`)

후속 세무신고 확장은 현재 보류한다.

원칙:

- 세법 연도별 rule module 분리
- UI에 세율 상수 하드코딩 금지
- 공식 자료 검증일 기록
- 법률/세무 최종 판단과 screening을 구분
- 출자공동사업자 배당소득의 Article 62/지방세법 제93조 특수 비교는 별도 구현 전까지 fail-closed
- 기납부 금융소득 원천징수세액은 실제 국세 소득세만 명시 입력하며 지방소득세를 섞지 않음
- 지방소득세는 납세지 조례를 확인하지 않은 상태에서 표준세율의 가감 여부를 자동 추정하지 않음
- 지방 배당세액공제는 기존 명시적 Gross-Up 적격 분류로 계산된 배당가산액을 기준으로 하며 자동 적격 추론을 추가하지 않음
- 금융소득 지방 특별징수 기납부세액은 실제 개인지방소득세 특별징수액만 명시 입력하며 국세 기납부세액이나 gross 금융소득에서 자동 추정하지 않음
- 국세 외국납부세액공제의 국가별 기준 국외원천소득과 조세조약상 공제대상 외국세액은 명시 입력으로 받으며 gross 해외배당에서 자동 추정하지 않음
- 전기 이월액·이월배제액·10년 이월공제는 공식 서식의 연도별 구조를 구현하기 전까지 현재 미공제액과 동일시하지 않음
- 지방 외국납부세액공제는 실제 국세 외국납부세액공제액의 10%만 연동하고 gross 해외배당이나 외국 원천징수액에서 독립 추정하지 않음
- 지방 외국납부세액공제 5년 이월 구조는 공식 연도별 계약을 구현하기 전까지 현재 미공제액과 동일시하지 않음
- 중간예납세액은 전년도 세액에서 자동 추정하지 않고 실제 확정신고에 반영되는 확인된 기납부액만 명시 입력
- 다른 종합소득 원천징수세액과 납세조합 징수세액은 gross 소득에서 자동 추정하지 않고 실제 확인된 기납부액만 명시 입력
- 납세조합공제는 납세조합영수증/신고서의 실제 공제액만 명시 입력하며 법정 3%를 제품이 자동 계산하지 않음
- 납세조합공제는 외국납부세액공제보다 앞선 제60조 선행 세액공제로 처리하고, 납세조합 징수세액은 제76조 후속 기납부세액 단계로 분리

## 4. Phase 10.5C 제품 원칙

- 기본 화면의 목적은 **배당을 얼마나 더 받을지 / 금융소득 2천만원까지 얼마나 남았는지 / 원천징수 후 현금이 얼마인지**를 빠르게 판단하는 것이다.
- `세후`는 반드시 계산 범위를 함께 표기한다. 최종 종합소득세가 미계산이면 `원천징수 후` 또는 `알려진 세금 후`로 표시한다.
- 사용자가 배당 유형을 명시하지 않으면 일반 국내 15.4% 등을 임의 적용하지 않는다.
- 국내 배당, 국내상장 해외 ETF, 미국직투의 원천징수 구조는 기존 verified backend를 재사용한다.
- 투자금액이 없으면 배당수익률을 임의 계산하지 않는다.
- 2천만원 threshold는 서버 계산 결과를 사용하고 UI에 별도 threshold 숫자를 계산식으로 하드코딩하지 않는다.
- What-if 상태는 `safe / approach / reached / exceeded`를 구분하며 정확히 기준에 도달한 상태를 안전 상태로 표시하지 않는다.
- 가족법인 비교, 고배당 특례, 상세 세무 입력은 고급 영역으로 유지한다.

## 5. 후속 세무·사회보험 영역

### 건강보험 영향

- 직장가입자/지역가입자 구분이 필요하므로 별도 모델링
- 단순 금융소득 2,000만원 기준과 동일시하지 않음
- 연도별 보험료 기준 검증 필요
- 현재 배당 대시보드에서는 자동 계산하지 않음

### 인적공제/부양가족 영향

- 소득요건과 금융소득 과세 방식의 관계를 별도 rule로 모델링
- 배우자/자녀 분산 기능과 연결 가능

### 법인 자금 인출 확장

현재 가족법인 비교는 법인 유보 및 배당 인출 중심이다.
후보:

- 급여
- 상여
- 퇴직금
- 대여금/가지급금 위험

법률·세무 복잡도가 높으므로 현재 기본 UX 우선순위에서는 제외한다.

## 6. 알림/자동화

Phase 10.5D 완료:

- 예상 금융소득 1,000만원 watch 알림
- 개인별 2,000만원 도달/초과 알림
- 공식 배당/ETF 분배금 event identity 신규 확인 알림
- 배당결정 공시 존재 알림
- 사용자 명시 opt-in 및 deterministic event-key 중복 방지

후보:

- 고배당기업 공식 자격 상태 변경 알림

원칙:

- 사용자가 명시적으로 켠 경우에만 알림
- 중복 알림 방지
- 공시 존재와 확정금액을 구분
- 가족 합계에는 금융소득 법정 threshold를 적용하지 않음
- 알림 실패는 daily-close snapshot 저장을 실패시키지 않음

## 7. UX 개선 backlog

완료:

- KRW 금액 입력 보조표시 `5,000,000원 · 5백만 원`
- 배당 세금 대시보드 C-1
- 포트폴리오 알려진 세금 후 배당수익률 C-5
- 2천만원 접근 What-if 상태 구분 C-6
- 종목/계좌별 알려진 세금 후 배당 기여도
- 배당 예상 confidence/source 근거 수준 구분
- 공식 공시 원문 바로가기
- 계산 근거 펼쳐보기
- point-in-time forecast 정확도/데이터 누적 상태 표시
- Dividend Intelligence KPI/근거 정보 계층 단순화 — 10.5E
- 고배당기업 공식 자격 chip 및 portfolio 요약 — 10.5E
- USD 예수금 입력 `$` 천 단위 + 현재 FX 기반 원화 보조표시 — 10.5F
- 종목 상세 계산 상태 한글화 / `대상 아님` 공식링크 정리 — 10.5F

Phase 10.5G 진행:

- 12개월 알려진 세금 후 배당 현금흐름
- 월평균 / 최대·최소월 / 최대월 편중
- 상위 예상 수령 기여 종목
- owner별 월배당 목표와 충족 월/연간 부족·초과
- attribution 불완전 시 목표 비교 fail-closed

후보:

- C-7 가족별 배당 분산 보기 단순화 (추후 진행)
- snapshot 누적 후 예측 정확도 의사결정 UX 고도화

## 8. 장기 구조 개선 후보

### stable user id 기반 저장 경로

현재 user data path는 `data/users/<username>/...`이다.
향후 stable UUID id 기반으로 바꾸려면 다음을 반드시 별도 migration으로 처리한다.

- 기존 디렉터리 rename/move
- rollback 전략
- 중복/누락 검증
- 각 서비스의 username/path 의존성 제거
- 백업 후 migration

현재 단계에서는 경로를 임의 변경하지 않는다.

### 세법 rule source metadata

모든 세법 모듈에 다음 정보를 일관되게 보관하는 방향을 유지한다.

- rule year
- verified date
- official source URL
- 계산 범위
- not calculated 목록
- screening/legal determination 구분

## 9. 우선순위 변경 규칙

우선순위를 바꿀 때는:

1. `PROJECT_STATE.md` 현재 단계 수정
2. 이 문서 순서 수정
3. 관련 PR/Issue에 이유 기록
4. 이미 구현된 API 계약을 깨뜨리는 경우 migration/compatibility plan 기록

실제 secret, 계좌번호, 토큰, 개인 금융 데이터는 roadmap에 기록하지 않는다.
