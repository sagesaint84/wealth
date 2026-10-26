# v2.1.6 — #180 섹션 접기/펼치기 제거

## 소스와 범위

- 기준 `origin/main`: `b86d5d50dee3d6bf1cb306186f3ad1b08f7133c7` (시작 시 fetch 확인).
- 독립 worktree `v216-remove-section-collapse/wealth`, branch `codex/v216-remove-section-collapse`.
- APP_VERSION, HTML 메타·사용자 표시, 회귀 계약: **2.1.6**.
- 9개 섹션 버튼(market/summary/heatmap/holdings/records/accounts/pnl/dividend/ledger)을 HTML에서 삭제했다. 달력/IPO까지 포함하던 11개 SECTION_MAP과 저장·복원·이벤트·자동 펼침·부트스트랩 호출 및 전용 CSS를 삭제했다. CSS로 버튼을 숨기는 방법은 사용하지 않는다.
- 기존 `collapsed_sections` 저장값은 더 이상 읽거나 쓰지 않는다. 사용자의 브라우저 저장소를 삭제하는 migration은 추가하지 않는다. 잘못된 JSON·기존 전체 접힘 값에서도 정상 표시를 검증한다.
- 기존 패널/요소 ID 및 렌더러를 재사용한다. 실제 홈/투자/자산/머니 로그/설정 탭과 국민연금·버킷 편집·OCR·간편 붙여넣기·IPO 상세·알림 내역·위험 삭제 확인은 목적별 기능이므로 보존한다.
- 히트맵 resize의 기존 200ms debounce는 유지한다. 삭제한 collapse 검사와 존재하지 않는 `#heatmapPanel` 대신 실제 활성 투자 히트맵 탭을 확인한다. 숨긴 페이지/하위 탭 resize에서는 렌더하지 않는다. 차트·가족/계좌 필터·금융 계산식은 변경하지 않는다.
- 변경된 `wealth.js`, `wealth-layout.css`, `wealth-overrides.css`만 revision `2.1.6-expand1`. 다른 JS/CSS, Service Worker revision은 유지한다. 두 금융 UI 계약에 남아 있던 구 layout/core URL도 실제 revision과 일치시켰다. 중복 스크립트·로드 순서 검증은 유지한다.

## 자동 검증

검증은 합성 계정/금융 자료 및 loopback API를 사용한다. 실제 금융 데이터·환경 비밀·Toss 설정은 사용하지 않는다.

- 신규 Chromium 매트릭스: **17 passed** (정적 2 + 5개 너비 × 3개 테마 15). 너비 320/360/390/768/1280px, Purple/White/OLED. 옛 저장값 무효화가 아닌 무사용, 초기 API 중복 없음, 비활성 시장/주식/가계부 작업 지연, 홈 3탭·차트·실제 투자 하위 탭·자산 분류·머니 로그·IPO 이동, resize, 중복 ID/가로 overflow/JS 오류, 새로고침을 확인한다.
- Static transport PR workflow에 신규 17건을 포함하고 skip/failure/error 없이 실제 실행된 수를 검증한다.
- 첫 확대 회귀: **722 passed / 1 failed / 1 skipped, 129 subtests passed**. 실패는 `test_docker_offline_native_dependencies_and_existing_auth_smoke_preserved`가 PR #171 이전의 직접 RUN 문자열만 기대하던 문제다. 기준 main의 함수·Dockerfile·requirements를 임시 합성 경로에서 그대로 실행해 같은 실패를 재현했다. 세 파일이 기준과 같음을 확인했다. Dockerfile/실행 코드는 변경하지 않고 테스트만 현재 offline RUN 블록의 smoke 명령·초기 상태·실패 코드 수집·최종 exit 보존을 검증하도록 동기화했다. 기존 검증을 삭제하거나 기준을 낮추지 않았다.
- 최종 확대 회귀: **818 passed / 1 skipped / 129 subtests passed**, 591.57초. 기존 범위 전체 재실행에 가계부 renderer·IPO lifecycle/compat·income chart·static transport 단위 검증을 추가했다. 수정한 Docker 계약도 PASS다. 최종 버전·문서 계약 강화 후 별도 재확인 **4 passed** (중복 합산하지 않음). 경고 2건은 기존 Starlette deprecation 및 OCR 과대 이미지 거부 테스트의 Pillow 경고다.
- Windows Unix IPC 통합 1건은 Linux 전용 skip이다. 실제 Unix IPC 및 격리 Docker/Compose는 기존 Linux CI에서 판정해야 한다.
- 전체 pytest: **NOT_RUN**.
- 구문 `node --check app/static/wealth.js`, `git diff --check`: PASS.
- 제거 대상 토큰을 모든 app/static HTML/JS/CSS에서 검사: 0건. 남은 접기 표현은 목적별 상세 보기 기능이다. updater/permission/worker/IPC/Compose 소스 diff는 없다.

## 초기 표시·요청 보호

- 시작 화면에서 dashboard/refresh-prices/planning snapshot API 각각 1회, 시장·주식 DOM·가계부 초기 작업 0회 검증. 기존 startup/opt-in telemetry·첫 페인트·딥링크·Service Worker 검사를 유지한다.
- LF 정규화 소스 크기 비교(줄바꿈 차이를 비용으로 계산하지 않음): index -1,439B, core JS -3,892B, layout CSS -73B, overrides CSS -3,274B. 같은 정규화 gzip 기준 각각 -168/-1,098/-15/-707B. 이는 전송 크기 참고이며 시간 성능 PASS를 의미하지 않는다.
- 이전 #177 성능 FAIL/HOLD 기록·원본 표본·보호 worktree는 변경하거나 삭제하지 않는다. 새 시간 벤치마크/엄격한 성능 게이트 판정은 이번 범위에서 **NOT_RUN**.

## 최종 로컬 판정

- SOURCE_GATE=PASS, FUNCTIONAL_GATE=PASS, REGRESSION_GATE=LOCAL_PASS (Unix IPC 1건은 Linux CI 대기).
- MOBILE_CHROMIUM_GATE=PASS (320/360/390/768/1280px, Purple/White/OLED).
- INITIAL_RENDER_API_GATE=PASS, DEAD_CODE_GATE=PASS, CHANGE_SCOPE_GATE=PASS.
- FULL_PYTEST=NOT_RUN, NUMERIC_PERFORMANCE_GATE=NOT_RUN.
- CI_STATUS=WEB_CHATGPT_REVIEW_PENDING. 로컬 결과와 최신 원격 HEAD의 CI 결과를 구분한다.
- 실제 호스트 설치/Oracle/운영 브라우저/이미지 정리=NOT_RUN.
- 원본 첫 실패 로그와 최종 XML/log는 로컬 임시 디렉터리의 `wealth-v216-regression*`에 보존하며 커밋하지 않는다. 가계부 테스트가 생성한 합성 PNG 2개도 로컬 임시 디렉터리의 `wealth-v216-chromium-evidence-20261026`으로 보존하고 커밋에서 제외했다. 원격에 실제 금융 데이터·인증정보·대용량 trace를 포함하지 않는다.

## 승인·운영 게이트

- 별도 **Draft PR**으로 사용자 실제 화면 검증과 승인을 기다린다. CI 결과 판정은 요청대로 웹 ChatGPT 담당이며, 로컬 pytest PASS를 원격 CI PASS로 쓰지 않는다.
- MERGE_GATE=HOLD_USER_APPROVAL. 이번 작업에서 main 병합 및 운영 배포하지 않는다.
- Oracle v2.1.5 앱 배포 PASS와 updater 확인 RELEASE_UNAVAILABLE은 별도 상태다. [#186](https://github.com/sagesaint84/wealth/issues/186) 해결 전 **v2.1.6 운영 원클릭 설치 금지**. 실제 운영 브라우저/서버 검증은 사용자 담당.
- 기존 host worker/IPC/Compose 재설치·수정·state 조작·이미지 정리 없음. 금융 데이터와 Toss 마운트·인증정보·롤백 이미지 보존.
- 미국 CNN 공포탐욕은 v2.1.7 #178 별도 작업이며 이번 PR에 포함하지 않는다.
