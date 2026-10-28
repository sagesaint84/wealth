# #178 — 개인용 CNN 지수 비공식 GitHub 중계 연동 후보

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

**최신 PowerShell 집중 회귀=63 PASS / DAY 38 PASS** (277.74초, 동적 차트 캐시 수정 이후). 과거 DAY 단발성 실패 원인은 UNCONFIRMED이며 실패 증거는 보존한다. 일 수익률은 사용자 확정식 `당일 가격변동 손익 ÷ 현재 총 주식자산 × 100`을 동일 가족 범위에서 계산하며, 결측·부분 데이터·분모 0 이하에서는 `—`다. 기존 IPO 배정수량 저장을 유지하고 신청수량은 추가하지 않는다. 새 원격 Linux CI는 NOT_RUN이며 운영 v2.1.7은 유지한다.

## 2026-10-28 — v2.1.8 표시 개선 후보 / v2.1.7 운영 수락

운영 v2.1.7 배포·사용자 수락은 사용자 확인 근거다. 아래 통합 후보의 미배포/NOT_RUN 상태는 당시 이력으로 보존한다. v2.1.8에서는 기존 score/status/valid_until·36시간/4일 신선도·실패 시 숫자 숨김·캐시/타이머 정책을 변경하지 않고 CNN을 주요지수 카드로 표시한다. 가짜 sparkline은 만들지 않는다. 공식 CNN 및 중계 GitHub 링크, 비공식 데이터 중계·실시간 보장 없음·기준일·KST 파일 갱신 시각은 카드의 출처 상세에 유지한다.

표시 카드 선택은 브라우저·로그인 계정별 localStorage에만 저장하며 서버 동기화는 하지 않는다. 새 카드는 기본 표시하고 전부 해제하면 설정 진입 안내를 표시한다. 설정 변경 자체는 API 요청을 발생시키지 않는다. 기존 Yahoo/TNX 조회와 CNN 어댑터·API는 그대로 유지한다. [후보 검증·릴리스 경계](UI_UX_V218.md).

## 2026-10-28 — v2.1.7 통합 후보 최종 정리 / 운영 미배포

- **APP_VERSION=2.1.7 릴리스 후보**, [PR #192](https://github.com/sagesaint84/wealth/pull/192)는 **Draft / 미병합**이다. 원래 통합 커밋 `f19ab03c7b07dbeaaa7608e2cef40687d5ebfc49`의 27개 변경 파일을 유지한다. 원본 #190의 코드 `fd8b7045`·문서 `d8d8434` 및 #191 `3897f0b`의 기술 계약과 검증 이력을 보존한다. 정적 자산 revision `2.1.7-cnn1` 및 기능 코드는 이번 정리에서 변경하지 않는다.
- **Windows 통합 근거:** Unit **369 PASS / 예상 Unix IPC SKIP 1**, Chromium **132 PASS**. DAY 전체 모듈 **38 PASS**. 기존 Starlette 경고 1건. 이는 이미 완료된 검증이며 이번 정리 후 전체 통합 검증을 반복했다는 뜻이 아니다.
- **진단 커밋 `20b6c3565f8d75bb0d3ed83a18682323042bc108`의 Linux CI:** 전체 워크플로 **4/4 SUCCESS**, Static transport **567 PASS / SKIP 0**, DAY **38 PASS**, CNN Chromium **15 PASS**, Toss **AMD64 / ARM64 PASS**, System update **synthetic IPC / isolated Docker PASS**, IPO schedule **PASS**. [Static transport 실행 40555628384](https://github.com/sagesaint84/wealth/actions/runs/40555628384). Windows 및 Linux 결과는 사용자 확인 근거다.
- **이전 Linux DAY 실패 ROOT_CAUSE=UNCONFIRMED.** 위 Linux 성공은 임시 진단 코드가 포함된 커밋의 결과다. 이번에는 DAY 테스트만 원래 통합 커밋과 동일한 blob으로 복원하여 instrumentation을 제거한다. 진단 커밋은 Git 이력에 보존한다. 정리가 원인 해결 또는 단순 flaky 판정의 근거는 아니다. **진단 제거 이후 새 HEAD CI=NOT_RUN**이며 위 PASS를 승계하지 않는다. 정리 후 로컬 집중 검증 결과는 별도 실행 기록으로 구분한다.
- **Oracle 읽기 전용 사전검사=PASS (사용자 제공):** 운영 **v2.1.6 유지**, 실행 이미지 SHA/digest 일치, Running=true / RestartCount=0, HTTP **307**, 여유 공간 **33G**. updater **active/running**, 진행 중 job **0**, rollback_failed job **0**, 마지막 설치 **succeeded/confirmed**. 오래된 rollback 참조가 남아 있고 해당 이미지는 **MISSING**이다. 참조를 해제하거나 이미지를 다시 받지 않았다.
- **CNN outbound:** Oracle에서 relay **HTTP 200 / 구조·신선도 PASS**. 이 사전검사는 v2.1.7 앱의 운영 설치·화면 수락을 의미하지 않는다. 오류·만료 시 숫자 숨김과 개인용 비공식 중계 표기를 유지한다.
- **운영 게이트:** HOST_MAINTENANCE=NOT_RUN, Git 태그=**NOT_CREATED**, main 병합=**NOT_RUN**, GHCR v2.1.7=**NOT_RELEASED**, Oracle v2.1.7=**NOT_DEPLOYED**. 앱 이미지 배포와 `/opt/wealth-updater` 호스트 코드 갱신은 별도 승인·검증 대상이다. 컨테이너/worker/systemd/state/Compose/pin/IPC key/금융·Toss 데이터/이미지는 이번 정리에서 변경하지 않는다. 원본 PR #190/#191은 보존한다.

아래 기존 후보 작성·버전별 검증/배포 상태 문구는 **당시 이력**이며, 현재 상태는 위 기록을 우선한다. 기존 기술 계약과 승인 후 적용·복구 절차는 계속 유효하다.

## 2026-10-28 — 정식 v2.1.7 릴리스 통합 후보

- 기준 main/현재 커밋 HEAD `bfdc874ec9f4e802604d452dcc5368d4348edc0e`, 새 branch `codex/v217-release-integration`. #190 코드 `fd8b7045d267d9ffbad4cf77518f5f780575c0c7`·문서 `d8d8434cb63ed6a121b14e299bc7dd16727abbe6`와 #191 `3897f0bea3806732553eaf01da16b0c961f23363`을 순서대로 `cherry-pick -n` 통합했다. 원본 PR/worktree는 변경하지 않는다.
- 현재 후보는 APP_VERSION/HTML meta·화면/회귀 계약 **2.1.7**, wealth.js·wealth-layout.css revision **2.1.7-cnn1**이다. 독립 IPO/OCR/Toss 등 자산 revision과 SW cache 이름은 유지한다. SW는 JS/CSS/API를 캐시하지 않으므로 cache 이름을 일괄 교체하지 않는다.
- #191 사용자 Windows 검증 **96 unit PASS, 66 Chromium PASS(CNN 15건)**, GitHub CI 전체 SUCCESS는 원본 HEAD의 검증 근거다. #190 원본 코드의 Windows 256 PASS/1 SKIP/1 warning·Linux synthetic-web-and-ipc 304 PASS 및 isolated-docker-compose 2 PASS도 보존한다.
- **새 통합 후보 pytest/Chromium/전체 회귀/CI는 NOT_RUN**이다. 원본 PR의 PASS를 통합 PASS로 쓰지 않는다. 아래 단독 개발 당시 버전 유지·PR 미생성 상태는 이 통합 후보의 현재 상태가 아니다.
- INTEGRATION_GATE=WAITING_USER_POWERSHELL, COMMIT/PUSH/PR_CREATION=NOT_RUN, MERGE=HOLD. Oracle outbound·GHCR 발행·v2.1.7 운영 설치·호스트 코드 교체/worker 재시작/state 변경·이미지 정리 NOT_RUN. 운영 v2.1.6 고정 이미지를 유지한다.
- 본문 아래 명령은 CNN 단독 검증 예시이며, 이번에는 유지보수/업데이트기·버전/캐시 계약까지 포함한 통합 명령을 사용자에게 별도로 제공한다. 테스트는 사용자가 PowerShell에서 실행한다. #190/#191은 Draft 미병합 상태로 보존하며 새 후보에서도 승인 전 병합·배포하지 않는다.

### 이번 통합 후보의 사용자 Windows 검증

다음 명령은 안내만 작성했으며 Codex는 실행하지 않았다. 지정 worktree의 작업 파일을 검사한다. Windows Unix IPC skip은 예상이며 실제 Linux IPC/격리 Docker는 추후 새 통합 HEAD CI에서 별도 검증해야 한다. 기존 개별 PR의 통과 건수를 이번 실행의 기대 건수로 고정하거나 테스트를 제외하지 않는다.

```powershell
Set-Location -LiteralPath 'C:\Users\USER\.codex\worktrees\v217-release-integration\wealth'
$env:PYTHONPATH='.;tests'
$env:WEALTH_ENV='test'
$env:WEALTH_DISABLE_ENV_FILE='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$unitTests = @(
  'tests/test_cnn_fear_greed.py', 'tests/test_market_daily_indicators.py',
  'tests/test_system_update_maintenance.py', 'tests/test_system_update_api.py',
  'tests/test_system_update_permissions.py', 'tests/test_system_update_host.py',
  'tests/test_system_update_releases.py', 'tests/test_release_version.py',
  'tests/test_dividend_official_source_static.py', 'tests/test_financial_income_what_if_static.py',
  'tests/test_money_input_ux.py', 'tests/test_toss_wts_import_modal_scroll.py'
)
python -B -m pytest @unitTests -q
if ($LASTEXITCODE -ne 0) { throw 'Integrated unit/contract gate failed' }
$browserTests = @(
  'tests/test_cnn_fear_greed_chrome.py', 'tests/test_home_three_tabs_chrome.py',
  'tests/test_market_signals_holdings_chrome.py', 'tests/test_home_initial_html_chrome.py',
  'tests/test_owner_filter_loads.py', 'tests/test_system_update_chrome.py',
  'tests/test_settings_surface_chrome.py', 'tests/test_service_worker_cache_guard.py',
  'tests/test_initial_asset_load.py', 'tests/test_view_initial_work_chrome.py'
)
python -B -m pytest @browserTests -q
if ($LASTEXITCODE -ne 0) { throw 'Integrated Chromium/startup gate failed' }
```

변경 파일 27개 = 두 PR 원본 16개 + 버전/정적 자산 계약 7개(app/main.py, app/static/index.html, tests/test_release_version.py, tests/test_money_input_ux.py, tests/test_dividend_official_source_static.py, tests/test_financial_income_what_if_static.py, tests/test_toss_wts_import_modal_scroll.py) + 현재 릴리스 문서 4개(README.md, CHANGELOG.md, docs/PROJECT_STATE.md, docs/ROADMAP.md). 원본 문서 3개도 상단 현재 상태를 추가했고 과거 본문은 보존했다. 삭제 파일과 예상 외 untracked 파일은 없다. 테스트 실행 전 소스 정적 확인이며 기능/CI PASS 판정이 아니다.

이하 내용은 **PR #191 단독 개발 당시 계약/검증 안내**로 보존한다. 데이터·보안·캐시·UI 동작은 통합에서도 그대로 유지한다.

## 출처와 범위

- 기준 main `bfdc874ec9f4e802604d452dcc5368d4348edc0e`, branch `codex/v217-cnn-relay`.
- [확정 구현 계약](https://github.com/sagesaint84/wealth/issues/178#issuecomment-6441528591)에 따른 개인용·비상업용 후보이며, [GitHub 프로젝트](https://github.com/chirag127/fear-greed-index-api)의 고정 [raw JSON](https://raw.githubusercontent.com/chirag127/fear-greed-index-api/main/data/latest.json)만 일반 HTTPS GET한다.
- 2026-10-27 개발 중 해당 URL 일반 GET HTTP 200과 CNN headline/date/updated/sources/unavailable 구조를 확인했다. 공개 검색 스냅샷은 직접 GET보다 오래된 데이터를 보여줄 수 있었다. 조사 숫자는 운영 코드에 넣지 않았고 실시간 CNN 사이트 대조를 한 것으로 취급하지 않는다.
- UI 표기는 **CNN 지수 · 비공식 데이터 중계**, 공식 CNN 페이지와 중계 프로젝트 링크, 실시간 보장 없음이다. 중계자의 수집 방식·MIT 코드 라이선스는 CNN의 공식 API/데이터 재이용 허가를 보증하지 않는다. 사용자가 승인한 개인 참고 범위이며 상업/다중 사용자 재배포 허가를 주장하지 않는다.
- Wealth는 CNN 직접 요청·브라우저 헤더/Referer 위장·우회 프록시·브라우저 자동화·대체 공급자/점수 계산을 하지 않는다. 한국/암호화폐/MMI 지수는 처리하지 않는다. GitHub raw 장애 때 다른 URL로 자동 전환하지 않는다.

## 엄격한 입력·시간 계약

- `headline['cnn-fng'].value`: bool 제외 finite number 0..100. `zone.label`: Extreme Fear/Fear/Neutral/Greed/Extreme Greed만 허용한다. 알려지지 않은 라벨/HTML/값 누락은 거부한다. 단계는 중계 원문을 사용하며 임의로 재계산하지 않는다.
- `date`: 유효한 ISO 날짜. 파일 `updated`: 명시적 UTC ISO timestamp(Z 또는 +00:00). naive/다른 offset/잘못된 날짜, 현재 UTC보다 미래인 날짜, 파일 갱신일보다 미래인 CNN 날짜, 5분 초과 미래 갱신 시각은 거부한다. `asOf`는 다른 시장 기준일이므로 사용하지 않는다.
- `sources.cnn.ok is True` 필수. `unavailable`은 문자열 배열이며 CNN 관련 항목이 있으면 거부한다. 형태가 바뀌면 안전하게 조회 불가로 처리한다.
- 파일 갱신 시각에서 36시간 경과하거나 CNN 날짜에서 4 UTC calendar days 경과하면 `status=stale`, score/rating=null. 이 한계는 주말/휴일을 완전히 판별하는 거래소 캘린더가 아니며 연휴에는 의도적으로 숫자를 숨길 수 있다.
- 응답은 CNN intraday timestamp가 아니라 중계의 **기준일**과 **파일 갱신 시각**을 구분한다. 날짜는 공급자의 date를 그대로 표시하고, 파일 갱신 시각은 UTC로 저장·KST로 표시한다. NY 거래 시각을 만들어내지 않는다.
- 브라우저도 `valid_until`을 확인하고 만료 콜백으로 표시 점수를 제거한다. 이 콜백은 네트워크 요청을 하지 않는다. 기간 변경으로 캐시 데이터를 다시 렌더할 때도 만료된 점수를 표시하지 않는다.

## 조회·캐시·실패 계약

- 전용 HTTP client, 식별 가능한 일반 User-Agent, no credentials/cookies/Referer, trust_env=False, 리다이렉트 불허. Yahoo HEADERS/클라이언트를 재사용하지 않는다.
- httpx timeout 5초, 전체 다운로드/처리 외곽 deadline 6초, 실제 디코딩 바이트 최대 64 KiB. HTTP 200만 성공. 403/418/429/5xx/redirect, 잘못된 JSON/NaN/크기 초과는 `source_error`, score/rating=null이다. 원문 오류/HTTP body를 UI로 전달하지 않는다.
- 기존 MarketReadCache를 **별도 인스턴스**로 사용한다. 메모리 1개 키, TTL 30분, 동시 요청 공유, 실패 backoff 60초. 마지막 성공이 내부 진단용으로 남더라도 실패한 refresh의 응답에는 과거 점수를 넣지 않는다. 캐시 hit 때도 데이터 연령을 다시 검사한다. 정상 수신됐지만 오래된 패킷도 30분 캐시될 수 있으며 그동안 숫자는 계속 숨긴다. 파일/DB 캐시·cron·자동 백그라운드 갱신 없음.
- WEALTH_ENV=test에서는 client 생성/캐시 조회 전에 외부 요청을 차단한다. 합성 테스트만 명시적으로 정책을 MockTransport에 맞춰 대체한다.
- 기존 /api/market-overview에서 Yahoo/TNX와 독립 coroutine으로 결합한다. Yahoo 25개 요청과 기존 TNX 경로·값은 변경하지 않는다. CNN 오류/예외는 CNN 객체만 조회 불가로 만든다.
- 기존 홈→주요지수 진입 경로를 재사용한다. 비활성 API 방어, 중복 GET 공유, generation/숨김 검사에 의한 늦은 응답 무시는 유지한다. 금융 파일·계좌·Toss·OCR·비밀키·운영 설정에 접근하거나 쓰지 않는다.

## 작성한 테스트와 사용자 실행 명령

이번 단계에서 pytest/Chromium/전체 회귀는 **NOT_RUN**이다. 코드 작성 및 git diff 정적 확인만 수행한다. 아래는 사용자가 이 worktree의 PowerShell에서 실행할 명령이며 통과 결과를 미리 주장하지 않는다.

```powershell
$env:PYTHONPATH='.;tests'
$env:WEALTH_ENV='test'
$env:WEALTH_DISABLE_ENV_FILE='1'
python -m pytest tests/test_cnn_fear_greed.py tests/test_market_daily_indicators.py -q
python -m pytest tests/test_cnn_fear_greed_chrome.py tests/test_home_three_tabs_chrome.py tests/test_market_signals_holdings_chrome.py tests/test_home_initial_html_chrome.py tests/test_owner_filter_loads.py tests/test_release_version.py -q
```

MockTransport는 고정 URL/헤더/redirect/timeout/바이트 제한, 정상·실패·입력·신선도·singleflight·TTL·backoff·과거 점수 미노출·금융 무쓰기를 검사한다. Chromium 코드는 320/360/390/768/1280px × Purple/White/OLED, 홈/순자산 비활성 조회 0, 주요지수 첫 조회, 숫자 경계값·오류·악성 문자열·만료 콜백·출처·늦은 응답·가로 overflow를 검사한다. 기존 Yahoo/TNX 테스트는 CNN 결과를 별도 mock하고 25 Yahoo 요청 및 금융 쓰기 0을 유지한다. 신규 테스트는 기존 loopback-only Static transport CI에도 등록했다.

## 릴리스와 남은 위험

- APP_VERSION **2.1.6 유지**. HTML asset revision도 이 단계에서는 변경하지 않았다. 실제 v2.1.7 릴리스 통합 시 버전·변경 wealth.js/layout.css revision·버전 계약·README/CHANGELOG/ROADMAP/PROJECT_STATE를 함께 갱신해야 한다. 현재 후보를 운영에 배포하면 안 된다.
- #189/#190은 별도 Draft로 유지하며 이번 브랜치로 가져오지 않는다. 이후 사용자 승인된 실제 릴리스 범위에서 통합·재검증한다. 운영 v2.1.6 및 고정 이미지 유지.
- 공급자 upstream 변경/오래된 정상 JSON/수집 중단/신뢰 훼손·재이용 조건의 불확실성, GitHub rate limit/Oracle outbound는 남은 위험이다. 점수의 CNN 실시간 동일성은 보증하지 않는다. 파싱·시각·상태 검사는 출처의 진실성까지 증명하지 않는다.
- 사용자 PowerShell PASS 후 Draft PR 제출. 커밋·푸시·PR·main 병합·GHCR/Oracle 작업은 이번 단계에서 NOT_RUN이다.
