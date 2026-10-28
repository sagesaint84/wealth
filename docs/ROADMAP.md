# Wealth Roadmap

## 2026-10-28 — v2.1.9 개발 후보

**Wealth v2.1.9 후보**는 운영 v2.1.8 사용자 확인 기준 main `72a7b0c97bfa6e94e6d5b38d9710c2439d9c4dd7`에서 별도 개발한다. 기존 v2.1.8 이력은 아래에 보존한다. 설치·정상 확인·정리만 비밀번호 재입력 없이 현재 세션/실제 권한/CSRF/Origin/일회성 작업 승인으로 처리하며, 관리자 권한 부여·회수의 비밀번호 재인증은 유지한다. 공포탐욕 명칭·표시 설정·은행 4개 금액 카드·공모주 상세 배치를 개선한다. 금융 서비스/host updater·Oracle·GHCR은 변경하지 않는다. 새 버전은 개발 후보이며 CI/병합/운영 완료로 간주하지 않는다. 상세: UI_UX_V219.md.

**최신 PowerShell 집중 회귀=63 PASS / DAY 38 PASS** (277.74초, 동적 차트 캐시 수정 이후). 과거 DAY 단발성 실패 원인은 UNCONFIRMED이며 실패 증거는 보존한다. 일 수익률은 사용자 확정식 `당일 가격변동 손익 ÷ 현재 총 주식자산 × 100`을 동일 가족 범위에서 계산하며, 결측·부분 데이터·분모 0 이하에서는 `—`다. 기존 IPO 배정수량 저장을 유지하고 신청수량은 추가하지 않는다. 새 원격 Linux CI는 NOT_RUN이며 운영 v2.1.7은 유지한다.

## 2026-10-28 — v2.1.8 개발 후보 / 사용자 로컬 검토 대기

**Wealth v2.1.8 후보**는 운영 배포·사용자 수락된 v2.1.7 main `c03256dcb8b0ece7c558637c94e7cc0aa422426d`에서 독립 개발합니다(운영 완료는 사용자 제공 근거). #192 통합 및 이전 검증 이력은 아래에 보존합니다. 기존 DAY 간헐 실패 원인은 UNCONFIRMED이며 이후 PASS로 원인 해결을 주장하지 않습니다.

- 업데이트 작업 기록은 화면 DOM/렌더만 제거하고 서버 job·감사·복구 이력과 보호 이미지/재인증/CSRF/preview token 계약을 유지합니다. 삭제 후보가 없으면 비활성 상태와 보호 이유를 표시합니다.
- 홈·주식투자 설명 간소화, 순자산/주식기록 금액 위계, 평가손익과 시장 일 가격손익 구분을 유지합니다. 일 수익률은 동일 조회의 현재 총 주식자산을 분모로 소수점 둘째 자리까지 표시하며 기록 대비 변화율을 재사용하지 않습니다. 결측/부분 데이터에서는 `—`입니다.
- CNN 비공식 중계는 카드·출처 상세를 사용합니다. 표시 카드 선택은 **현재 브라우저·로그인 계정별 localStorage**이며 서버/다른 브라우저로 동기화하지 않습니다. 새 카드는 기본 표시합니다. 신호는 홈 주요지수 한 곳에서만 조회하며 수식/TTL/가족·늦은 응답 방어를 유지합니다.
- 목표 버킷만 기존 revision/API로 직접 편집합니다. 현재 비중/분류/자산/금융 기록은 읽기 전용입니다. 캘린더 공모주는 기존 상세의 계좌·배정·매도 연결 렌더러와 검증 API를 공유합니다. **사용자 요구는 기존 배정수량 저장이며 신청수량 필드는 추가하지 않습니다.** 실현손익 원본을 중복 저장하거나 자동 생성하지 않습니다.
- APP_VERSION/표시/계약은 **2.1.8**, wealth.js는 **2.1.8-ui2**, 나머지 변경 정적 자산 9개는 **2.1.8-ui1**입니다. Service Worker 및 미변경 자산 revision은 유지합니다. [단계별 구현·검증 및 잔여 위험](UI_UX_V218.md).
- COMMIT/PUSH=NOT_RUN, PR=NOT_CREATED, 새 Linux CI=NOT_RUN, MERGE=HOLD, Git 태그/GHCR 발행/Oracle 설치=NOT_RUN. 실제 운영 v2.1.7·호스트 updater·금융/Toss/Compose/state/pin/IPC는 변경하지 않습니다. 아래 버전별 상태 문구는 당시 이력입니다.

## 2026-10-28 — v2.1.7 통합 후보 최종 정리 / 운영 미배포

- **APP_VERSION=2.1.7 릴리스 후보**, [PR #192](https://github.com/sagesaint84/wealth/pull/192)는 **Draft / 미병합**이다. 원래 통합 커밋 `f19ab03c7b07dbeaaa7608e2cef40687d5ebfc49`의 27개 변경 파일을 유지한다. 원본 #190의 코드 `fd8b7045`·문서 `d8d8434` 및 #191 `3897f0b`의 기술 계약과 검증 이력을 보존한다. 정적 자산 revision `2.1.7-cnn1` 및 기능 코드는 이번 정리에서 변경하지 않는다.
- **Windows 통합 근거:** Unit **369 PASS / 예상 Unix IPC SKIP 1**, Chromium **132 PASS**. DAY 전체 모듈 **38 PASS**. 기존 Starlette 경고 1건. 이는 이미 완료된 검증이며 이번 정리 후 전체 통합 검증을 반복했다는 뜻이 아니다.
- **진단 커밋 `20b6c3565f8d75bb0d3ed83a18682323042bc108`의 Linux CI:** 전체 워크플로 **4/4 SUCCESS**, Static transport **567 PASS / SKIP 0**, DAY **38 PASS**, CNN Chromium **15 PASS**, Toss **AMD64 / ARM64 PASS**, System update **synthetic IPC / isolated Docker PASS**, IPO schedule **PASS**. [Static transport 실행 40555628384](https://github.com/sagesaint84/wealth/actions/runs/40555628384). Windows 및 Linux 결과는 사용자 확인 근거다.
- **이전 Linux DAY 실패 ROOT_CAUSE=UNCONFIRMED.** 위 Linux 성공은 임시 진단 코드가 포함된 커밋의 결과다. 이번에는 DAY 테스트만 원래 통합 커밋과 동일한 blob으로 복원하여 instrumentation을 제거한다. 진단 커밋은 Git 이력에 보존한다. 정리가 원인 해결 또는 단순 flaky 판정의 근거는 아니다. **진단 제거 이후 새 HEAD CI=NOT_RUN**이며 위 PASS를 승계하지 않는다. 정리 후 로컬 집중 검증 결과는 별도 실행 기록으로 구분한다.
- **Oracle 읽기 전용 사전검사=PASS (사용자 제공):** 운영 **v2.1.6 유지**, 실행 이미지 SHA/digest 일치, Running=true / RestartCount=0, HTTP **307**, 여유 공간 **33G**. updater **active/running**, 진행 중 job **0**, rollback_failed job **0**, 마지막 설치 **succeeded/confirmed**. 오래된 rollback 참조가 남아 있고 해당 이미지는 **MISSING**이다. 참조를 해제하거나 이미지를 다시 받지 않았다.
- **CNN outbound:** Oracle에서 relay **HTTP 200 / 구조·신선도 PASS**. 이 사전검사는 v2.1.7 앱의 운영 설치·화면 수락을 의미하지 않는다. 오류·만료 시 숫자 숨김과 개인용 비공식 중계 표기를 유지한다.
- **운영 게이트:** HOST_MAINTENANCE=NOT_RUN, Git 태그=**NOT_CREATED**, main 병합=**NOT_RUN**, GHCR v2.1.7=**NOT_RELEASED**, Oracle v2.1.7=**NOT_DEPLOYED**. 앱 이미지 배포와 `/opt/wealth-updater` 호스트 코드 갱신은 별도 승인·검증 대상이다. 컨테이너/worker/systemd/state/Compose/pin/IPC key/금융·Toss 데이터/이미지는 이번 정리에서 변경하지 않는다. 원본 PR #190/#191은 보존한다.

아래 기존 후보 작성·버전별 검증/배포 상태 문구는 **당시 이력**이며, 현재 상태는 위 기록을 우선한다. 기존 기술 계약과 승인 후 적용·복구 절차는 계속 유효하다.

## 2026-10-28 — v2.1.7 통합 후보

1. **현재 운영 v2.1.6:** 사용자 원클릭 업데이트·수락 PASS, 기존 고정 이미지 유지.
2. **v2.1.7 통합 검증 대기:** #191 CNN 개인용 비공식 GitHub 중계 + #190 누락 rollback 참조 root 전용 도구를 새 독립 worktree에서 통합했다. APP_VERSION 2.1.7과 변경 자산 revision/버전 계약을 맞춘 로컬 후보다. 각 PR 사전 PASS와 구분하여 통합 테스트·새 CI는 NOT_RUN이다.
3. 사용자 PowerShell 통합 PASS → 별도 승인 → 통합 commit/push/Draft PR → 새 HEAD CI·사용자 출시 판단 순으로 진행한다. 그 전 main 병합·GHCR 발행·Oracle 작업 없음. 기존 두 Draft PR은 보존하며 향후 통합 병합 후 중복 병합하지 않는다.
4. 호스트 `/opt/wealth-updater` 코드 적용·서비스 조작·rollback state 변경은 별도의 읽기 전용 감사와 사용자 승인 후에만 검토한다. 앱 이미지 릴리스가 호스트 코드를 자동 갱신하지 않는다.
5. 이 범위를 마치면 추가 기능을 시작하지 않고 사용자와 다음 방향을 재상담한다. 아래 일정은 과거 기록이다.

## 2026-10-27 — v2.1.6 통합 릴리스 검증 대기

- v2.1.6 #187은 섹션 접기 제거와 #188의 #186 GHCR 검증기 수정을 통합한 후보로 진행한다. 기존 보안·Digest 검증을 유지하며 버전은 2.1.6이다. 통합 PowerShell PASS 후 커밋·푸시, 새 HEAD CI는 웹 ChatGPT 검증, 최종 승인·운영 확인은 사용자 담당이다.
- #187/#188 Draft 유지. 사용자 승인 전 병합·운영 배포 금지. #186 운영 검증 전 원클릭 설치 보류. worker 재설치/재시작·이미지 정리 없음. 통합 main 병합 후 #188은 중복 병합하지 않고 이력을 기록해 정리한다.
- CNN 미국 공포탐욕은 여전히 v2.1.7 별도 작업이다. [통합 상태](SECTION_EXPANDED_V216.md). 아래 일정은 통합 전 이력이다.

## 2026-10-26 — v2.1.6 #180 구현 후보와 운영 게이트

1. **v2.1.5 #184:** 기준 main b86d5d50dee3d6bf1cb306186f3ad1b08f7133c7에 반영. Oracle 앱 배포 PASS는 사용자 확인 상태. 권한 위임·관리자 화면과 기존 host updater/IPC를 보존한다.
2. **v2.1.6 #180:** 섹션 전체 접기/펼치기 실제 제거. 독립 worktree·Draft 검토 대상. CI 판단은 웹 ChatGPT, 실제 화면·최종 승인은 사용자 담당. 사용자 승인 전 병합·배포 금지. **#186 RELEASE_UNAVAILABLE 해결 전 운영 원클릭 설치 금지.**
3. **v2.1.7 #178:** 미국 CNN 공포탐욕 별도 작업. 이번 변경에 포함하지 않는다. 이후 사용자와 재상담한다.

[구현·검증 기록](SECTION_EXPANDED_V216.md). 아래 일정은 당시 이력이며 이 항목이 현재 우선한다.

## 2026-10-26 — #184에 따른 최신 출시 순서

1. **v2.1.5 #184 — 관리자 UI 접근 + 선택 사용자 updater/이미지 정리 위임.** 별도 Draft 검증 중, role=user 유지. 기존 worker/IPC 변경 없음. 사용자 승인 후 앱 수동 digest 배포로 실제 화면 확인.
2. **v2.1.6 #180 — 접기/펼치기 제거.** 첫 실제 원클릭 설치 검증 예정. 이 hotfix 확정 후 최신 main에서 별도 worktree/PR.
3. **v2.1.7 #178 — 미국 CNN 공포탐욕.** 주요지수 영역만, 한국 지수 제외. 그 후 사용자 상담.

최종 정책은 system_update 위임에 cleanup까지 포함한다. admin-only cleanup 초안은 철회됐다. [권한/운영 계약](UPDATER_PERMISSIONS_V215.md). 아래 이전 버전 예약은 날짜별 과거 이력이다.


## 2026-10-26 — 확정 순차 개발 #182

1. **v2.1.4 / #181 시스템 업데이트 — 구현·격리 검증 중, Draft 대상.** 조회 전용과 호스트 실행기 테스트를 분리한다. 운영 수동 설치·사용자 화면 검증·새 HEAD CI·출시 승인 전 병합/배포하지 않는다.
2. **v2.1.5 / #180 접기/펼치기 제거 — 대기.** 첫 변경 확정 최신 main에서 별도 worktree/PR. 필요한 상세 입력/OCR/위험 확인은 보존한다.
3. **v2.1.6 / #178 미국 CNN — 대기.** 두 번째 확정 최신 main에서 실제 응답 확인 후 주요지수 안에만 구현. 한국 지수 제외. 세 기능 후 개발 범위를 추가하지 않고 사용자와 상담한다.

각 독립 코드 출시에서 APP_VERSION·문서·표시·테스트 계약을 동기화하고 변경 자산만 갱신한다. [시스템 업데이트 설계·운영 경계](SYSTEM_UPDATE.md). 아래 날짜별 항목은 당시 이력이며 현재 우선순위는 이 목록을 따른다.


## 2026-10-26 — PR #177 한정 사용자 출시 승인

PERFORMANCE_GATE=FAIL/HOLD를 유지한 채 RELEASE_EXCEPTION=USER_APPROVED_PR177_ONLY로 출시 절차를 진행한다. 이전 HOLD 기록은 당시 판단이다. 새 HEAD 필수 CI 전부 SUCCESS, 정확한 Squash Merge 및 GHCR 검증이 선행되어야 하며 Oracle 배포·운영 smoke는 실제 실행 여부를 별도로 기록한다. [릴리스 기록](PR177_RELEASE.md). PR #179는 병합하지 않는다.

## 현재 사용자 요구 우선순위 — 2026-10-25 (계획, 미배포)

- **홈 3탭 개편 — 구현 후보, 미배포·성능 HOLD**: 현행 홈에서 위·중간·아래 순서로 배치된 **자산 포트폴리오 / 순자산 추이 / 주요지수**를 기존 섹션·데이터·렌더러 그대로 홈 내부의 3개 탭으로 분리한다. 별도 신규 시장심리·투자신호 탭을 만드는 요청이 아니다. 가족/시세/계좌 동기화, 순자산 차트·기간·기록 CRUD, 주요지수 동작 보존. [요구사항 #176](https://github.com/sagesaint84/wealth/issues/176).
- **국장/미장 공포탐욕지수 점수화 — 미착수**: 실제 0~100 점수·단계·기준 시각·출처·조회 실패 표시의 공식 데이터/계산 계약 검토 후 구현. PR #169에서 미국 CNN 공식 페이지 링크만 제공했고 실제 점수 자동 조회 및 한국 지수 산식/조회는 미구현.
- **배당·이자 로딩 성능 후속 분석 — 미착수**: 합성 데이터로 화면 진입/재진입/필터/API 중복/차트 표시를 먼저 측정. 기존 정확성·소유자 격리·요청 공유·늦은 응답 방어 보존.
- **사용자 안내서 — PR #165 병합 완료**: README를 새 사용자의 기능·설정 사용 설명서로 재작성. 기존 배포/개발 이력은 별도 보존. 기준 main `940a420`에 포함되며 홈 탭 구현에 맞춰 안내를 갱신한다.
- **보유종목 SMA20/SMA50 이탈·골든/데드크로스 — 기존 개발 완료**: PR #169 이후 후속 수정 PR #170/#172/#173까지 병합 및 운영 반영됨. 아래 2026-10-22의 '미착수' 문구는 당시 작성된 과거 기록임.
- **정리 보호**: PR #161 민감 ignored 파일·잔여 진단 로그/금융 데이터/Toss 설정·운영 Compose/롤백 자료를 일괄 삭제하지 않는다. 완료 PR #175 Worktree와 브랜치는 2026-10-25 사용자 로그 기준 정리됨.


## 현재 완료 단계 — 2026-10-22 / v2.1.3 Oracle 배포

- **완료**: [PR #163](https://github.com/sagesaint84/wealth/pull/163) Squash Merge `f9cb3cd87644fc8a51cd25488802878ee680613a`; 비활성 홈 초기 읽기 지연/공유, 배당 차트 준비-표시 순서·늦은 응답 방어. 코드 APP_VERSION 2.1.3, 변경 JS·SW revision `2.1.3-p0`; IPO·가계부·gzip·Toss WTS 유지.
- **완료**: PR CI **4/4 SUCCESS**, 44개 release/SW 실제 Chrome 집중 검사 PASS, GHCR [39741300759](https://github.com/sagesaint84/wealth/actions/runs/39741300759) 성공, ARM64·AMD64 manifest `sha256:f2683c22acd77e8fe8f03b11c5bbfcf60115c095c7a242069a81c4d2ba64d1d8`. Oracle v2.1.3 배포·데이터/Toss/HTTP 307/gzip/restart0 확인(사용자 SSH 로그), 브라우저 7/7 PASS(사용자 보고), v2.1.2 롤백 이미지 보존.
- **남은 릴리스 기록**: [`v2.1.3` annotated Git 태그](https://github.com/sagesaint84/wealth/tree/v2.1.3)는 배포 커밋 `f9cb3cd87644fc8a51cd25488802878ee680613a`를 대상으로 원격 등록·검증 **완료**. GitHub Release는 **아직 미발행**(2026-10-22 확인). v2.1.2 태그는 보존. 이 절 아래의 미배포 후보 및 HOLD 표현은 과거 작업 당시 기록이다.
- **남은 품질 검토**: 전체 v2.1.3 pytest NOT_RUN. 360px 동일 HTTP 캐시 A/B에서 초기 API 15→12 감소 재현, 합산 8 vs 8 중앙값 자산 -82.9ms·ready -117.2ms이나 개별 실행 변동으로 **PERFORMANCE_NUMERIC_GATE=REVIEW_REQUIRED**. 해당 PR 조건부 머지·배포 승인과 수치 무회귀 PASS를 구분한다. 후속 성능 분석은 증거·환경 통제를 갖추어 별도 계획으로 진행.
- **다음 개발 백로그(미착수)**: 국장/미장 공포탐욕지수, 보유종목 20/50일 이동평균선 이탈 및 데드크로스. 기존 P0/Route1 보호 worktree·실제 운영 데이터·Toss 설정 및 증거 파일 정리는 별도 검토 없이 수행하지 않는다.


## 과거 완료 단계 — 2026-10-21 / PR #161 운영 배포

- **완료**: [PR #161](https://github.com/sagesaint84/wealth/pull/161) 초기 deep-link 라우팅, 숨김 투자 렌더 지연, 가계부 요청 공유·오래된 응답 차단, 검증된 미사용 UI 정리. Squash Merge `fc0bb1092b6d55ee21a786b0d295c48bdcba4c14`, 앱 **v2.1.2**, 정적 자산 **2.1.2-route1**.
- **완료**: GitHub CI 4/4 PASS, [GHCR 이미지](https://github.com/sagesaint84/wealth/actions/runs/39572486587) SUCCESS (`ghcr.io/sagesaint84/wealth:fc0bb10`, Digest `sha256:b82b79c9a3e781810a9c823237473fe09549fa72825c5756c5c97b0774cd05b9`), Oracle Docker 실행 이미지·영구/Toss 마운트·HTTP 307 PASS (사용자 출력), 운영 브라우저 5/5 PASS (사용자 보고).
- **잔존 위험**: Windows 전체 pytest 4424 PASS / 1 FAIL / 5 SKIP; 모바일 DAY 후속 matrix 4/4 PASS이나 실패 원인 UNCONFIRMED. 모바일 첫 자산 약 +488ms/readiness 약 +532ms로 **성능 게이트 FAIL**. **PR #161 한정 승인 예외**로 운영 배포했으며 후속 작업에서 별도 해결·재평가 필요.
- **다음 개발**: 보호된 **v2.1.3 P0**(원본27/통합33/최소2)를 손실 없이 검토하고 별도 PR·게이트로 진행. 모바일 실측 회귀 위험은 보존·판단하고, 국장/미장 공포탐욕지수·보유종목 20/50일선 이탈/데드크로스는 미착수 백로그로 유지.
- **문서 이력**: 아래 '운영 미배포'·'HOLD' 표기는 출시 전 검증 경과이며, 현재 운영 배포와 혼동하지 않는다.

- **태그·Release 현황(2026-10-22, 사용자 제공)**: 운영 배포 커밋 `fc0bb1092b6d55ee21a786b0d295c48bdcba4c14`에 Git 태그 `v2.1.2` 등록 완료. **GitHub Release는 아직 생성되지 않았다.** 아래 과거 태그 미등록 문구는 당시 조회 기록으로 보존한다.

## 과거 릴리스 준비 단계 — v2.1.3 P0 (2026-10-22 당시)

기준 main `9ff5c9719454cb7a0a4b9cd3d18e489158b7b36f`, 작업 브랜치 `codex/v213-mainline-p0-integration`, 릴리스 준비 시작 HEAD `7ade00e68729fcec67a68f288c9efc00e71bcba2`. 사용자 제공 현황은 [Draft PR #163](https://github.com/sagesaint84/wealth/pull/163), 커밋 `7ade00e`, **CI 4/4 PASS**다. 이후의 버전 정리·SW 실동작 테스트 추가는 이 HEAD 위의 미커밋 변경이며 해당 CI 결과에 포함되지 않는다.

**Wealth v2.1.3**을 코드상 출시 버전으로 준비한다. FastAPI와 HTML 앱 버전·사용자 표시를 **2.1.3**으로 맞추지만 **미머지·미배포 후보**다. 운영은 여전히 PR #161의 **v2.1.2**다. 변경된 JS와 application-assets-revision은 **2.1.3-p0**, SW 캐시는 **wealth-cache-v2.1.3-p0**를 유지한다. 변경하지 않은 layout JS/CSS의 **2.1.2-route1** 및 IPO·캘린더의 독립 revision은 유지한다. 정적 캐시 식별자를 앱 출시 버전과 일괄 동기화하지 않는다.

반영 범위는 자산 준비 후 활성 화면 조회, 같은 범위의 진행 중 GET 공유·쓰기 후 무효화, 오래된 응답과 숨김 차트 작업 방어, 배당 데이터 준비 후 실제 폭에서 차트 생성이다. 배당 준비 결과·원천 캐시·확정 차트의 쓰기 세대를 검사하며, 최신 main의 가계부 요청 공유와 투자 화면 지연 렌더를 보존한다. DAY 계산에 공유되는 자산 기록의 초기 조회 생략은 보류했다. PR #161 화면·초기 라우팅, PR #162 운영 기록, 기존 IPO 및 gzip 전송을 유지한다.

**기능 집중 검증(사용자 제공)**: 1차 **50 PASS**, 2차 **54 PASS**, 금융 집중 **22 PASS**, 리뷰 수정 검증 **15 PASS**, 수정 후 차트 회귀 **20 PASS**. 각 검사 당시 `git diff --check`도 **PASS**였다. 중복 가능성이 있어 고유 통과 건수로 합산하지 않는다. **이번 통합 후보의 전체 pytest는 미실행**이다. 이번 버전 정리 후 검사와 새 `test_p0_service_worker_real_browser_cache_and_navigation`의 실제 Chromium 결과는 **미확정/NOT_RUN**이며 사용자가 별도로 실행한다. 새 검사는 실제 SW 등록·활성화·제어, 첫 홈 방문/정상 새로고침, Cache Storage의 API·JS·CSS 제외, 배당 이동/새로고침을 합성 데이터로 확인하도록 작성했다. 이 기록은 SW 실동작 PASS를 의미하지 않는다.

**최종 HTTP 캐시 통일 제한 성능 비교(2026-10-22, 사용자 실행)**: 360px Chromium, gzip, CPU 4배 제한, 네트워크 40ms 지연, JS·CSS HTTP 캐시 **53/53 적중**, Service Worker 우회, 합성 데이터의 동일 조건으로 두 차례 실행했다.

| 실행 | 첫 자산 표시 차이(P0 − main) | 준비 완료 차이(P0 − main) | API 요청 차이 |
|---|---:|---:|---:|
| 1차 중앙값 | -196.3ms | -219.4ms | -3건 |
| 2차 중앙값 | +34.6ms | +15.5ms | -3건 |

두 실행을 합친 **각 8개 표본의 중앙값**:

| 항목 | main | P0 | 차이(P0 − main) |
|---|---:|---:|---:|
| 첫 자산 표시 | 2239.5ms | 2156.6ms | -82.9ms |
| 준비 완료 | 2589.1ms | 2471.9ms | -117.2ms |

**캐시 조건 검증 PASS**, 초기 API 요청 3건 감소는 두 실행에서 재현됐다. 큰 성능 회귀는 관찰되지 않았으나 실행 간 편차가 있어 개선을 확정하지 않는다. SW를 우회한 결과이므로 SW 실동작 검증과 구분한다. 기존 모바일 warm-start 성능 위험을 해소한 것으로 판정하지 않으며 **PERFORMANCE_NUMERIC_GATE=REVIEW_REQUIRED**를 유지한다. **PR #161의 성능 예외 승인은 승계하지 않는다.** 동일 벤치마크는 재실행하지 않았다.

이전 비교 이력(HTTP 캐시 통일 전, 별도 조건)은 보존한다: 운영 main/P0 각 3회, 360px·gzip·CPU 4배·네트워크 40ms·캐시 우회·합성 데이터에서 첫 자산 3901.7/3841.8ms(-59.9ms), 준비 완료 4465.6/4223.6ms(-242.0ms), FCP 616/632ms(+16ms), API 15/12건(-3건), JS·CSS 429512/436343B(+6831B)였다. 개별 변동과 main→P0 고정 순서의 영향 가능성이 있어 개선 확정 근거로 삼지 않으며, 위 HTTP 캐시 통일 결과와 표본을 합치지 않는다.

기존 P0 후보의 CI 대체안은 이관하지 않았으며 최신 main의 IPO·gzip CI 목록을 유지한다. 원본·구 통합·최소·Route1 worktree와 PNG 증거는 변경하지 않았다. 이 단계에서는 commit/push, PR Ready, merge, 태그 생성, 운영 배포를 수행하지 않는다.

## 과거 검토 기록 — PR #161 병합 전 상태 (현재 운영 상태 아님)

기준 main `99277956dc3c9e6383b533bd2efba259c1418cae`, 브랜치 `codex/v212-initial-deeplink-paint-fix`. 운영은 앱 **v2.1.2 / home1** 그대로이며 미커밋 후보의 변경 core JS와 layout CSS/JS·SW assets는 **2.1.2-route1**이다. v2.1.3 P0 27/33/2 작업을 포함하지 않는다.

공통 순자산·실현손익 계산 및 원천 상태 갱신은 유지하고, 주식 분류/히트맵/보유종목 DOM은 주식 화면 첫 진입 또는 dashboard 데이터 변경 시 렌더한다. 같은 데이터로 재방문할 때 중복 렌더를 생략한다. 기존 히트맵은 이미 숨김 화면 방어가 있었으므로 이를 신규 개선으로 중복 주장하지 않는다. 가계부는 해당 화면 진입 시 조회하며 같은 사용자·소유자·연월의 진행 중 요청만 공유한다. 사용자/소유자/기간/요청 순서가 바뀐 응답은 폐기하고 쓰기 시 기존 읽기를 무효화한다. 완료 결과를 금융 캐시로 재사용하지 않는다.

주식 기록은 DAY 기준 계산과 차트가 공유하고, 예적금·보험·부동산은 원천 상태를 갱신하므로 유지했다. 가족 조회 병렬화 및 후속 Promise.allSettled도 이미 존재해 중복 구현하지 않았다. 시세 성공→dashboard 주식 스냅샷→snapshot-all 순서 및 실패 시 자동 기록 방어는 그대로다. 초기 라우트/접근성/history는 유지하고 동일 text/aria/dataset 기록만 조건부 처리했다. 미사용 layout views 별칭은 참조 확인 후 제거했다.

검증 상태: 집중 결과는 표적13 PASS, 기존 회귀179 PASS/34 subtests(DAY38 포함), 스냅샷3 PASS이며 중복 실행 건수는 합산하지 않는다. 실제 앱 인증·세션·가족/사용자 격리 E2E24 PASS. 전체 pytest는 정확1회 실행하여 **4421 PASS / 4 FAIL / 5 SKIP / 888 subtests PASS**였다. 실패4건은 이전 CSS revision 기대값2건, 이동 전 메뉴 파일 참조1건, Node 샌드박스 의존성 누락1건이었다. 테스트 계약만 보완한 관련4모듈은 **20 PASS**이며 전체 pytest는 재실행하지 않았다. 최초 전체 실패 결과는 보존하고 전체 PASS로 재분류하지 않는다. 최소 비교1회(390/1280 A/B 각first1+warm1)는 완료했고 재측정하지 않는다. 모바일warm FCP220→248ms, 자산1528.5→2016.3ms, readiness1861.6→2393.1ms, CLS0.0210155→0.0352354였고 PCwarm은 FCP88→72ms, 자산204.3→239.6ms, readiness282.2→291.2ms였다. 초기API16→15/숨김주식DOM 미생성은 확인했으나 속도 개선은 입증하지 못했다. **PERFORMANCE_NUMERIC_GATE=FAIL**, **FUNCTIONAL_GATE=이전 집중 검증 PASS / 아래 최종 전체 결과 참조**, **USABILITY_GATE=HOLD**로 모바일 사용성 위험은 사용자 검토 대상으로 남긴다. 기존 수치 실패를 완화하거나 추가 좋은 표본을 수집하지 않는다. 기존 성능 FAIL/HOLD는 아래 이력으로 보존하며 수치 무회귀 PASS로 재분류하지 않는다. 구조 개선 후 최소 비교는 390/1280 A/B 각 최초1+warm1 한 번만 수행하고 반복하지 않는다. 기능·사용성·숫자 게이트를 분리하며 최종 출시 결정은 **USER_APPROVAL_REQUIRED**다. Commit/push/PR/merge/GHCR/Oracle/Compose 변경은 미실행이다.

후속 개발: 국장/미장 공포탐욕지수, 보유종목 20일·50일선 이탈 및 데드크로스는 계획으로만 유지하며 이번 앱 변경에는 포함하지 않는다.

최종 품질 정리: **TEST_CONTRACT_REVIEW=PASS**. 단일 exact stylesheet 링크/revision, 소유자별 계좌·보유종목 정확 결과, HTML 메뉴5개 검증 유지. 계약 보완 후 승인된 최종 전체 pytest 별도1회 결과는 **4424 PASS / 1 FAIL / 5 SKIP / 888 subtests PASS (1651.71초)**다. 실패 `test_native_daily_pointer_accuracy[True-dividend]`는 모바일 배당 DAY 차트의 상세 선택·선택 막대·기하 구조 검사 이후 수집 이벤트에서 pointerdown을 찾지 못한 StopIteration이다. 원인 UNCONFIRMED이며 과거 DAY 실패와 같은 원인이라고 단정하지 않는다. 자동 패치·재실행 없음. **FINAL_FULL_PYTEST=FAIL, FUNCTIONAL_GATE=HOLD, PR_PREPARATION=HOLD, RELEASE_GATE=HOLD**. 기존 인증 E2E24 및 합성 금융 검증 PASS는 기존 범위의 결과이며 전체 기능 PASS를 뜻하지 않는다. 기존 모바일 기능 경로 증거는 유지하되 자산 약+488ms/readiness 약+532ms는 단일 비교의 미해결 위험이다. 반복 재현으로 단정하지 않으며 PERFORMANCE_NUMERIC_GATE=FAIL을 유지한다. 이번 단계 앱·테스트·CI 변경 및 새 성능 측정은 0개다. 운영 v2.1.2/home1과 미배포 후보 v2.1.2/route1을 구분한다.

### 이전 단계 이력 — 아래는 구조 개선 전 후보의 측정·검증 기록


기준 main `99277956dc3c9e6383b533bd2efba259c1418cae`, 브랜치 `codex/v212-initial-deeplink-paint-fix`. 운영은 PR #159의 앱 **v2.1.2 / 홈 assets 2.1.2-home1**을 유지하며 아래는 별도 미커밋 후보다. PR #160 문서 병합은 앱 코드를 변경하지 않았다.

수정 전 합성 Chromium 390px 일반 reload에서 `#invest`는 FCP332ms에 홈을 표시하고 약1348ms에 주식 화면으로 전환했다. `#ledger`도 홈→캘린더→가계부 및 ‘최근 6개월’→‘월간’ 제목 전환을 재현했다. 원인은 HTML 기본 홈과 뒤늦은 hash navigate의 불일치, 차트 기본 MONTH 모드와 HTML 초기 제목의 불일치다.

기존 HTML-first를 유지하고 파서 체크포인트에서 선택 페이지·머니로그 패널을 맞춘다. 초기 표시와 이후 navigate는 하나의 라우트 규칙을 공유하며 detached 탭을 삽입 전에 선택한다. 가계부 초기 제목은 기본 차트 모드에 맞춘 ‘월간 현금흐름 추이’다. 인증·금융·차트 계산·기록 순서는 변경하지 않는다. CSS 변경은 사용하지 않는 과거 카드/바로가기 선택자 제거에 한정한다. 타이머/전체 앱 숨김 없이 JS 비활성 홈 기본 구조를 보존한다.

후보 변경 asset revision/layout CSS·JS/SW는 **2.1.2-route1**, core **2.1.2-r1** 및 앱 **2.1.2**는 유지한다. v2.1.3 P0는 제외·보호한다. 기존 FCP200→220ms 승인 예외는 PR #159 후보만의 기록이며 이번 후보에 자동 적용하지 않는다. DAY 과거 일회성 실패 원인 **UNCONFIRMED**를 유지한다.

과거 UI 정리 전 검증 상태: 첫 프레임 5폭×13라우트×첫 방문/일반 reload PASS. 테마3종·SW 제어 재방문·히스토리·비홈 권한, 가계부 렌더러·기간 변경, DAY38·IPO35 및 금융 격리 집중 검증 PASS. 추가 IPO 직접 새로고침·제외/복원·정적 gzip/캐시 회귀22 PASS. 초기 홈 기존4 PASS + route matrix1 PASS + 나머지 집중215 PASS/Windows의 Linux전용2 SKIP/45subtests PASS이며, 실제 FastAPI 인증·세션·사용자 격리와 Chromium E2E도 이번 후보에서24 PASS다. CI 홈 모듈의 실제 수집은9개로 확인했고 XML 무스킵 guard를4→9로 보완했다. CI 실행은 하지 않았다.

성능 게이트는 **FAIL / HOLD**다. 줄바꿈을 Windows CRLF로 일치시킨 baseline/candidate 비교(각 최초1+warm3, 같은 기존 CPU/네트워크·purple·캐시/SW 조건)에서 모바일 warm 중앙값 FCP204→196ms, 자산1760→1911ms, readiness2064→2311ms, CLS0.0335→0.0224였다. PC는 FCP76→76ms, 자산213→192ms, readiness358→335ms, CLS0.00456→0.00456. 모바일 자산/readiness 무회귀를 충족하지 못했고 정확한 코드 인과관계는 미확정이다. 앞선 LF/CRLF 혼재 비교는 진단 자료로 보존하고 판정 근거와 구분한다. 추가 임의 측정·추측 튜닝이나 기존 FCP 예외 확장은 하지 않는다.

전체 pytest는 **NOT_RUN**이다. 기능 집중 검사는 통과했지만 성능 게이트가 미충족이므로 전체 출시 재검증으로 진행하지 않았다. 후보를 미커밋·미배포 상태로 보존하며 commit/push/PR/머지/GHCR/Oracle/Compose 변경은 실행하지 않는다.

추가 과거 UI 정리: 항상 hidden/aria-hidden이던 `data-legacy-summary`의 카드3개, 전용 링크 이벤트1개·중복 값 갱신5개와 전용 CSS를 삭제했다. HTML/JS에서 이미 제거된 바로가기 패널의 잔여 CSS도 삭제했다. 현재 `homeAssetPortfolioPanel`, 주식 `summaryPanel`, 가족 선택·내부 탭 및 인증/권한용 표시 제어는 실제 사용 중이므로 보존했다. 정리 전후 합성 360px 비교에서 홈 DOM188→168, 현재 자산 값·표시 링크·주요 computed style/좌표·접근성 링크/제목이 동일했다. CSS/JS로 과거 UI를 은폐하는 신규 규칙은 없다. 이전 성능 결과는 정리 전 후보의 기록으로 보존한다. 아래의 정리 후 고정 비교에서도 출시 HOLD를 유지한다.
정리 후 집중 회귀는 137 pytest PASS/20 subtests PASS, 실제 인증·세션·가족 선택·데이터 격리 E2E 24 PASS. 홈 초기 모듈9개 및 CI XML 수집 guard9는 유지한다. 전체 pytest/커밋/PR/배포는 미실행이다.

과거 UI 정리 후 사전 고정 경량 비교(Chrome155.0.8059.84, #home, 모바일5쌍 AB/BA/AB/BA/AB·PC2쌍 BA/AB, side별 최초1+warm3, 전체56회)를 완료했다. 모바일 warm15개/side 중앙값은 FCP160→172ms, 첫 유효 자산1373.5→1533.5ms, 같은 readiness1912.6→2080.8ms, ScriptDuration414.623→464.862ms, CLS0.033507→0.033507. PC warm6개/side는 FCP64→68ms, 자산182.15→209.90ms, readiness272→312.60ms다. 무회귀를 충족하지 못해 **PERFORMANCE_GATE=HOLD**다. 최초 방문은 별도로 보존했으며 warm 판정과 합치지 않았다. 기존 정리 전 실패 이력도 유지한다.

판정 시점 완료 API는 모바일 A13건6회/16건9회, B13건9회/16건6회로 차이가 있었지만 별도 후속 관찰에서는 양쪽 모든 warm 표본이 동일16건이었다. 늦게 완료된 요청은 planning 재조회·market-overview·realized-pnl 재조회였다. 인증1회/workspace1개, 시세 완료→dashboard→snapshot-all 순서와 합성 순자산397,000,000원은 모두 유지됐다. 100ms polling과 누적 CPU 지표만으로 특정 코드의 인과관계는 확인하지 못했다(**UNCONFIRMED**). API·readiness·assertion을 변경하지 않았고 추가 앱 수정0개, 추가 성능 재측정/출시 집중 검사/전체 pytest/커밋/PR/배포도 미실행이다. 기존 기능 PASS 결과를 새 고유 통과 건수로 합산하지 않는다.


## 홈 초기 UI 핫픽스 — PR #159 배포 완료 및 남은 확인 (2026-10-21)

- [x] [PR #159](https://github.com/sagesaint84/wealth/pull/159) Squash Merge 확인. main/운영 배포 코드 SHA `b5a5c525f24ec7233b85af70dc8242a25966e150`. 앱 **v2.1.2**, 홈 assets/SW **2.1.2-home1**, core **2.1.2-r1** 유지, v2.1.3 P0 제외.
- [x] HTML-first 홈·다섯 화면 폭·테마·역할·가족·SW/gzip의 출시 전 합성 검증 및 실제 앱 인증24 PASS 보존. Windows4414 PASS/0 FAIL/5 SKIP/888subtests PASS.
- [x] [정적·홈·DAY CI](https://github.com/sagesaint84/wealth/actions/runs/39521010150)330 PASS, DAY38개 및 과거 실패 대상 무스킵 PASS; [IPO](https://github.com/sagesaint84/wealth/actions/runs/39521010106)239 PASS; [native](https://github.com/sagesaint84/wealth/actions/runs/39521010029) 양쪽 아키텍처에서 Linux필수2개 무스킵 PASS와 ledger488/process24/11subtests PASS 확인.
- [x] [GHCR 발행 39522925985](https://github.com/sagesaint84/wealth/actions/runs/39522925985) SUCCESS, manifest `sha256:c9b586098a4d31860008782531f2163e7f274938de2e2f0c6bc185b143fd4ffc` 및 Linux AMD64/ARM64를 레지스트리에서 확인.
- [x] 사용자 제공 Oracle **IMAGE_DIGEST_GATE=PASS / DEPLOY_GATE=PASS / wealth running** 기록. Codex의 서버 직접 확인이나 재배포는 아님.
- [x] 모바일 warm FCP **200→220ms FAIL_WITH_APPROVED_CANDIDATE_EXCEPTION**, 이번 후보만 승인. 기존 자산1698→1396ms/readiness2072→1718ms/CLS0.243→0.034 합성 결과 보존. DAY 일회성 실패 원인은 **UNCONFIRMED** 유지.
- [ ] 운영 실제 브라우저 smoke 확인: 로그인·일반 새로고침에서 구형 UI/현재 홈 재소실 여부·가족/탭·테마·자산 표시. 현재 **NOT_CONFIRMED**이며 합성 PASS로 대체하지 않는다.
- [x] 사용자 제공 Oracle 읽기 전용 조회로 실행 이미지 `RepoDigests`와 GHCR 발행 Digest 일치 확인: **ORACLE_IMAGE_DIGEST_VERIFIED=PASS**. 이전 스크립트 기대값만 확인했던 상태와 구분하며 Codex 직접 서버 접속 결과가 아니다.
- [ ] 문서 PR 별도 검토·승인 후 반영. 완료 홈 브랜치는 커밋 보존·clean·연결 사용 여부 재확인 및 사용자 삭제 승인 후에만 정리한다. 기존 홈 worktree는 문서 PR 작업 경로로 재사용 중이다.
- [x] 사용자 제공 Oracle 출력으로 `docker-compose.release.ipo155.yml` 존재 및 현재 컨테이너 Compose 목록 미포함 확인.
- [ ] 다른 배포 스크립트·예약 작업 참조를 확인한 뒤 정리 후보 여부를 판단한다. 현재 **UNCONFIRMED**, 삭제하지 않는다.

P0 원본27/통합33/최소2개 변경과 브랜치/worktree를 보호한다. GitHub Releases 조회0건 및 v2.1.2 tag 없음은 앱 버전과 별도로 기록하며 새 Release/tag를 만들지 않는다. 이번 문서 후속 작업에서 앱·이미지·Oracle·Compose를 변경하지 않는다.

사용자 제공 Oracle 읽기 전용 출력의 현재 컨테이너 Compose 목록은 `/docker/wealth/docker-compose.ghcr.yml`, `/docker/wealth/docker-compose.override.yml` 두 파일이다. `docker-compose.release.ipo155.yml`은 서버에 존재하지만 이 목록에는 없으며, 다른 배포 스크립트·예약 작업 참조는 아직 미확인이다. 현재 컨테이너에서 사용하지 않는다는 사실만으로 전체 미사용이나 삭제 가능을 판단하지 않는다.

```text
ORACLE_IMAGE_DIGEST_VERIFIED=PASS
COMPOSE_FILES_VERIFIED=PASS
RELEASE_COMPOSE_EXISTS=YES
RELEASE_COMPOSE_CURRENT_CONTAINER_USED=NO
RELEASE_COMPOSE_OTHER_REFERENCES=UNCONFIRMED
BROWSER_SMOKE=NOT_CONFIRMED
```

## PR #159 조사·출시 준비 당시 기록 (현재 운영 상태 아님)

2026-10-21, 대상 `codex/v212-home-initial-flash-fix` (기준 v2.1.2 / PR #158 / `baee68438fed1822581e83211756304d3f080bc1`).

- [x] 구형 초기 HTML→JS 홈 재구성을 HTML-first로 바꾸고 현재 홈 유지·다섯 화면 폭·테마·역할·가족 및 SW/gzip을 검증한다.
- [x] 기존 실제 인증 E2E 24 PASS와 금융 계산·기록 완료 순서 검증을 관련 구현 불변 범위에서 보존한다.
- [x] 최종 Windows 전체 pytest 1회: **4,414 PASS / 0 FAIL / 5 SKIP / 888 subtests PASS**, exit **0**. DAY 차트·IPO 계약 2건 PASS.
- [x] 모바일 FCP **200→220ms FAIL**은 이번 후보 한정 사용자 승인 예외로 기록한다. 기존 자산 표시 1698→1396ms, readiness 2072→1718ms, CLS 0.243→0.034 개선을 보존하고 게이트를 일반적으로 완화하지 않는다.
- [ ] 과거 DAY 차트 비결정적 실패 위험을 PR에 명시한다. 원인은 **UNCONFIRMED**이며 이번 PASS를 원인 해결로 표현하지 않는다.
- [x] 기존 선택형 CI에 DAY 38개와 IPO 계약 모듈 2개를 추가하고 XML로 무스킵 실행 및 DAY 대상 PASS를 강제한다. YAML·실행 명령·XML 검사 로직 정적 검증 PASS.
- [ ] 실제 차트 회귀 및 기존 native CI의 Linux subreaper/pidfd 2개를 필수 통과시킨다. 외부 live 3개와 Linux 대기 2개를 구분한다.
- [ ] Linux CI 통과 이후에만 머지·이미지·배포 승인을 별도로 검토한다. 현재 **PR_READY_PENDING_LINUX_CI**, 최종 머지·배포 승인 **NOT_YET**다.

앱 **2.1.2**, workspace assets/SW **2.1.2-home1** 유지. 미완료 v2.1.3 P0와 분리한다. 이 기록은 PR 제출 준비 시점이다. 제출 후 커밋·PR·실제 Linux CI 결과는 해당 PR/Actions를 따른다. Merge·GHCR 발행·Oracle 배포·Compose 수정은 별도 승인 전까지 진행하지 않는다. 운영 서버는 기존 v2.1.2 그대로다.

## PR #158 개발 당시 기록 — 정적 전송 최적화 (당시 미배포)

기준 main `92956f620e9316b111b419f8c1d01891b7fe2562`에서 공개 `/static` JS/CSS(1KB 이상)에만 표준 gzip(level 5)을 적용한다. API·금융 응답·이미지·저장 형식·계산·스냅샷 순서·인증은 변경하지 않는다. Range·HEAD·ETag/304·MIME·gzip 거부를 보존하고 `Vary: Accept-Encoding`을 설정한다. 디스크 압축 캐시나 영구 파일은 생성하지 않는다.

같은 합성 홈 화면을 새 문서로 각 3회 측정했다(콜드 HTTP 캐시, SW 우회). PC 1280px/4Mbps/20ms에서는 첫 유효 자산 표시 중앙값 **4.06→1.62초**, 초기 준비 **4.56→1.87초**. 모바일 390px/2Mbps/40ms/CPU 4배 제한에서는 **8.54→4.39초**, **9.64→4.96초**였다. JS/CSS 본문 전송량은 **1,835,964→432,675바이트(-76.4%)**, 압축 해제 후 파일 내용은 동일하다. 운영 환경 실측이나 CPU·메모리 절감은 입증하지 않았다. Python 프로세스 CPU는 서버와 CDP 처리가 섞인 대리 지표이며 PC에서 압축 비용 증가가 관측됐다. API 수 차이는 측정 종료 시점 영향이 있어 중복 요청 감소로 주장하지 않는다.

기존 v2.1.3 P0의 가시성·요청 공유·prepare/commit·epoch 방어를 읽기 전용 검토했으며 복제하거나 합치지 않는다. 숨김 탭 렌더·프런트엔드 정리는 P0와 충돌 검토 후 별도로 진행한다. 독립 API의 기존 병렬화와 시세 갱신 성공→대시보드/주식 스냅샷→순자산 스냅샷 의존성은 유지한다. 불확실한 코드/CSS 삭제는 하지 않는다.

앱 버전 **2.1.2**, 정적 원문과 기존 revision **2.1.2-ipo-ui1**은 유지한다(전송 방식만 변경). 원본 P0 27개·기존 worktree를 보존한다. 로컬 집중 회귀 **253 PASS / 1 의존성 경고**, 실제 Chromium **15건** 포함(신규 전송 14건, 기존 관련 239건). Python AST·CI YAML·diff 검사 PASS. 전체 pytest·Oracle 접속은 하지 않았다. 최신 CI 성공 전 머지하지 않고 운영 배포 완료로 기록하지 않는다. 배포 시 고정 Digest 및 영구 데이터/Toss 마운트를 확인하되 롤백 이미지 생성·백업 저장은 하지 않는다.

## PR #157 개발 당시 기록 — IPO·통합 캘린더 UI (당시 미배포)

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

## 2026-10-25 PR #177 로컬 성능 조사

- 기존 360px 실패 2회 기록을 보존하고 16표본씩 비교했다. 숨긴 순자산 패널의 geometry 검사로 동기 Layout이 발생하는 경로를 확인해 로컬 최소 패치를 작성했으나, 전체 무회귀 기준은 충족하지 못했다. 최초 표시 지연의 전체 원인은 UNCONFIRMED, PERFORMANCE_GATE=FAIL/HOLD를 유지한다.
- main/수정 전/수정 후 비교, 격리 실험·trace·API 타이밍과 전체 회귀 결과는 [조사 보고서](home-tabs-hold-20261025/REPORT.md)를 따른다. 모든 게이트 PASS 전 Commit·Push하지 않으며 Draft 해제·머지·Oracle 배포는 금지한다.
