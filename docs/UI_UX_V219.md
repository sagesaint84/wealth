# Wealth v2.1.9 운영 피드백 후보

## 현재 운영 기준 상태 — 2026-10-28 / Wealth v2.1.9

**현재 운영 앱 APP_VERSION=2.1.9. Oracle 실제 화면 사용자 확인 완료는 사용자 보고에 근거한다.** Issue #189의 현재 이미지·rollback 상태는 별도 읽기 전용 감사로 확인했으며, 이번 문서 갱신에서 운영 서비스·이미지·state는 변경하지 않는다.

GitHub에서 직접 확인한 릴리스 이력(annotated 태그의 원격 역참조 SHA도 일치):

| 버전·태그 | 병합 PR | 정확한 병합 커밋 |
|---|---|---|
| v2.1.7 | [#192](https://github.com/sagesaint84/wealth/pull/192) | `c03256dcb8b0ece7c558637c94e7cc0aa422426d` |
| v2.1.8 | [#193](https://github.com/sagesaint84/wealth/pull/193) | `72a7b0c97bfa6e94e6d5b38d9710c2439d9c4dd7` |
| v2.1.9 | [#194](https://github.com/sagesaint84/wealth/pull/194) | `4c62a5e8ef2e65d98d835a5e8a70c534ccf53f3d` |

- **직접 검증한 CI:** v2.1.9 PR HEAD `031ab646513fccbc615ab0cd6e6655667e0281d9`의 Linux CI **4/4 SUCCESS**. [Static transport](https://github.com/sagesaint84/wealth/actions/runs/40627717046) **642 PASS / SKIP 0**, 기존 경고 1건, 실제 Chromium/SKIP 금지 검증 단계 성공. [IPO](https://github.com/sagesaint84/wealth/actions/runs/40627717081), [Toss WTS](https://github.com/sagesaint84/wealth/actions/runs/40627717113), [System update](https://github.com/sagesaint84/wealth/actions/runs/40627717108)도 SUCCESS. 이는 해당 릴리스 코드의 결과이며 새 문서 PR HEAD의 결과로 승계하지 않는다.
- **직접 검증한 GHCR:** [docker-publish run 40636503851](https://github.com/sagesaint84/wealth/actions/runs/40636503851)의 build-and-push SUCCESS 및 checkout SHA `4c62a5e8ef2e65d98d835a5e8a70c534ccf53f3d` 확인. 이 작업에서 이미지 발행/태그 변경/설치를 실행하지 않는다.
- **중복 통합 정리:** [#190](https://github.com/sagesaint84/wealth/pull/190)·[#191](https://github.com/sagesaint84/wealth/pull/191)은 #192 통합 및 #193/#194 후속 변경 감사 후 **미병합 CLOSED**. 삭제 승인된 원격 feature 브랜치 7개를 정리해 이번 문서 브랜치 생성 전 원격에는 main만 남았다. 이 문서 Draft 제출 시 문서 브랜치/PR은 새로 추가되며, 이전의 열린 PR 0개 상태와 구분한다. 로컬 보호 브랜치·worktree·증거는 삭제하지 않는다.
- **남은 Issue:** [#178](https://github.com/sagesaint84/wealth/issues/178)은 미국 CNN 비공식 중계 완료 / 한국 시장심리 출처·이용조건·산식 별도 검토로 OPEN. [#182](https://github.com/sagesaint84/wealth/issues/182)는 태그 보완 완료, 문서·배포 정책 후속 설계로 OPEN. [#189](https://github.com/sagesaint84/wealth/issues/189)는 **Oracle 읽기 전용 감사에서 현재·rollback 이미지 존재 및 SHA/digest/image ID 일치를 확인해 CLOSED** 처리했다. worker ACTIVE, 진행 중/rollback_failed 0, 마지막 install succeeded/confirmed, 디스크 여유 29.75 GiB로 현재 누락 참조 해제 조치는 불필요하다. **maintenance 모듈은 호스트 미설치·도구 미실행**이며, 도구로 참조를 해제해서 해결한 것이 아니다. 과거 누락 참조 기록은 당시 이력으로 보존한다.
- **검증 한계 보존:** 전체 pytest=NOT_RUN. 과거 DAY 간헐 실패 원인=UNCONFIRMED. 이후 집중/CI PASS를 원인 해결 또는 단순 flaky 확정의 근거로 사용하지 않으며 과거 실패 로그·JUnit과 아래 당시 판단을 보존한다.

### 배포 계약 — 이번 문서 작업에서 변경하지 않음

`app/updater/releases.py`의 ReleaseVerifier는 **최신 main HEAD에 대응하는 성공한 GHCR 빌드**를 요구한다. `.github/workflows/docker-publish.yml`은 main Push마다 실행된다. 문서 PR도 main에 병합하면 새 SHA와 GHCR 빌드가 생길 수 있으므로 **사용자 승인 전 이 문서 PR을 Ready/병합하지 않는다.** 이 작업은 feature 브랜치 Push와 Draft PR 제출만 허용하며 main Push·APP_VERSION 변경·버전 태그 이동·GHCR 발행·Oracle Docker/worker/state 변경을 하지 않는다.

문서 전용 변경을 발행하지 않는 정책은 **Issue #182의 별도 설계 대상**이다. 단순 paths-ignore 추가는 최신 main용 빌드가 없어 업데이트 확인을 막을 수 있으므로, ReleaseVerifier·배포/검증 계약을 함께 검토하고 별도 승인하기 전에는 적용하지 않는다.

**아래의 개발 후보·NOT_RUN·HOLD·Draft·미배포 문구는 각 절 작성 당시의 역사적 기록이다. 현재 운영 상태는 이 상단 절을 우선하며, 기술 계약·사용자 설명과 과거 버전 이력은 삭제하지 않는다.**

---

Base main: 72a7b0c97bfa6e94e6d5b38d9710c2439d9c4dd7. Branch: codex/v219-ui-ux-polish. 운영 v2.1.8은 사용자 확인 근거로 보존한다. 기존 worktree/PR190/191/운영 데이터 변경 없음.

## 구현 경계

1. 업데이트 세 작업만 서버 session authorization으로 분리한다. 실제 DB 권한·사용자/세션/epoch, 비밀번호 변경 완료, CSRF 및 Origin/Referer를 검사한다. status가 발급하는 세션 귀속 일회성 operation token을 mutation에서 소비하고 rate limit/감사를 유지한다. cleanup은 기존 images와 preview token도 별도 소비한다. 권한 부여/회수는 기존 별도 관리자 password reauth를 유지한다. Host IPC, SHA/digest 검증/롤백/보호 이미지 정책은 불변이다. 브라우저는 updatePassword DOM 자체를 제거하며 각 작업 확인 checkbox는 유지한다.
2. CNN은 공포탐욕지수, 점수 (단계)로 표시한다. 데이터 어댑터/0~100/만료/출처/시각/캐시는 불변이다. 지수 설정은 기존 브라우저·계정별 저장을 유지하고 범위 한정 CSS로 checkbox/목록 스크롤을 수정한다.
3. 은행 계좌 수 카드/소유자 반복 DOM 생성을 제거한다. 기존 금액 DOM 4개와 상세/서브탭을 사용하며 계좌 수만 보조정보로 갱신한다. 기존 상단 계좌 요약의 owner+linked overdraft 제외 기준을 단일 금액 렌더러로 이동하여 같은 부채/이자를 두 번 더하지 않는다. 납입액/만기 수식과 금융 서비스는 바꾸지 않는다. 증권 요약은 유지한다.
4. IPO lazy dialog와 공유 계좌/배정/매도 연결 renderer를 유지한다. 회사·기간·공모가·상장일을 구조화하고 dialog 안의 가족별 영역만 grid로 배치한다. max-width important와 checkbox 너비 충돌을 해당 ID 범위에서 해결한다. revision/409/사용자 전환/입력 보존 계약 불변, 신청수량 모델 없음.

## 검증·릴리스 상태

업데이트 API/권한 66 PASS(기존 Starlette 경고 1), 업데이트 Chromium 17 PASS를 합성 TEMP에서 확인했다. 최종 보안/화면·통합 검증 결과는 아래에 기록한다. 전체 pytest NOT_RUN. 이 문서는 로컬 검증을 기록하며 원격 제출·CI 상태는 Draft PR의 새 HEAD로 별도 확인한다. 모든 필수 Gate 통과 후에만 Draft PR을 제출한다. Ready/main/GHCR/Oracle/host worker 작업은 하지 않는다. 로그/JUnit/합성 시각 증거는 TEMP에 보존하고 Git에 넣지 않는다.

## 최종 로컬 검증 기록

- API/권한 초기 66 PASS, 업데이트 UI 초기 17 PASS. 보강한 일회성 승인 재사용/세션 방어와 금융/host/버전/자산 계약을 포함한 최종 단위 묶음은 **156 PASS / 예상 Windows Unix IPC SKIP 1 / subtests 7 PASS / 기존 Starlette 경고 1** (16.04초)다. Windows에서는 실제 Unix IPC를 수행하지 못하며 Linux CI에서 별도 검증한다. Host 테스트는 가짜 Docker executor를 사용하며 운영 Docker 명령은 실행하지 않았다.
- 최종 Chromium **91 PASS** (267.78초): 신규 시장·은행 15, IPO 상세 16, 기술 신호·시장 23, CNN 15, 업데이트 17, 기존 카드 개인 선택 5. 이후 계좌 수 갱신/매우 긴 금액/카드 겹침 검증을 보강한 신규 모듈만 **15 PASS** (43.90초)로 재확인했다. 중복 실행을 고유 테스트 수에 더하지 않는다.
- 최초 신규 smoke 1 FAIL은 서로 다른 fixture용 choose()가 존재하지 않는 __tabs를 참조한 테스트 작성 오류였다. 실제 탭 클릭/라우트/aria 선택 확인으로 수정 후 1 PASS 및 위 전체 검증을 수행했다. 실패 로그/JUnit은 삭제하지 않았다.
- 320/360/390/768/1280px, purple/white/oled를 확인했다. TEMP 시장 설정/IPO/은행 합성 PNG를 시각 검토했다. 가족 전환 직후 계좌 수는 기존 비동기 summary 갱신 전 잠시 이전 값일 수 있어, 신규 검증은 실제 계좌 수 완료 조건도 확인한다. 최종 은행 캡처는 긴 합성 금액과 계좌 수 3/예적금 1/대출 1의 갱신을 확인했다. 계좌 수는 기존 debounce로 갱신되며 금융 금액은 현재 선택 범위로 렌더된다.
- 증거 경로: TEMP wealth-v219-29b67e3358ec4d15aa173f7ad03a1178의 security/update-ui/contracts/browser/bank-final.log 및 .xml. 모든 자료는 로컬 보존하며 Git에 포함하지 않는다. 전체 pytest=NOT_RUN, 새 원격 Linux CI=NOT_RUN(제출 후 새 HEAD 확인).

## 최종 소스·캐시 감사

APP_VERSION/메타/화면/계약 2.1.9. 실제 변경 자산 8개와 관련 dynamic loader parent만 2.1.9-ui1로 갱신한다. wealth-account-section-summary는 owner-options→money-input의 실제 로딩 경로를 따라 cache revision을 반영했다. 미변경 IPO 세부 모듈/OCR/Toss/SW revision은 유지한다. core wealth.js 기대 URL을 참조하는 관련 static 계약도 일치시켰다.

금융 서비스(app/services), host updater(app/updater), Compose/Docker, 로그인 전역 계약과 원본 DAY blob은 불변이다. 웹 app/system_update.py의 세 작업 인증 경계만 변경했다. 은행 상단 수량 카드/소유자 반복 renderer를 실제 제거했고 증권 renderer·공유 IPO controls를 유지한다. 범위가 불명확한 과거 공용 CSS/기능을 임의 삭제하지 않는다. 기존 v2.1.8 worktree는 clean으로 보존한다. 이 문서의 테스트는 로컬 증거이며 CI 성공/병합/운영 설치와 구분한다. 사용자 승인 전 Ready/main/GHCR/Oracle 작업 금지.

## 변경 파일 (32개)

- `.github/workflows/static-transport-pr-validation.yml`
- `CHANGELOG.md`
- `README.md`
- `app/main.py`
- `app/static/index.html`
- `app/static/wealth-account-section-summary.js`
- `app/static/wealth-accountinfo-owner-options.js`
- `app/static/wealth-ipo.js`
- `app/static/wealth-layout.css`
- `app/static/wealth-money-input.js`
- `app/static/wealth-settings-surface.js`
- `app/static/wealth-system-update.js`
- `app/static/wealth.js`
- `app/system_update.py`
- `docs/PROJECT_STATE.md`
- `docs/ROADMAP.md`
- `docs/SYSTEM_UPDATE.md`
- `docs/UI_UX_V219.md`
- `tests/test_account_section_summary_10_6b_frontend.py`
- `tests/test_accountinfo_owner_options_frontend.py`
- `tests/test_cnn_fear_greed_chrome.py`
- `tests/test_dividend_official_source_static.py`
- `tests/test_financial_income_what_if_static.py`
- `tests/test_market_signals_holdings_chrome.py`
- `tests/test_money_input_ux.py`
- `tests/test_release_version.py`
- `tests/test_system_update_api.py`
- `tests/test_system_update_chrome.py`
- `tests/test_system_update_permissions.py`
- `tests/test_toss_wts_import_modal_scroll.py`
- `tests/test_v218_ipo_detail_chrome.py`
- `tests/test_v219_ui_chrome.py`
