# v2.0.0 UI 마감 / 표시 정책 / 사용자 검증

기준 main: 55e3dcb68b85881d3c233f5de8d1f80bd2e0e2d6.
Branch: codex/v2-ui-cleanup. 작성일: 2026-10-13.

상태: 구현 및 테스트 코드 작성만 완료. 이 branch의 pytest/Node/Chrome/syntax
검증은 실행하지 않았으며 commit·push·PR·merge·배포도 하지 않았다.

## 표시 변경

- 절세계좌 카드: title/선택 badge를 nowrap으로 유지하고 종목·계좌 수를
  compact하게 표시한다. 폭이 부족하면 보조 count가 이동하며 제목 내부
  글자가 두 줄로 분리되지 않는다. 긴 실제 계좌명은 ellipsis와 전체 이름
  tooltip을 제공한다. filter ID, 계좌 수정 버튼과 금융 집계는 유지한다.
- Toss 실현손익·배당이자 가져오기: 귀속 Wealth 계좌 select와 기존 DOM ID,
  workflow default API·owner 검증·provider mapping 우선순위를 유지한다.
  버튼은 기본계좌로 지정 / 해제, 결과는 기본계좌 지정됨 / 기본계좌 해제됨.
  상태를 버튼과 같은 compact 영역에 배치한다. stale 계좌 안내와 명시적
  저장/해제 계약은 유지한다.

## 자산 구성의 두 퍼센트

근거: wealth.js의 computeFilteredClassifications / renderSummary,
wealth-layout.js의 HOME summary consumer, portfolio.py의 stock classification
집계를 읽었다. 실제 portfolio 파일은 읽지 않았다.

| 자산군 | 좌측 비중 | 우측 수익률 표시 |
| --- | --- | --- |
| 주식/ETF | 기존 classification.weight | 기존 return_rate, 유효한 양수 매입금액·손익 근거가 있을 때 |
| 부동산 | 기존 current_price × owner share의 구성 비중 | HOME의 기존 propertyExpectedRate, 기존 매입금액 합계가 양수일 때 |
| 현금·예수금 | 증권 예수금 + 은행 잔액 + 예적금의 기존 비중 | — |
| 보험 | 기존 expected/converted/paid/refund 기준 금액의 비중 | — |
| 임차보증금 | 기존 보증금 비중 | — |
| 새 자산군 | 기존 비중 | 기존 rate/profit/positive cost 근거가 있으면 rate, 아니면 — |

분모는 **표시 자산군 금액의 기존 합계**이며 순자산 분모로 바꾸지 않는다.
부동산 classification 금액은 현재 가격 기준이므로 설명을 부동산 평가액으로
정리한다. 현금 설명에는 예적금도 포함하며 여러 평가 기준을 쓰는 보험은
보험 평가 기준액으로 표시한다.

원가=평가액 / 손익=0으로 만든 비투자 항목의 0%는 투자 수익률 근거가 아니다.
이를 대신해 우측에 비중을 재표시하던 경로를 제거했다. 미산정·non-finite
값도 —이며 양수 원가에 근거한 실제 0% 수익률은 유지한다. 주식 투자 내
자산군 목록의 동일한 우측 비중 fallback도 —로 정리했다. 그 경로의 부동산은
별도 HOME 매입 근거를 받지 않으므로 미산정 상태다.

표시 helper는 값을 검증·선택만 한다. 금액, 원가, weight, 수익률 공식,
sorting, owner 집계, 대출 차감 정책, persistence는 바꾸지 않았다.
HOME summary에 기존 매입금액 합계를 display 근거로 추가 전달하며 새 금융
금액을 계산하거나 저장하지 않는다.

## 버전과 문서

- APP_VERSION, application-version meta, 화면 버전, service-worker cache를
  2.0.0으로 맞춘다. 기존 캐시 eligible/security 정책은 그대로다.
- 실제 변경한 wealth.js / wealth-layout.js / wealth-transaction-defaults.js /
  wealth-ui-density.css만 asset cache revision을 2.0.0으로 갱신한다.
  변경하지 않은 파일의 1.3.0/10.x query는 앱 버전이 아닌 과거 cache revision이다.
- README / PROJECT_STATE / ROADMAP / shared-color-system / CHANGELOG를 갱신한다.
  역사 릴리즈와 당시 검증 수치는 보존하며 현재 검증 결과로 재사용하지 않는다.
- Toss ARM64 설명은 ops/toss-auth/README.md와 vendor MIT/patch 문서를 연결한다.
  Docker·helper·인증 서비스·GitHub workflow는 이 branch에서 변경하지 않는다.

## Cleanup 근거

| 항목 | 정리 | 참조 확인 / 보존 계약 |
| --- | --- | --- |
| ASSET_CLASS_ORDER | 미사용 상수 제거 | base git grep에서 정의 1건만 존재. app/tests/docs 소비자 없음. 실제 정렬은 기존 weight 비교식이며 유지 |
| release-version 테스트 | 중복 조건을 asset별 map으로 정리 | index의 모든 CSS/JS ref에 대한 assertEqual 유지. 앞 조건에 가려진 중복 분기와 해당 set만 제거. 역사 changelog assertion 유지 |
| README KIS IPO 설명 | 현재 no-KIS source 계약으로 교정 | source_discovery.py / refresh_adapter.py priority 확인. 일반 KIS broker 기능과 역사 provenance 보존 |
| shared-color 문서 | 현재 inline 편집·7 calendar key·8색·bucket 저장 경로 반영 | 현재 shared picker/preference/planning/calendar source 계약 참조 |
| 옛 audit/phase/운영 자료 | 삭제하지 않음 | 역사 증거·운영 근거 보존. ui-shadow/ledger audit의 fallback/loader/observer는 숨겨졌다는 이유만으로 제거할 수 없음 |

파일 삭제는 **0개**. vendor/license/auth 문서, fixtures, import pipeline,
timeseries fallback, scheduler, 금융 서비스는 삭제·수정하지 않았다.

## 사용자 실행용 검증

실제 data/.env/credentials 및 금융 파일이 없는, **이번 변경을 포함한**
synthetic source copy에서 실행한다. 아래 명령은 작성만 했으며 Codex가
실행하지 않았다. Node와 기존 native Chrome test prerequisites가 필요하다.

PowerShell:

~~~powershell
$oldPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = "tests"
    python -m pytest -q tests/test_v2_ui_cleanup.py tests/test_release_version.py tests/test_service_worker_cache_guard.py tests/test_tax_account_holdings_regression.py tests/test_frontend_pension_irp_tax_correctness.py tests/test_dividend_official_source_static.py tests/test_financial_income_what_if_static.py tests/test_money_input_ux.py
    if ($LASTEXITCODE -ne 0) { throw "FOCUSED=FAIL" }

    python -m pytest -q tests/test_v2_ui_cleanup_chrome.py tests/test_defaults_interest_chrome.py tests/test_notification_asset_details.py tests/test_ui_density_chrome.py tests/test_color_preferences_chrome.py tests/test_invest_reload_chrome.py tests/test_pnl_first_visible_frame.py
    if ($LASTEXITCODE -ne 0) { throw "CHROME=FAIL" }

    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "FULL_PYTEST=FAIL" }
}
finally {
    $env:PYTHONPATH = $oldPythonPath
}

node --check app/static/wealth.js
node --check app/static/wealth-layout.js
node --check app/static/wealth-transaction-defaults.js
node --check app/static/sw.js
python -m py_compile app/main.py tests/test_release_version.py tests/test_service_worker_cache_guard.py tests/test_dividend_official_source_static.py tests/test_financial_income_what_if_static.py tests/test_money_input_ux.py tests/test_v2_ui_cleanup.py tests/test_v2_ui_cleanup_chrome.py
git diff --check
git status --short
~~~

각 syntax 명령의 exit code도 확인한다. Node 모델 테스트는 신규 및 기존
frontend tests에서 실행된다. Chrome matrix는 1280/390과 purple/white/OLED에서
title/badge 한 줄, 내부/page overflow, 기본계좌 명시적 지정/해제, 기존
비중·총액 불변과 미산정 수익률을 검증한다. 기존 assertion은 제거·완화하지 않았다.

사용자가 보고한 최신 main full green과 이 branch 검증은 별개다.
새 실패를 과거 baseline으로 자동 분류하지 말고 exact node/signature를
확인한다. 검증 전 responsive 성공·release gate PASS·실제 ARM64 QR 성공을
주장하지 않는다.
