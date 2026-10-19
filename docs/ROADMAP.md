# Wealth Roadmap

## IPO·통합 캘린더 UI 보완 — 구현·검증 기록 / 운영 미배포

운영 기준 main `a17ef0681f95a2d874257b796eb25ac9f7840e22`의 PR #156 기능을 유지하면서 안내·출처·기본 링크 스타일 누락과 추가 버튼의 카드 헤더 정렬을 보완한다. 다크 테마 토큰·청약/상장/수익/손실/배당/수입/지출의 기존 색상 의미를 유지한다. 기업명·배지·출처·동작을 분리하고 긴 텍스트와 모바일 월 선택·가족 체크박스의 줄바꿈을 정리한다. 제외·복원·재수집·신청·배정·손익 연결·시장 원본·IPO ID·데이터 판정 로직은 변경하지 않는다.

앱 버전 **2.1.2**, core revision 유지. 수정한 layout CSS·IPO/캘린더 JS와 SW 캐시만 **2.1.2-ipo-ui1**. 별도 `codex/ipo-calendar-ui-polish`에서 작업하며 P0 원본 27개와 기존 worktree를 보존한다. 로컬 관련 회귀 **239 PASS / 1 의존성 경고**, 실제 Chromium **13건** 포함(신규 UI 320·390·768·1280px 4건). 기존 IPO 224건을 유지하고 초기 표시·증권사/과거 필터·공통 레이아웃 검증을 확대했다. 안내/복원 16px·기본 링크색에서 보조정보 10.5~11px·테마색으로 바뀐 합성 화면을 비교했으며 UI 콘솔 오류와 가로 넘침은 없었다. Python/JS·YAML 문법 및 diff 검사 PASS. 전체 pytest·Oracle 운영 확인은 미실행이다. 최신 CI 통과 후 승인 범위에서 Squash Merge하며 미완료 결과를 PASS로 기록하지 않는다. Oracle에는 접속하지 않고 `/docker/wealth`의 기존 Compose와 고정 이미지 파일을 사용하는 배포 명령만 제공한다. 롤백 태그 자동 생성·백업 이미지 저장은 하지 않으며 영구 데이터·Toss 마운트는 유지한다.

## PR #156 구현·검증 당시 기록 — 현재 머지·배포는 사용자 확인 기준

2026-10-19 사용자 운영 정책을 적용한다. Wealth IPO는 편리한 일정 참고·개인 신청 관리 도구다. 목록과 통합 캘린더에서 사용자별 일정을 제외하고, 공모주 **제외 목록 / 다시 표시**에서 복원한다. 제외는 원본 market JSON·IPO ID·가족별 신청·배정·연결을 수정하거나 삭제하지 않는다. 동일 ID·검증된 기업 코드·메타로고스 종목 키로 재수집된 일정은 제외를 유지한다. 날짜가 바뀌면 제외 목록에서 변경 안내를 보고 사용자가 복원한다. 새 날짜를 이유로 자동 재등장시키지 않는다. 제외 목록은 월·진행 상태 필터에 갇히지 않는다.

메타로고스 공개 캘린더는 월별 청약·상장 일정을 제공한다. 우선 활용을 검토했으나 이용 조건·제공 범위의 충분한 확인이 없어 기존 안정적인 수집 경로와 출처 우선순위를 유지한다. 새 외부 수집 경로를 추가하지 않는다. 출처·조회일과 참고용 안내를 표시하며 최신 공시 자동 판정을 완벽하게 보장하지 않는다. 자정 만료·이름 유사도 경고와 접수번호만으로 묶는 처리는 제거했다. 같은 제공자 종목 키 또는 기업 코드와 같은 공모 근거가 일치할 때만 화면에서 묶고 원본 ID별 신청을 보존한다. 운영 엘리스 레코드의 실제 동일성은 미확인이다.

앱 버전 **2.1.2**, core revision 유지. 실제 수정된 IPO·캘린더 JS 및 SW 캐시는 **2.1.2-ipo3**. 원본 v2.1.3 P0는 별도 보존한다. 로컬 관련 회귀 **224 PASS / 1 의존성 경고**(실제 Chromium 목록·캘린더 3건 포함), Python/JS 문법·diff 검사 PASS. 전체 pytest·운영 검증은 미실행이다. 최신 PR CI 통과 후 승인 범위에서 Squash Merge한다. Oracle 직접 접속·배포는 하지 않으며 고정 이미지 배포 명령만 제공한다. 롤백 태그 자동 생성·별도 백업 이미지 저장은 하지 않는다. 기존 이미지·영구 데이터 마운트는 보존한다.

## PR #155 개발 당시 계획 — 현재 머지·배포는 사용자 확인 기준

정정요구·철회·새 일정 복원, 조회 실패 시 확인 필요 표시, 회사·접수번호 범위 및 사용자 신청 체크 보존을 합성 데이터로 검증한다. 운영 v2.1.2는 유지한다. PR 이후에도 전체 회귀·최신 공식 공시 확인·운영 사용자 화면 확인은 별도 단계이며 머지·배포는 사용자 승인 전 실행하지 않는다.

로컬 관련 회귀 142건 통과 후 확대 IPO CI를 새 HEAD에 적용한다. Draft 해제·머지·배포는 하지 않으며 CI 통과와 실제 공시 최신성 확인은 별도 조건이다.

> 현재 작업 상태는 `docs/PROJECT_STATE.md`를 먼저 읽습니다.
> 이 문서는 앞으로 진행할 기능의 우선순위와 완료 기준을 기록합니다.

마지막 갱신: 2026-10-18 (운영 v2.1.2 배포 완료 / 실제 사용자 브라우저 검증 대기)

## v2.1.2 — 금융소득 기준 포함액 (운영 배포 완료)

사용자 제공 완료 기록: [PR #153](https://github.com/sagesaint84/wealth/pull/153) Squash Merge, main `255d135b8562b5569a11ac7c213787dccbcc2513`, 기능 커밋 `71e5c254f01a57336d31a7b2f634088dfce5ab23`. 전체 pytest **4,353 passed / 2 skipped / 4 warnings / 888 subtests passed**, 집중 테스트 **191 passed / 30 subtests passed**, 기존 Chromium 회귀 **35 passed**. AMD64/ARM64 PR CI SUCCESS ([실행 39103493324](https://github.com/sagesaint84/wealth/actions/runs/39103493324)), GHCR 빌드 SUCCESS ([실행 39103784893](https://github.com/sagesaint84/wealth/actions/runs/39103784893)).

운영 이미지 `ghcr.io/sagesaint84/wealth:255d135`, Manifest Digest `sha256:837709730d1b0d80abf7360b13d71e3c7261d793923befaab2238753429ad7eb`. Oracle ARM64: `V212_PRE_DEPLOY_GATE=PASS`, `V212_IMAGE_GATE=PASS`, `DATA_MOUNTS=PASS`, `V212_COMPOSE_GATE=PASS`, `VERSION_212=PASS`, 최종 HTTP 307, 컨테이너 running / RESTARTS=0, **`ORACLE_V212_DEPLOY=PASS`**. v2.1.1 롤백 이미지 `rollback-before-v212`와 이전 운영 Compose 백업 `docker-compose.release.before-v212.yml`은 보존됐다.

실제 배당 기록에 고배당 분리과세 적용 및 선택형 대상 금액을 추가한다. 공식 자격과 사용자 선택·신청 가정을 분리하며 기존 capital_dividend_mode 호환성을 유지한다. 기존 세전 역산·기록 환율·2026 What-if 계산을 재사용해 전체 세전 금융소득, 감액배당 제외, 고배당 분리과세 제외, 기준 포함액과 여유 금액을 표시한다. 감액배당과 고배당은 중복 차감하지 않으며 현금 하한은 제외 전 총액에만 적용한다. 개인별 2천만원 기준은 정확히 같은 금액까지 기준 이내이고 가족 합계에는 적용하지 않는다. 실제 입금·세전·원천징수 원본 및 기존 배당 카드는 변경하지 않고 과거 기록을 일괄 변환하지 않는다.

**실제 사용자 브라우저 검증 대기:** v2.1.2 세금 유형·금융소득 화면의 최종 사용자 확인은 아직 보고되지 않았다. 운영 배포 성공과 화면 사용자 검증 완료는 구분한다. 위 테스트·CI·배포 결과는 사용자 제공 이력이며 이번 문서 작업에서 테스트 실행이나 Oracle 서버 재확인은 하지 않았다.

금융소득 특례 계산은 기존 2026년/KRW 범위를 유지하고 USD 일반 배당은 저장 환율과 기존 역산을 재사용한다. 공식 공시 조회의 기존 범위·정정 계보 한계는 유지하며 사용자 선택을 공식 자격으로 승격하지 않는다.

## v2.1.1 — 배당 및 차트 UX 운영 완료

사용자 제공 운영 검증: v2.1.1 PR #152 Squash Merge, main `251d51ea4112a117f6748d5c7c73c03a4b274280`. 전체 pytest 4327 PASS / 2 SKIP, Chromium 35 PASS, AMD64/ARM64 PR CI SUCCESS. GHCR 실행 `39085363475` SUCCESS, 이미지 `ghcr.io/sagesaint84/wealth@sha256:000ba9c6b47c09d50899695fd8a51619f1eab0a25e24c8dd46b5019077e3cdba`. Oracle ARM64 IMAGE_GATE/DATA_MOUNTS/VERSION_211/ORACLE_DEPLOY=PASS, HTTP_STATUS=307, RESTARTS=0. 이번 작업에서 운영 서버를 재검증한 결과가 아니다.

## v2.1.1 개발 당시 기록 (아래 미배포·미실행은 당시 상태)

## v2.1.1 — 개인 자산관리 편의성 중심 UX (개발·미배포)

- 실제 배당 세금 유형 선택 보존·세전 자동 역산·선택형 세금 상세 및 월/연간 카드 분리 구현.
- 기존 통합 차트 공통 툴팁·최신 주식자산/순자산 금액 표시 구현. 별도 차트 라이브러리나 전문 세무 엔진은 만들지 않는다.
- 합성 테스트 작성 완료, 실행은 사용자 PowerShell 단계로 남긴다. 특히 순자산 소유자 전환·모바일 핀치/드래그·Y축·입금액 저장 불변 검증이 필요하다.
- 기준 main `7236dd39381ed0d2f16cf982b36055c8c43e3cc0`; 운영 v2.1.0 배포 완료(사용자 확인), 개발 v2.1.1 미커밋·미배포. 실제 서버 확인은 이번 작업에 포함하지 않는다.

## 과거 v2.1.0 개발 당시 계획 및 검증 기록

## v2.1.0 — 감액배당 공식 근거 (PR 미병합·운영 미배포)

- Phase A: 파서 안정화·로컬 검증 및 보호 커밋 `f290d9b211b166e49e320d38fa0a2bdd571bfad7` 완료.
- Phase B1: 기존 DART 원문을 재사용하는 보통주 구성금액·공식 출처의 읽기 전용 응답 연결.
  이벤트/정정 관계가 불명확하면 미확인을 유지하며 예상/실제 배당·세금·금융 저장·UI를 변경하지 않는다.
- B1 감사 보완: 두 파서의 실패 독립성·원문 1회 조회·API 오류/정상 부재 구분 및 기존 금융 fallback 유지.
  수정 후 격리 집중 **222 PASS / 0 FAIL / 0 SKIP**, subtests **72 PASS**.
  수정 전 B1 비-live 전체 재실행은 **4,278 PASS / 0 FAIL / 2 SKIP**, subtests **849 PASS**다.
  이전 실패 node ID·원인은 재현되지 않아 UNKNOWN이다. B1 읽기 전용 연결은 확정하며 수정 후 전체 pytest·
  전체 CI·실제 API·병합·배포는 미완료이며 운영 v2.0.3 검증과 구분한다.
- B2 개발 구현: 기존 공식 고배당기업 판정·2026 What-if·누진세를 재사용하는 이벤트별 예상 혜택 UI.
  AUTO/사용자 가정 적용/사용자 제외와 대상 금액 입력을 제공하며 공식 판정과 세션 선택은 별개다.
  고배당기업은 이벤트·연도·대상 금액 확인 범위만 자동 적용하고 감액배당 적용분을 중복 차감하지 않는다.
  현재 B1만으로 개인 감액배당 AUTO 비과세를 확정하지 않으며 수동 가정은 가능하다. 실제 기록은 불변이다.
  세션 선택 영구 보존·개인 적용 근거 수집·2026년 외 계산·전체 정정 계보는 후속 범위다.
  별도 세무 엔진은 만들지 않으며 상세 계산 범위·제약은 PROJECT_STATE.md를 따른다.
- B2 로컬 집중 검증 **242 PASS / 0 FAIL / 0 SKIP**(21개 모듈 214 + 기존/신규 Chromium 28).
  모바일·데스크톱, 사용자/소유자/연도·이벤트 분리, 입력 실패/늦은 응답과 기존 What-if 회귀를 검증했다.
  커밋 전 핵심 재검증은 별도 73 PASS / 0 FAIL / 0 SKIP이며 기본 세후 카드와 별도 미리보기임을 화면에 명시했다.
  전체 pytest·PR CI·실제 외부 API·병합·운영 배포는 미실행이다. PR CI가 다음 검증 단계다.
- v2.1.0 앱/HTML/SW·버전 테스트·4개 MD를 동기화하고 미변경 정적 revision은 유지한다.
  전체 pytest·CI·실제 외부 API·병합·배포는 아직 완료되지 않았다. 운영 v2.0.3 검증은 아래 과거 기록과 구분한다.

## 1. 완료된 제품 영역

v2.0.2 국민연금 PDF·사진 가져오기, 세금 탭 복원 및 모바일 부동산 UI 구현과 합성 검증은 완료됐다. Windows 전체 pytest 3,699 passed / 5 skipped / 0 failed / 5 warnings, 798 subtests passed 및 Python·JS 문법 PASS를 사용자에게 확인받았다. Actions run 38493482329 attempt #8의 native amd64/arm64 Docker·Chromium·OCR·document worker smoke도 성공했다.

당시 PR #144의 Draft·운영 미배포 상태는 과거 기록이다. PR #147은 CI·병합·Oracle 배포 완료된 이전 단계이며, Oracle 운영은 v2.0.3 / 코드 `b1e6e59d0f650db6023cdc7bf95c1b22d2f5694b`를 유지한다. PR #150 반영 main은 `a28d31995df3af71ed945b9fe61968064a1dd757`, 신규 개발은 위 v2.1.0 상태다. 실제 문서 양식별 정확성 및 운영 자원·이미지 크기 측정은 완료 항목에 포함하지 않는다. 최신 검증 상세와 필수 버전·MD 동기화 원칙은 `PROJECT_STATE.md`, 아래 phase 기록은 당시 완료 내역을 따른다.

### v2.0.3 — AccountInfo 반응형 미리보기

상태: **운영 완료**. [PR #149](https://github.com/sagesaint84/wealth/pull/149) Squash Merge, 운영 main `b1e6e59d0f650db6023cdc7bf95c1b22d2f5694b`. Native AMD64/ARM64 CI `38930119488`와 GHCR `38931035808` SUCCESS, 이미지 `ghcr.io/sagesaint84/wealth:b1e6e59`의 Oracle 배포 및 10분 안정성·마운트·이전 롤백 이미지 보존 확인 완료다. 개발 당시 로컬 집중 검증은 129 PASS / 실패·skip 0이다.

반응형 카드·단일 스크롤·잔액 전체 표시와 금융 데이터 보호 정책을 유지하며, 사용자 실제 화면 확인 6개 항목도 정상이다. 이는 신규 계좌 등록·전체 금융 API 실거래 검증 완료를 뜻하지 않는다. 개발 브랜치 `codex/v202-accountinfo-pdf-responsive-preview`와 UI 구현 커밋 `ebd66452e185ddbf3e0d2a7cc6d6a290790c6dc7`은 이전 구현 이력이다. 기존 향후 후보와 phase 완료 기록은 유지하며 새 기능 계획을 추가하지 않는다.

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

상태: **완료** — PR #53 merge (`076e81a`). 선택 연도 12개월 알려진 세금 후 현금흐름과 사용자 월배당 목표 비교.

목표:

- 기존 `monthly_schedule`의 월별 gross forecast를 그대로 재사용
- 기존 종목별 `after_known_tax_cash_krw`를 각 종목의 월별 gross 비중으로 배분해 월별 알려진 세금 후 예상 현금 계산
- 월평균 예상 수령, 최대/최소 월, 최대월 편중, 상위 예상수령 기여 종목 표시
- owner별 사용자 월배당 목표를 browser localStorage에만 보관하고 12개월 충족 수와 연간 부족/초과 표시
- 기존 세후 계산 complete + residual 0 + 월별 attribution 100% + 연간 reconciliation 일치 조건에서만 목표 판단 확정
- 불완전하면 `목표 비교 보류`로 fail-closed
- 새 세율, 새 threshold, 새 지급월 추론, residual 임의 배분 없음

### Phase 10.5H / 10.5I — 월별 attribution과 진단

상태: **완료** — 10.5H PR #54 merge (`3f3f141`), 10.5I PR #55 merge (`19a294d`). 월별 알려진 세금 후 배분과 불완전한 attribution의 진단·목표 UX를 보강했다. 계산 범위와 fail-closed 조건은 각 phase 문서에 보존한다.

### Phase 10.6A / 10.6B — 계좌 가져오기와 요약

상태: **완료** — AccountInfo PDF 가져오기 PR #56 merge (`8bb3dcb`), 증권·은행 계좌 섹션 요약 PR #60 merge (`e0573d1`). PDF 미리보기·중복/소유자 확인과 기존 계좌 데이터 기반 요약을 제공한다.

### 이후 main에 반영된 안정화 영역

- 금융소득·실현손익 기간/증권사 필터와 금융 시계열 표시 통합
- IPO 발견·과거자료·DART 추출·Wealth IPO Score의 source 검증 및 안정화
- Toss WTS 읽기 전용 실현손익 조회·선택 가져오기와 표시·미리보기 보강
- 로그인 후 초기 자산 데이터 표시 경로의 중복 작업 축소 — PR #89
- 절세계좌 보유종목 상세 복구와 IPO 캘린더 청약 색상 첫 페인트 수정 — PR #90

C-7 가족별 배당 분산 보기 단순화는 기존 Family Financial Income Risk / Family Allocation Simulation과 기능 중복이 커서 **추후 진행 후보**로 계속 보류한다.

## 2. 다음 단계

### 2026-10-07 시스템 audit 후속 backlog

현재 시스템 audit에서 확인된 안정화 작업은 다음 우선순위로 추적한다. P0 demo 사용자 격리는 완료되었고, 나머지는 기능 작업과 섞지 않고 별도 branch/PR로 진행한다.

| 우선순위 | 항목 | 상태 / 완료 기준 |
| --- | --- | --- |
| P0 | `/api/demo` 사용자 격리 | **완료** — PR #110 merge (`2031cc2`). 인증된 사용자에게만 demo portfolio를 기록하고 타 사용자 데이터 불변 regression을 유지한다. |
| P1 | 금융 JSON writer atomicity / concurrency 일관화 | 대기 — financial writer의 temp+replace/lock 정책을 통일하고 중단·동시쓰기·손상파일 fail-closed regression을 추가한다. |
| P1 | 초기 계정/비밀번호 및 username 경로 검증 | 대기 — fresh-install credential 정책과 username/path traversal boundary를 분리 점검하고 stable user id migration과 혼합하지 않는다. |
| P1 | CI test gate before Docker publish | 대기 — PR/main 테스트 성공을 image publish보다 앞선 required gate로 만든다. |
| P1 | `main` branch protection / required checks | 대기 — required checks 없이 main에 병합되지 않도록 repository rule을 정비한다. |
| P2 | 로그인 brute-force 방어 / 세션 강제 무효화 | 대기 |
| P2 | 보안 HTTP headers | 대기 |
| P2 | 업로드 파일 크기 제한 일관화 | 대기 |
| P2 | 의존성 고정 / Docker non-root | 대기 |
| P2 | `main.py`, `wealth.js` 대형 monolith 축소 | 장기 구조개선 |
| P2 | `PROJECT_STATE.md` / `ROADMAP.md` 최신화 | 진행 중 — 구현/운영 상태가 바뀔 때 문서를 함께 갱신한다. |

### IPO 후속 확인 / 개선 checklist

다음 IPO 작업에서는 **Metalogos 160 매력지수를 Wealth IPO Score로 복사하지 않는다.** 160은 참고 source로 유지하고 Wealth 점수는 기존 canonical feature/provenance 규칙으로 계산한다.

- [ ] Metalogos 참고행을 한 줄로 표시: `160 원문 · 매력지수 · 수요예측기관 · 확약기관 · 유통가능`.
- [ ] `160 원문` 클릭이 신뢰된 `https://metalogos.ai/160ipo/stock/...` URL을 실제 새 창/새 탭에서 여는지 Chrome regression으로 검증한다.
- [ ] 엠에스바이오처럼 160 참고수치는 이미 수집됐지만 Wealth가 `tradable_share_ratio` 부족으로 `점수 산정중`인 경우를 실제 pipeline 기준으로 재현한다.
- [ ] Wealth `tradable_share_ratio`의 canonical source는 DART 문서 파싱 경로를 우선 유지한다. Metalogos `tradable_share_ratio_reference`는 자동으로 canonical feature로 승격하지 않는다.
- [ ] 일반 새로고침의 targeted DART score recovery가 청약 D-1까지 불필요하게 기다리는지 검증한다. 청약 전에 이미 유효한 DART 근거가 공개된 경우에는 point-in-time 규칙을 지키면서 더 일찍 canonical feature를 회수할 수 있는지 개선한다.
- [ ] DART source date / filing selection cutoff를 보존하여 청약 이후 공개 정보가 과거 Wealth Score에 역유입되지 않도록 한다.
- [ ] `attractiveness_score`, 기관 수, 확약기관 수 등 Metalogos reference 값이 Wealth 자체 score feature에 섞이지 않는 regression을 유지한다.
- [ ] IPO refresh 후 score coverage/core_missing 변화, reference 표시, 링크 동작을 backend + Chrome 테스트로 함께 검증한다.

현재 확정된 다음 기능은 없다. 다음 기능 착수 여부와 순서는 제품 우선순위 결정 후 정한다.

추후 후보:

- **예측 정확도 고도화** — point-in-time snapshot과 actual 비교 데이터가 충분히 누적된 뒤 source별 accuracy/편향을 의사결정에 연결
- **고배당기업 공식 자격 상태 변경 알림** — 실제 공식 상태 변화 데이터가 쌓인 뒤 기존 opt-in alert/dedup 계약 재사용 여부 검토
- **C-7 가족별 배당 분산 보기 단순화** — 기존 두 family 패널을 단순 통합할 필요성이 다시 커질 때 진행

건강보험·부양가족 영향과 법인 자금 인출 확장도 현재 우선순위에서 보류한다. stable user id 저장 경로 전환은 아래 장기 구조 개선 후보이며 별도 migration 설계가 필요하다.

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

10.5G 완료:

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
