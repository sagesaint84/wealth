# Wealth

## 현재 운영 배포 — 2026-10-24 / Wealth v2.1.3

- **현재 운영 코드**: [PR #172](https://github.com/sagesaint84/wealth/pull/172) Squash Merge `f90e9b7589a2180c518ecb34f9c7343ed0241367` → [PR #173](https://github.com/sagesaint84/wealth/pull/173) Squash Merge `6a14c0d5cd7dda27501db770572d1d3334b37901`; 실제 Oracle에 배포된 앱 버전은 **v2.1.3**, 릴리스 이미지 태그는 `ghcr.io/sagesaint84/wealth:6a14c0d`이다. 문서 전용 후속 커밋은 앱 실행 이미지를 바꾸지 않는다.
- **GHCR 발행**: [Docker build #40100539869](https://github.com/sagesaint84/wealth/actions/runs/40100539869) **SUCCESS** (Linux AMD64/ARM64); multi-platform manifest `sha256:f4e0e17bafa7158a43b43fc3b5b47d540bbfcb1667dc00ec3accdb79cd9c634e`.
- **Oracle ARM64 배포 완료 (2026-10-24 사용자 SSH 실행 로그)**: Digest 고정 이미지 다운로드, `qemu_*.core` 검사 **PASS**, 실행 중 이미지 대조 **PASS**, HTTP `/` → **307**, 금융 데이터·Toss 마운트 동일 **PASS**, `DEPLOY_AND_CLEANUP=PASS`. 사용 종료된 직전 Wealth 이미지 `f90e9b7` 삭제 후 파일시스템 약 **194GB 중 164GB 사용 / 31GB 여유(85%)**. Docker 전체 정리·볼륨 삭제·백업 이미지 추가 생성은 수행하지 않았다. **RECLAIMABLE 4.272GB는 선별 검증 없이 지우지 않는다.**
- **운영 브라우저 (사용자 스크린샷 확인)**: 📈 증권 / 🏦 은행 / 🛡️ 연금·보험 / 🏠 부동산 / 🧾 세금의 5개 균등 탭과 괄호 카운트 제거, 금리 카드 Sparkline·금리(연%)·변동(bp)·링크 제거 확인. PR #172의 기존 보유종목 기술적 신호 4섹션 구조 유지. 운영 전체 E2E·모든 계좌의 데이터 감사 완료를 의미하지 않는다.
- **검증 기록**: PR #173 최종 GitHub CI Static transport **387 passed**, IPO **239 passed**, Toss WTS Linux **AMD64/ARM64 SUCCESS**; 로컬 표적 **89 passed**, Chromium **30 passed**(320/360/390/768/1280px). PR #172도 병합 당시 CI 통과했다. 이번 작업으로 전체 pytest를 추가 실행했다고 표시하지 않는다.
- **배포 운영 원칙**: 확정한 GHCR Digest 다운로드 → Wealth 단일 서비스 교체 → 실행 이미지·HTTP 307·데이터/Toss 마운트 확인 → 다른 컨테이너가 사용하지 않는 이전 Wealth 이미지만 정리. 검증 실패 시 정리 금지 및 이전 이미지 복구 시도. 다른 서비스·볼륨·실제 금융 데이터 보존.

## 과거 운영 배포 기록 — 2026-10-22 / Wealth v2.1.3

- **운영 앱 v2.1.3**: [PR #163](https://github.com/sagesaint84/wealth/pull/163) Squash Merge `f9cb3cd87644fc8a51cd25488802878ee680613a` 완료. 코드 앱 버전 및 HTML 표시 **2.1.3**, 변경된 JS와 SW 캐시 식별자 **2.1.3-p0**. 미변경 IPO·레이아웃의 개별 asset revision은 유지.
- **GHCR 발행 완료**: [Docker build #39741300759](https://github.com/sagesaint84/wealth/actions/runs/39741300759) SUCCESS; Linux AMD64/ARM64; `ghcr.io/sagesaint84/wealth:f9cb3cd`, 고정 manifest Digest `sha256:f2683c22acd77e8fe8f03b11c5bbfcf60115c095c7a242069a81c4d2ba64d1d8`.
- **Oracle ARM64 배포 완료(사용자 SSH 로그)**: /docker/wealth의 dashboard 서비스, `wealth` 컨테이너 이미지 ID `sha256:18076e45b121569d349997d29489adb3335cf6fbc4121914d1f1f3616e7b4d35`; 데이터 /app/data 및 Toss 바이너리·설정 마운트 보존, HTTP / → 307, gzip JS PASS, 재시작 0회. 운영 교체 전 v2.1.2 이미지 `rollback-before-v213` 보존.
- **실제 운영 브라우저(사용자 확인 7/7 PASS)**: 로그인/홈 자산·추이, 모바일 360px 재진입, 배당 DAY, 실현손익·주식기록, 가계부, IPO, 소유자·기간 변경 시 오래된 데이터 방어. 운영 사이트에 대한 별도 독립 자동 브라우저 E2E는 미실행.
- **검증 범위**: PR 최신 CI **4/4 PASS**, 릴리스 버전·실제 Chromium SW 집중 테스트 **44 PASS**, 과거 집중 검사 50/54/22/15/20 PASS(중복 가능). v2.1.3 전체 pytest **NOT_RUN**. 초기 API 호출 15→12 감소는 재현됐으나, 360px warm 동일 HTTP 캐시 비교 두 실행에서 속도 편차가 있어 **PERFORMANCE_NUMERIC_GATE=REVIEW_REQUIRED**; 사용자 승인으로 **이 PR에 한해 조건부 머지·배포**. 성능 개선 확정이나 PR #161의 이전 예외 승계를 의미하지 않는다.
- **릴리스 기록(문서 작성 시점)**: `v2.1.2` 태그는 기존 운영 커밋에 등록됨. [annotated Git 태그 `v2.1.3`](https://github.com/sagesaint84/wealth/tree/v2.1.3)는 배포 커밋 `f9cb3cd87644fc8a51cd25488802878ee680613a`를 가리키는 것으로 GitHub에서 **검증 완료**. GitHub Release는 **아직 발행되지 않음**(2026-10-22 확인); 태그 등록과 Release 발행을 구분한다. 아래 절은 각 작업 당시 상태를 보존한 과거 기록이다.


## 과거 운영 배포 기록 — 2026-10-21 / PR #161

- **운영 앱 v2.1.2** (정적 화면·레이아웃·서비스워커 revision **2.1.2-route1**; core **2.1.2-r1**). [PR #161](https://github.com/sagesaint84/wealth/pull/161) Squash Merge SHA `fc0bb1092b6d55ee21a786b0d295c48bdcba4c14`. **v2.1.3 P0 변경 미포함**.
- GHCR 이미지 `ghcr.io/sagesaint84/wealth:fc0bb10` / 고정 manifest Digest `sha256:b82b79c9a3e781810a9c823237473fe09549fa72825c5756c5c97b0774cd05b9`. [이미지 발행 워크플로](https://github.com/sagesaint84/wealth/actions/runs/39572486587) SUCCESS; Linux AMD64/ARM64 이미지 발행.
- **Oracle 배포 검증(사용자 실행 출력)**: 실행 이미지 ID `sha256:4d6133a4e1977b739c3e1065023e7f18616e0289674911a2050c64783c9a3f82`, 영구 데이터 `/app/data`, Toss WTS 바이너리·설정 마운트 유지, `wealth` 실행, HTTP `/` → **307**, 배포·이미지·마운트·HTTP 게이트 PASS.
- **운영 브라우저(사용자 보고)**: 로그인/홈, 주식 `#invest` 직접 새로고침, 가계부 `#ledger`·월간 현금흐름, DAY 상세 선택, 모바일 탐색·새로고침 **5/5 PASS**. 별도의 원격 브라우저 자동 검증은 수행하지 않았다.
- 품질 이력: PR #161 CI **4/4 PASS**; Windows 전체 pytest **4,424 PASS / 1 FAIL / 5 SKIP / 888 subtests PASS**였으며 실패한 모바일 배당 DAY pointer 검사는 후속 집중 재검증 **4/4 PASS**. 원인은 **UNCONFIRMED**, 전체 pytest를 PASS로 바꾸지 않는다.
- 성능 숫자 게이트 **FAIL** (한정 비교에서 모바일 첫 자산 약 **+488ms**, readiness 약 **+532ms**). **사용자가 PR #161에 한해 출시 예외를 승인**했으며, 성능 자체가 개선·해결되었다는 의미는 아니다. 이 예외는 v2.1.3 P0 또는 후속 릴리스에 적용되지 않는다.

- **태그·Release 현황(2026-10-22, 사용자 제공)**: 운영 배포 커밋 `fc0bb1092b6d55ee21a786b0d295c48bdcba4c14`에 Git 태그 `v2.1.2` 등록 완료. **GitHub Release는 아직 생성되지 않았다.** 아래 과거 태그 미등록 문구는 당시 조회 기록으로 보존한다.

## 과거 릴리스 준비 기록 — v2.1.3 P0 (2026-10-22 당시)

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


## 현재 운영 상태 — PR #159 홈 초기 UI 핫픽스 (2026-10-21)

앱 **v2.1.2**, 홈 assets 및 SW **2.1.2-home1**, 변경하지 않은 core JS **2.1.2-r1**이다. [PR #159](https://github.com/sagesaint84/wealth/pull/159)는 Squash Merge 완료됐고, 이 문서 갱신 시 확인한 main 및 운영 배포 코드 SHA는 `b5a5c525f24ec7233b85af70dc8242a25966e150`다. v2.1.3 P0는 포함하지 않았다.

[GHCR 발행 실행 39522925985](https://github.com/sagesaint84/wealth/actions/runs/39522925985)는 해당 SHA에서 SUCCESS다. 이미지 `ghcr.io/sagesaint84/wealth:b5a5c52`, 발행 manifest Digest는 `sha256:c9b586098a4d31860008782531f2163e7f274938de2e2f0c6bc185b143fd4ffc`이며, 레지스트리에서 원문 SHA256 및 Linux AMD64/ARM64 manifest를 확인했다. 사용자가 제공한 Oracle 결과는 **IMAGE_DIGEST_GATE=PASS**, **DEPLOY_GATE=PASS**, 컨테이너 **wealth running**이다. 이전 기록에서는 스크립트 기대값만 확인했고 실행 이미지의 `RepoDigests` 조회는 미실행이었다. 이후 사용자가 Oracle에서 실행한 읽기 전용 명령 출력으로 실행 이미지 ID `sha256:4ec2929e1bac2df9458d987b762f7128e3b6de12f1ffe9c228245074f3a5cede` 및 `RepoDigests`의 GHCR 발행 Digest 일치를 확인했다고 전달했다. 현재 **ORACLE_IMAGE_DIGEST_VERIFIED=PASS**는 이 사용자 제공 증거에 근거한다. Codex는 Oracle에 접속하거나 재배포하지 않았다.

**운영 실제 브라우저 smoke는 NOT_CONFIRMED**다. 배포 후 새로고침·로그인·가족·탭·테마·자산 표시의 사용자 브라우저 결과는 아직 제공되지 않았다. 아래 합성/출시 전 검증을 운영 브라우저 PASS로 해석하지 않는다.

출시 전 Windows 전체 **4,414 PASS / 0 FAIL / 5 SKIP / 888 subtests PASS**, 실제 앱 인증 E2E **24 PASS**를 보존한다. [정적·홈·DAY CI](https://github.com/sagesaint84/wealth/actions/runs/39521010150) **330 PASS**(DAY 38개 및 과거 실패 대상 무스킵 PASS), [IPO CI](https://github.com/sagesaint84/wealth/actions/runs/39521010106) **239 PASS**, [native CI](https://github.com/sagesaint84/wealth/actions/runs/39521010029)는 AMD64/ARM64 각각 금융·가계부 **488 PASS**, 프로세스 **24 PASS / 11 subtests PASS**다. Linux 필수 2개는 양쪽에서 실제 무스킵 통과했다. Windows skip은 외부 live 3개와 Linux 전용 2개이며 CI 결과와 구분한다. job 간 중복을 고유 테스트 수로 합산하지 않는다.

기존 합성 모바일 warm 자산 표시 **1698→1396ms**, readiness **2072→1718ms**, CLS **0.243→0.034**. FCP **200→220ms**는 **FAIL_WITH_APPROVED_CANDIDATE_EXCEPTION**으로 이번 후보 한정 승인이다. 과거 DAY 차트 일회성 실패 원인은 계속 **UNCONFIRMED**다. 운영 성능을 새로 측정하지 않았다.

GitHub Releases는 조회 시 0건이며 `v2.1.2` Git tag도 없다. 이 운영 이력은 앱/asset 버전·PR·SHA·GHCR Digest 기준이며 GitHub Release/tag 발행 완료를 뜻하지 않는다. 미완료 P0 27/33/2개 파일을 보호한다. 정리 검토 범위와 미확인 Compose 사용 여부는 [PROJECT_STATE](docs/PROJECT_STATE.md)를 따른다.

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

2026-10-21 기준 `codex/v212-home-initial-flash-fix` 후보다. 사용자 제공 운영 기준은 **Wealth v2.1.2**, PR #158, SHA `baee68438fed1822581e83211756304d3f080bc1`이다. 구형 홈 HTML을 먼저 그린 뒤 JavaScript가 현재 홈을 재구성하던 경로를 HTML-first 구조로 바꿨다. 합성 Chromium 캡처에서 구형 UI 재노출과 현재 홈 재소실은 관찰되지 않았다.

기존 모바일 warm 중앙값은 자산 표시 **1698→1396ms**, readiness **2072→1718ms**, CLS **0.243→0.034**로 개선됐다. FCP **200→220ms(+20ms, +10%)**는 계속 **`FAIL_WITH_APPROVED_CANDIDATE_EXCEPTION`**이다. 사용자가 승인한 이번 후보만의 예외이며 다른 후보·v2.1.3 P0·미래 릴리스에 적용하지 않는다. FCP 기준이나 다른 성능·기능 차단 조건은 완화하지 않았다. 이번 전체 재검증에서 성능은 다시 측정하지 않았다.

최종 Windows 전체 pytest를 정확히 1회 실행해 **4,414 passed / 0 failed / 5 skipped / 888 subtests passed**, exit **0**을 확인했다. DAY 차트 검사와 IPO 계약 2건도 전체 실행에서 PASS다. 과거 전체 실행에서 DAY 차트가 한 번 실패한 이력과 원인 **`UNCONFIRMED`**는 유지하며 비결정성 위험을 PR 검토 항목으로 남긴다. 실제 앱 인증 E2E **24개 PASS**는 인증 구현이 불변인 범위의 보존 검증 결과다.

상태는 **`PR_READY_PENDING_LINUX_CI`**다. skip은 비활성 외부 live 3개와 Windows에서 실행할 수 없는 Linux subreaper/pidfd 2개다. 기존 GitHub Actions에서 Linux 전용 2개와 DAY 차트 회귀를 실제 통과시키기 전에는 머지·배포를 승인하지 않는다. 기존 선택형 CI에 DAY 차트 38개와 IPO 계약 모듈 2개를 추가하고, 결과 XML에서 실제 수집·무스킵 PASS와 DAY 대상 검사를 강제하도록 보완했다. 기존 native Linux CI는 두 프로세스 검사의 무스킵 PASS를 이미 강제한다. YAML·실행 명령·XML 검사 로직의 로컬 정적 검증은 PASS이며 실제 Linux CI 결과는 PR에서 별도로 확인해야 한다.

앱 **2.1.2**, workspace assets revision 및 SW cache suffix **2.1.2-home1**, 변경하지 않은 core JS **2.1.2-r1**을 유지한다. 미완료 v2.1.3 P0는 포함하지 않았다. 이 기록은 PR 제출 준비 시점이며 커밋·PR 및 실제 Linux CI 결과는 해당 PR/Actions에서 확인한다. 머지·GHCR 발행·Oracle 배포는 별도 승인 전까지 진행하지 않으며 운영 서버와 Compose는 변경하지 않았다. 아래 절은 이전 개발 당시의 기록이다.

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

## PR #155 개발 당시 기록 — 사용자 확인 기준 현재 머지·배포 완료

Draft [PR #155](https://github.com/sagesaint84/wealth/pull/155)의 `codex/ipo-schedule-status`에서 정정요구·철회로 무효화된 청약 일정의 캘린더 투영을 보완한다. 운영 v2.1.2와 원본 v2.1.3 P0 작업은 변경하지 않는다. 범위·검증 제한은 [PROJECT_STATE](docs/PROJECT_STATE.md)의 IPO 항목을 따른다.

Wealth는 사용 편의성과 자동화를 우선하는 개인·가족 자산관리 도우미이며 전문 세무·회계·신고 프로그램이 아니다. 합리적인 기본값으로 추정하고 추가 입력은 선택으로 둔다. 공식 근거가 충분한 예상 혜택은 자동 반영하되 제외할 수 있고, 부족한 경우 일반 배당을 기본으로 사용자 가정을 허용한다. 실제 입금·원천징수·금융 원본은 보존하며 기존 계산·저장 구조와 UI를 재사용한다. 별도 전문 세무 엔진·중복 UI·불필요한 확인 절차를 추가하지 않는다.

PR #153 배포 당시 앱 및 운영 버전은 **Wealth v2.1.2**였다. 당시 문서 정리 브랜치 `codex/v212-postdeploy-docs`, 기준 HEAD/main `255d135b8562b5569a11ac7c213787dccbcc2513`.

사용자 제공 완료 기록: [PR #153](https://github.com/sagesaint84/wealth/pull/153) Squash Merge, main `255d135b8562b5569a11ac7c213787dccbcc2513`, 기능 커밋 `71e5c254f01a57336d31a7b2f634088dfce5ab23`. 전체 pytest **4,353 passed / 2 skipped / 4 warnings / 888 subtests passed**, 집중 테스트 **191 passed / 30 subtests passed**, 기존 Chromium 회귀 **35 passed**. AMD64/ARM64 PR CI SUCCESS ([실행 39103493324](https://github.com/sagesaint84/wealth/actions/runs/39103493324)), GHCR 빌드 SUCCESS ([실행 39103784893](https://github.com/sagesaint84/wealth/actions/runs/39103784893)).

운영 이미지 `ghcr.io/sagesaint84/wealth:255d135`, Manifest Digest `sha256:837709730d1b0d80abf7360b13d71e3c7261d793923befaab2238753429ad7eb`. Oracle ARM64: `V212_PRE_DEPLOY_GATE=PASS`, `V212_IMAGE_GATE=PASS`, `DATA_MOUNTS=PASS`, `V212_COMPOSE_GATE=PASS`, `VERSION_212=PASS`, 최종 HTTP 307, 컨테이너 running / RESTARTS=0, **`ORACLE_V212_DEPLOY=PASS`**. v2.1.1 롤백 이미지 `rollback-before-v212`와 이전 운영 Compose 백업 `docker-compose.release.before-v212.yml`은 보존됐다.

실제 배당 기록에 고배당 분리과세 적용 및 선택형 대상 금액을 추가한다. 공식 자격과 사용자 선택·신청 가정을 분리하며 기존 capital_dividend_mode 호환성을 유지한다. 기존 세전 역산·기록 환율·2026 What-if 계산을 재사용해 전체 세전 금융소득, 감액배당 제외, 고배당 분리과세 제외, 기준 포함액과 여유 금액을 표시한다. 감액배당과 고배당은 중복 차감하지 않으며 현금 하한은 제외 전 총액에만 적용한다. 개인별 2천만원 기준은 정확히 같은 금액까지 기준 이내이고 가족 합계에는 적용하지 않는다. 실제 입금·세전·원천징수 원본 및 기존 배당 카드는 변경하지 않고 과거 기록을 일괄 변환하지 않는다.

**실제 사용자 브라우저 검증 대기:** v2.1.2 세금 유형·금융소득 화면의 최종 사용자 확인은 아직 보고되지 않았다. 운영 배포 성공과 화면 사용자 검증 완료는 구분한다. 위 테스트·CI·배포 결과는 사용자 제공 이력이며 이번 문서 작업에서 테스트 실행이나 Oracle 서버 재확인은 하지 않았다.

금융소득 특례 계산은 기존 2026년/KRW 범위를 유지하고 USD 일반 배당은 저장 환율과 기존 역산을 재사용한다. 공식 공시 조회의 기존 범위·정정 계보 한계는 유지하며 사용자 선택을 공식 자격으로 승격하지 않는다.

## 이전 v2.1.1 운영 배포 기록

사용자 제공 운영 검증: v2.1.1 PR #152 Squash Merge, main `251d51ea4112a117f6748d5c7c73c03a4b274280`. 전체 pytest 4327 PASS / 2 SKIP, Chromium 35 PASS, AMD64/ARM64 PR CI SUCCESS. GHCR 실행 `39085363475` SUCCESS, 이미지 `ghcr.io/sagesaint84/wealth@sha256:000ba9c6b47c09d50899695fd8a51619f1eab0a25e24c8dd46b5019077e3cdba`. Oracle ARM64 IMAGE_GATE/DATA_MOUNTS/VERSION_211/ORACLE_DEPLOY=PASS, HTTP_STATUS=307, RESTARTS=0. 이번 작업에서 운영 서버를 재검증한 결과가 아니다.

## v2.1.1 개발 당시 기록 (아래 미배포·미실행은 당시 상태)

현재 개발 버전은 **Wealth v2.1.1**, 운영 배포 완료 버전은 **Wealth v2.1.0**이다. 기준 main은 `7236dd39381ed0d2f16cf982b36055c8c43e3cc0`, 개발 브랜치는 `codex/v211-dividend-record-chart-ux`다(미커밋·미배포).

v2.1.1은 실제 배당 기록의 감액배당 AUTO/직접 적용/제외, 선택형 세전·세액·세율 입력과 입금액 자동 역산, 월/연간 요약 카드 분리, 공통 차트 금액 툴팁 및 최신 저장 자산 금액을 구현한다. 개인별 법적 비과세 확정이나 실제 세금 기록 수정 기능이 아니다. 테스트 코드는 작성했으며 이번 단계에서 pytest/Chromium은 실행하지 않았다.

## v2.1.0 개발 및 이전 배포 당시 기록

아래의 당시 미병합·미배포 및 v2.0.3 운영 설명은 과거 이력이다. 현재 운영/개발 상태는 위 내용을 따른다.

Wealth는 개인과 가족의 자산, 투자 성과, 생활 수입·지출을 한곳에서 관리하는 self-hosted 웹 애플리케이션입니다. 데이터는 서버의 `data/`에 사용자별로 저장됩니다. 현재 개발 버전은 **Wealth v2.1.0**, Oracle 운영 버전은 **Wealth v2.0.3**입니다. [PR #149](https://github.com/sagesaint84/wealth/pull/149) Squash Merge 후 운영 코드 기준은 `b1e6e59d0f650db6023cdc7bf95c1b22d2f5694b`, 운영 이미지는 `ghcr.io/sagesaint84/wealth:b1e6e59`입니다. Native AMD64/ARM64 [CI 38930119488](https://github.com/sagesaint84/wealth/actions/runs/38930119488)와 [GHCR 이미지 빌드 38931035808](https://github.com/sagesaint84/wealth/actions/runs/38931035808)는 SUCCESS입니다. 사용자 제공 Oracle 배포·10분 안정성·실제 AccountInfo 화면 확인도 완료됐습니다. 문서 전용 [PR #150](https://github.com/sagesaint84/wealth/pull/150)까지 반영된 main은 `a28d31995df3af71ed945b9fe61968064a1dd757`이며 Oracle 컨테이너는 재배포하지 않았습니다. PR #147의 이전 병합·운영 배포 완료 기록은 보존합니다.

v2.1.0 개발 소스에는 Phase A/B1 공식 근거 연결과 B2 이벤트별 예상 세금 혜택 미리보기가 포함됩니다. PR 미병합·운영 미배포 상태입니다. 배당/What-if의 같은 화면에서 AUTO·사용자 적용·사용자 제외를 선택하며, 공식 판정과 사용자 선택은 분리합니다. 기존 고배당기업 판정·2026 누진세·What-if를 재사용하고 실제 입금·원천징수·실현손익·기존 배당 예상 총액은 바꾸지 않습니다.

B2는 기본 세후 카드에 자동 합산하지 않는 별도 미리보기로, 소유자·이벤트·과세연도별 예상 대상 금액을 계산합니다. 고배당기업 AUTO는 공식 자격·대상 이벤트·연도·금액 및 정정 경고를 함께 확인하며, 근거 부족 시 일반 계산을 유지합니다. 사용자는 해제하거나 금액을 입력해 사용자 가정으로 적용할 수 있습니다. **현재 B1의 감액배당 구성금액 verified만으로는 AUTO 비과세를 적용하지 않습니다.** 개인별 적용 요건 확인 경로는 미구현이며 수동 가정만 가능합니다. 선택은 인증 사용자 범위를 구분한 화면 메모리에만 보존하고 새로고침하면 AUTO로 돌아갑니다. 2026년 계산만 지원하며 고배당기업은 신고 신청이 필요하고 일반과세 대비 절세를 확정하지 않습니다. 상세 범위와 검증은 [현재 상태](docs/PROJECT_STATE.md)를 따릅니다.

이번 B2 합성/mock 집중 검증은 **242 PASS / 0 FAIL / 0 SKIP**(서비스·API·버전 등 21개 모듈 214 PASS, 실제 Chromium 모듈 28 PASS)입니다. 전체 pytest·실제 외부 API·PR CI·운영 검증은 이번 작업에서 실행하지 않았습니다.

B1 감사 보완에서는 두 파서의 실패를 독립 처리하고 API 오류·정상 공시 부재·비정상 응답을 구분했습니다. 격리된 Python 3.14.2 집중 검증은 **222 PASS / 0 FAIL / 0 SKIP**, subtests **72 PASS**입니다. 감사 시작 시점의 수정 전 B1 복사본으로 비-live 전체 범위를 재실행해 **4,278 PASS / 0 FAIL / 2 SKIP**, subtests **849 PASS**를 확인했습니다. 이전 중단 실행의 실패는 재현되지 않아 node ID·원인은 UNKNOWN이며 당시 실행을 성공으로 바꾸어 기록하지 않습니다. 수정 후 B1 전체 실행·실제 API·CI는 미검증입니다.

AccountInfo 반응형 카드 UI는 운영 반영 완료입니다. 개발 당시 로컬 집중 검증은 **129 PASS / 0 FAIL / 0 SKIP**입니다. 실제 브라우저에서 계좌 카드, PDF 잔액 전체 표시, 은행 신규 잔액 편집, 증권 참고값 구분, 버튼 접근성, 기존 자산 데이터 유지의 6개 항목을 확인했습니다. 이는 실제 신규 계좌 등록이나 전체 금융 API 실거래 검증 완료를 뜻하지 않습니다. parser·중복·Owner·마스킹·금융 저장·증권 예수금 정책은 유지합니다. 운영 환경·마운트·롤백 보존 및 과거 이력의 상세는 [현재 상태와 필수 작업 원칙](docs/PROJECT_STATE.md)을 따릅니다. [계좌 UI·보험 표시 정책](docs/v2-wts-insurance-roi.md), [국민연금 분석 기준과 한계](docs/national-pension-analysis.md), [국민연금 자료 가져오기](docs/national-pension-import.md)도 참고하세요.

과거 v2.0.2 검증 기록: 사용자 확인 Windows 전체 pytest **3,699 passed / 5 skipped / 0 failed / 5 warnings**, **798 subtests passed**, Python·JavaScript 문법 검사 **PASS**. [GitHub Actions run 38493482329, attempt #8](https://github.com/sagesaint84/wealth/actions/runs/38493482329/attempts/8)은 **Success**이며 native amd64/arm64 두 job에서 Docker 빌드, network-disabled Chromium smoke, Poppler/Tesseract kor/eng/osd, 합성 한국어 PNG/PDF OCR 및 production document worker smoke가 성공했습니다. 실제 개인 국민연금 문서는 사용하지 않았으며 CI 성공은 운영 배포·인식률 검증 완료를 뜻하지 않습니다.

v2.0.1의 기존 PR 검증 기록은 전체 pytest **3,596 passed / 5 skipped / 0 failed**, **798 subtests passed**, Chrome UI **30 passed**, AMD64/ARM64 PR CI 성공입니다. v2.0.2 결과와 구분합니다.

v2.0.0은 사용자 확인 Windows 전체 pytest **3,568 passed / 5 skipped / 0 failed**, **798 subtests passed**, 신규 Chrome UI 테스트 **14 passed**를 기록했습니다. PR #142 main 병합과 Oracle ARM64 운영 배포·HTTP 검증도 사용자 확인으로 완료됐습니다. 이 수치는 당시 v2.0.0 검증 기록입니다.

## 주요 기능

- **자산과 계좌**: 증권·은행·예적금·보험·부동산·대출을 모아 순자산과 자산 구성을 표시합니다. 계좌별 보유종목과 평가금액을 관리합니다.
- **국민연금 상세 분석**: 실제 연간 납부 이력과 가입유형·본인/사업장 부담액·세금 정보를 분리 관리합니다. 확인한 과세표준·공제 인정액의 누진 산출세액 감소분과 사용자 가정의 수령 나이별 현금흐름·IRR을 제공합니다. 미확인 개인 비용, 미등록 세율 연도, 복수 해 가능성 및 세후 근거 부족은 미산정으로 표시합니다.
- **주식 투자**: 포트폴리오, 히트맵, 주식기록, 전략 버킷, 절세계좌 보유종목, 전체 보유종목을 조회합니다. ISA·IRP·연금저축 등 절세계좌의 소유자와 계좌 선택을 반영합니다.
- **머니로그**: 통합 캘린더, 실현손익, 배당·이자, 가계부, 공모주 일정과 가족별 청약 상태를 관리합니다.
- **세금과 배당**: 금융소득 전망·What-if, 알려진 세금 후 배당 현금흐름, 월별 목표와 계산 근거를 표시합니다. 불완전한 근거는 확정값으로 채우지 않습니다.
- **공모주(IPO/SPAC)**: DART/OpenDART·KIND·NAVER/Npay·Metalogos 160을 조합해 일정·공시·score를 관리합니다. IPO에서 KIS 인증·API는 사용하지 않으며 일반 KIS 계좌·실현손익 연동은 유지합니다. KRX 공식 과거자료는 별도 미리보기 후 명시적으로 반영하고, source 실패 시 기존 시장 기록을 보존합니다.
- **가져오기**: 증권사 파일·피드의 선택 가져오기와 AccountInfo 계좌통합현황 PDF를 지원합니다. AccountInfo PDF는 브라우저에서 파싱하고 계좌를 마스킹된 미리보기에서 확인한 뒤 선택하여 추가합니다.

## 화면 구성

데스크톱은 좌측 내비게이션, 모바일은 하단 내비게이션을 사용합니다. 홈에서 자산 요약을 보고, **주식 투자**에서 포트폴리오·히트맵·주식기록·전략 버킷·절세계좌·보유종목을 전환합니다. **종합 자산**은 계좌와 자산군을, **머니로그**는 캘린더·실현손익·배당·가계부·공모주를, **세금**은 금융소득 의사결정 도구를 제공합니다. **설정**에서 가족, 연동 인증정보, 자동화와 계정 설정을 관리합니다.

화면을 실제 계정 없이 확인하려면 `python tests/ui_preview.py`를 실행해 `http://127.0.0.1:8765`에 접속할 수 있습니다. 이 미리보기는 가상 데이터만 제공하고 저장 요청을 거부하며, 일부 외부 연동 화면은 재현하지 않습니다.

## 데이터 및 안전 원칙

- 사용자 자산·기록은 `data/users/<username>/` 아래 JSON으로 격리합니다. `./data:/app/data` 마운트는 컨테이너 재생성 뒤에도 유지해야 합니다.
- 증권사 동기화는 오류나 모순된 빈 응답을 기존 보유종목 삭제 근거로 삼지 않는 **fail-closed** 정책을 사용합니다. 가져오기와 공모주 반영은 미리보기·선택·충돌 확인을 거칩니다.
- 웹 데이터 백업은 일반 자산·거래 데이터용입니다. OpenAPI 비밀값, 토큰, 비밀번호 해시와 세션 키는 내보내지 않습니다.
- 외부 연동은 조회용이며 주문·이체·청약 실행 API를 제공하지 않습니다. 외부 피드를 Wealth 기록에 저장하는 단계에는 사용자의 명시적 선택이 필요합니다.
- 실제 `data/`, `.env`, 인증정보와 개인 금융 파일을 Git이나 공개 로그에 넣지 마세요. 저장·마스킹 계약은 [보안 및 설정 문서](docs/SECURITY_AND_CONFIG.md)를 따릅니다.

## 증권사 / 외부 데이터 연동

토스증권, KB증권, NH투자증권, 한국투자증권(KIS), 키움증권의 공식 조회 연동을 지원합니다. 보유종목·예수금·국내외 실현손익 지원 범위는 증권사마다 다르며, 실현손익은 조회 후 선택 가져오기 방식입니다. Toss WTS의 `tossctl` 브릿지는 선택적인 **읽기 전용 피드**로 사용합니다.

증권사 OpenAPI와 DART 키는 로그인한 사용자의 설정에서 등록하며, DART에는 기존 `DART_API_KEY` 환경변수 호환 fallback이 있습니다. KRX Data Marketplace 로그인은 사용자별 별도 private 저장소를 사용하며 전역 환경변수 fallback은 사용하지 않습니다. 인증정보 전체값은 설정 상태 응답에 노출하지 않습니다. IPO의 일정·과거자료·공시 값은 소스와 시점을 검증하고 불확실한 값을 임의로 채우지 않습니다.

## 설치 및 로컬 실행

Python 3.11 이상이 필요합니다. Windows PowerShell 기준:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 4829
```

`http://127.0.0.1:4829`에 접속합니다. `.env.example`은 선택적 설정의 이름과 형식을 보여줍니다. `DASHBOARD_SECRET_KEY`를 명시하지 않으면 앱이 `data/system/secrets/application.json`에 세션 서명 키를 안전하게 생성·재사용합니다. 운영에서는 영구 데이터 마운트와 호스트 파일 권한을 확인하세요.

## Docker / 운영 배포

`docker-compose.yml`은 소스에서 직접 빌드하는 로컬용입니다. 운영 표준은 GHCR 이미지와 `docker-compose.ghcr.yml` 및 호스트별 `docker-compose.override.yml` 조합입니다. 배포 전 운영 호스트의 데이터·Toss WTS 마운트를 확인하세요.

배포 전 Docker 저장소의 가용 용량과 inode를 확인하세요. 불필요한 백업 이미지·아카이브·롤백 태그를 자동 생성하지 않으며, 공간 확보를 위해 금융 데이터 볼륨을 삭제하거나 변경하지 않습니다.

```bash
docker compose \
  -f docker-compose.ghcr.yml \
  -f docker-compose.override.yml \
  pull dashboard

docker compose \
  -f docker-compose.ghcr.yml \
  -f docker-compose.override.yml \
  up -d dashboard
```

기본 서비스명은 `dashboard`, 컨테이너명은 `wealth`입니다. 배포와 자격정보 보존 규칙은 [현재 프로젝트 상태](docs/PROJECT_STATE.md)와 [보안 및 설정 문서](docs/SECURITY_AND_CONFIG.md)를 참고하세요.

### Toss WTS QR 인증 런타임

Docker 이미지는 Python 3.11 / Debian Bookworm 기반이며, 인증 전용 venv에 고정 버전 Playwright와 Chromium·시스템 의존성을 빌드 시 설치합니다. AMD64와 ARM64를 지원하며 로그인 시 패키지 설치나 브라우저 다운로드를 하지 않습니다. 공식 tossctl v0.50.3 helper와 MIT 고지를 vendor에 보존하고 Chromium 채널 및 비공개 QR 확인 문자 전달만 필요한 범위에서 확장했습니다.

사용자별 세션 경로 `/app/data/toss-wts/users/<username>/config/session.json`과 `/opt/toss-wts/tossctl` 실행파일 마운트는 유지합니다. QR와 확인 문자는 owner 전용 API로 전달하며 인증 성공은 `auth status`의 `active && valid`로 확인합니다. Linux supervisor는 자식 종료 증거가 불확실하면 인증 guard를 유지합니다. 자세한 설치·제약·운영 확인 항목은 [Toss 인증 런타임](ops/toss-auth/README.md)을 참고하세요. 로컬 Python 설치만으로 Docker의 브라우저 인증 환경이 설치되는 것은 아닙니다.

main 대상 관련 PR에는 `.github/workflows/toss-auth-pr-validation.yml`이 네이티브 `ubuntu-24.04` / `ubuntu-24.04-arm`에서 synthetic 프로세스 테스트와 Docker build smoke를 실행합니다. detached-child 테스트가 skip되면 실패하며 Docker의 network-disabled Chromium smoke도 우회하지 않습니다. 이 워크플로는 이미지를 push하지 않습니다. 기존 `docker-publish.yml`은 main push 시 멀티아키텍처 이미지를 발행합니다. 실제 운영 QR 인증 성공 여부는 CI 결과와 구분하여 별도로 확인해야 합니다.

## 테스트

전체 회귀 테스트는 pytest로 실행합니다. 테스트는 실제 운영 데이터나 외부 증권사 계정을 사용하지 않아야 합니다.

```powershell
$oldPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = "tests"
    python -m pytest -q
    $testExit = $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $oldPythonPath
}
Write-Host "PYTEST_EXIT=$testExit"
```

관련 기능을 바꿀 때는 해당 테스트를 먼저 실행하고, Python 변경은 `py_compile`, JavaScript 변경은 `node --check`, 최종 변경은 `git diff --check`로 확인합니다.

v2 UI 변경의 사용자 실행용 검증 목록, 자산 비중/수익률 표시 정책과 cleanup 근거는 [v2 UI 마감 기록](docs/v2-ui-cleanup.md)에 정리했습니다. 현재 개발 소스의 앱 버전·service-worker cache는 `2.1.1`이며 static asset의 `?v=`는 파일별 cache revision입니다. 미변경 AccountInfo importer·money-input loader·dialog CSS는 `2.0.3-ai1`이고, 변경된 core JS와 연결된 `application-assets-revision`은 `2.1.1-r1`, layout CSS는 `2.0.2-r5`를 유지합니다. B2 배당 출처 JS·What-if JS/CSS revision은 `2.1.0-b2`입니다. 현재 Oracle 운영은 v2.1.0이며 v2.1.1은 미배포입니다.

## 프로젝트 문서

- [현재 상태](docs/PROJECT_STATE.md): main에 반영된 범위와 운영·검증 관례
- [ROADMAP](docs/ROADMAP.md): 완료 영역, 다음 후보, 보류 항목
- [보안 및 설정](docs/SECURITY_AND_CONFIG.md): 데이터 위치와 인증정보 해석 계약
- [CHANGELOG](CHANGELOG.md): 상세 변경 이력
- [docs/](docs/): 기능별 계산·가져오기·외부 공급자 계약

## 주의사항

Wealth의 시세·평가·수익률·세금 추정은 금융기관의 최종 정산이나 법적 신고 결과와 다를 수 있습니다. 금융 거래와 세무 신고 전에는 원본 자료를 확인하세요.
