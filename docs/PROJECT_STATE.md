# Wealth Project State

> 이 문서는 Wealth 프로젝트의 **현재 상태를 복구하기 위한 첫 진입점**입니다.
> 새 대화, 새 작업 세션, 새 개발자가 시작할 때 가장 먼저 이 문서를 읽습니다.
> 세부 계획은 `docs/ROADMAP.md`, 비밀값·환경설정 원칙은 `docs/SECURITY_AND_CONFIG.md`를 참조합니다.

마지막 갱신: 2026-09-26

## 1. 현재 개발 상태

현재 작업 단계는 **Phase 10.5B-3 — 배우자/자녀 분산 시뮬레이션**입니다.

현재 작업:

- branch: `phase10-5b3-family-allocation-simulation`
- base: `main`
- 상태: 구현/검증 중
- 작업 시작 기준 main: `404059a` (PR #27 merge)

B-3 목표:

1. 등록된 가족 구성원 사이에서 아직 발생하지 않은 미래 금융소득을 가상 배분하고 개인별 screening 전/후를 비교한다.
2. 이미 발생한 YTD 배당·이자 소득은 이동시키지 않고 projection의 미래 미실현 component만 배분 가능액으로 사용한다.
3. source의 미래 배분 가능액을 초과하거나 source forecast가 확인 불가인 배분은 fail-closed로 거부한다.
4. 가족 합계는 reference-only이며 B-1의 미분류/소유자 충돌 및 reference completeness 상태를 그대로 계승한다.
5. 실제 portfolio, holding owner, 배당 기록, 가족 설정을 변경하지 않고 모든 시나리오는 stateless로 처리한다.
6. 증여세·명의신탁·실질귀속·소득 귀속은 계산하거나 자동 판정하지 않는다.

## 2. Phase 10.5 완료/진행 현황

- [x] 10.5A-1 금융소득 projection 기반
- [x] 10.5A-2 stateless 금융소득 simulation API
- [x] 10.5A-2.5 개인 vs 가족법인 투자 세금 비교 엔진
- [x] 10.5A-3 금융소득 What-if / 퀵 시뮬레이터
- [x] 10.5A-3.1 공통 KRW 금액 입력 UX 정비
- [x] 10.5A-4 2026 고배당기업 배당소득 분리과세 규칙 엔진
- [x] 10.5A-4.1 공식 공시 기반 배당예상 Source 계층 — PR #22 merge (`19b0af2`)
- [x] 10.5A-4.2 고배당 분리과세 What-if 연결 — PR #23 merge (`0f5f25a`)
- [x] 10.5A-4.3 미래 배당 확정공시 구조화 — PR #24 merge (`86a07ea`)
- [x] 10.5A-4.4 국내 ETF 분배금 공식 Source 개선 — PR #25 merge (`39ca928`)
- [x] 10.5B-1 가족 금융소득 위험 보기 — PR #26 merge (`a8883c2`)
- [x] 10.5B-2 추가 배당/매매 What-if 확장 — PR #27 merge (`404059a`)
- [ ] 10.5B-3 배우자/자녀 분산 시뮬레이션 — 진행 중
- 다음 단계: 10.5B-4 개인 종합과세 정밀화

세부 후속 순서는 `docs/ROADMAP.md`를 따른다.

## 3. 현재 금융소득/세금 제품 원칙

### 금융소득 projection

- 실제 YTD 배당/이자 + 미래 예상 배당 + 사용자가 입력한 예상 이자를 결합한다.
- 제품 주의 기준은 1,000만원이다.
- 법정 금융소득 종합과세 screening 기준은 2,000만원이다.
- 계산 결과는 screening 목적이며 최종 세법 판단으로 표시하지 않는다.
- 현재 월 자동 예상은 실제 수령 기록과 중복될 수 있어 기본적으로 제외한다.

### 가족 금융소득 위험 보기

- 법정 금융소득 종합과세 기준은 개인별 기준으로만 평가한다.
- 가족 합계는 자산배분 참고용이며 법정 threshold 판정값이 아니다.
- 가족 구성원은 `settings.family_members` 순서를 따른다.
- `모두`/미등록 소유자의 데이터는 구성원에게 임의 배분하지 않는다.
- 자동 미래 이자 forecast는 아직 없으며 B-1은 기존 projection 기본값(추가 이자 0원)을 사용한다.

### 배우자/자녀 분산 시뮬레이션

- 등록된 `settings.family_members` 사이의 미래 금융소득 가상 배분만 request 단위로 비교한다.
- 배분 가능액은 미래 월 예상 배당, 명시적 현재월 잔여 배당 조정, 예상 잔여 이자 등 아직 발생하지 않은 gross component만 사용한다.
- 이미 발생한 YTD 금융소득의 귀속은 변경하지 않는다.
- 실제 portfolio, holding owner, 배당 기록, 가족 설정을 변경하거나 scenario를 저장하지 않는다.
- source의 미래 배분 가능액을 초과하는 금액과 미확정 source forecast 배분은 fail-closed로 거부한다.
- B-1에서 미분류/소유자 충돌 등으로 가족 reference가 불완전하면 B-3도 완전한 가족 합계로 승격하지 않는다.
- 가족 합계는 보존 확인용 참고값이며 법정 threshold를 적용하지 않는다.
- 이 결과는 미래 금융소득 배분 가정에 따른 screening 비교이며, 실제 증여·명의·소득 귀속의 법률/세무 판단을 포함하지 않는다.

### 개인 vs 가족법인 비교

지원 범위:

- 국내 배당주
- 국내상장 미국 ETF
- 미국주식/미국 ETF 직접투자
- 배당/분배금
- 실현차익
- 법인세/지방소득세 screening
- 국내 수입배당금 익금불산입 조건
- 외국자회사 배당 익금불산입 조건
- 외국납부세액공제 screening
- 법인 유보 vs 법인→개인 배당 인출

아직 최종 법률·세무 판단으로 계산하지 않는 항목:

- 개인 종합소득 최종 누진세액
- 건강보험료 영향
- 인적공제 영향
- 급여/상여/퇴직금 형태의 법인 자금 인출
- 증여/상속세
- 복잡한 외국납부세액공제 한도 및 지방세 세부 계산

### 2026 고배당기업 분리과세

- A-4에 규칙 엔진이 존재한다.
- A-4.2에서 금융소득 What-if와 연결됐다.
- 자동 적격 판정을 배당수익률 등으로 임의 추정하지 않는다.
- 고배당기업 여부는 공식 자료 확인이 전제된다.
- 실제 적용은 신고 시 신청이 필요한 제도라는 전제를 유지한다.
- 고배당기업 공식 자격의 자동 확인은 배당금 확정공시 구조화와 별개의 source 문제로 취급한다.

## 4. 현재 배당예상 데이터 원칙

기존 배당 예상은 다음 순서를 기본으로 한다.

### 국내

기존 숫자 추정:

1. Naver 금융 데이터
2. Naver 정보가 없을 때 기존 휴리스틱

A-4.1 공식자료 보강:

1. OpenDART 정기보고서의 공식 과거 DPS는 공식 이력으로 보관
2. 기존 Naver DPS가 0/누락일 때만 공식 과거 DPS로 fill
3. 최근 배당결정 공시 존재 여부를 별도로 기록
4. 공시 제목만으로 미래 확정금액을 만들지 않는다

A-4.3 확정공시 구조화:

1. 최근 배당결정 공시의 접수번호로 OpenDART `document.xml` 원문 ZIP을 조회한다.
2. 원문에서 보통주 1주당 현금배당금이 구조적으로 검증된 경우에만 `confirmed_amount=true`로 처리한다.
3. 배당기준일과 지급예정일은 공시에 명시된 값만 보관하며, 미기재 날짜를 추정하지 않는다.
4. 지급예정일이 현재 연도 미래 날짜이고 기존 예상월과 안전하게 매칭되면 해당 월 금액을 확정 공시값으로 교체한다.
5. 기존 예상이 0인 경우에는 확정 주당배당금과 지급월이 확인되면 해당 확정 이벤트를 새 예상으로 반영할 수 있다.
6. 기존 예상이 존재하지만 지급월이 매칭되지 않으면 중복계상을 피하기 위해 자동 금액 override를 하지 않는다.
7. 원문 다운로드/파싱 실패는 기존 예상 전체 실패로 전파하지 않는다.

A-4.4 KIND ETF 분배금 보강:

1. 기존 Naver integration이 ETF로 확인한 종목만 KIND ETF source 대상이 된다.
2. KIND ETF 검색은 별도 API credential 없이 공개 공시 화면을 사용한다.
3. 검색 결과 제목만으로 확정하지 않고 viewer의 공식 `/external/` 문서에서 대상 ISIN 행을 구조 검증한다.
4. 공식 기준일 월에 기존 휴리스틱 항목이 있으면 그 항목을 제거하고 실제 지급예정월에 공식 분배금으로 이동한다.
5. 기존 양수 forecast에 안전하게 매칭되는 월이 없으면 공식 이벤트는 증거로만 남기고 숫자에는 자동 반영하지 않는다.
6. 공식 Source 장애는 기존 Naver/OpenDART/Yahoo forecast를 실패시키지 않는다.

### 미국

- Yahoo Finance 최근 배당 이력을 계속 사용한다.

### 중요

공식 과거 이력과 미래 확정 배당은 같은 의미가 아니다.
`공시가 존재한다`와 `미래 지급액을 구조적으로 검증했다`도 반드시 구분한다.
`confirmed_amount=true`와 `confirmed_numeric_override=true`도 구분한다. 전자는 공시 금액 구조 검증, 후자는 안전한 월별 예상 교체까지 완료됐음을 의미한다.

## 5. 사용자별 DART 인증 계약

DART 인증정보는 A-4.1 전용 새 환경변수를 만들지 않는다.
기존 사용자 OpenAPI 설정을 재사용한다.

현재 저장 계약:

```text
data/users/<username>/openapi_config.json
└─ dart.api_key
```

compose 기본 마운트:

```text
host:      ./data
container: /app/data
```

따라서 `/docker/wealth`에서 compose를 실행하는 기본 운영 구조라면 대략 다음과 같다.

```text
host:      /docker/wealth/data/users/<username>/openapi_config.json
container: /app/data/users/<username>/openapi_config.json
```

주의:

- 현재 디렉터리 키는 stable UUID user id가 아니라 **username**이다.
- 코드 변경 없이 `<username>`을 UUID로 바꾸지 않는다.
- stable ID 경로로 마이그레이션하려면 별도 명시적 migration 설계가 필요하다.

DART 해석 우선순위:

1. 사용자별 `dart.api_key`
2. 기존 호환용 `DART_API_KEY`
3. 미설정

A-4.1에서 `WEALTH_OPENDART_API_KEY` 같은 별도 전역 키 계약은 사용하지 않는다.

## 6. 배포 표준

운영 서버는 GHCR 이미지를 사용한다.
표준 배포 명령은 다음 compose 조합이다.

```bash
cd /docker/wealth

docker compose \
  -f docker-compose.ghcr.yml \
  -f docker-compose.override.yml \
  pull dashboard

docker compose \
  -f docker-compose.ghcr.yml \
  -f docker-compose.override.yml \
  up -d --force-recreate dashboard

docker compose \
  -f docker-compose.ghcr.yml \
  -f docker-compose.override.yml \
  ps
```

기본 `docker-compose.yml`은 `build: .` 중심이므로 GHCR 배포 절차와 동일하게 취급하지 않는다.

## 7. 개발/검증 관례

기능 변경 시 기본 순서:

1. 새 branch
2. targeted tests
3. 관련 regression tests
4. full unittest suite
5. `git diff --check`
6. `git status --short -- app tests` 또는 변경 범위에 맞는 status 확인
7. Draft PR
8. 사용자 로컬 전체 테스트 확인
9. 사용자 승인 후 Ready → merge
10. GHCR build 확인
11. 서버 배포

merge는 사용자 명시적 승인 없이 진행하지 않는다.

## 8. 문서 유지 규칙

다음 상황에서는 이 문서를 반드시 갱신한다.

- Phase 완료/시작
- 주요 PR merge
- 데이터 저장 위치 변경
- secret 해석 우선순위 변경
- 배포 방식 변경
- 세금 계산 범위/법적 의미 변경
- 중요한 설계 결정 변경

업데이트 시 실제 secret, 계좌번호, 토큰, 사용자 개인 금융정보는 절대 기록하지 않는다.