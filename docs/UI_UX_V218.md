# Wealth v2.1.8 UI/UX 통합 후보

기준 main: `c03256dcb8b0ece7c558637c94e7cc0aa422426d`.
Branch: `codex/v218-ui-ux-ipo-integration`. Oracle 운영 v2.1.7은 사용자 수락된 상태 그대로 유지한다.

## 최신 판정 및 확정 요구 (2026-10-28)

사용자 PowerShell 집중 검사 **63 PASS / DAY 38 PASS**, 277.74초, exit 0. 동적 차트 캐시 보완 이후 결과이며 `wealth-v218-final-review-eb0310c92ebe47e6b9a56c96843c1c23/final.xml`의 63건/실패 0건을 확인했다. LATEST_DAY_38=PASS, FINAL_FOCUSED_REGRESSION=PASS. 과거 DAY `filters` 실패 원인은 **UNCONFIRMED**이며 아래 실패 기록은 삭제하지 않는다. 이는 이전 코드의 검증이며 일 수익률 수정 후 영향 범위는 아래에 별도로 기록한다.

일 수익률은 같은 renderSummary(data)의 `day_change.day_profit_krw / summary.total_stock_value_krw * 100`. renderWithOwner가 동일 payload에서 가족별 summary와 daily_metrics_by_owner를 함께 선택한다. 다른 날짜/계정 응답이나 record_change_rate/value_krw와 결합하지 않는다. 유한 숫자·complete·양의 분모일 때만 부호와 소수점 둘째 자리로 표시한다. 0 손익은 +0.00%, 결측/비유한/부분 데이터/분모 0 이하는 —. 부분 금액 경고 유지. UI에는 새 설명/아이콘 없이 기존 금액의 title 한 줄만 사용한다.

사용자 확정 요구는 **배정수량 저장**이다. 기존 IPO/캘린더 공통 컨트롤과 계좌·가족·revision·손익 연결 방어는 정상 구현/기검증되어 이번 수정에서 변경하지 않는다. 신청수량 필드나 별도 손익 모델은 추가하지 않는다.

이번 추가 변경: wealth.js의 표시 계산, index.html의 wealth.js revision **2.1.8-ui2**, 관련 기존 테스트와 문서. 다른 변경 자산 9개는 ui1 유지. 변경 파일 집합 31개 유지.

## 구현 및 데이터 경계

- Phase A: 작업 기록 화면과 설명 문구 제거, 보호 이미지 역할/정리 사유, 기록 금액 위계, 총 평가손익/일 가격손익 구분. 일 수익률은 위 사용자 확정식으로 표시하며 백엔드 금융 계산식 불변.
- Phase B: CNN 카드는 기존 만료/실패/출처 계약 유지. 시장 설정은 브라우저 로컬 계정 ID(없으면 username) 키로 격리. 새 지수 기본 표시, 모두 해제 시 설정 안내. 신호 DOM 하나를 이동하고 실제 hash/선택 상태/자산 준비를 검사해 비활성 조회 및 늦은 응답 방어.
- Phase C: 목표 도넛/범례에서 기존 buckets revision으로 저장. CSS inset의 실제 빈 공간을 hit-test에 사용하며 Enter/Space를 명시적으로 처리해 중복 활성화를 막는다. 목표 0~100, 0.1 단위, 합계 100 이하, 미배정 유지. 다른 비중 자동 재분배 없음. 미저장 편집 차단, 충돌 재조회, 실패 입력 보존. 현재 비중·자산 분류 불변.
- Phase D: 같은 ipo_id로 원본 조회 후 기존 신청/계좌/배정/연결 UI 공유. 신청 수량은 모델 미지원이라 별도 저장하지 않는다. 컨트롤별 revision과 중복 작업 잠금, 계좌 후보 늦은 응답 방어. 연결/해제는 기존 API만 사용하며 손익 원본은 생성/중복 저장하지 않는다. 기존 실현손익 입력/수정 화면을 사용한다.
- 업데이트기 backend/host/IPC/Compose/상태/이미지 정책 변경 없음. 서버 job 이력 삭제 API 없음. 보호 이미지 삭제 허용 없음.

## 단계별 검증 기록

모든 검증은 `wealth-qa-venv` Python, WEALTH_ENV=test/WEALTH_DISABLE_ENV_FILE=1 및 TEMP synthetic 경로에서 수행한다. 실제 금융 데이터·.env·Oracle 접근 없음.

- Phase A: 37 PASS. 초기 새 테스트 import 오류 및 직접 전역 기록 주입 경쟁은 fixture를 실제 합성 API 응답으로 수정해 재검증했다. 실패 기록도 보존.
- Phase B: 본 검증 111 PASS 이후 새로고침 준비 조건의 ReferenceError 1건을 수정해 해당 카드 선호 모듈 5 PASS. 앞선 비활성 탭 추가 조회 및 직접 진입 누락은 실제 라우트/자산 준비 상태로 수정. 이후 확대 230건에서 통과했으며, 아래 최신 실패 판정을 별도로 유지한다.
- Phase C: 32 PASS / 21 subtests PASS. 최초 PYTHONPATH 누락 수집 실패는 기존 Windows 계약 `.;tests` 설정 후 통과. 테스트 코드 스킵/완화 없음.
- Phase D: 58 PASS / 7 subtests PASS / 기존 Starlette 경고 1건. 그 뒤 기록 상세 진입과 3개 테마 범위를 보강했으므로 최종 확대 검증은 별도로 기록한다.
- 최종 단위/계약·금융·보안 확대: **489 PASS / Windows Unix IPC 예상 SKIP 1 / subtests 45 PASS**, 경고 9건(기존 Starlette 1 + pandas 8). `final-unit2.xml` 및 `.log`.
- Chromium 중심 UI/초기화 확대: **230 PASS**, `final-browser.xml` / `.log`, 696.61초. 실제 Chromium 검사와 Service Worker/초기화 계약 모듈을 포함한 묶음이며 전체 pytest가 아니다. DAY 모듈 **38 PASS**, CNN 15 PASS 및 홈·업데이트 권한·모바일·테마 회귀 포함.
- 보완 후 집중: **63 PASS** (`focused3.xml`, 262.11초, 브라우저 59 + 릴리스 계약 4). IPO 기록 상세 진입, 표시 revision 충돌, 보호 이미지 역할/삭제 후보 0개, 신호 범위·초기 프레임을 재검증했다. 중복 사례를 기존 실행에 더해 고유 테스트 수로 부풀리지 않는다.
- 목표 편집 보완의 최신 16건과 기존 색상 편집 8건은 `focused2.xml`에서 전부 통과했다. 해당 실행 전체는 이후 IPO 준비 조건 실패로 **33 PASS / 1 FAIL**였음을 보존한다. IPO의 배정 표시 직후 매도 후보가 아직 준비되지 않은 상태를 테스트가 클릭한 것으로, 실제 버튼 활성 조건을 기다리도록 수정 후 위 집중 63건에서 통과했다.
- 추가 계약 **2 PASS** (`metric2.xml`, 4.80초): 일 가격손익/부분 데이터/금액 미확인과 기록 변화율 혼동 없음, 실제 연결된 오래된 카드 revision 0와 새 상세 revision 1의 충돌 거절. 새 테스트의 초기 시작 조건 누락으로 분리된 DOM을 클릭했던 실패(`connected=false`, 요청 0건)는 준비 조건을 수정해 재검증했다. 과거 Linux DAY 실패의 원인을 확정한 것은 아니다.
- 최종 CNN 카드 타이포그래피 수정 후 **15 PASS** (`cnn-final.xml`, 40.11초). White/360px 합성 화면에서 CNN/기존 시장 가격 모두 **14px**를 확인했다. 합성 PNG 2개를 TEMP에 보존해 시각 검토했다. 수정 전 PNG도 삭제하지 않았다.
- 동적 차트 캐시 최종 감사에서 `wealth-planning-model.js`의 child URL도 변경 필요함을 확인했다. child unified JS와 parent loader의 revision을 `2.1.8-ui1`로 맞췄고 계약을 추가했다. 변경 자산은 총 **10개**이며 미변경 자산/SW는 유지한다.
- 캐시 수정 후 `cache-final.xml/.log`: **15 PASS / 1 FAIL**, 39.07초. 릴리스 계약 5건은 모두 PASS. 기존 DAY `filters`에서 SETUP waitUntil이 CDP Promise 예외를 반환했다. pytest 출력은 상세를 축약했고 pnl/dividend visibility 및 unified 상태 false, errors=[] 일부만 확인된다. 정확한 실패 단계·원인·동적 URL 변경과의 인과관계는 **UNCONFIRMED**다. maxfail로 중단되어 이후 홈 모듈은 이 실행에서 미완료다.
- 외부 임시 진단 wrapper는 같은 Runtime.evaluate 파라미터/성공 값을 유지하고 실패할 때만 전체 CDP/초기화 상태를 출력하도록 한 번 실행했다. `filter-diagnostic.xml/.log`: **1 PASS**, 3.18초. 재현되지 않아 새 예외 증거는 없었으며 당시 회귀 HOLD를 유지했다. 이후 사용자 PowerShell 63 PASS / DAY 38 PASS는 문서 상단의 최신 결과로 구분한다. 이 결과를 해결 또는 단순 flaky의 증거로 사용하지 않는다.
- 기존 DAY assertion·RAF·timeout 및 테스트 blob은 변경하지 않았다. 저장소 내 임시 DAY 진단, skip/xfail, 무조건 sleep 또는 timeout 증가는 없다. 최종 Python AST/JS node --check 및 diff check PASS.
- 전체 pytest=NOT_RUN. Linux CI / 격리 Docker=NOT_RUN. Docker 실행 금지로 호스트 관련 로컬 검사는 합성 단위 테스트만 수행한다.

실패를 포함한 stdout/JUnit 증거는 TEMP의 `wealth-v218-aa8480dbf8644711b2cab200ca55543f`에 보존하며 Git에 포함하지 않는다. 운영 스크린샷은 UI 참고만 사용하고 금액/계좌는 합성 fixture에 복사하지 않았다.

## 정리 및 잔여 위험

삭제 근거: updateJobs는 목록 UI만 삭제하고 jobs를 사용하는 상태/확인 로직 보존. 설명 전용 history-description/help CSS는 마크업 제거 후 사용처가 없어 삭제. 시장 장식은 wealth.css의 market-card:after 정의만 제거. 신호 영역과 공모주 컨트롤은 단일 기존 렌더러를 재사용하며 중복된 구형 화면을 CSS로 감추지 않는다.

시장 선택은 다른 브라우저와 동기화하지 않으며 브라우저 저장 실패를 화면에 알린다. 손익/공모주 동시 저장은 서버 revision으로 거절되며 사용자의 최신 상태 재확인이 필요하다. 일 수익률 분모는 현재 총 주식자산으로 확정됐다. 청약 신청수량 추가는 요구사항이 아니다. 사용 여부가 불분명한 과거 공용 CSS/코드는 삭제하지 않는다.

사용자 실제 화면·디자인 수락과 새 HEAD Linux CI는 아직 대기. COMMIT/PUSH/PR/병합/GHCR/Oracle/태그/호스트 유지보수=NOT_RUN.

## 지표 기준 및 남은 운영 확인

`portfolio.py`의 record_change_rate/value_krw는 기록 변화/이전 기록 값이므로 일 수익률 계산에 사용하지 않는다. 기존 asset_records session 손익과 총 평가손익 계산은 그대로다. 현재 payload의 summary.total_stock_value_krw만 분모로 사용한다.

앞선 자동 검증 PASS는 최신 통합 회귀 PASS, 사용자 실제 화면 수락 또는 Linux CI 성공을 의미하지 않는다. GitHub CI·실제 격리 Docker·사용자 운영 화면/디자인 수락은 아직 대기다. 실제 Docker pull/build/push/deploy/prune, Oracle SSH, host worker/state/Compose/금융·Toss 데이터 조작 없음. 표시 설정은 브라우저 로컬 범위다. 기존 배정수량 저장만 유지하며 신청수량 추가는 하지 않는다.

## 기능별 파일·검증 대응

| 항목 | 구현 파일 | 근거 |
|---|---|---|
| 업데이트 목록 제거·보호 이미지 안내 | wealth-settings-surface.js, wealth-system-update.js | 기존 updater Chromium + 신규 empty-preview 5건, API/permissions/host/maintenance 회귀 |
| 홈/주식 설명·금액 위계·일 손익 | index.html, wealth.js, wealth-planning.js, wealth-timeseries-unified.js, wealth-layout.css | UI 15개 너비/테마, metric2, daily metric separation·금융 회귀 |
| CNN 카드/카드 선택·장식 제거 | wealth.js, wealth-layout.css, wealth.css | CNN 15건, 표시 선택 5건, unit cache/stale/입력 방어, 360px 시각 확인 |
| 기술 신호 이동·가족/계좌·늦은 응답 | index.html, wealth.js | market_signals_holdings Chromium 23건, holding_technical_signals unit |
| 목표 도넛/범례 직접 편집 | wealth-planning.js, wealth-layout.css | v218_bucket 16건, legend_color 8건, 기존 planning/bucket unit 및 21 subtests |
| 공통 IPO 계좌/배정/손익 연결 | wealth-ipo.js, wealth-calendar.js, wealth-layout.css | v218_ipo_detail 16건, 기존 calendar 4건, applications/account_resolution/allocation/sale_action_v2/critical_financial unit |
| 버전/캐시/SW·초기 API | main.py(APP_VERSION만), index.html, 관련 계약·Static transport workflow | release_version 5건 PASS, 최신 PowerShell 집중 63 PASS / DAY 38 PASS; 일 수익률 수정 후 12 PASS / UI 15 PASS. 과거 filters 실패 원인 UNCONFIRMED |

도넛과 카드 설정은 네이티브 dialog·button·checkbox를 사용한다. 새로운 대규모 UI 프레임워크나 서버 저장 스키마를 도입하지 않았다. 지수/신호는 읽기 전용이며 계좌 동기화·P&L 계산·일반 금융 메뉴·권한 API는 변경하지 않았다. Source Gate의 Python 금융 서비스·updater backend diff는 0이다.

## 최종 변경 파일 (31개)

- `.github/workflows/static-transport-pr-validation.yml`
- `CHANGELOG.md`
- `README.md`
- `app/main.py`
- `app/static/index.html`
- `app/static/wealth-calendar.js`
- `app/static/wealth-ipo.js`
- `app/static/wealth-layout.css`
- `app/static/wealth-planning-model.js`
- `app/static/wealth-planning.js`
- `app/static/wealth-settings-surface.js`
- `app/static/wealth-system-update.js`
- `app/static/wealth-timeseries-unified.js`
- `app/static/wealth.css`
- `app/static/wealth.js`
- `docs/CNN_RELAY_V217.md`
- `docs/PROJECT_STATE.md`
- `docs/ROADMAP.md`
- `docs/SYSTEM_UPDATE.md`
- `docs/UI_UX_V218.md`
- `tests/test_dashboard_daily_metric_separation.py`
- `tests/test_dividend_official_source_static.py`
- `tests/test_financial_income_what_if_static.py`
- `tests/test_market_signals_holdings_chrome.py`
- `tests/test_money_input_ux.py`
- `tests/test_release_version.py`
- `tests/test_system_update_chrome.py`
- `tests/test_toss_wts_import_modal_scroll.py`
- `tests/test_v218_bucket_chrome.py`
- `tests/test_v218_ipo_detail_chrome.py`
- `tests/test_v218_ui_chrome.py`

## 최종 안전·임시 산출물 Gate

- Python/JS 문법 및 YAML 파싱 확인. 초기 CI 등록 건수는 26/16/16이었으나 일 수익률 테스트 추가 후 UI 실제 건수는 27이며, 아래 최종 제출 감사에서 CI 계약 불일치를 기록한다. DAY 원본 blob `39951d2884bdb22742e74f772f85c4e82c09c95d` 일치. app/services·app/updater·app/system_update.py diff 0. main.py는 APP_VERSION 한 줄만 변경.
- 새 worktree `.env`는 없음. 테스트 후 `data`는 메타데이터 검사에서 빈 디렉터리였으며 파일 내용은 읽지 않았다. 금융 데이터나 인증 파일은 Git 변경에 포함하지 않는다.
- TEMP 합성 데이터 및 빈 worktree data 디렉터리 정리를 시도했으나 자동 승인 검토가 명령을 `blocked by policy`로 거부했다. 삭제 명령은 실행되지 않았고 다른 수단으로 우회하지 않았다. 따라서 TEMP_CLEANUP=HOLD_AUTO_REVIEW이며 디렉터리·로그·JUnit·합성 PNG는 보존한다. 구체적인 추가 거부 사유는 제공되지 않았다.
- COMMIT/PUSH=NOT_RUN, PR=NOT_CREATED, MAIN/GHCR/ORACLE=UNCHANGED. 실제 사용자 화면 수락·새 Linux CI·격리 Docker 검증은 별도 승인 단계다.

## 사용자 Windows 재검증 예시

```powershell
Set-Location -LiteralPath 'C:\Users\USER\.codex\worktrees\v218-ui-ux-ipo-integration\wealth'
$qaRun = Join-Path $env:TEMP ('wealth-v218-review-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $qaRun | Out-Null
$env:PYTHONPATH='.;tests'
$env:WEALTH_ENV='test'
$env:WEALTH_DISABLE_ENV_FILE='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTEST_ADDOPTS=''
$env:DART_API_KEY=''
$env:WEALTH_DATA_DIR=Join-Path $qaRun 'data'
$env:DATA_DIR=$env:WEALTH_DATA_DIR
New-Item -ItemType Directory -Path $env:DATA_DIR | Out-Null
& "$env:TEMP\wealth-qa-venv\Scripts\python.exe" -B -m pytest -q -p no:cacheprovider --maxfail=1 --basetemp "$qaRun\pytest" --junitxml "$qaRun\ui.xml" tests/test_v218_ui_chrome.py tests/test_v218_bucket_chrome.py tests/test_v218_ipo_detail_chrome.py tests/test_release_version.py
if ($LASTEXITCODE -ne 0) { throw 'v2.1.8 candidate verification failed; preserve evidence' }
```

이 예시는 신규 UI/계약 집중 범위이며 전체 pytest 또는 Linux IPC/Docker를 대체하지 않는다. 새 통합 HEAD가 아직 없으므로 GitHub CI 결과를 선기록하지 않는다. 사용자가 승인하기 전 커밋·푸시·PR 생성으로 진행하지 않는다.

## 일 수익률 최소 검증

- 계산·합성 가족별 실제 renderWithOwner·결측/부분·기존 총 평가손익/실현손익/배당·record delta 분리 및 릴리스 계약: **12 PASS**, 7.93초 (`wealth-v218-daily-rate-19dc9dd1bab94365936aa2d298cec028/daily.xml`, log 보존).
- +36,316,081 / 1,368,081,330 = **+2.65%**. 음수 -2.65%, 0 +0.00%, 결측/비유한/분모 0 이하/partial/unavailable는 —. 금액/기준 날짜 보존 및 입력 불변 확인.
- 신규 호출·초기화·공통 차트 변경 없음. 사용자 제공 63건은 위 최신 코드 전 검증으로 구분하고, 영향 UI 5너비×3테마는 새 코드로 별도 확인한다. 전체 pytest 및 230건 재실행/변경 없는 IPO 회귀 반복은 하지 않는다.

- 영향 UI 최신 실행: **15 PASS**, 40.16초 (`ui.xml/ui.log`), 320/360/390/768/1280px × purple/white/oled. 정확한 금액·+2.65%·title·금액/날짜 간격·전체 가로 overflow 및 기존 홈/기록 렌더 확인. 일 수익률 회귀/표시 Gate=PASS. 역사적 DAY 실패 원인은 UNCONFIRMED로 유지.

## 최종 제출 문서·정적 감사 (2026-10-28)

- source HEAD와 fetch 후 origin/main은 모두 `c03256dcb8b0ece7c558637c94e7cc0aa422426d`, branch 일치. 원격 후보 브랜치는 아직 없음. staged 없음, 수정/추가 합집합은 허용된 31개와 정확히 일치한다.
- 기존 JUnit/로그를 읽어 최신 집중 63 PASS, DAY 38 PASS, 일 수익률 12 PASS/UI 15 PASS, 확대 단위 489 PASS/예상 IPC SKIP 1, 확대 230 PASS를 확인했다. 기존 실패 XML/로그도 보존했다. 테스트는 재실행하지 않았다.
- DAY 원본 blob·금융 backend·updater 불변, main.py는 APP_VERSION만 변경, 자산 revision 일치. 기능 코드/테스트/워크플로를 이번 문서 감사에서 추가 수정하지 않았다.
- **제출 Gate=HOLD_CI_COUNT_CONTRACT**: `test_v218_ui_chrome.py`의 AST 기준 실제 수는 27건(15+5+5+1+1)인데 Static transport workflow의 `expected_ui_counts`는 정확히 26건을 요구한다. 그대로 제출하면 실제 테스트가 전부 통과해도 count assertion에서 실패한다. 버킷 16/IPO 상세 16/DAY 38 및 SKIP 0 계약은 그대로다.
- 필요한 최소 후속 변경은 `.github/workflows/static-transport-pr-validation.yml`의 해당 기대 건수 26→27과 그 계약 검토다. 이번 요청은 문서 수정만 허용하므로 임의 변경하지 않고 중단했다. 테스트 삭제나 기대 건수 검사 완화는 하지 않는다.
- Linux CI=NOT_RUN, 전체 pytest=NOT_RUN, COMMIT/PUSH=NOT_RUN, PR=NOT_CREATED. Oracle 운영 v2.1.7·main·GHCR·기존 PR190/191은 그대로 유지한다. 이 HOLD는 과거 DAY 실패의 원인이 확인됐다는 뜻이 아니다.

## CI 건수 계약 해소 및 제출 후보 (2026-10-28)

이전 HOLD_CI_COUNT_CONTRACT는 당시 제출 중단 이력으로 보존한다. 사용자 승인에 따라 workflow의 UI 기대 건수 **26→27 한 곳만** 수정했다. UI 27 / 버킷 16 / IPO 상세 16의 실제 pytest collection 및 YAML을 제출 전 검증한다. DAY 38/CNN 15/실제 Chromium/SKIP 0/네트워크 격리/trigger 계약은 유지한다. 기존 기능·테스트 소스는 추가 변경하지 않는다.

최신 로컬 DAY 38 PASS / Windows 집중 63 PASS 및 일 수익률 12 PASS / UI 15 PASS는 기존 XML·로그 근거다. 전체 pytest=NOT_RUN, 새 Linux CI=NOT_RUN(제출 후 새 HEAD 상태 별도 보고). 과거 DAY filters 실패 원인은 UNCONFIRMED이며 운영 v2.1.7 및 호스트 유지보수 미실행 상태를 유지한다. 커밋·Push·Draft PR 결과는 실제 제출 결과로 별도 보고하며 성공을 선기록하지 않는다.
