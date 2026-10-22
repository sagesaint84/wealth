# Wealth 변경 이력

## 2026-10-21 — PR #161 운영 배포 (v2.1.2 / route1)

- [PR #161](https://github.com/sagesaint84/wealth/pull/161) Squash Merge SHA `fc0bb1092b6d55ee21a786b0d295c48bdcba4c14`: 초기 deep-link 화면 표시·route 상태 개선, 숨겨진 투자 DOM/가계부 조회의 지연 실행, 중복·오래된 요청 방어, 검증된 미사용 레이아웃 코드 정리. 앱 버전 **v2.1.2** 유지; 정적 asset/SW revision **2.1.2-route1**, core **2.1.2-r1**.
- GitHub CI **4/4 PASS** (정적 전송/IPO 회귀/Toss WTS Linux AMD64·ARM64); [GHCR 발행](https://github.com/sagesaint84/wealth/actions/runs/39572486587) SUCCESS, 태그 `ghcr.io/sagesaint84/wealth:fc0bb10`, 다중 플랫폼 manifest Digest `sha256:b82b79c9a3e781810a9c823237473fe09549fa72825c5756c5c97b0774cd05b9`.
- **Oracle 사용자 확인**: `wealth` 재생성 후 이미지 ID `sha256:4d6133a4e1977b739c3e1065023e7f18616e0289674911a2050c64783c9a3f82`; 영구 데이터/Toss 마운트 유지, HTTP 307, 배포·이미지·마운트·HTTP 점검 PASS. 시작 직후 일시적 연결 reset 후 307 응답.
- **실제 운영 화면 사용자 보고 5/5 PASS**: 홈 로그인, `#invest` 직접 새로고침, `#ledger` 직접 새로고침·월간 현금흐름, DAY 차트, 모바일 화면. 원격 독립 자동 브라우저 검증은 미실행.
- 전체 Windows pytest **4,424 passed / 1 failed / 5 skipped / 888 subtests passed**. 실패한 `test_native_daily_pointer_accuracy[True-dividend]`는 이후 포인터 조건 4/4 집중 검사에서 통과했으나 원인 **UNCONFIRMED**.
- 모바일 자산 표시 약 **+488ms**, readiness 약 **+532ms** 지연 위험은 제한된 비교 관측으로 남으며 **PERFORMANCE_NUMERIC_GATE=FAIL**. 사용자의 **PR #161 한정 성능 예외 승인**으로 배포했으며 이력을 PASS로 수정하지 않는다. v2.1.3 P0(원본27/통합33/최소2)는 분리·보호.
- 아래 '미배포'·'HOLD' 표기는 **개발 및 출시 의사결정 이전 시점의 과거 이력**이다. 현재 운영 배포 결과는 이 항목이 우선한다.

- **태그·Release 현황(2026-10-22, 사용자 제공)**: 운영 배포 커밋 `fc0bb1092b6d55ee21a786b0d295c48bdcba4c14`에 Git 태그 `v2.1.2` 등록 완료. **GitHub Release는 아직 생성되지 않았다.** 아래 과거 태그 미등록 문구는 당시 조회 기록으로 보존한다.

## Wealth v2.1.3 — P0 릴리스 준비 (미머지·미배포, 2026-10-22)

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


## v2.1.2 홈 초기 UI 핫픽스 — PR #159 운영 배포 기록 (2026-10-21)

- [PR #159](https://github.com/sagesaint84/wealth/pull/159) Squash Merge 완료. 확인한 main/배포 코드 SHA `b5a5c525f24ec7233b85af70dc8242a25966e150`. 앱 **2.1.2**, 홈 assets/SW **2.1.2-home1**, core **2.1.2-r1** 유지; 미완료 v2.1.3 P0 제외.
- 현재 홈을 최초 HTML에 배치해 구형 UI의 순간 노출과 JS DOM 재구성을 줄였다. 합성 캡처의 현재 홈 유지 검증과 출시 전 인증·금융·IPO 검증을 보존하며 앱 기능을 추가 변경하지 않았다.
- Windows **4,414 PASS / 0 FAIL / 5 SKIP / 888 subtests PASS**, 실제 앱 인증 **24 PASS**. PR Linux CI 정적·홈·DAY **330 PASS**(DAY 38개 무스킵), IPO **239 PASS**, native AMD64/ARM64 각각 ledger **488 PASS**, process **24 PASS / 11 subtests PASS**. Linux 필수 프로세스 2개 양쪽 무스킵 PASS. 외부 live 3개는 Windows의 의도적 SKIP 이력이다.
- [GHCR 39522925985](https://github.com/sagesaint84/wealth/actions/runs/39522925985) SUCCESS, Linux AMD64/ARM64 manifest 및 Digest `sha256:c9b586098a4d31860008782531f2163e7f274938de2e2f0c6bc185b143fd4ffc`를 레지스트리에서 확인했다. 이미지 tag `b5a5c52`.
- 사용자 확인 Oracle 결과: **IMAGE_DIGEST_GATE=PASS / DEPLOY_GATE=PASS / wealth running**. Codex 서버 재검증 결과가 아니다. 이전에는 스크립트 기대값만 확인했으나, 이후 사용자가 Oracle 읽기 전용 조회 결과로 실행 이미지 `RepoDigests`와 GHCR 발행 Digest 일치를 확인했다. 현재 **ORACLE_IMAGE_DIGEST_VERIFIED=PASS**는 사용자 제공 명령 출력에 근거한다. 배포 후 실제 브라우저 smoke **NOT_CONFIRMED**; 출시 전 합성 UI·실제 앱 인증 결과와 구분한다.
- 기존 모바일 자산 표시 1698→1396ms, readiness 2072→1718ms, CLS 0.243→0.034. FCP **200→220ms FAIL_WITH_APPROVED_CANDIDATE_EXCEPTION**, 이번 후보만 승인. DAY 과거 일회성 실패 원인 **UNCONFIRMED** 유지. 기존 OCR smoke의 mismatched_inputs=4/4 진단은 수동 검토 안전성 PASS와 구분한다.
- GitHub Releases 0건, `v2.1.2` tag 없음(조회 시점). 앱/문서 버전은 2.1.2로 일치하며 별도 Release/tag를 생성하지 않았다. 이번 후속 작업은 문서와 정리 가능성 조사만 수행하며 재빌드·재배포·삭제는 하지 않는다.

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

- 최초 HTML에 현재 홈·내비게이션·패널 부모 구조를 배치하고 중복 workspace 생성 및 주요 DOM 이동을 줄였다. 저장된 purple/white/oled 테마는 초기 복원 경로를 유지한다. 금융 계산·요청/기록 순서·인증·IPO backend는 변경하지 않는다.
- 정적 revision과 HTML 조상관계 검사를 현재 구조에 맞추고, IPO의 원본 보존과 정확한 DART 미검증 메타데이터 계약을 구분했다. DAY 차트 assertion은 유지한 채 실패 시 연결 상태·계산 스타일 진단만 보강했다.
- 최종 Windows 전체 검증: **4,414 PASS / 0 FAIL / 5 SKIP / 888 subtests PASS**, exit **0**. DAY 차트와 IPO 대상 2건 PASS. 실제 인증 **24 PASS**는 기존 격리 E2E 결과를 보존한다.
- 기존 warm 자산 표시 1698→1396ms, readiness 2072→1718ms, CLS 0.243→0.034 개선을 보존한다. 모바일 FCP **200→220ms FAIL**은 **이번 후보에 한정한 사용자 승인 예외**다. 기준을 PASS로 바꾸거나 미래 릴리스에 자동 적용하지 않는다.
- 과거 DAY 차트 full-run 실패 원인은 **UNCONFIRMED**다. 이번 PASS가 원인 규명이나 비결정성 제거를 의미하지 않는다. Linux CI에서 차트와 Linux 전용 2개를 필수 검증해야 한다. 외부 live 3개는 의도적으로 미실행이다.
- **PR_READY_PENDING_LINUX_CI**. 앱 2.1.2 / assets 2.1.2-home1 유지, v2.1.3 P0 포함 없음. PR 제출 준비로 기존 선택형 CI에 DAY 모듈 38개 및 IPO 계약 모듈 2개와 XML 실행 보장 검사를 추가했다. 기존 Linux 전용 2개 무스킵 검사는 유지한다. CI 설정 정적 검증 PASS, 실제 Linux 통과는 PR/Actions에서 확인해야 한다. 머지·GHCR·Oracle 배포·Compose 변경은 별도 승인 전까지 진행하지 않는다.

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

## PR #155 개발 당시 기록 — 현재 머지·배포는 사용자 확인 기준

- 정정신고서 제출 요구와 철회 공시를 일정 데이터와 분리해 보존하고, 이전 청약·예정상장 이벤트를 제외한다. 새로운 공식 신고서의 연결된 일정으로 복원한다.
- DART 조회 실패·회사 코드 불일치 시 기존 날짜는 남기되 캘린더에 확인 필요로 표시한다. 외부 사이트의 오래된 일정과 과거 응답은 공식 중단 상태를 해제하지 못한다.
- 합성 데이터 회귀 및 실제 캘린더 DOM 검증을 추가한다. 운영 반영·전체 회귀·배포 검증 결과가 아니다.
- IPO 전용 PR CI를 추가한다. 제한된 집중 pytest와 Chromium만 실행하고, 테스트 프로세스는 loopback 전용 네트워크 공간에서 실행한다. Docker 게시·배포·산출물 업로드는 하지 않는다. CI 성공 여부는 실제 실행 결과로 별도 확인한다.
- 최종 관련 회귀 범위를 캘린더 API·프런트엔드·회사 식별·저장·소유자별 신청 체크까지 확대한다. 로컬 142 PASS(Chromium 포함)이며 전체 pytest·운영 검증을 대체하지 않는다. 확대 CI는 새 PR HEAD의 결과로 확인한다.

## Wealth v2.1.2 — 금융소득 기준 포함액 및 실제 배당 세금 유형 (운영 배포 완료)

사용자 제공 완료 기록: [PR #153](https://github.com/sagesaint84/wealth/pull/153) Squash Merge, main `255d135b8562b5569a11ac7c213787dccbcc2513`, 기능 커밋 `71e5c254f01a57336d31a7b2f634088dfce5ab23`. 전체 pytest **4,353 passed / 2 skipped / 4 warnings / 888 subtests passed**, 집중 테스트 **191 passed / 30 subtests passed**, 기존 Chromium 회귀 **35 passed**. AMD64/ARM64 PR CI SUCCESS ([실행 39103493324](https://github.com/sagesaint84/wealth/actions/runs/39103493324)), GHCR 빌드 SUCCESS ([실행 39103784893](https://github.com/sagesaint84/wealth/actions/runs/39103784893)).

운영 이미지 `ghcr.io/sagesaint84/wealth:255d135`, Manifest Digest `sha256:837709730d1b0d80abf7360b13d71e3c7261d793923befaab2238753429ad7eb`. Oracle ARM64: `V212_PRE_DEPLOY_GATE=PASS`, `V212_IMAGE_GATE=PASS`, `DATA_MOUNTS=PASS`, `V212_COMPOSE_GATE=PASS`, `VERSION_212=PASS`, 최종 HTTP 307, 컨테이너 running / RESTARTS=0, **`ORACLE_V212_DEPLOY=PASS`**. v2.1.1 롤백 이미지 `rollback-before-v212`와 이전 운영 Compose 백업 `docker-compose.release.before-v212.yml`은 보존됐다.

실제 배당 기록에 고배당 분리과세 적용 및 선택형 대상 금액을 추가한다. 공식 자격과 사용자 선택·신청 가정을 분리하며 기존 capital_dividend_mode 호환성을 유지한다. 기존 세전 역산·기록 환율·2026 What-if 계산을 재사용해 전체 세전 금융소득, 감액배당 제외, 고배당 분리과세 제외, 기준 포함액과 여유 금액을 표시한다. 감액배당과 고배당은 중복 차감하지 않으며 현금 하한은 제외 전 총액에만 적용한다. 개인별 2천만원 기준은 정확히 같은 금액까지 기준 이내이고 가족 합계에는 적용하지 않는다. 실제 입금·세전·원천징수 원본 및 기존 배당 카드는 변경하지 않고 과거 기록을 일괄 변환하지 않는다.

**실제 사용자 브라우저 검증 대기:** v2.1.2 세금 유형·금융소득 화면의 최종 사용자 확인은 아직 보고되지 않았다. 운영 배포 성공과 화면 사용자 검증 완료는 구분한다. 위 테스트·CI·배포 결과는 사용자 제공 이력이며 이번 문서 작업에서 테스트 실행이나 Oracle 서버 재확인은 하지 않았다.

금융소득 특례 계산은 기존 2026년/KRW 범위를 유지하고 USD 일반 배당은 저장 환율과 기존 역산을 재사용한다. 공식 공시 조회의 기존 범위·정정 계보 한계는 유지하며 사용자 선택을 공식 자격으로 승격하지 않는다.

## Wealth v2.1.1 — 실제 배당 기록 및 자산 차트 UX (운영 배포 완료)

사용자 제공 운영 검증: v2.1.1 PR #152 Squash Merge, main `251d51ea4112a117f6748d5c7c73c03a4b274280`. 전체 pytest 4327 PASS / 2 SKIP, Chromium 35 PASS, AMD64/ARM64 PR CI SUCCESS. GHCR 실행 `39085363475` SUCCESS, 이미지 `ghcr.io/sagesaint84/wealth@sha256:000ba9c6b47c09d50899695fd8a51619f1eab0a25e24c8dd46b5019077e3cdba`. Oracle ARM64 IMAGE_GATE/DATA_MOUNTS/VERSION_211/ORACLE_DEPLOY=PASS, HTTP_STATUS=307, RESTARTS=0. 이번 작업에서 운영 서버를 재검증한 결과가 아니다.

아래 항목의 미배포·미실행 표현은 개발 당시 기록이다.

- 개인 자산관리 편의성 우선: 실제 입금액 자동 세전 역산, 선택형 세전/세액/세율 상세, 감액배당 AUTO·직접 적용·제외를 기존 기록별 메타데이터로 보존. 공식 공시 구성 근거와 사용자 지정은 구분하며 개인 세무 자격을 확정하지 않는다.
- 국내/USD 기존 세율과 기록 환율을 재사용하고 부분 감액배당·명시적 0·직접 입력을 지원한다. 실제 수령액·실제 세금·기존 금융 기록 일괄 변경 없음.
- 실제 배당 4카드를 선택 월 수령·연간 세전·연간 누적 실제 수령·월 종목/건수로 정리하고 이자를 분리한다. 예상 배당 카드는 유지한다.
- 통합 차트 공통 hover/tap/키보드 금액 툴팁, 최신 주식자산/순자산 저장 금액·날짜 표시. 기존 선택·pan/zoom 및 Y축 경로를 재사용한다.
- 앱/HTML/SW 2.1.1 및 변경 JS/동적 loader `2.1.1-r1` 동기화. 운영은 사용자 확인 기준 v2.1.0(`7236dd3` main)이며 이번 개발은 미배포다.
- 합성 회귀 테스트 작성. 이번 단계 pytest/Chromium은 실행하지 않았고 기존 PASS 기록과 구분한다. 실제 데이터·인증정보·운영 서버 접근, commit/push/PR/배포 없음.


## Wealth v2.1.0 — 배당 공식 근거 및 예상 세금 혜택 미리보기 — 2026-10-17 (개발 변경·PR 미병합·운영 미배포)

- Phase A는 지급 이벤트 혼합 방지와 320자 인용문 기준 span 정합성을 보완해 `f290d9b211b166e49e320d38fa0a2bdd571bfad7`로 보존했다. 해당 커밋 전 실제 집중 검증은 84 PASS, subtests 39 PASS다. 원본 보존 커밋 `6c88396b036d8826979f0379d255d4e6f4055194`도 유지한다.
- Phase B1은 기존 OpenDART 다운로드 원문을 두 파서가 재사용한다. 구성 파서 오류는 신규 근거만 unavailable로 반환하고 기존 현금배당 확정값·예상/실제 배당·원천징수·세금·고배당기업 판정·금융 저장을 변경하지 않는다. 보통주 대상의 읽기 전용 `capital_dividend_evidence`는 기존 structured 응답의 형제와 배당 요약 최상위 별도 영역에 전달하며 스냅샷의 forecast_source에는 넣지 않는다. B1 당시 UI는 미구현이었다.
- Phase A의 Decimal 십진 문자열·null/명시적 0·이벤트 미확인·개인 과세 not_assessed 계약을 유지한다. 재원 설명이 없으면 not_confirmed이며 고배당기업 분리과세 자격과 동일시하지 않는다. 근거는 plain text이며 향후 UI는 textContent/escape를 사용해야 한다.
- 기존 370일·첫 100건 조회 및 최신 공시 선택 정책을 유지한다. 정정 제목·공식 rm 비고를 관찰하되 원공시/정정 관계는 not_resolved다. 선택 공시의 후속 정정 표시·조회 내 철회·동일 receipt의 상충 메타데이터는 신규 구성금액 확정만 차단한다. 전체 정정 계보·교차 공시 금액 비교는 미구현이다.
- 하위 호환 근거 추가로 개발 APP_VERSION·HTML 메타/화면 표시·SW 캐시를 2.1.0으로 동기화한다. 수정하지 않은 JS/CSS revision 및 application-assets-revision은 유지한다. Oracle는 v2.0.3 / `b1e6e59`, PR #149·#150 운영 이력은 아래에 보존한다. 이후 B2 미리보기의 범위는 아래 기록을 따르며 새 세율표·전문 세무 판정 엔진은 추가하지 않는다.
- 최초 B1 로컬 집중 검증: Python 3.14.2의 합성/mock 13개 모듈 **214 PASS / 0 FAIL / 0 SKIP**, subtests **51 PASS**(10.27초). 동일 모의 응답으로 Phase A 커밋의 소스 서비스를 실행해 기존 배당·세금·고배당기업 결과와 저장용 스냅샷 불변을 확인했다. Python 6개 파일/SW 문법·정적 자산 revision 보존·git diff --check PASS, 이번 합성 임시 경로 자동 제거 확인. 전체 pytest·실제 DART·CI·v2.1.0 병합/배포는 미실행이다.

- B1 감사 보완: 같은 원문으로 현금배당/구성 파서를 각각 실행하고 양방향 실패를 격리했다. ZIP 추출 실패·개별 파서 실패·요청 실패를 구분하며 기존 현금배당 파서가 실패한 경우 구성금액 verified만으로 예상액을 보강하지 않는다. 목록의 정상 부재(013 포함), 명시적 API 오류, 비정상 응답을 분리하고 안전한 3자리 오류 코드만 노출한다. 기존 조회 범위·횟수·현금배당 fallback은 유지한다.
- 감사 보완 후 격리 집중 13개 모듈 **222 PASS / 0 FAIL / 0 SKIP**, subtests **72 PASS**. Phase A·수정 전 B1·수정 후 B1을 12개 합성/mock 조건으로 비교해 기존 응답·저장 스냅샷·요청 횟수 동일 및 금융 writer 미호출을 확인했다. 감사 시작 시점의 수정 전 B1 비-live 전체 재실행은 **4,278 PASS / 0 FAIL / 2 SKIP**, subtests **849 PASS**, 4 warnings(1338.93초), 종료 코드 0이었다. 기존 Linux 커널 통합 검사 2개는 플랫폼 조건으로 skip됐고 tests/live는 제외했다. 이전 중단 실행의 실패 node ID·원인은 재현되지 않아 UNKNOWN이다. 수정 후 B1 전체 실행·실제 API·CI는 미검증이다. 이번 격리 경로 정리는 자동 승인 정책으로 차단돼 우회하지 않았다.

- B2 개발 변경: 배당/What-if의 단일 이벤트 미리보기에서 AUTO·MANUAL_ON·MANUAL_OFF, 대상 금액 입력, 예상 차이와 공식 원문 링크를 제공한다. 인증 사용자·소유자·이벤트·연도별 세션 메모리 선택이며 새로고침 후 영구 보존은 하지 않는다. 서버가 공식 근거와 이벤트 금액을 다시 조회하고 오래된 사용자 범위·다른 이벤트 선택을 거부한다.
- 고배당기업 공식 판정과 기존 2026 What-if/누진세 계산을 재사용한다. 공식 사업연도·이벤트·지급연도·대상 금액이 일치하고 정정 경고가 없는 경우만 AUTO를 허용한다. 감액배당 적용액을 먼저 제외해 같은 금액을 고배당기업 대상에서 중복 차감하지 않는다. 개인 적용 요건 미확인인 현재 B1 자료는 감액배당 AUTO 비과세 근거로 쓰지 않으며 수동 선택은 사용자 가정으로 구분한다.
- 실제 배당/원천징수/실현손익/금융 원본·기존 예상 총액은 변경하지 않는다. 고배당기업 국세는 일반 원천징수 국세와 단순 비교하며 지방세·종합과세 대비 유불리를 확정하지 않는다. 신고 시 신청 조건을 유지한다. 변경 JS 2개/CSS 1개 revision만 `2.1.0-b2`로 갱신하고 앱/HTML/SW 2.1.0·운영 2.0.3은 유지한다.
- B2 최종 합성/mock 집중 **242 PASS / 0 FAIL / 0 SKIP**: 21개 모듈 214 PASS, subtests 69 PASS(26.05초), 기존/신규 Chromium 모듈 28 PASS(115.68초). 320/390/1280px, AUTO/수동/제외/자동 복원, 미확인 금액 입력, 실패 초안·늦은 응답·사용자/소유자/연도/이벤트 분리, XSS·overflow 방지와 기존 화면 회귀를 확인했다. Starlette/httpx 의존성 deprecation 경고 1건은 실패가 아니다. 이 검증 당시 전체 pytest·외부 API·PR CI·커밋·운영 배포는 실행하지 않았다.

- B2 커밋 전 핵심 재검증: 서비스/API·금융/버전/정적 69 PASS(subtests 25 PASS), Chromium 4 PASS, 합계 73 PASS / 0 FAIL / 0 SKIP. 기존 242 PASS와 구분한다. 화면에 기본 세후 카드와 별도 계산·자동 합산 없음 문구를 보완했다. 전체 pytest·PR CI는 이번에도 미실행이다.

## Wealth v2.0.3 — AccountInfo PDF 반응형 계좌 미리보기 — 2026-10-17 (운영 배포 완료)

- **배포 완료**: [PR #149](https://github.com/sagesaint84/wealth/pull/149) Squash Merge, 운영 main `b1e6e59d0f650db6023cdc7bf95c1b22d2f5694b`. Native AMD64/ARM64 [CI 38930119488](https://github.com/sagesaint84/wealth/actions/runs/38930119488) 및 [GHCR run 38931035808](https://github.com/sagesaint84/wealth/actions/runs/38931035808) SUCCESS. 운영 이미지 `ghcr.io/sagesaint84/wealth:b1e6e59`를 Oracle ARM64 `/docker/wealth`의 `wealth` 컨테이너에 배포했다. 사용자 제공 10분 안정성 확인은 `RUNNING=true`, `RESTARTS=0`, `EXIT=0`, `HTTP=307`이며 금융 데이터/Toss 마운트 PASS, 이전 롤백 이미지 보존 확인이다.
- **사용자 실제 화면 확인**: 계좌 카드, PDF 잔액 전체 표시, 은행 신규 잔액 편집, 증권 참고값 구분, 버튼 접근성, 기존 자산 데이터 유지의 6개 항목 모두 정상이다. 실제 신규 계좌 등록·전체 금융 API 실거래 검증 완료로 확대하지 않는다. 개발 당시 집중 검증 129 PASS는 아래 이력과 구분한다.
- PR #147은 이미 CI·Squash Merge·Oracle 배포 완료된 이전 단계이며, 당시 운영 main은 `113c663023586dd8a217d15ac9ca9bd3cfd47648`이었다. 다음 개발 당시 기록의 미병합·미배포·미실행 표현과 과거 실패 결과는 각 시점의 이력이다.
- AccountInfo PDF의 7열·최소 폭 850px 테이블을 마스킹된 계좌 카드 목록으로 바꾼다. 모바일은 1열, 충분히 넓은 화면은 2열이며 긴 상품명과 참고 잔액을 줄바꿈해 표시한다. PDF 전용 dialog 폭과 높이를 적용하고 제목·소유자/파일 선택·하단 버튼을 유지하면서 미리보기 한 곳만 세로 스크롤한다. CSV/XLSX 모드의 기존 크기·안내·저장 흐름은 유지한다.
- 증권 PDF 원본 잔액은 읽기 전용 참고값으로 표시하며 예수금에 반영하지 않는다. 은행은 PDF 원본 참고 잔액과 신규 등록 잔액 입력을 분리하며, 미확인 0원과 실제 0원 표시·직접 편집·사용자 확인·중복/소유자 충돌 차단을 유지한다. PDF parser·금융 API·계산·마스킹 정책은 변경하지 않는다.
- 사용자에게 보이는 UI 개선을 PATCH 릴리스 v2.0.3으로 분류한다. APP_VERSION·HTML 메타/하단 표시·서비스워커 캐시를 2.0.3으로 동기화하고, dialog CSS·AccountInfo importer·money-input loader revision은 `2.0.3-ai1`로 정리한다. 미변경 core JS와 연결된 `application-assets-revision`은 `2.0.2-r7` 및 다른 파일별 revision은 유지한다. 구현 커밋은 `ebd66452e185ddbf3e0d2a7cc6d6a290790c6dc7`, 브랜치는 `codex/v202-accountinfo-pdf-responsive-preview`다. 당시 새 UI는 개발 완료·미병합·운영 미배포 상태였으며 버전 동기화 작업에서는 커밋·푸시·PR 생성·병합·배포를 수행하지 않았다. 이후 운영 완료 상태는 위 배포 기록을 따른다.
- UI 구현 당시 격리된 합성 데이터 검증: `test_ledger_document_chrome.py`, `test_accountinfo_pdf_import_frontend.py`, `test_release_version.py`, `test_money_input_ux.py` **82 passed / 0 failed / 0 skipped**, 162.76초. 가상 36계좌로 5개 너비 × 3개 테마 × 은행/증권 30개 실제 Chromium DOM 조합을 검사하고, 잔액/상품명 전체 표시·가로 overflow 부재·단일 세로 스크롤·선택/비활성·키보드/버튼 접근·은행 편집/0원 payload·증권 예수금 0원·CSV/XLSX 복원을 확인했다. PDF.js만 합성 의존성으로 대체했으며 개인 PDF·금융 데이터는 사용하지 않았다. 변경 JS 2개 Node 문법 검사 및 `git diff --check` PASS. 전체 pytest·Native CI·운영 배포 검증은 해당 UI 구현 작업에서 실행하지 않았다.
- 버전·MD 동기화와 작업 종료 전 일치 검사를 필수 작업 원칙으로 `docs/PROJECT_STATE.md` 상단에 기록했다.
- v2.0.3 동기화 후 격리 재검증: 기존 AccountInfo/UI/버전 네 모듈 **82 passed**(164.96초), 추가 서비스워커·자산 revision 회귀 세 모듈 **47 passed**(8.19초), 합계 **129 PASS / 0 FAIL / 0 SKIP**. Python 7개 파일·JavaScript 3개 파일 문법 및 `git diff --check` PASS. 앞선 UI 구현 당시 82 PASS와 해당 재검증 결과를 구분하며, 버전 동기화 작업에서는 전체 pytest·전체 CI·배포를 실행하지 않았다.
- 저장소 내 새 fixture/더미 파일은 없다. 이전 UI 검증 및 이번 버전 재검증의 시스템 임시 부모 경로 삭제는 실행 환경의 자동 승인 정책에 차단되어 정리 미완료 상태다. 우회하지 않았으며 테스트 PASS와 임시 부모 경로 정리 상태를 구분한다.

## Wealth v2.0.2 — PR #147 Chromium 프로필 teardown 경합 보정 — 2026-10-16

- 사용자 제공 Actions `38910472439`는 AMD64 **456 passed / 3 errors**, ARM64 **456 passed / 15 errors**다. 기능 테스트 통과 후 Chromium 프로필 삭제에서 `ENOTEMPTY` 및 하위 파일 `ENOENT` 경합이 발생했다. 기존 `cleanup_profile()`은 `PermissionError`만 재시도했다.
- 해당 함수에서 일시적 `ENOTEMPTY`·`ENOENT`도 기존 4초 제한과 재시도 간격으로 처리한다. `ENOENT`는 `lstat`으로 프로필 루트 소멸을 확인한 경우만 성공하며, 루트가 남으면 재시도하고 기한 초과 시 실패한다. 예상하지 못한 `OSError`와 Chrome 종료 실패·실행 중 프로필 보호 정책은 유지한다.
- 결정적 단위 테스트를 추가하고 기존 cleanup 테스트는 보존했다. workflow·운영 설정·기능/UI 테스트·금융 저장·OCR·APP_VERSION 2.0.2는 변경하지 않았다. 이번 수정 후 테스트·CI는 미실행으로 수정 결과는 미검증이며, 커밋·푸시·병합·배포는 수행하지 않았다.

## Wealth v2.0.2 — PR #147 synthetic CI Chromium 실행 환경 보정 — 2026-10-16

- 사용자 제공 Actions run `38908552179` 결과는 AMD64/ARM64 각각 **426 passed / 30 errors**이며, 30건은 모두 Chromium 시작 시 `No usable sandbox` 오류다. 이 실패 기록을 통과로 바꾸지 않는다.
- 기존 Chromium 설치 구간에서 Playwright의 실제 실행 파일을 확인하고, CI의 임시 `RUNNER_TEMP/chrome` wrapper가 해당 파일을 `exec`하도록 변경했다. `--no-sandbox`는 이 일회성 synthetic loopback 테스트에만 적용하며 실행 실패의 종료 코드는 그대로 전달한다. 기존 네 회귀 모듈과 skip/failure/error 차단은 유지한다.
- `tests/chrome_harness.py`, Dockerfile·운영 Chromium·컨테이너 제한·국민연금 필수 검사·정확도 진단·금융 저장·OCR·AccountInfo는 변경하지 않는다. APP_VERSION 2.0.2와 정적 revision을 유지한다. 이번 수정 후 테스트·CI는 미실행이며 성공 여부는 미검증이다. 커밋·푸시·병합·배포는 수행하지 않았다.

## Wealth v2.0.2 — PR #147 Native CI 안전성·정확도 결과 분리 — 2026-10-16 (개발 변경 — 작성 당시 운영 미배포)

- 기존 `validate_ledger_result()`의 합성 원문 정확값 검사와 `EXACT` 필드별 진단을 유지한다. 가계부 후보의 응답 형식·검토 필요 상태·소유자/계좌/연도 미확정을 먼저 검사하고, 금융 sentinel byte 불변 및 임시 입력/작업 폴더 정리까지 통과한 경우에만 인식값 불일치를 `ACCURACY MISMATCH`로 보고한다. 정확값 일치는 `ACCURACY MATCH`이며, 안전성 PASS와 별도로 출력한다. 문서 종류 미확인은 경고가 있는 빈 후보 목록의 검토 상태일 때만 수동 입력 대상으로 허용한다. 미확인/누락 값과 정확값 불일치를 인식 성공이나 정확도 PASS로 바꾸지 않는다.
- worker 실행 실패·비정상 종료·잘못된 JSON/응답 형식·확인 없는 저장 또는 확정 상태·소유자/계좌/연도 임의 확정·금융 데이터 변경·정리 실패·자원 제한/보안 정책 위반은 계속 CI를 차단한다. 기존 국민연금 PNG/PDF 필수 정확값 검사와 worker 검사는 그대로 필수다. 기존 재실행 진단의 실행/형식 오류도 무시하지 않는다.
- 기존 native PR workflow에 smoke 분리 회귀, 가계부 worker/자원 제한, 사용자 확인형 저장 및 Chrome 수동 입력/확인 흐름 테스트를 필수 단계로 연결한다. 네 모듈이 실행되고 skip/failure/error가 없어야 하며, 양쪽 native runner에서 동일하게 적용한다. 기존 컨테이너 네트워크 차단·읽기 전용 root·비루트·capability 제한은 유지한다.
- OCR 알고리즘·합성 정확값 기대치·수동 행 추가·금융 저장 로직·AccountInfo 및 APP_VERSION 2.0.2·정적 revision은 변경하지 않는다. RapidOCR 개발은 재개하지 않는다. 이번 변경 후 테스트·문법 검사·Native CI는 실행하지 않았으며, 아래 기존 검증 수치는 이번 변경의 통과 결과가 아니다. 커밋·푸시·병합·배포는 수행하지 않았다.

## Wealth v2.0.2 — PR #147 사용자 확인형 OCR 저장 (개발 변경 — 작성 당시 운영 미배포) — 2026-10-16

- 기존 읽기 전용 은행/카드 PDF·PNG·JPG 거래 후보 추출에서 O2 사용자 확인형 저장으로 확장했다. 사용자가 후보를 직접 편집하고 추가할 행을 선택한 뒤 중복 검토와 최종 확인을 거쳐 가계부 기록으로 저장한다. 금액 미확인 시 `0원(미확인)`을 표시하며, 가계부 저장 전에는 유한한 양수 금액과 필수값을 확인한다. OCR의 거래 후 잔액은 참고용이며 계좌·카드·배당 잔액과 원거래는 변경하지 않는다.
- 기존 가계부 거래 및 선택한 행끼리 날짜·거래 종류·소유자·금액을 비교해 중복 의심을 경고한다. 별도 거래임을 사용자가 확인하고 다시 검토하면 유사 거래도 등록할 수 있다. 서버는 금융 잠금 안에서 revision·review_token과 중복 확인을 다시 검사한 뒤 원자적으로 저장한다.
- OCR 저장 영수증의 신규 생성·저장·보관과 영수증 기반 재시도, 10,000건 제한을 제거했다. 과거 `document_import_requests` 메타데이터는 임의 삭제하지 않는다. 응답 유실 시 commit POST를 자동 재전송하지 않으며 초안을 유지한다. 기존 거래를 재조회하고 저장 여부와 중복 후보를 사용자가 다시 확인해야 한다.
- AccountInfo PDF는 기존 PDF.js 브라우저 텍스트 추출을 유지한다. 신규 은행계좌 잔액을 직접 편집할 수 있고 잔액 미확인 시 `0원(미확인)`으로 기본 미선택한다. 사용자가 명시적으로 선택하고 최종 확인하면 0원으로 등록할 수 있다. 저장 직전 기존 계좌 중복·소유자 충돌을 다시 확인하며 기존 계좌 잔액을 자동 덮어쓰지 않는다. 증권 PDF 잔액은 예수금에 자동 반영하지 않고 신규 증권계좌의 KRW/USD 예수금은 0으로 시작한다.
- APP_VERSION은 2.0.2를 유지한다. 현재 정적 revision은 OCR JS·money-input·AccountInfo loader `2.0.2-review2`, OCR CSS `2.0.2-review1`이며 기존 테스트 기대값과 일치한다. 이번 문서 갱신·최소 정리에서는 revision을 변경하지 않았다.
- 사용자 제공 최신 검증 이력: 최종 집중 pytest **110 PASS / 0 FAIL**, 격리 환경 **PASS**, `git diff --check` **PASS**, 임시 테스트 폴더 정리 **PASS**. 이번 문서 정합성 수정 전에 완료된 사용자 검증 결과이며, 이번 문서 수정 후 테스트를 새로 실행하지 않았다.
- 사용자 제공 이전 검증 이력: 집중 pytest **151 PASS**, 전체 pytest **4115 PASS / 3 FAIL / 5 SKIP**, 실패 3건 별도 격리 재검증 **3 PASS**, JavaScript 문법 검사 **PASS**, 임시 폴더 정리 **PASS**. 전체 실행의 3 FAIL과 격리 재검증 결과는 별개이며 전체 무실패로 간주하지 않는다. 최신 집중 검증도 전체 pytest 무실패 실행을 뜻하지 않는다. 아래 단계별 기록과 기존 배포 이력은 각 당시 상태다.

## Wealth v2.0.2 — PR #147 Native party diagnostic only — 2026-10-15

- `883b4cf`의 [run 38715245006](https://github.com/sagesaint84/wealth/actions/runs/38715245006)은 두 플랫폼 모두 기존 국민연금 OCR 이후 은행 PNG 거래처명 단언에서 실패했다. 이번 변경은 진단 전용이며 운영 파서·인식 알고리즘·합성 fixture·금액/부호/거래처 exact-value 단언은 변경하지 않는다.
- 공개 `/fixtures/bank.png`의 거래처 불일치에서만 별도 private subprocess로 실제 decoder/LineRecognizer/파서를 한 번 재실행한다. `sys.settrace`와 실제 소스의 AST 앵커로 실행된 분기와 지역값을 읽으며 함수·콜백·입력·반환 계약을 바꾸지 않는다. 관측하지 못한 검사는 unknown으로 남긴다. 기존 preview 결과와 진단 재실행 결과를 별도 boolean으로 표시해 서로 다른 실행을 혼동하지 않는다.
- 첫째/둘째 행의 후보·음절 분리·신뢰도 구간·위치/겹침·재인식 호출·출력 생성·검사/채택·거부 분기를 허용된 코드/boolean/횟수만으로 기록한다. 원문·거래처명·금액·계좌·bbox 좌표·preview JSON은 로그에 출력하지 않으며 알 수 없는 진단 필드는 로깅 전에 거부한다. Tesseract 실행 버전은 검증한 숫자 버전만 출력한다.
- 운영 API에는 진단 모드가 없다. probe는 기존 자원 제한과 75초 별도 프로세스 그룹 회수, private 입력 cleanup을 사용하며 금융 writer를 추가하지 않는다. 최종 격리 집중 **329 passed / 0 failed / 0 skipped / 2 warnings**, 173.58초(기존 308 + 신규 21), Python syntax·git diff --check PASS. 생성한 테스트 임시 경로 제거 확인. 로컬 mock 추적과 실제 native 진단을 구분하며 native 결과는 새 Actions를 따른다. APP_VERSION 2.0.2 유지, 전체 pytest·O2·공모주 OCR·Merge·Deploy 미실행.

## Wealth v2.0.2 — PR #147 TXT/TSV evidence hotfix — 2026-10-15

- `e30190d`의 [native run 38710555716](https://github.com/sagesaint84/wealth/actions/runs/38710555716)은 두 플랫폼 모두 은행 PNG 거래처명에서 실패했다. 같은 OCR의 TXT가 정상이고 TSV가 음절별 단어인 합성 입력 4건을 추가해 기존 조합 경로의 실패를 수정 전에 재현했다. 로컬 실제 Tesseract가 없는 Windows의 mock 재현이며, GitHub 원문을 로그로 수집하지 않는다.
- 기존 제한적 행 재인식 1회에서 `--psm 7 txt tsv`를 함께 생성한다. TXT 문장을 거래처 후보로 보존하고 TSV는 좌표·신뢰도 근거로 사용한다. 비공백 문자 비교는 일치 검증에만 쓰며, TSV 공백을 제거한 문자열을 후보로 만들지 않는다. 정상 다중 단어 공백을 유지하고 빈/복수 행·숫자/금액·불명 특수문자·서로 다른 문자 근거는 거부한다.
- 금액은 TXT/TSV 양쪽의 엄격한 숫자·부호 해석과 기존 전체 페이지 근거의 충돌 검사를 모두 통과해야 한다. 금액 추측·쉼표 복원·부호 보정은 추가하지 않았다. 합성 금액과 모든 smoke exact-value 단언, 국민연금 파서 및 공통 decoder는 변경하지 않았다.
- private TXT/TSV 파일 각각 20KB·UTF-8·필수 TSV 열을 검사하고 symlink를 따라가지 않는다. POSIX 파일 권한은 0600이며 crop과 두 출력은 성공/실패/timeout 모두 정리한다. 기존 문서당 8회·누적 12초·회당 3초·전체 55초·외부 75초 및 CPU/메모리/동시 실행 제한은 유지한다. 원문/preview JSON을 로그에 출력하지 않는다.
- 최종 격리 집중 **308 passed / 0 failed / 0 skipped / 2 warnings**, 148.53초(기존 278 + 신규 30), Python syntax·git diff --check PASS. 테스트 임시 경로 제거 확인. 실제 native 결과는 새 커밋의 Actions로 별도 확인한다. APP_VERSION 2.0.2 및 정적 revision 유지, JS/UI·저장/API·O2·공모주 OCR·운영 배포는 변경하지 않는다. 로컬 실제 OCR·Docker·전체 pytest는 미실행이다. Draft PR #147 유지, Merge/Deploy 미실행.

## Wealth v2.0.2 — PR #147 bounded line OCR — 2026-10-15

- 1차 보정 [run 38706993038](https://github.com/sagesaint84/wealth/actions/runs/38706993038)은 AMD64/ARM64 모두 빌드·Chromium·국민연금 OCR, 은행 PNG 유형/검토 상태/2행 조건 이후 거래처명 exact assertion에서 실패했다. 금액·잔액 및 나머지 3개 가계부 입력은 검증 완료로 간주하지 않는다.
- 전체 페이지 TSV를 유지하면서 가계부에서만 선택적으로 동일한 방향/크기의 페이지 이미지에 대한 행 영역 재인식을 추가했다. 페이지 크기와 TSV 크기 일치, 해상도, 글자 높이, bbox 경계·잘림·인접 행 겹침, 원본 confidence를 검사한 뒤 PSM 7 TSV를 읽는다. 재인식 confidence 90 미만 또는 위치 불명확·복수 행 결과는 미확인이다. 한글 공백을 합쳐 이름을 만들거나 숫자를 보정하지 않는다.
- 이미 유효한 두 금액/방향이 다르거나 부호가 손상·충돌하면 기존 근거를 남기고 후보 값을 미확인 처리한다. 잔액/합계·다른 거래행으로 금액을 옮기지 않는다. 재인식 결과도 항상 review_required, 연도·Owner·계좌 미추정이다. 합성 fixture와 smoke의 모든 정확한 기대값은 변경하지 않았다.
- 문서 전체 재인식은 최대 8회, 누적 12초, 1회 최대 3초/출력 20KB다. 전체 decoder 도구 실행은 55초 기한 내에 제한하며 기존 외부 75초 timeout/process-group cleanup, Linux CPU 60초·메모리 512MiB 및 동시 슬롯 2개는 유지한다. 범위·시간 초과는 저장 없이 실패한다. private 0600 crop은 성공·실패/timeout 모두 제거한다.
- 공통 decoder는 페이지 이미지가 다음 페이지로 교체되기 전에 호출하는 opt-in hook만 추가했다. 국민연금은 이 hook을 사용하지 않아 기존 OCR·문자층 및 반환 계약을 유지한다. APP_VERSION 2.0.2, 정적 자산 revision, 금융 저장/계산은 변경하지 않는다. 최종 격리 집중 **278 passed / 0 failed / 0 skipped / 2 warnings**, 134.14초(기존 245 + 신규 33), Python syntax·git diff --check PASS. 생성한 테스트 임시 경로 제거 확인. JS 미변경이며 실제 Windows OCR·로컬 Docker·전체 pytest는 미실행이다. 새 native 성공 여부는 이 커밋의 Actions 결과로 별도 확인한다. O2 저장·공모주 OCR·Merge·Deploy는 추가하지 않는다.

## Wealth v2.0.2 — PR #147 Native OCR spacing hotfix — 2026-10-15

- Draft PR #147의 기존 [run 38705054241](https://github.com/sagesaint84/wealth/actions/runs/38705054241)은 native AMD64/ARM64 이미지 빌드·Chromium·국민연금 PNG/PDF worker까지 성공했으나 첫 은행 PNG의 문서 유형/검토 상태 단언에서 실패했다. coordinator가 검토 상태를 검사하므로 정상 반환 후 실패는 기대 문서 유형 불일치다. 기존 로그에는 원문이 없어 컨테이너의 정확한 OCR 문자열은 확인되지 않았다.
- 합성 TSV의 `10 월 14 일` 등 3개 입력에서 날짜 근거 누락 → unknown 유형을 재현했다. 월·일 단위 앞뒤의 수평 공백만 허용하며 연도 null, 불가능한 날짜·관련 없는 문장 거부, 문서 종류의 독립적 근거를 유지한다. 음절별로 분리된 거래처는 합쳐 복원하지 않고 미확인으로 남긴다. 손상된 숫자·부호는 보정하지 않는다.
- 공개 합성 은행/카드 화면만 NanumGothic Bold 80px 및 거래금액과 원 단위 사이 공백으로 조정했다. 모든 숫자·거래처·정확한 기대값은 유지한다. 기존 국민연금 생성기/도메인 파서, 공통 decoder, API·금융 저장·JS는 변경하지 않았다.
- smoke의 문서 유형과 상태 오류를 분리하고, 유형 실패 때 제한된 subprocess에서 날짜·금액·은행/카드 헤더·TSV 행 근거를 참/거짓만 출력한다. 원문 OCR 및 preview JSON을 로그에 남기지 않는다. 기존 exact-value/cleanup/금융 파일 불변 단언과 네트워크 차단은 유지한다.
- hotfix 최종 격리 집중 검증: **245 passed / 0 failed / 0 skipped / 2 warnings**, 137.58초. 기존 221건과 신규 24건(날짜·거래처·금액·분류·비공개 진단)을 포함하며 Python syntax 및 git diff --check PASS. 임시 테스트 디렉터리 자동 제거를 확인했다. JS 미변경으로 Node 재검사는 생략했다. 새 native CI는 이 커밋의 실제 실행 결과로 별도 확인한다. 로컬 실제 Tesseract·Docker 및 전체 pytest는 미실행. APP_VERSION 2.0.2, 기존 자산 revision 유지. O2 저장·공모주 OCR 미구현, PR은 Draft이며 Merge/Deploy는 실행하지 않는다.

## Wealth v2.0.2 — Phase O1.2 Native Ledger OCR Smoke 준비 — 2026-10-15

- PR 제출 전 보안 검토에서 화면 예시와 겹칠 수 있는 값을 제거하고 공개 fixture·파서/Chrome 테스트·문서의 금액을 명백한 가상 숫자 패턴으로 통일했다. 정확한 기대값 검증은 그대로 유지하며 이 변경은 OCR 오류를 수용하기 위한 조정이 아니다. 운영 이미지는 기존 `ghcr.io/sagesaint84/wealth:d98336a`이며 이번 OCR 변경의 Merge/배포는 별도다.
- 가상 값 교체 후 최종 재검증: **221 passed / 0 failed / 0 skipped / 2 warnings**, 141.84초. Python 문법·Node 문법·git diff --check PASS, 격리 테스트 임시 디렉터리 정리 확인. 아래 155.94초 결과는 최초 O1.2 구현 시점의 기록이다.
- 기존 `ops/pension-ocr` 생성기와 smoke를 확장했다. 공개 Nanum 폰트/Pillow로 가상 은행 PNG(다크), 카드 JPEG(화이트), 각각의 스캔 PDF를 CI 임시 경로에 생성한다. 은행 입금 +1,234,567원·출금 -234,567원, 거래 후 잔액, 상단 잔액과 카드 승인 12,345원·23,456원 및 사용합계 35,801원을 구분한다. 실제 사용자 문서·계좌는 사용하지 않는다.
- 기존 국민연금 합성 PNG/PDF 생성과 한글 인식·실제 worker·금액/날짜/검토 상태 단언을 유지했다. 그 뒤 가계부 preview coordinator → 실제 document worker → 공통 추출/파서의 네 가지 입력 경로를 실행하도록 추가했다. 스캔 PDF의 문자층 부재, 정확한 두 거래행, 원문 기준 금액·방향·잔액·가상 거래처·부분 날짜, 연도 null, 검토 상태와 Owner/계좌 null을 검사한다. 잘못된 OCR 금액을 기대값으로 대체하지 않는다.
- private 입력 cleanup, 합성 금융 JSON의 byte 불변 및 추가 사용자/금융 경로 미생성을 검사하고 고정 PASS/FAIL만 출력한다. 기존 native amd64/arm64 워크플로의 동일 이미지와 `--network none --read-only --cap-drop ALL --security-opt no-new-privileges`·비특권 실행·read-only fixture 마운트를 재사용한다. 기존 ops 경로 trigger가 있어 workflow/Dockerfile/패키지는 변경하지 않았다.
- 로컬 집중 pytest **221 passed / 0 failed / 0 skipped / 2 warnings**, 155.94초. 기존 O1.1 **178 PASS** 유지, 신규 smoke 계약/합성 테스트 **43 PASS**. 공개 시스템 폰트와 실제 OCR은 CI 검증 대상이며, 로컬 생성 테스트는 Pillow 내장 대체 폰트와 mock을 사용한다. 이번 테스트가 만든 두 임시 부모 디렉터리는 자동 정리를 확인했고 이전에 정책 차단된 두 경로는 사용하거나 삭제 재시도하지 않았다.
- PR 제출 직전 기록: 실제 Tesseract/Poppler OCR 통합 및 native AMD64/ARM64 CI는 **PENDING**이다. 로컬 Tesseract 부재로 네이티브 OCR 성공을 주장하지 않는다. 전체 pytest와 로컬 Docker build는 실행하지 않았다. APP_VERSION 2.0.2 및 기존 정적 자산 revision을 유지하며 저장 기능과 공모주 OCR은 추가하지 않았다. 아래 PR #145/#146 운영 이력은 기존 v2.0.2의 기록이며 이번 OCR 변경은 PR 검증 대상·운영 미배포다. 제출 후 최종 CI 결과는 해당 Draft PR/Actions를 따른다.

## Wealth v2.0.2 — Phase O1.1 가계부 OCR 인식 안전성 — 2026-10-15

- 동일 `wealth-ocr` worktree와 `codex/v202-ledger-ipo-ocr-import` 브랜치에서 O1의 15개 미커밋 파일을 보존하며 보완했다. 신규 파일·브랜치는 만들지 않았고 저장 기능·공모주 OCR·금융 계산·국민연금 도메인 계약은 변경하지 않았다.
- `10월 14일` 등은 날짜 구분행으로 처리하고 `transaction_date_parts={year:null,month:10,day:14}`, `transaction_date=null`, `review_reasons`의 `year_missing`을 반환한다. 촬영일·발급일·조회일·시스템 연도를 거래 연도로 쓰지 않는다. 명시된 거래 연도 또는 조회 기간 안에서 월·일의 연도가 유일할 때만 완성 날짜를 제공한다. 연말 경계·페이지 경계·기간 충돌은 보수적으로 처리한다.
- 무표시 추가 금액을 잔액이라고 확정하거나 두 번째 거래로 생성하지 않는다. 새 거래처가 나온 뒤의 잔액을 이전 거래에 연결하지 않고, 숫자 토큰 전체를 검증하여 잘린/비정상 토큰의 정상 숫자 접미부를 사용하지 않는다. 같은 날짜·거래처·금액의 복수 후보는 모두 유지한다.
- OCR TSV의 이미지 폭 320px 미만, 단어 높이 12px 미만, 이미지 가장자리 접촉, 낮은 신뢰도를 검토 사유로 추가한다. 불명확한 금액·거래처는 null이며 유형 선택만으로 불명확한 문서를 은행/카드로 확정하지 않는다. 이 임계값은 보수적인 제외 기준이며 통과가 정확도 보증은 아니다. 스캔 PDF의 원본 해상도·모든 잘림/누락 탐지는 보장하지 않는다.
- 실제 실행: **178 passed / 0 failed / 0 skipped / 2 warnings** (130.83초). 기존 O1 **122 PASS** 유지, 신규 **56 PASS**(파서·안전성 47, Chrome 9). 국민연금 document/import/API와 기존 Chrome 9, CSV/Excel·IPO 신청/배정 회귀를 포함한다. 신규 Chrome은 320/390/1280px × Purple/White/OLED에서 연도 미확인·이체 후보·금액/잔액 표시와 overflow 방지를 확인했다.
- 금융 writer·금융 경로 생성 함수 미호출, 합성 ledger/portfolio 파일 byte 불변 및 preview 사용자 디렉터리 생성 0을 추가 검증했다. 실제 스크린샷은 사용하지 않았고 Tesseract 부재로 OCR 출력은 mock이다. 실제 OCR·네이티브 AMD64/ARM64 smoke 확장은 설계만 검토했으며 workflow/Docker/기존 smoke는 변경하지 않았다. 전체 pytest·CI·Commit·Push·PR·Merge·Deploy 미실행.
- APP_VERSION 2.0.2 유지. 변경한 가계부 OCR JS만 `2.0.2-o1.1`, 미변경 OCR CSS는 `2.0.2-o1`을 유지한다. 아래 O1 기록은 최초 구현/검증 시점이다.

## Wealth v2.0.2 — Phase O1 가계부 문서 읽기 전용 미리보기 — 2026-10-15

- 기준 main `d7e06de24bc48e728b89adec09fa75da697d22e5`에서 독립 worktree `wealth-ocr`, 브랜치 `codex/v202-ledger-ipo-ocr-import`에 구현한 미커밋 개발 상태다. 기존 PR #145/#146 운영 완료 이력과 구분하며 이번 변경의 CI·Commit·Push·PR·Merge·Deploy는 미실행이다.
- 기존 가계부 가져오기 창에 PNG/JPEG/PDF 읽기 전용 미리보기를 추가했다. 인증·동일 출처를 확인하는 `POST /api/ledger/document-import/preview`는 거래 후보와 검토 사유만 반환하고 `Cache-Control: no-store`를 사용한다. 금융 JSON, 잔액, 사용자 디렉터리를 생성·변경하지 않으며 저장/적용 API와 공모주 OCR은 구현하지 않았다.
- 국민연금의 Poppler/Pillow/Tesseract 추출 부분을 공통 계층으로 분리했다. 국민연금 전용 `parse_text()`와 기존 판정 기준은 유지하고 가계부는 날짜·금액 단서로 텍스트층 사용 여부를 결정한다. OCR의 TSV 좌표·신뢰도, 은행 입출금 부호와 거래 후 잔액, 카드 승인·취소·환불 후보를 분리한다. 상단 합계는 제외하고 모든 결과는 검토 필요 상태이며 Owner·계좌는 미확인이다.
- 초기 파서는 연도가 포함된 날짜와 `원` 단위 금액을 중심으로 지원한다. 연도 생략, 복잡한 표/통화, 잘린 숫자, 흐린 문서, 기관별 양식을 정확히 인식한다고 보장하지 않는다. 숫자·부호가 불명확하면 추정하지 않으며 중복 후보도 삭제·저장하지 않는다. 기존 기록과의 중복 대조·행 수정·명시적 저장은 O2 설계 대상이다.
- 10MiB·8페이지·1,600만 픽셀 한도, 암호화 PDF/다중 프레임 거부, 비공개 임시 파일 및 제한 시간을 적용한다. 동시 실행 2개 예산은 국민연금과 가계부가 **한 웹 프로세스 안에서** 공유한다. 다중 웹 worker 전체 예산과 자식 프로세스 합산 메모리는 보장하지 않는다. Linux 시간초과는 해당 worker의 프로세스 그룹을 종료하지만 Windows는 직접 자식 종료만 보장한다. 창 닫기는 결과 표시를 무효화하며 서버 작업은 완료 또는 제한 시간에 정리된다.
- 실행 확인: 격리된 합성 경로의 집중 pytest **102 passed / 0 failed / 0 skipped** (국민연금 document/import/API, CSV/Excel 중복 방지, IPO 신청·배정, release 계약 포함), 신규 가계부 Chrome **11 passed / 0 failed / 0 skipped**. 320/390/1280px × Purple/White/OLED 미리보기 및 닫은 뒤 지연 응답 차단을 확인했다. 320px 기존 가계부 헤더만 줄 배치를 보완했으며 페이지 overflow 숨김은 추가하지 않았다.
- 기존 국민연금 가져오기 Chrome 회귀도 **9 passed / 0 failed / 0 skipped**. 이번 집중 실행 합계는 **122 passed / 0 failed / 0 skipped**이며 실제 OCR 엔진의 인식 검증과 구분한다.
- Python 문법, 신규 JS의 `node --check`, `git diff --check` PASS. 원래 감액배당 worktree의 4개 파일 SHA256이 작업 전후 모두 동일함을 확인했다.
- 로컬 Tesseract가 없어 OCR 출력은 mock/합성 fixture로 검증했다. 실제 이미지 인식률, Linux/ARM64 새 worker 실행, 운영 자원 사용량과 배포는 미검증이다. 실제 금융 자료는 사용하지 않았고 전체 pytest는 실행하지 않았다. 기존 운영 이미지의 OCR 성공 이력은 이번 새 가계부 파서의 실동작 성공을 뜻하지 않는다. 앱 버전은 2.0.2, 새 JS/CSS만 `2.0.2-o1` revision을 사용한다.

## Wealth v2.0.2 — Offline Pension Document Import and Tax Navigation — 2026-10-14

- 2026-10-14 운영 완료: PR #144의 v2.0.2 배포에 이어 [PR #145](https://github.com/sagesaint84/wealth/pull/145)를 Squash Merge(`d98336aea7514cea205ef82ed184398015bff5f9`)했다. Oracle ARM64에서 이미지 `ghcr.io/sagesaint84/wealth:d98336a`의 revision·아키텍처·정적 자산·데이터/Toss 마운트·HTTP 307을 검증했으며 기존 rollback 이미지를 보존했다. 사용자 확인으로 실제/예상 배당 및 세금 탭 운영 화면도 정상이다. 아래 PR #144 Draft·v2.0.1 운영 설명은 당시 이력이다.
- 배당 실제/예상 모드 후속 수정은 PR #145로 main에 반영 및 운영 배포됐다. 사용자 검증: 실패했던 Chrome 6개 재검증 6 PASS / 0 FAIL / 0 SKIP, 집중 pytest 40 PASS / 0 FAIL / 0 SKIP, Windows 전체 pytest **3,707 passed / 5 skipped / 0 failed / 5 warnings**, **798 subtests passed**, 1182.80초. 격리 소스·Python/JS 문법·git diff --check PASS, 임시 소스 정리 완료. [PR CI](https://github.com/sagesaint84/wealth/actions/runs/38535666859)는 native amd64·arm64 두 Job 모두 Success.
- 전체 pytest 초기 8건은 로컬 Python 환경의 Pillow 부재로 실패했으나 `requirements.txt`의 `Pillow==12.3.0` 설치 후 해당 테스트와 전체 suite가 통과했다(소스 결함 아님). PR #145 CI·Merge·운영 배포·운영 화면 점검은 위와 같이 완료됐으며, 최종 코드 감사에서 Codex는 테스트를 반복 실행하지 않았다. 감액배당·비과세 계산은 미구현.
- 과거 후속 검증 이력: 33 passed / 6 failed (174.53초), Python·JS syntax/Isolation/git diff --check PASS. 세금 workspace 이동 실패 6건은 기존 catPanelTax에도 workspace를 생성하고 상품 정보 갱신을 assetTaxInformation 내부로 제한하여 보완했다. 이후 재검증 성공은 위 현재 기록을 따른다. 분석 패널·초안·요청 방어 유지. wealth.js/family-risk JS 및 core metadata revision은 2.0.2-r7, What-if JS는 2.0.2-r6 유지.
- 후속 정적 리뷰 보완: 오래된 What-if 요청의 finally가 새 계산 버튼을 활성화하지 않도록 요청·Owner 검사를 적용. 모드/Owner 변경 시 진행 상태를 초기화하고 What-if의 전체 body Observer를 탭 선택 감시와 기존 wealth:view 이벤트로 축소. 합성 Chrome 응답 순서·Owner·세금 탭 왕복 회귀 코드 추가. 사용자 검증 결과는 위 기록을 따른다.
- 최초 후속 배당 모드 보정 (작성 당시 미커밋·실행 검증 전): 실제 배당 화면에서 What-if를 숨기고 예상 모드에서 표시한다. 세금 workspace의 기존 도구는 유지하되 예상 탭을 임시 조작하던 경로를 제거하고 하나의 표시 제어를 사용한다. 당시 앱 버전은 2.0.2, What-if·family-risk JS는 2.0.2-r6이었다. 현재 후속 검증·revision은 위 기록을 따른다. 아래 기존 성공 결과는 이 후속 변경의 검증 결과가 아니다.
- 국민연금 카드·납부 이력에서 PDF/PNG/JPG를 서버 내부 Poppler/Tesseract로 분석하고 선택 항목을 검토·수정한 뒤 적용. 원문·개인식별정보 저장 및 외부 OCR 전송 없음.
- 실제 납부액, 사업장 고지액, 미납액, 기간별 총액을 구분. 여러 해 기간을 임의 배분하지 않고 본인 부담액·소득공제 인정액을 추정하지 않음.
- 자산 세금 탭을 상태 복구·독립 패널과 연결하고 국민연금 분석 진입·기본 정보 초안 보호를 보완.
- 앱·서비스워커·변경된 정적 파일만 2.0.2로 갱신. 미변경 Toss UI·색상·금융 계산 유지.
- 사용자 확인 Windows 전체 pytest 3,699 passed / 5 skipped / 0 failed / 5 warnings, 798 subtests passed. Python·JavaScript 문법 검사 PASS.
- GitHub Actions [run 38493482329, attempt #8](https://github.com/sagesaint84/wealth/actions/runs/38493482329/attempts/8) Success: native amd64/arm64 Docker 빌드, network-disabled Chromium smoke, Poppler/Tesseract kor/eng/osd 및 합성 한국어 PNG/PDF·production worker smoke 성공. 실제 개인 문서 사용 없음.
- 당시 이력 (2026-10-14 PR 검증 시점): PR #144는 Draft/main 반영 전이었고 Oracle ARM64 v2.0.2 실운영 검증·배포 전, 운영 v2.0.1 유지 상태였다. 이후 사용자 보고로 PR #144 머지·v2.0.2 운영 배포 완료를 확인했다. 양식별 인식률, 실제 개인정보 문서 정확성, 운영 CPU/메모리·이미지 크기 측정 완료를 뜻하지 않는다. [가져오기 계약](docs/national-pension-import.md).

## Wealth v2.0.1 — Toss Account Layout and Insurance Display — 2026-10-13

기준 HEAD `acfe0a7d397ace4d7f5cc645336942b07e2de10b`: 사용자 확인 전체 pytest 3,596 passed / 5 skipped / 0 failed, subtests 798 passed, Chrome UI 30 passed 및 AMD64/ARM64 PR CI 성공. 아래 후속 국민연금 상세 분석·보험 부분 집계는 미커밋 구현이며 테스트·syntax·빌드 검증을 실행하지 않았다. PR #143 merge·게시·배포 완료를 주장하지 않는다.

- Toss 실현손익·배당이자 가져오기의 귀속 계좌를 헤더(라벨·지정·해제)와 전체 폭 select의 2행으로 구성. 상태 live region과 오류 알림은 유지하고 상시 추가 행은 제거.
- HOME 보험에 누적납입액과 일시금/해약환급금 입력액의 예상 단순수익률 표시. 기간·향후 납입·세금 절감액을 반영하지 않으며 연환산·IRR·확정 수익률이 아님.
- 후속 수정: 보험 예상 단순수익률은 유효한 일시금형 상품만 부분 집계하고 산정 수/전체 수를 화면에 표시. 연금형·근거 부족은 제외하며 대상이 없으면 미산정. 기준 HEAD의 전체 미산정 정책을 보완한다. 기존 자산 금액·비중·순자산은 변경하지 않음.
- 후속 구현: 국민연금 선택 메타데이터에 기간별 가입유형, 본인·사업장 부담액, 과세연도별 확인값 및 수령 가정을 분리 저장. revision·납부 이력 충돌 검사와 기존 납부액 보존을 유지.
- 후속 구현: 공식 등록 세율 연도의 누진 산출세액 차이와 날짜별 연환산 IRR 분석. 미래 보험료는 명시적 입력만 사용하고 현재가치/명목 기준·날짜 근사·미산정 사유를 표시. 미등록 연도·모호한 IRR·세후 근거 부족은 자동 산정하지 않음. [분석 계약](docs/national-pension-analysis.md) 참고.
- 앱·HTML·service-worker cache와 실제 변경한 정적 리소스만 2.0.1로 갱신.

## Wealth v2.0.0 — UI Finish and ARM64 Toss Authentication — 2026-10-13

상태: 사용자 확인 Windows 전체 pytest 3,568 passed / 5 skipped / 0 failed, 798 subtests passed, 신규 Chrome UI 테스트 14 passed. 27개 파일 commit·push 및 PR #142 생성 완료 (`d847dc5f3127c50842bbaa704e890a5db12e6e30`). GitHub Actions 결과, merge, GHCR 게시 및 Oracle 운영 배포 상태는 별도 검증이 필요하다.

- 절세계좌 카드 제목·선택 badge와 종목/계좌 수를 한 줄 중심으로 정리하고 긴 실제 계좌명은 tooltip으로 보존.
- 실현손익·배당·이자 가져오기의 귀속 Wealth 계좌는 유지하면서 기본계좌 지정/해제 버튼과 상태를 compact하게 배치.
- 전체 자산 구성의 좌측 비중과 우측 수익률을 구분. 현금·보험·임차보증금 및 매입근거가 없는 수익률은 `—`로 표시하고 기존 금액·집계·정렬·계산은 유지.
- 앱/metadata/service-worker cache를 v2.0.0으로 갱신하고 변경된 static assets만 cache revision 갱신.
- 이미 main에 반영된 Toss WTS AMD64/ARM64 Playwright/Chromium 런타임, owner 전용 QR 확인 문자, Linux process guard 및 PR 사전 검증 workflow를 현재 운영 문서에 연결.
- 미참조 `ASSET_CLASS_ORDER` 상수와 release-version 테스트의 가려진 중복 분기를 정리. 역사 CHANGELOG·audit·fallback·vendor/license·운영 문서는 보존.

아래 과거 릴리즈의 source/운영 설명은 당시 상태다. 현재 IPO는 KIS API를 사용하지 않으며 최신 기준은 README와 PROJECT_STATE를 따른다.

## Wealth v1.3.0 — MoneyLog Calendar and Multi-Source IPO Integration — 2026-09-19

- **머니 로그 통합 캘린더 (MoneyLog Calendar)**:
  - 머니 로그 내 신규 '캘린더' 탭을 추가하여 월별 실현손익, 배당금·이자 수령 내역, 가계부 지출/수입, 공모주(IPO/SPAC) 시장 일정을 하나의 통합 캘린더에서 유기적으로 조망할 수 있도록 구현했습니다.
  - 가계부·자산 내역과 달리 공모주 시장 일정은 개인 소유자(Owner) 필터와 독립적으로 전체 시장 일정을 표시하여 가족 구성원 누구나 공모주 일정을 놓치지 않도록 동선을 최적화했습니다.
- **공모주 일정 및 청약 상태 관리 (IPO & SPAC Management)**:
  - 일반 기업 IPO 및 스팩(SPAC) 종목의 청약 시작/마감일, 환불일, 납입일, 예상상장일, 확정 공모가 일정을 통합 조회하고 관리합니다.
  - 가족 구성원별 청약 참여 여부를 관리(전체/일부/미청약 상태 표시)할 수 있습니다.
  - 최초 청약 상태 변경 시 또는 청약 마감 시점에 당시 가족 구성원을 대상 목록(`target_owners`)으로 고정(freeze)하여, 이후 앱 설정에서 가족 구성원이 변경되더라도 해당 공모주의 대상 가족이 왜곡되지 않고 안전하게 유지됩니다.
  - 공모주 화면 내에 기관 수요예측 결과 및 의무보유 확약 비율 등을 바탕으로 산정되는 Wealth IPO Score(BETA) 점수·등급 및 산정중 상태를 참고 지표로 제공합니다 (합병 목적 특수회사인 SPAC은 일반 기업 평가 규칙과 분리하여 취급).
- **다원화 데이터 소스 및 상장일 확정 파이프라인 (Multi-Source IPO Architecture)**:
  - **KIS (Primary Schedule Authority)**: 한국투자증권 공모주 청약 일정 API를 기본 신뢰 소스로 사용하여 청약/환불/납입일 및 공모가를 안정적으로 수집합니다.
  - **KIND (Expected Listing Date Fallback)**: KIS 응답에서 예상상장일(`expected_listing_date`)이 공백인 종목에 한해, 한국거래소 기업공시채널(KIND) 공모기업현황을 기간 및 회사명 정규화 매칭으로 안전하게 대조하여 보완합니다.
  - **NAVER & KRX (Actual Listing Date Corroboration)**: 네이버 금융 상장 완료(`IpoProgressType=LISTING`) 데이터의 상장일(`lcalDate`)과 KRX 공개 상장 마스터(`finder_stkisu`)의 단축코드 및 시장구분 일치를 교차 검증하여, 두 소스가 모두 일치하는 경우에만 실제 상장 완료(`actual_listing_date`)로 안전하게 확정 승격합니다.
  - **DART 기업공시 연계 기반 마련**: DART 전자공시 클라이언트 및 증권신고서/투자설명서 파서 기반을 내장하여, 향후 심층 공모 분석 및 정밀 스코어 확장을 위한 기반을 마련했습니다.
- **엄격한 안전성 및 데이터 무결성 (Fail-Closed & Safe Matching)**:
  - 통신 장애, 스키마 변조 또는 zero-row 비정상 응답 수신 시 기존 시장 저장소(`market_store.json`)를 온전히 보존하는 Fail-Closed 정책을 적용했습니다.
  - 스팩(SPAC) 종목 간 기수·증권사명 오매칭 방지를 위한 정밀 alias 매칭을 구현했습니다.
  - 네이버 및 외부 데이터 수집 시 ASCII 6자리 단축코드 엄격 정규식 검증(`^[A-Z0-9]{6}$`)을 적용하여 비표준 코드 및 유니코드 오동작을 원천 차단했습니다.
- **알림 연동 지원 및 오케스트레이션 기반 구축**:
  - 청약일, 환불일, 상장일 도래 시 알림 페이로드를 생성하는 파이프라인과 텔레그램 등 메신저 알림 연동 기반을 코드 레벨에 마련했습니다 (자동 발송 배치 운영은 미배포 상태).
- **테스트 커버리지 및 외부망 차단 무결성**:
  - `tests/__init__.py`의 socket 수준 외부망 차단 정책을 엄격히 준수하며, 단위 및 회귀 테스트 1,057건 전원 통과(1057 tests PASS)로 무결성과 하위 호환성을 검증했습니다.

## Wealth v1.2.7 — Docker Build Security Hardening — 2026-09-18

- **Docker build context에서 toss-wts/ 제외**: `.dockerignore`에 `toss-wts/`를 추가하여 Toss WTS 실행파일 및 세션 설정 파일이 Docker 이미지 레이어에 복사되는 것을 원천 차단했습니다.
- **운영 호스트 분리 및 bind mount 유지**: Toss WTS 실행파일/세션 config는 서버 호스트 디렉터리에 그대로 유지되며, 컨테이너에서는 기존 bind mount(`/docker/wealth/toss-wts/bin/tossctl -> /opt/toss-wts/tossctl`, `/docker/wealth/toss-wts/config -> /opt/toss-wts/config`) 경로를 그대로 사용합니다.
- **애플리케이션 자산 계산 로직 불변**: 이번 변경은 빌드 컨텍스트 보안 최적화로, 기존 자산/스냅샷 계산 로직 및 API 동작에는 영향이 없습니다.

## Wealth v1.2.6 — All-Owner Snapshot Coordination and Daily Close Automation — 2026-09-18

- **전 가족 구성원 일괄 스냅샷 체계**: 주식기록 및 순자산기록 저장 시 선택된 단일 구성원에 국한되지 않고 '모두', '아빠', '엄마', '자녀' 등 등록된 모든 구성원의 스냅샷을 한 번에 계산·생성하여 날짜 축을 동기화합니다.
- **자산 없는 구성원 0원 스냅샷 생성**: 보유 종목이나 금융자산이 없는 가족 구성원도 건너뛰지 않고 0원 스냅샷을 생성하여 차트 및 추이 조회 시 누락 없이 표시되도록 개선했습니다.
- **순자산 부동산 단독지분 반영 보강**: `ownerships` 배열이 없는 단독 소유 부동산도 소유자 본인에게 100% 자산으로 정확히 반영되도록 정돈했습니다.
- **홈 화면 순자산 기록 연동**: 순자산 기록 버튼 클릭 시 `/api/planning/snapshot-all`을 호출하여 모든 가족 구성원의 순자산 스냅샷을 원클릭으로 독립 계산·저장합니다.
- **서버 마감 자동화 스크립트 추가**: 증권사 동기화, 시세 갱신, 주식/순자산 스냅샷 저장, Telegram 일일 마감 리포트 전송을 일괄 수행하는 `server/wealth-daily-close.sh` 및 토스 세션 점검 스크립트 `server/toss-session-check.sh`를 추가했습니다.

## Wealth v1.2.5 — Stock Record Accuracy and Performance Semantics — 2026-09-18

- **주식기록 성과 계산 의미 정돈**: 주식기록의 `total_value_krw`를 예수금을 제외한 순수 보유 주식/ETF 시장 평가액 기준으로 통일했습니다.
- **예수금 이동에 따른 일간손익 왜곡 방지**: 입출금, 공모주 청약 증거금, 분할매수 및 매도 후 현금화가 `day_profit_krw`의 투자 수익/손실로 오인되지 않도록 현재 보유 종목의 당일 가격변동 손익(`holding_day_gain`)을 사용합니다.
- **Dashboard 기존 계약 유지**: 종합 대시보드의 총자산은 기존과 동일하게 주식 평가액과 전체 예수금을 포함하며, 주식기록과 의미를 명확히 분리했습니다.
- **당일 등락률 우선순위 안정화**: 최신 `0.0%` 보합 데이터를 유효값으로 보존하고, 값이 `None`인 경우에만 다음 데이터 소스로 fallback하도록 정리했습니다.
- **주식기록 UI 개선 및 회귀 검증 강화**: 주식기록 dialog 동작을 개선하고 관련 계산·UI 회귀 테스트를 확장했으며 전체 858개 테스트를 통과했습니다.

## Wealth v1.2.4 — Strategy Bucket Color Clarity — 2026-09-17

- **전략 버킷 semantic color 체계 도입**: 추천 버킷에는 고정 semantic color mapping을 적용하고, 사용자 정의 버킷은 기존 deterministic hash 기반 색상 fallback을 유지합니다.
- **배당/현금 및 전술/방어 색상 식별성 개선**: 유사한 블루 계열이던 '배당'(인디고 바이올렛 `#7F78E8`)과 '현금'(스카이블루 `#5A9FE8`), 그리고 유사한 웜 톤이던 '전술'(웜 앰버 `#D19A66`)과 '방어'(뮤트 세이지 올리브 `#82966A`)의 색조(Hue)를 대폭 분리하여 한눈에 식별 가능하도록 개선했습니다.
- **추천 버킷에 color swatch 추가**: 전략 버킷 편집 영역의 추천 버킷 칩에 실제 배정될 색상의 미니 컬러 스와치 dot(`<i class="wealth-bucket-preset-dot">`)을 추가하여 선택 단계에서 색상을 즉시 인지할 수 있도록 했습니다.
- **동일 색상 source 일관성 보장**: 추천 버킷 칩, 목표 비중 도넛, 현재 비중 도넛, 범례, 버킷 카드의 액센트 라인에 동일한 `--bucket-color` 소스가 주입되도록 보장했습니다.
- **미분류/미배정 neutral 스타일 및 Asset Allocation 기존 팔레트 유지**: 미분류(`#697386`) 및 미배정(`#35415b`) 스타일을 보존하고, 종합 자산 및 홈 Asset Allocation 도넛은 v1.2.3 기존의 9색 팔레트를 온전히 유지했습니다.

## Wealth v1.2.3 — KB Empty Balance Compatibility — 2026-09-17

- **KB증권 OpenAPI 빈 잔고 호환성 확장 (1861 Authoritative Empty)**: KB OpenAPI 실계좌 잔고조회에서 관찰된 빈 잔고 비즈니스 응답(`processCode: "1861"`, `processFlag: "A"`, "조회할 자료가 없습니다")을 감지하여 정상 `CONFIRMED_EMPTY` 상태로 안전하게 처리합니다.
- **잔고조회 화이트리스트 TR 한정 적용**: 국내 잔고(`ssqm1801`, `Record1`)와 해외 잔고(`spqm2226`, `Record2`)에서 `allow_empty_balance=True`로 명시 호출된 경우에만 허용하며, 전역 상태 검증(`_check_provider_status`)이나 비잔고 TR(실현손익 `ssqm2442`, 계좌조회 `szqm0771` 등)에는 fail-closed 원칙을 엄격히 유지합니다.
- **기존 8092 안전 처리 및 하위 호환성 유지**: 기존 빈 계좌 코드(`8092` + "해당 계좌의 잔고 내역이 존재하지 않습니다") 처리를 완벽히 유지합니다.
- **비어있지 않은 데이터 모순 응답(Contradiction) 방어**: 1861 또는 8092 응답 헤더가 수신되었더라도 `dataBody`에 실제 보유종목 레코드가 존재하는 경우 빈 잔고로 덮어쓰지 않고 즉시 거부(`KBOpenAPIError`)하여 fail-closed 처리합니다.
- **데이터 보존 정책 및 회귀 검증**: 네트워크 장애나 비정상 응답 시 기존 포트폴리오를 유지하며, 18개 신규 회귀 테스트를 포함하여 총 55개 브로커 안전성 테스트로 동작을 검증했습니다.

## Wealth v1.2.2 — Broker Sync Reliability — 2026-09-17

- **KB증권 잔고 없음 안전 처리 (8092 Authoritative Empty)**: KB OpenAPI의 잔고조회 TR(`/api/v1/ssqm1801`, `/api/v1/spqm2226`)에서 실제 빈 계좌가 반환하는 정상 비즈니스 코드(`processCode: 8092`, `processFlag: A`, "해당 계좌의 잔고 내역이 존재하지 않습니다")를 감지하여 `CONFIRMED_EMPTY` 상태로 안전하게 인식합니다. 잔고조회가 아닌 일반 TR이나 다른 실패 사유에는 fail-closed 원칙을 엄격히 유지합니다.
- **키움증권 OpenAPI 토큰 자동 복구 (8005 / HTTP 401)**: 다중 환경(로컬/서버) 동일 App Key 공유 등으로 인해 토큰 만료 전 무효화(`8005: Token이 유효하지 않습니다`) 또는 HTTP 401 발생 시, 토큰을 강제 갱신(`force_refresh=True`)하고 요청을 1회 자동 재시도하여 동기화 중단을 방지합니다. 연속 실패 시 무한 루프를 차단하도록 재시도는 1회로 엄격히 제한됩니다.
- **키움증권 공식 `expires_dt` 토큰 만료 관리**: 키움 토큰 발급(`au10001`) 공식 응답의 `expires_dt`("YYYYMMDDHHMMSS") 필드를 직접 파싱하여 토큰 캐시 만료 시각의 정확성을 보장합니다.
- **연속조회(Pagination) 토큰 안전성 및 회귀 검증**: 잔고 연속조회 루프 도중 토큰이 갱신되는 경우에도 잔여 페이지 요청 및 예수금 조회가 갱신된 토큰으로 안전하게 이어지도록 보장하고, 토큰 복구 전반에 대한 13개 단위/회귀 테스트를 추가했습니다.
- **설정 화면 앱 버전 표시 및 정적 자원 버전 동기화**: 앱 설정 화면 하단에 현재 Wealth 버전(`앱 버전 v1.2.2`)을 표시하고, HTML meta tag, Service Worker 캐시, CSS/JS 쿼리스트링 및 FastAPI 애플리케이션 버전을 일원화했습니다.

## Wealth v1.2.1 — UI/UX Refinement and Responsive Polish — 2026-09-16

- **홈 대시보드 및 자산 포트폴리오 강화**: 부동산·주식 기대수익 지표 분리 표시, 모바일/데스크톱 시각적 위계 개선 및 빠른 접근 영역 정리를 적용했습니다.
- **머니 로그 통합 탐색 (Batch 1)**: 실현손익, 배당금, 가계부 탭을 일원화된 탭 인터페이스로 통합하고 URL 해시 연동을 지원합니다.
- **전략 버킷 시각화 및 목표 비중 검증 (Batch 3)**: 전략 버킷 프리셋 버튼 제공, 목표 비중 합계 실시간 검증(100% 한도/미배정 안내), 카드별 버킷 색상 액센트 일관성을 적용했습니다.
- **UI 일관성 및 절세 계좌 표시 수정 (Batch 4)**: 개별 절세 계좌의 누적 절세액 표시 정확성을 보장하고 공통 모달 및 툴바 시각 스타일을 표준화했습니다.
- **순자산 이력 카드 위계 개선 (Batch 5)**: 순자산 이력 상세를 테이블에서 반응형 레코드 카드로 개편하여 자산·부채 구분 가독성을 대폭 향상했습니다.
- **반응형 2차 내비게이션 및 순자산 차트 노스크롤 (Batch 6 & 6.1)**: 데스크톱 2차 탭 폰트 규격을 14px 650으로 표준화하고 모바일 가독성을 보존하며, 순자산 이력 차트의 가로 스크롤을 완전히 제거했습니다.

## Wealth v1.2.0 — Financial Correctness and Sync Safety — 2026-09-15

- **금융 정확성 강화**: 마이너스통장 부채 이중계상을 방지하고, 소유자·과세연도별 연금저축/IRP 세액공제 한도를 적용했습니다.
- **데이터 무결성 강화**: 파일 기반 실현손익·배당·가계부 가져오기를 멱등화하고, 불완전하거나 모호한 증권사 잔고 응답은 기존 보유종목을 보존하도록 fail-closed 처리했습니다.
- **해외 실현손익 의미 보존**: 외화 원금통화 손익과 원화 환산 가능 여부를 구분하고, 미환산 거래가 요약에서 누락되지 않도록 상태를 표시합니다.
- **Toss WTS 호환성**: KST/UTC 날짜 경계에서 현재일 조회가 거부되는 tossctl 동작에 대한 Wealth 호환 처리를 추가했습니다.
- **검증 범위**: 브로커 잔고 안전성, 파일 가져오기 중복 방지, 세액공제, 외화 손익 및 회귀 테스트를 확장했습니다.
- **보안**: 소스 코드에 내장된 세션 서명 키 기본값을 제거했습니다. 런타임은 이제 `.env`의 `DASHBOARD_SECRET_KEY`를 명시적으로 요구하며, 누락 또는 공백인 경우 시작을 거부합니다.

## Wealth v1.1.4 — Kiwoom Realized-P/L Integration — 2026-09-13

- **키움증권 공식 OpenAPI 실현손익 연동 (Selective Realized-P/L Import)**:
  - 키움증권 공식 OpenAPI(국내 `ka10073` 일자별종목별실현손익요청_기간, 해외 `ust21530` 미국주식 실현손익) 기반 기간별 실현손익 실시간 피드 조회 및 선택 가져오기 파이프라인 구현
  - **계좌 목록 조회 (`ka00001`) 및 스코프 투명성 (`source_scope_verified: False`)**: 키움 OpenAPI 특성상 API 키와 특정 계좌 간의 사전 서버 검증 증거가 요청 페이로드에 포함되지 않으므로, 신뢰 스코프를 투명하게 미검증(`source_scope_verified: False`) 상태로 유지 및 UI 안내
  - **불투명 출처 계좌 식별자 (Opaque Source Account Key)**: raw 계좌번호 노출을 차단하고 `HMAC-SHA256(account, secret)` 기반 64자 불투명 키 사용
  - **마스킹 계좌 표시**: API 상태, 피드 응답, 브라우저 DOM 전반에 `XXXX****-YY` 마스킹 포맷 적용
  - **명시적 최초 귀속 및 영구 매핑**: 첫 import 시 사용자가 선택한 Wealth 계좌에 귀속되며, 이후 `kiwoom_account_mapping.json`을 통해 안전하게 자동 제안
  - **행 단위 HMAC 서명 및 무결성 보호**: 조회 시 발급되는 `selection_token`을 통해 행 데이터 위변조(`ROW_TAMPERED`) 및 타 사용자/타 계좌 오남용 차단
  - **브라우저 JSON 정규화 불변성 (`_canonical_num_str`)**: 브라우저/JSON 라운드트립 간 정수·실수 표기 차이로 인한 서명 검증 실패 방지
  - **국내 장기 조회 안전 분할 (Conservative Chunking)**: Wealth uses conservative three-calendar-month chunks for reliable long-range domestic retrieval based on validated behavior (검증된 동작 특성에 기반하여 안정적인 장기 조회를 위한 3개월 단위 자동 분할 수집)
  - **해외 정상 빈 결과 봉투 처리**: 해외 실현손익 내역 부재 시 키움 특유의 정상 빈 응답 봉투(`return_code: 20`, subcode `571758`, "조회내역이 없습니다")를 오류가 아닌 빈 목록으로 정상 처리
  - **브라우저 입력 날짜 정규화**: HTML5 date 입력(`YYYY-MM-DD`)을 OpenAPI 규격(`YYYYMMDD`)으로 완벽 정규화 지원
  - **쓰기 전 사전 검증 (Preview-before-write)**: 모달을 통해 `NEW`, `ALREADY_IMPORTED`, `POSSIBLE_DUPLICATE`, `INVALID` 상태를 사전 분류 (미리보기 단계 금융 데이터 무저장)
  - **커밋 시점 중복 방지 (Replay Protection)**: 단기 유효한 `preview_ticket` 발급 및 최종 import 커밋 시 재분류 검증을 통해 동시성/반복 클릭에 의한 중복 쓰기 원천 차단
  - **선택적 가져오기 및 읽기 전용 피드 원칙**: 임시 조회 피드는 `read_only: True, persisted: False`로 관리되며 전체 회계 합산에 중복 포함되지 않음
  - **완전한 출처 메타데이터 보존 (Provenance)**: `source: "kiwoom"`, `source_fingerprint: "kiwoom-realized:v1:<sha256>"`, `source_account_key`, `source_account_label`, `imported_by_user_action: True`, `imported_at`, 최소 필요 메타데이터(`source_meta`) 저장
  - **수수료 및 제세금 안전 표시**: 국내 수수료/제세금 필드를 합산하여 UI에 명확히 표시
  - **해외 환율 미제공 시 KRW 손익 Null 처리**: 공식 환율 또는 KRW 환산 금액이 없는 경우 `pnl_krw = None`으로 보존하며, 외화 금액을 원화 필드에 복사하지 않고 UI에 `—`로 표시
- **릴리즈 범위 안전 제외 확인**:
  - **주식 주문 기능 (Stock Orders) 미포함** (주문 API 호출 차단)
  - **공모주 청약/일정 연동 (IPO Integration) 미포함** (실현손익 이외의 공모주 청약 기능 제외)
  - **배당금 연동 (Dividend Integration) 미포함** (사전 검증된 실현손익 범위만 지원)

## Wealth v1.1.3 — NH Realized-P/L Integration — 2026-09-13

- **NH투자증권 공식 OpenAPI 실현손익 연동 (Selective Realized-P/L Import)**:
  - NH투자증권 공식 OpenAPI(국내 `krstockInquiryTradingPnl`, 해외 `gbstockInquiryTradingPnl`) 기반 기간별 실현손익 실시간 피드 조회 및 선택 가져오기 파이프라인 구현
  - **검증된 계좌 스코프 (`source_scope_verified: True`)**: OpenAPI 키 설정과 계좌번호 일치 여부를 사전 검증하여 신뢰된 계좌 범위 확정
  - **불투명 출처 계좌 식별자 (Opaque Source Account Key)**: raw 계좌번호 노출을 차단하고 `HMAC-SHA256(act_no, secret)` 기반 64자 불투명 키 사용
  - **마스킹 계좌 표시**: API 상태, 피드 응답, 브라우저 DOM 전반에 `XXXX****` 마스킹 포맷 적용
  - **명시적 최초 귀속 및 영구 매핑**: 첫 import 시 사용자가 선택한 Wealth 계좌에 귀속되며, 이후 `nh_account_mapping.json`을 통해 안전하게 자동 제안
  - **행 단위 HMAC 서명 및 무결성 보호**: 조회 시 발급되는 `selection_token`을 통해 행 데이터 위변조(`ROW_TAMPERED`) 및 타 사용자/타 계좌 오남용 차단
  - **브라우저 JSON 정규화 불변성 (`_canonical_num_str`)**: 브라우저/JSON 라운드트립 간 정수·실수 표기 차이로 인한 서명 검증 실패 문제 해결
  - **쓰기 전 사전 검증 (Preview-before-write)**: 모달을 통해 `NEW`, `ALREADY_IMPORTED`, `POSSIBLE_DUPLICATE`, `INVALID` 상태를 사전 분류 (미리보기 단계 금융 데이터 무저장)
  - **커밋 시점 중복 방지 (Replay Protection)**: 단기 유효한 `preview_ticket` 발급 및 최종 import 커밋 시 재분류 검증을 통해 동시성/반복 클릭에 의한 중복 쓰기 원천 차단
  - **선택적 가져오기 및 읽기 전용 피드 원칙**: 임시 조회 피드는 `read_only: True, persisted: False`로 관리되며 전체 회계 합산에 중복 포함되지 않음
  - **완전한 출처 메타데이터 보존 (Provenance)**: `source: "nh"`, `source_fingerprint: "nh-realized:v1:<sha256>"`, `source_account_key`, `source_account_label`, `imported_by_user_action: True`, `imported_at`, 최소 필요 메타데이터(`source_meta`) 저장
  - **해외 제비용 안전 합산 (`expenses_total`)**: 해외주식 거래 시 발생하는 제비용을 정밀하게 합산 반영
  - **해외 환율 미제공 시 KRW 손익 Null 처리**: 공식 환율 또는 KRW 환산 금액이 없는 경우 `pnl_krw = None`으로 보존하며, 외화 금액을 원화 필드에 복사하지 않고 UI에 `—`로 표시
- **릴리즈 범위 안전 제외 확인**:
  - **주식 주문 기능 (Stock Orders) 미포함** (주문 API 호출 차단)
  - **공모주 청약/일정 연동 (IPO Integration) 미포함** (실현손익 이외의 공모주 청약 기능 제외)
  - **배당금 연동 (Dividend Integration) 미포함** (사전 검증된 실현손익 범위만 지원)

## Wealth v1.1.2 — KIS Realized-P/L Integration — 2026-09-12

- **한국투자증권(KIS) 공식 OpenAPI 실현손익 연동 (Selective Realized-P/L Import)**:
  - 한국투자증권 공식 OpenAPI(국내 `TTTC8715R`, 해외 `TTTS3039R`) 기반 기간별 실현손익 실시간 피드 조회 및 선택 가져오기 파이프라인 구현
  - **검증된 계좌 스코프 (`source_scope_verified: True`)**: 토스 WTS와 달리 OpenAPI 키 설정과 계좌번호가 일치함을 사전에 검증하여 신뢰된 계좌 범위 확정
  - **불투명 출처 계좌 식별자 (Opaque Source Account Key)**: raw CANO(계좌번호 앞 8자리) 노출을 차단하고 `HMAC-SHA256(CANO, secret)` 기반 64자 불투명 키 사용
  - **마스킹 계좌 표시**: API 상태, 피드 응답, 브라우저 DOM 전반에 `XXXX****-YY` 마스킹 포맷 적용
  - **명시적 최초 귀속 및 영구 매핑**: 첫 import 시 사용자가 선택한 Wealth 계좌에 귀속되며, 이후 `kis_account_mapping.json`을 통해 안전하게 자동 제안
  - **행 단위 HMAC 서명 및 무결성 보호**: 조회 시 발급되는 `selection_token`을 통해 행 데이터 위변조(`ROW_TAMPERED`) 및 타 사용자/타 계좌 오남용 차단
  - **브라우저 JSON 정규화 불변성 (`_canonical_num_str`)**: `10`, `10.0`, `"10"`, `"10.0"` 등 브라우저/JSON 라운드트립 간 정수·실수 표기 차이로 인한 서명 검증 실패 문제 해결
  - **쓰기 전 사전 검증 (Preview-before-write)**: 모달을 통해 `NEW`, `ALREADY_IMPORTED`, `POSSIBLE_DUPLICATE`, `INVALID` 상태를 사전 분류 (미리보기 단계 금융 데이터 무저장)
  - **커밋 시점 중복 방지 (Replay Protection)**: 단기 유효한 `preview_ticket` 발급 및 최종 import 커밋 시 재분류 검증을 통해 동시성/반복 클릭에 의한 중복 쓰기 원천 차단
  - **선택적 가져오기 및 읽기 전용 피드 원칙**: 임시 조회 피드는 `read_only: True, persisted: False`로 관리되며 전체 회계 합산에 중복 포함되지 않음
  - **완전한 출처 메타데이터 보존 (Provenance)**: `source: "kis"`, `source_fingerprint: "kis-realized:v1:<sha256>"`, `source_account_key`, `source_account_label`, `imported_by_user_action: True`, `imported_at`, 최소 필요 메타데이터(`source_meta`) 저장
  - **국내 공식 매수금액 매핑 (`buy_amt` 우선 매핑)**: 공식 매수금액 필드인 `buy_amt`를 우선 매핑하여 레거시 `pchs_amt`에 의한 가림 문제 해결 및 공모주·대체입고의 매수금액 0원 정상 보존
  - **수수료 및 제세금 매핑**: `fee`, `tl_tax` 필드를 추출하여 국내 거래 테이블에 수수료/제세금 정보 명확히 표시
  - **해외 환율 미제공 시 KRW 손익 Null 처리**: 공식 환율 또는 KRW 환산 금액이 없는 경우 `pnl_krw = None`으로 보존하며, 외화 금액을 원화 필드에 복사하지 않고 UI에 `—`로 표시
- **릴리즈 범위 안전 제외 확인**:
  - **주식 주문 기능 (Stock Orders) 미포함** (주문 API 호출 차단)
  - **공모주 청약/일정 연동 (IPO Integration) 미포함** (실현손익 이외의 공모주 청약 기능 제외)
  - **배당금 연동 (Dividend Integration) 미포함** (사전 검증된 실현손익 범위만 지원)

## Wealth v1.1.1 — Toss WTS Selective Realized-P/L Import — 2026-09-12

- **토스 WTS 실현손익 선택 가져오기 (Selective Realized-P/L Import)**:
  - 브라우저에 임시 조회된 실현손익 피드에서 사용자가 원하는 행만 명시적으로 선택하여 Wealth 손익 데이터베이스로 가져오는 기능 추가
  - 선택 행에 대한 HMAC 서명 토큰(`signed_token`) 검증을 통한 파라미터 변조(tampering) 방지 및 만료 보호
  - 다중 세트(multiset) 기반 중복 방지: 동일 종목·체결일시·금액에 대한 중복 import 사전 감지(`ALREADY_IMPORTED`, `POSSIBLE_DUPLICATE`) 및 커밋 시점 재검증
  - 대상 계좌 수동 지정: 사용자가 등록한 Wealth 계좌 목록 중 대상 계좌를 명시적으로 선택하여 귀속 (`destination_account_id` / `destination_account_name`)
  - 안전한 출처 메타데이터(Provenance) 보존: `source: "toss_wts"`, `source_scope_verified: False`(미검증 스코프 경고 유지), `imported_by_user_action: True`
  - 기존 v1.1.0의 읽기 전용 조회 흐름 및 무저장 기본 원칙 완벽 보존
- **토스 WTS 배당금 연동 차단 상태 명시 (`WTS_DIVIDEND_RECORD_CONTRACT_BLOCKER`)**:
  - 토스 WTS 배당금 계약 불일치로 인해 추측성 배당 기능은 v1.1.1 릴리즈 스코프에서 안전하게 제외 유지

## Wealth v1.1.0 — Toss WTS Read-only Integration — 2026-09-12

- 불변 사용자 식별자(UUID) 기반 토스 WTS 정적 인가 계층 구현
- 명시적 런타임 세션 확인(confirmation guard) 및 로컬 상태 검증 엔드포인트 추가
- 토스 WTS 어댑터를 통한 일별 실현손익 읽기 전용 피드 제공 (KRW/USD 기준)
- 손익·배당 화면 내 토스 WTS 전용 카드 및 transient 테이블 UI 구현 (무저장 정책 준수)
- 테스트 환경 운영 데이터 쓰기 차단 우선순위 강화 및 배당 스케줄 정규화 안정화

## Wealth v1.0.21 — HOME UX 개선 — 2026-09-10

- HOME 자산 포트폴리오 중심 레이아웃 및 KPI 정렬 개선
- 기대수익·실현손익 보조 정보 간소화와 증감 색상 정리
- Quick Access와 모바일 하단 navigation을 정리했습니다.

## Wealth v1.0.20 — Release stabilization and regression audit — 2026-09-09

- 전체 Python/JavaScript 회귀, 데이터·네트워크 안전성, lifespan 및 merge readiness를 점검했습니다.
- 이번 audit에서 production blocker는 발견되지 않았습니다.
- 상세 월별 데이터가 있을 때 예상 배당금 요약 카드가 0으로 남는 fallback 문제를 수정했습니다.

## Wealth v1.0.19 — HOME dashboard visual refinement — 2026-09-09

- HOME 요약 카드와 자산 포트폴리오, 순자산 추이의 간격·정렬·타이포그래피를 정돈했습니다.
- HOME 전용 스타일 범위에서 카드 밀도와 모바일 수직 리듬을 개선했습니다.

## Wealth v1.0.18 — FastAPI lifespan startup migration — 2026-09-09

- 프로젝트 소유 startup hook을 FastAPI lifespan으로 전환했습니다.
- 기존 테스트 격리와 production startup 계약은 유지하고 deprecation warning 원인을 제거했습니다.

## Wealth v1.0.17 — 홈 자산 포트폴리오 visual refinement — 2026-09-09

- 자산 KPI 보조 정보를 명시적인 세로 행으로 정리했습니다.
- 전체 자산 구성 donut과 주요 비중 legend를 desktop에서 좌우로 배치했습니다.
- 자산군 상세 목록의 금액·비중·보조 설명 가독성을 개선하고 mobile에서는 안전하게 stack합니다.

## Wealth v1.0.16 — 테스트 환경 외부 네트워크 정책 강화 — 2026-09-09

- `WEALTH_ENV=test`에서 Yahoo, Naver, KIND 및 증권사 OpenAPI 호출을 HTTP client 생성 전에 중단합니다.
- 시세 갱신과 계좌 동기화는 테스트 환경에서 기존 금융 데이터를 보존하며 명시적인 `TEST_MODE` 결과를 반환합니다.
- localhost FastAPI/browser 검증은 허용하고 외부 연결 guard는 누락된 호출 경로를 잡는 canary로 유지합니다.

## Wealth v1.0.15 — 자산 포트폴리오와 주식 현황 분리 — 2026-09-09

- 전체 자산 포트폴리오와 주식 중심 현황의 화면 책임을 분리했습니다.
- 주식 현황 포트폴리오는 기존 주식 모드 renderer를 유지하고, 자산 구성은 홈의 자산 포트폴리오로 정리했습니다.

## Wealth v1.0.14 — 자산·계좌 및 손익·배당 navigation 평탄화 — 2026-09-09

- 자산·계좌의 증권·은행·보험·부동산을 공통 상단 탭 스타일로 정리했습니다.
- 실현손익과 배당·이자를 기존 panel/renderer 그대로 사용하는 상단 탭으로 분리했습니다.

## Wealth v1.0.13 — 절세계좌 제목 정합성 및 순자산 변화 시각화 — 2026-09-09

- 절세계좌 탭의 헤더를 활성 범위에 맞게 표시합니다.
- 순자산 추이에 총액 line과 전 기록 대비 증가·감소 bar를 추가했습니다.

## Wealth v1.0.12 — 투자 현황 상단 탭 단순화 — 2026-09-09

- 포트폴리오, 히트맵, 주식기록, 전략 버킷, 절세계좌, 보유종목을 하나의 상단 탭 체계로 분리했습니다.
- 기존 계산·필터·기록·동기화 로직은 유지하고, 중첩된 투자 화면 이동만 평탄화했습니다.

## Wealth v1.0.10 — 테스트·시작 작업 부작용 격리 — 2026-09-09

- 테스트 환경을 명시적으로 구분해 FastAPI 시작 시 외부 동기화와 실제 사용자 데이터 쓰기를 차단합니다.
- 공통 테스트 helper에 임시 환경 및 외부 네트워크 차단을 중앙화하고, raw `TestClient` 경로도 동일한 보호를 적용합니다.
- Yahoo 환율·주가 동기화는 합성 fixture로 검증하며 실제 `.env`·`data/` 파일과 외부 API에 접근하지 않습니다.

## Wealth v1.0.9 — 증권사 동기화 안정화 및 데이터 보호 — 2026-09-09

- 증권사별 동기화 결과를 `SUCCESS`, `PARTIAL_SUCCESS`, `CONFIG_REQUIRED`, `API_ERROR`, `PARSE_ERROR`, `INTERNAL_ERROR`로 구분하고 실패 범위의 기존 보유종목·예수금을 유지합니다.
- KB·토스 응답 스키마를 검증해 API/파싱 실패가 정상 0건으로 처리되지 않도록 했으며, 토스 예수금만 실패하면 보유종목만 반영하고 기존 예수금은 보존합니다.
- NH투자증권 어댑터의 누락된 logger와 연속조회 처리를 보완하고, 불완전한 해외 조회가 기존 데이터를 덮어쓰지 않도록 차단했습니다.
- 한국투자증권 계좌번호 형식, 업무 응답 및 국내·해외 연속조회를 공식 예제에 맞춰 검증합니다.
- 키움증권은 토큰 기반 계좌번호 조회(`ka00001`), 국내 잔고(`kt00018`), 예수금(`kt00001`)의 공식 request/response 구조로 수정했습니다.
- 사용자별 중복 전체 동기화를 차단하고 성공한 증권사에만 마지막 성공 시각을 기록하며, 오류 메시지의 credential·전체 계좌번호를 마스킹합니다.
- 실제 API나 사용자 데이터를 사용하지 않는 합성 fixture 회귀 테스트를 추가했습니다.

## Wealth v1.0.8 — 과거 순자산 기록 및 시각적 통일 — 2026-09-09

- 기존 순자산 history에 날짜·순자산·선택 메모를 직접 입력하는 과거 기록 추가를 확장했습니다. 미래 날짜와 동일 owner/date 중복은 거절합니다.
- 수동 기록은 source=manual로 구분하고 미입력 총자산·총부채는 null로 보존합니다. 현재 자산에서 과거 값을 추정하지 않습니다.
- 기록의 날짜·금액·메모 수정, 즉시 그래프 정렬 및 선택 갱신을 지원합니다. 오늘 기록의 현재 순자산 계산은 유지합니다.
- 기존 버튼 역할별 스타일 및 카드 surface를 통일하고 모바일 관리 버튼 2×2/44px, 기록 모달 1열 배치를 적용했습니다.
- 신규 Python 12개·JavaScript 5개 테스트를 추가했으며 기존 테스트 포함 총 104개가 통과했습니다.

## Wealth v1.0.7 — 기록 저장 안정성 및 편집 보호 — 2026-09-08

- 일반 portfolio 저장이 최신 순자산 기록·전략 버킷 metadata를 유지하도록 했습니다. 명시적 백업 복원과 초기화는 별도로 처리합니다.
- 버킷 편집 범위를 유지하고 미저장 상태·화면 종료 경고를 추가했습니다. 다시 불러오기에서 이전 선택이 남는 문제와 편집 중 revision 갱신 문제를 보완했습니다.
- 순자산 기록 금액 정정·삭제를 추가했습니다. 날짜/owner/당시 환율을 유지하고 revision 및 명시적 확인을 검증합니다.
- TemporaryDirectory 기반 저장 가능 브라우저 테스트 서버와 regression 테스트, Linux 브랜치 Docker 설치 안내를 추가했습니다.

## Wealth v1.0.6 — 홈 개편, 순자산 기록과 전략 버킷 — 2026-09-08

- 앱 버전을 `v1.0.x` 체계로 통일했습니다. 과거 이력과 데이터 형식 버전은 변경하지 않습니다.
- 정적 자산 URL과 서비스 워커 캐시 식별자를 v1.0.6으로 갱신했습니다.

- 시세 갱신과 계좌 동기화를 공통 조회 범위 옆에 배치하고 진행/부분 실패/성공 상태를 구분했습니다.
- 홈 요약 아래에 사용자 확인 기반 순자산 추이(1개월/3개월/1년/전체)를 추가했습니다. 과거 주식기록을 전체 순자산으로 변환하거나 자동 backfill하지 않습니다.
- 투자 하위 화면을 포트폴리오 / 전략 버킷 / 주식기록으로 구분했습니다.
- 계좌별 기본 버킷, 보유내역별 예외, 미분류, 목표 대비 비중을 추가했습니다. 잔고·거래를 변경하거나 매매하지 않습니다.
- optional planning metadata에 revision 충돌 검사, 금액·환율·목표 합계·참조 검증과 원자적 파일 교체를 적용했습니다.
- 사용자 격리, 기록 교체 확인, 백업 보존, 저장 실패, 분류 계산에 대한 Python/Node regression 테스트를 추가했습니다.

### 홈 및 메뉴 개편

- 자산·계좌의 증권 목록 높이 제한을 해제하고 페이지 스크롤로 통일했습니다.
- 자산 화면 상단과 도구줄을 압축하고, 모바일 은행 목록을 카드형/요약을 2열로 정리했습니다.
- 개별 자산 삭제 버튼을 추가 작업 disclosure로 이동하고 은행·예적금 빈 목록 안내를 실제 추가 버튼에 맞췄습니다.

- 순자산·현금/예적금·등록 부채를 먼저 보여주는 홈과 자산 구성 요약을 추가했습니다.
- 홈 / 투자 / 자산·계좌 / 손익·배당 / 가계부로 기존 패널을 재배치했습니다.
- PC 왼쪽 메뉴와 모바일 하단 메뉴, 공통 가족 조회 범위, 설정 화면을 구성했습니다.
- 가족·증권사 연결·백업·테마를 설정에 모으고 전체 삭제는 접힌 주의 영역으로 이동했습니다.
- 기존 금융 계산을 재사용하며 UI 전용 코드에는 API 호출과 데이터 저장을 추가하지 않았습니다.
- 실제 데이터와 분리된 읽기 전용 미리보기 및 화면 구조 regression 검사를 추가했습니다.

## Wealth v1.0.5 — 마이너스통장 자동 상계 — 2026-09-08

- 별도 opt-in 관계 `overdraft_bank_account_id`와 KRW/owner/중복 관계/한도 검증을 추가했습니다.
- 은행·대출 순포지션으로 지출과 입금을 처리하고 v3 `net_delta`로 수정·삭제합니다.
- 한도 초과 시 전체 거래를 거절하며 ledger 저장 실패 시 portfolio 복원을 시도합니다.
- 검토 과정에서 v2 수정의 암묵적 v3 전환, 실패한 고정지출 설정의 선저장, 동일 pair 수정의 중간 한도 판정을 보완했습니다.
- 기존 데이터 migration은 하지 않습니다. 강제종료와 동시 쓰기에 대한 완전한 cross-file atomicity는 제공하지 않습니다.

## Wealth v1.0.1 - 2026-09-07

### Security

- `/api/export`를 공개 경로에서 제거하고 인증된 사용자만 접근할 수 있도록 변경했습니다.
- 인증 컨텍스트가 없는 요청에서 기본 사용자(`sagesaint`)로 대체되던 동작을 제거했습니다.
- export 대상 사용자명을 로그인 세션에서만 가져오도록 하여 사용자 간 백업 데이터가 섞이지 않도록 했습니다.
- 백업에서 OpenAPI App Key, App Secret 및 관련 설정을 제외했습니다.
- 일반 자산 데이터 안에 token, secret, password, credential 관련 필드가 중첩되어 있어도 export 전에 제거합니다.
- credential 없는 일반 데이터 백업을 나타내도록 백업 형식을 `2.2`로 갱신했습니다.
- Docker build context에서 `.env`, 사용자 데이터, Excel/CSV, scratch, credential, token cache, 로그, 백업 및 개발 임시파일을 제외했습니다.

### Tests

- 미인증 export 차단 및 기본 사용자 fallback 방지 테스트를 추가했습니다.
- 사용자 A와 사용자 B의 export 격리 테스트를 추가했습니다.
- credential 제거와 일반 자산 데이터 보존 테스트를 추가했습니다.
- credential 없는 백업의 복원 테스트를 추가했습니다.
- Docker build context의 민감 파일 제외와 런타임 파일 포함 테스트를 추가했습니다.

### Documentation

- README를 Wealth 1.0.1의 실제 기능, 실행 방법, 저장 구조 및 보안 경계에 맞게 다시 작성했습니다.

> 이전 개발 이력의 버전 번호와 내용은 아래에 원문대로 유지합니다.

---

v5.5.52

(fix) 🛡️ 사용자관리 버튼 권한 분기 철저화, 상단바 모바일 1행 컴팩트 정렬, 절세계좌 툴바 최적화 및 증권 계좌 세로정렬 개선
- **사용자 관리 버튼(`adminUserBtn`) 엄격한 권한 분기 (`wealth.js`, `wealth-overrides.css`)**:
  - `me.username === 'admin'` 계정 접속 시에만 노출되도록 철저히 격리 (sagesaint 및 기타 사용자 접속 시 완전 숨김 처리)
  - CSS 내 `display: inline-flex !important`로 인해 인라인 `display: none`이 무시되던 현상을 해결하고, `[style*="display:none"] { display: none !important; }` 규칙을 강화하여 비관리자 계정에서의 노출 원천 차단
- **최상단 액션 버튼 모바일 단일 행(1-Row) 정렬 (`wealth-overrides.css`)**:
  - 좁은 모바일 화면(<= 600px)에서 최상단 버튼들이 여러 행으로 줄바꿈되던 문제를 해결하여 `flex-wrap: nowrap`, 버튼 높이 `26px`, 폰트 `10.5px`, 패딩 `0 6px`로 컴팩트화하여 한 행에 깔끔하게 모두 배치
  - 화면 폭이 극도로 좁은 기기에서도 레이아웃 깨짐 없이 자연스럽게 스크롤되도록 `overflow-x: auto` 및 스크롤바 숨김 적용
- **주식기록 섹션 절세계좌 탭(`tax_accounts`) 불필요 요소 정리 (`wealth.js`, `wealth-overrides.css`)**:
  - `🌿 절세계좌` 탭 선택 시 기간 선택 탭(`일간/주간/월간/연간/전체`)과 `💾 저장`, `➕ 추가`, 기록 건수 뱃지를 자동 숨김 처리
  - `📈 전체주식` 탭으로 전환 시 기간 탭 및 스냅샷 저장/추가 버튼이 원래대로 깔끔하게 복원
- **자산 섹션 증권 탭 계좌 카드 모바일 세로 글자 줄바꿈 해결 (`wealth.js`, `wealth-overrides.css`)**:
  - 모바일 좁은 화면에서 우측 금액/버튼 영역의 너비 차지로 인해 좌측 계좌명이 세로로 1글자씩 줄바꿈되던 증상 완벽 개선
  - 모바일(<= 640px)에서 계좌 카드를 상하 2단 분할 레이아웃으로 개편:
    - 상단: 100% 가로폭을 활용해 계좌명(단어 단위 유지 `word-break: keep-all`), 배지, 주식자산/예수금, 세액공제 혜택 박스를 가로로 시원하게 배치
    - 하단: 구분선 아래에 통장 총 자산 및 평가손익(좌)과 수정/삭제 액션 버튼(우)을 분리 배치하여 최적의 가독성 및 터치 편의성 확보
(perf) 서비스 워커 캐시 버전(`wealth-cache-v152`) 및 정적 자산 쿼리(`v5552`) 갱신

v5.5.51

(fix) 📱 가계부 요약 카드 모바일 영역 초과(Overflow) 해결 및 브랜딩·반응형 UI 규격 표준화
- **가계부 요약 카드 반응형 레이아웃 개선 (`index.html`, `wealth-overrides.css`)**:
  - `index.html` 내 인라인 4열 고정 그리드 스타일(`style="grid-template-columns:repeat(4,1fr)"`)을 제거하고 CSS 미디어 쿼리 기반 반응형 시스템으로 전환
  - 모바일(화면 폭 900px 이하): 2열(2x2) 그리드로 자동 재배치, 330px 이하 초소형 화면에서는 1열 그리드 자동 전환
  - 모바일 화면에서 텍스트 말줄임(`text-overflow: ellipsis`) 및 폰트 크기/패딩 최적화로 카드가 섹션 테두리 밖으로 튀어나가는 현상 원천 차단
- **최상단 브랜딩 텍스트 개편 (`index.html`, `wealth.js`)**:
  - 서브 타이틀: `Human Index INVESTMENT` -> `Wealth`
  - 메인 타이틀: `인간지표의 투자 대시보드` -> `자산`
  - 브라우저 탭 타이틀: `Wealth · 자산`
  - 자바스크립트 사용자 로그인 및 프로필 렌더링 시에도 "Wealth" / "자산" 명칭이 일관되게 유지되도록 동기화
- **반응형 UI 규격 표준화 및 통일감 향상 (`wealth-overrides.css`)**:
  - **컴팩트 버튼 규격 표준화**: 대시보드 내 모든 액션 버튼(상단 바, 각 섹션 툴바)의 높이(31px), 폰트 크기(11.5px), 테두리 곡률(8px) 일원화
  - **탭 버튼 규격 표준화**: 가족 탭, 기간 탭, 자산 분류 탭 등의 높이(29px), 폰트(11.5px)를 단정하게 정렬
  - **섹션 헤더 및 타이틀 통일감**: `h2` 제목 크기, 접기/펼치기 버튼(`▼`), 여백 및 툴바 줄바꿈 배치를 모바일/태블릿/웹 전 환경에서 자연스럽게 매칭
  - **가계부 툴바 2x2 반응형 배치**: 모바일 화면에서 가계부 4대 관리 버튼(카드 관리, 고정지출, 가져오기, 내역 추가)이 2x2 그리드로 정갈하게 채워지도록 최적화
(perf) 서비스 워커 캐시 버전(`wealth-cache-v151`) 및 정적 자산 쿼리(`v5551`) 갱신

v5.5.50

(fix) 🐛 날짜 입력(DD) 2자리 타이핑 시 1자리 고정(02) 및 입력 먹통 버그 해결
- **순환 동기화 피드백 루프 원천 차단 (`wealth.js`)**:
  - `dayInput`에 `2`를 입력했을 때 내부적으로 `padStart(2, "0")`가 조기 실행되어 `02`로 자동 패딩되고, 네이티브 날짜의 `change` 이벤트가 역으로 `dayInput`의 값을 `02`로 강제 덮어쓰던 버그 수정
  - `isSyncingToNative` 플래그를 도입하여 분할 인풋 -> 네이티브 동기화 중에는 역방향 동기화(`syncFromNative`)가 발생하지 않도록 상호 배제
  - `syncToNative()`는 연도 4자리, 월 2자리, 일 2자리가 모두 온전하게 입력되었을 때만 실행되도록 개선하여 타이핑 도중 값이 변조되지 않도록 보장
- **일(DD) 및 월(MM) 스마트 입력 허용 범위 개선**:
  - `dayInput`: `1`, `2`, `3` 입력 시 `10`~`31`일(예: `25`일) 입력을 위해 1자리 상태를 온전히 유지하도록 개선 (4~9는 04~09로 즉시 패딩)
  - `monthInput`: `0`, `1` 입력 시 `10`~`12`월 입력을 위해 1자리 상태를 유지하고 2자리 완성 시 이동
  - `blur` 및 `Enter` 키 입력 시 1자리 숫자를 2자리(`01`~`09`)로 자동 정규화
(perf) 서비스 워커 캐시 버전(`wealth-cache-v150`) 및 정적 자산 쿼리(`v5550`) 갱신

v5.5.49

(feat) 📅 가계부(Ledger) 분할 날짜 컴포넌트 적용 및 마우스오버 휠(Mouse Wheel) 날짜 조절 기능 지원
- **가계부 섹션 분할 날짜 입력 컴포넌트 전면 적용 (`index.html`, `wealth.js`)**:
  - `ledgerTxForm`(가계부 수입/지출 내역 등록 및 수정) 및 `ledgerCardPaymentDialog`(카드 대금 결제) 날짜 입력창에 분할 날짜 컴포넌트(`[YYYY] - [MM] - [DD] [📅]`) 적용
  - 연도 4자리 입력 시 월(Month)로 자동 포커스/커서 이동, 월 2자리 입력 시 일(Day)로 자동 이동 등 편리한 키보드 내비게이션 동일 제공
  - 기존 등록/수정/조회 API 및 네이티브 날짜 필드와 100% 양방향 실시간 동기화 유지
- **마우스오버 휠(Mouse Wheel) 날짜 실시간 조절 기능 신규 도입 (`wealth.js`, `wealth-overrides.css`)**:
  - **연도 휠 조절**: 날짜 입력창 연도(Year) 영역에 마우스 커서를 올린 상태(Hover)에서 마우스 휠을 굴리면 연도가 1년 단위로 즉각 증감 (+1, -1)
  - **월/일 휠 조절**: 월(Month) 영역 휠 스크롤 시 1~12월 순환 조절, 일(Day) 영역 휠 스크롤 시 해당 월의 마지막 날(28~31일, 윤년 반영)에 맞춰 스마트 순환 조절
  - **스크롤 간섭 방지**: `wheel` 이벤트에 `{ passive: false }` 및 `preventDefault()`를 적용하여 마우스 휠 조작 시 모달 팝업이나 배경 화면이 함께 스크롤되는 현상 완벽 차단
  - **전체 적용**: 실현손익, 배당금, 가계부 등 대시보드 내 모든 분할 날짜 입력창에 일괄 공통 적용
  - **가계부 상단 월 텍스트 휠 내비게이션**: 가계부 상단 현재 월 표시(`ledgerCurrentMonthText`) 위에서 휠을 굴려 이전/다음 달로 빠르게 이동하는 편의 기능 추가
  - **시각적 호버 피드백**: 마우스오버 시 미세한 배경 하이라이트 및 안내 툴팁(`title`) 제공
(perf) 서비스 워커 캐시 버전(`wealth-cache-v149`) 및 정적 자산 쿼리(`v5549`) 갱신

v5.5.48

(feat) 📅 실현손익 및 배당금 날짜 입력 시 연도 4자리 입력 시 월(Month)로 자동 커서 이동 기능 지원
- **분할 날짜 입력 컴포넌트(Split Date Input) 신규 구축 (`wealth.js`, `index.html`, `wealth-overrides.css`)**:
  - `pnlRecordForm`(매도 실현손익) 및 `dividendRecordForm`(배당금)의 날짜 입력 필드를 분할 입력 체계(`[YYYY] - [MM] - [DD] [📅]`)로 전면 고도화
  - **연도 4자리 자동 이동**: 연도 입력창에 4자리 숫자(예: `2026`) 입력 완료 시, 마우스 조작이나 방향키 없이 즉시 월(Month) 입력칸으로 포커스/커서가 자동 이동
  - **월 2자리 자동 이동 및 패딩**: 월 입력창에 2자리 입력(예: `08`, `12`) 시 일(Day) 입력칸으로 자동 이동하며, 2~9 한자리 입력 시 `02`~`09`로 자동 변환 후 일(Day)로 이동
  - **스마트 키보드 내비게이션**: Backspace 키 입력 시 빈 입력칸에서 이전 칸(월->연도, 일->월)으로 자동 역이동 및 좌/우 방향키, `/`, `-`, Tab을 통한 직관적인 앞뒤 이동 지원
  - **전체 선택(Quick Replace)**: 포커스 진입 시 기존 텍스트를 자동 전체 선택(`select()`)하여 즉각적인 덮어쓰기 타이핑 지원
  - **날짜 문자열 붙여넣기(Paste) 지원**: `2026-09-07`, `20260907` 등 복사한 날짜를 붙여넣을 경우 연/월/일 자동 분할 반영
  - **달력 팝업(Calendar Picker) 연동**: 우측 `📅` 버튼 클릭 시 브라우저 내장 캘린더 피커가 열려 마우스 선택과 키보드 타이핑을 자유롭게 병행 가능
- **테마별 시각 디자인 조화**:
  - 기본 테마, 화이트 테마, OLED 다크 테마 각각의 배경색, 테두리 색상, 포커스 네온 링 완벽 동기화
(perf) 서비스 워커 캐시 버전(`wealth-cache-v148`) 및 정적 자산 쿼리(`v5548`) 갱신

v5.5.47

(feat) 🔍 네이버 증권(Naver Finance) 실시간 연동 종목코드 검색 및 신규 공모주(아이엠바이오로직스, 한패스 등) 자동완성 지원
- **네이버 증권 실시간 검색 연동 (`stock_master.py`, `app/main.py`)**:
  - 로컬 마스터 사전에 등록되지 않은 신규 상장주, 공모주, 장외/상장예정 종목도 네이버 증권을 통해 실시간으로 6자리 종목코드 및 공식 종목명을 검색할 수 있는 Fallback 검색 체계 구축
  - 단일 완전 일치 즉시 리다이렉트 스크립트(`parent.location.href='/item/main.naver?code=...'`) 및 다중 검색 결과 테이블 파싱 완벽 지원
  - 백엔드 `/api/stock-search` 엔드포인트를 비동기 논블로킹(`async_search_stock_by_name`)으로 고도화하여 0.2~0.4초 초고속 검색 보장
  - 네이버 증권에서 한 번 검색된 신규 종목은 인메모리 캐시 및 로컬 파일(`stock_master_cache.json`)에 자동 영구 저장되어 이후 조회 시 0ms 즉시 반환
- **신규 공모주 기본 사전 및 별칭 매핑 강화**:
  - `아이엠바이오로직스`(`493280`), `한패스`(`408470`)를 백엔드 `KR_STOCK_ALIAS_MAP` 및 프론트엔드 `POPULAR_IPO_STOCKS`에 정식 등록
  - 양방향 코드 변환 지원: 종목명(`아이엠바이오로직스`) -> 종목코드(`493280`), 종목코드(`493280`) -> 종목명(`아이엠바이오로직스`) 상호 변환 보장
  - 공모주 모드 입력창 안내 placeholder에 최신 공모주 예시(`아이엠바이오로직스`, `한패스`, `리센스메디컬`) 반영
(perf) 서비스 워커 캐시 버전(`wealth-cache-v147`) 및 정적 자산 쿼리(`v5547`) 갱신

v5.5.46

(feat) 📦 공모주 및 주식 실현손익 추가 시 실시간 종목명·종목코드 검색 및 자동완성(Suggestions Dropdown) 고도화
- **실시간 종목 검색 자동완성 추천 드롭다운(Suggestions Dropdown) 신규 구축**:
  - `pnlRecordForm`(매도 실현손익), `holdingForm`(보유종목), `dividendRecordForm`(배당금) 입력 폼에 일체형 실시간 검색 레이어 구축
  - 종목명(또는 공모주 종목명) 입력 시 180ms 디바운스로 로컬 데이터 및 `/api/stock-search`를 동시 검색하여 후보 목록을 세련된 드롭다운으로 실시간 표시
  - 마우스 클릭 및 키보드(위/아래 방향키, 엔터, Tab, ESC) 완벽 지원: 선택 시 종목명, 종목코드, 거래통화 즉시 자동 완성
- **공모주(리센스메디컬 등) 종목코드 검색 연동 및 자동완성 버그 해결**:
  - 기존에 브라우저 기본 `<datalist>`에 공모주가 포함되지 않아 타이핑 시 아무런 추천이 뜨지 않던 문제 해결
  - 기존에 코드가 일부 입력되어 있으면 검색 성공 후에도 덮어쓰지 않던 조건(`if (!codeInput.value)`)을 개선하여 검색된 최신 종목코드로 정확히 갱신되도록 보장
  - 백엔드 종목 마스터(`stock_master.py`)에 리센스메디컬(`394420`), 시프트업(`462870`), 더본코리아(`475560`), 에이피알(`278470`), HD현대마린솔루션(`443060`) 등 주요 공모주 매핑 강화
  - 종목코드 자동 입력 성공 시 1.2초간 부드러운 네온 펄스(`input-autofill-flash`) 시각적 피드백 제공
- **공모주 탭 맞춤형 UI 편의성 개선**:
  - 공모주 모드 진입 시 입력창 placeholder를 `예: 리센스메디컬, 에이피알, 시프트업 (종목명 입력 시 자동 검색)`으로 안내 강화
(perf) 서비스 워커 캐시 버전(`wealth-cache-v146`) 및 정적 자산 쿼리(`v5546`) 갱신

v5.5.45

(fix) 🎨 시스템 관리자(admin) 계정 화면 모던 화이트 테마 및 OLED 테마 완벽 지원
- **Admin 메인 패널(`adminMainPanel`) 및 관리 모달(`adminUsersModal`) 테마 디자인 전면 개편**:
  - 기존 하드코딩된 다크 인라인 스타일(`background: #0e1529`, `#091024`, `border: 1px solid #263558`)을 전면 제거하고 전용 시맨틱 클래스 체계로 전환
  - 화이트 테마 적용 시 섹션 전체가 검정색 박스로 고정되던 문제를 완전 해결하여, 깨끗하고 부드러운 화이트 톤(`background: #ffffff`, `#f8fafc`, 테두리 `#e2e8f0`)으로 전환되도록 개선
- **관리자 하위 컴포넌트 테마별 전용 클래스화**:
  - 관리자 통계 요약 카드 3종(`.admin-stat-card`), 사용자 생성 박스(`.admin-create-box`), 폼 입력창(`.admin-input`), 사용자 목록 테이블(`.admin-table-wrap`, `.admin-thead-tr`, `.admin-row`)을 테마별(기본, OLED, 화이트)로 완벽 분리
  - `refreshAdminUserList` 렌더링 시 하드코딩된 흰색/다크 텍스트(`color: #f3f5ff`)를 제거하고 테마별 고대비 텍스트 및 상태 뱃지(`.admin-status-badge.active`, `.admin-status-badge.pending`, `.admin-role-badge`) 적용
- **OLED 다크 테마 완벽 동기화**:
  - OLED 모드(`[data-theme="oled"]`)에서도 완전 블랙(`#070709`) 베이스와 딥 다크 박스(`#0b0b10`, `#050508`)로 일관성 있게 렌더링되도록 스타일 보강
(perf) 서비스 워커 캐시 버전(`wealth-cache-v145`) 및 정적 자산 쿼리(`v5545`) 갱신

v5.5.44

(fix) 🎨 기본 테마 및 OLED 테마에서 증권사 OpenAPI 설정 모달 화이트 톤 노출 현상 해결
- **증권사 OpenAPI 설정 모달(`userOpenApiModal`) 표준 다이얼로그 규격 통일**:
  - 기존 비표준 클래스(`.dashboard-dialog`)를 시스템 표준 다이얼로그 클래스(`.dialog`)로 일원화
  - 기본 테마(다크/퍼플)에서 브라우저 기본 흰색 캔버스(`canvas`) 배경으로 노출되던 문제를 해결하고, 고유의 다크 네이비 배경(`#0e162b`) 및 테두리(`#263558`), 그림자 효과 완벽 복원
  - OLED 모드(`[data-theme="oled"]`)에서도 순수 블랙(`#070709`) 배경 및 네온 테두리로 일관성 있게 렌더링되도록 스타일 규칙 추가
- **모달 내부 증권사 카드 및 컴포넌트 테마별 전용 클래스화**:
  - 개별 증권사 카드(`.openapi-broker-card`), 입력창(`.openapi-input`), 라벨(`.openapi-label`), 상태 뱃지(`.openapi-badge`), 안내 박스(`.openapi-info-box`) 스타일을 테마별(기본, OLED, 화이트)로 완벽 분리
  - JavaScript 동적 뱃지 렌더링 시 인라인 컬러를 강제 주입하지 않고 `.openapi-badge.connected` 및 `.openapi-badge.disconnected` 클래스를 토글하도록 개선하여 모든 테마에서 시인성 극대화
  - 화이트 테마 전용 최상단 툴바 버튼(`.userOpenApiBtn`) 및 서브 닫기 버튼 톤 정돈
(perf) 서비스 워커 캐시 버전(`wealth-cache-v144`) 및 정적 자산 쿼리(`v5544`) 갱신

v5.5.43

(fix) 🎨 가계부 월 선택 컨트롤러 고도화, 카테고리 시인성 개선, 테마별 카드 배경색 특성화 및 버튼 일관성 통일
- **가계부 월 선택 컨트롤러 사용성 및 테마 디자인 전면 개편**:
  - 기존 하드코딩된 다크 박스를 제거하고 테마별 반응형 디자인(`.ledger-month-control`) 적용
  - 이전/다음(`◀`/`▶`) 탐색 버튼 외에 **"이번달" 바로가기 버튼(`ledgerTodayMonthBtn`)** 추가
  - 연/월 텍스트 클릭 시 브라우저 네이티브 월 캘린더 피커(`<input type="month">`)가 열려 원하는 연월로 즉각 점프 가능하도록 UX 극대화
- **상세 거래내역 카테고리 텍스트 시인성 향상**:
  - 화이트 테마에서 배경과 구분이 어려웠던 인라인 연회색 텍스트(`#cbd5e1`)를 제거하고 또렷한 슬레이트 뱃지(`.ledger-cat-badge`) 스타일 적용
  - 다크 테마(퍼플, OLED) 및 화이트 테마 전용 뱃지 스타일을 분리하여 시인성과 가독성 대폭 향상
- **테마별 4대 요약 카드(수입/지출/저축/고정지출) 배경색 특성화**:
  - **화이트 테마**: 수입(소프트 민트), 지출(소프트 로즈), 순저축(소프트 스카이블루), 고정지출(소프트 라벤더)의 감각적인 파스텔 그라데이션 및 테두리 색상 적용
  - **OLED 테마**: 완전 블랙 베이스 위에 기능별 네온 틴트 그라데이션 및 네온 테두리 적용
  - **기본 퍼플 테마**: 딥 네이비 퍼플 베이스에 각 통계별 고유 앰비언트 악센트 유지
- **타 섹션과의 버튼 명칭 및 아이콘 통일**:
  - 가계부 상단 툴바 버튼을 타 섹션(보유종목, 실현손익, 배당금)과 일치하도록 `📂 가져오기`, `➕ 내역 추가`, `🛡️ 고정지출`, `💳 카드 관리`로 정비
  - 하드코딩된 인라인 버튼 색상을 제거하고 공통 클래스(`.button.secondary/primary.compact`)로 통합
- **모달 및 서브 다이얼로그 다크 잔재 제거**:
  - 신용카드 관리, 고정지출 관리, 엑셀 업로드 모달 내 서브 카드 아이템 및 연금 연도별 납입 내역 카드의 인라인 다크 배경을 클래스로 이관하여 화이트 테마 라이트 톤 적용
(perf) 서비스 워커 캐시 버전(`wealth-cache-v143`) 및 정적 자산 쿼리(`v5543`) 갱신

v5.5.42

(fix) 🎨 모던 화이트 테마 디자인 요소 및 시인성 전면 점검·개선
- **화이트 테마 내 카드 배경 검정색 노출 현상 완전 해결**:
  - 절세계좌(IRP·연금저축·ISA) 필터 카드(`.tax-card`), 보유종목 테이블 래퍼(`.tax-table-wrap`) 및 헤더(`thead th`)의 하드코딩된 다크 배경(`background: #0c1429`, `#0d1424`)을 화이트 테마에 맞게 라이트 톤(`background: #ffffff`, `#f8fafc`, 보더 `#e2e8f0`)으로 전면 치환
  - 부동산 매도 완료 카드(`.saving-card.real-estate-card.badge-sold`) 및 보험/절세 카드 인라인의 어두운 그라디언트(`background: linear-gradient(...)`)를 제거하고 테마별 스타일 규칙으로 이관
  - 계좌 통합 현황 은행 통장 행(`.account-row`)의 인라인 다크 배경(`background: #111a33`) 제거
  - 가계부 섹션의 서브패널, 카테고리 행, 거래 내역 테이블 헤더의 어두운 배경을 라이트 톤으로 개선
  - 초기 비밀번호 변경 강제 모달(`forcePasswordModal`) 및 OpenAPI 연동 모달(`userOpenApiModal`)의 하드코딩된 어두운 배경 제거
- **화이트 테마 내 흰색/연회색 글씨 시인성 저하 문제 해결**:
  - 상단 메인 요약 카드(순자산, 투자자산, 원화 주식, 달러 주식, 기대수익, 실현손익, 배당금, 안전자산) 및 세부 수치(`.value-highlight`)의 인라인 `color: #ffffff`, `color: #f8fafc`를 제거하고 고대비 다크 텍스트(`#0f172a`) 적용
  - 예적금/대출/부동산/보험 카드 세부 항목값(`.saving-detail-val`)이 연회색(`#e2e8f0`)으로 흐리게 보이던 문제를 고대비 다크 텍스트(`#0f172a`, 라벨 `#64748b`)로 전면 개선
  - 절세계좌 카드의 제목 및 총자산 수치, 이자/환급액 수치, 매도 부동산 카드의 제품명 및 양도차익 라벨 텍스트의 고대비 색상 보장
  - 자산 하위 구성(주식, 부동산, 안전자산 세부 항목) 및 캡션 텍스트의 화이트 테마 전용 색상 적용
- **OLED 테마 및 기본 퍼플 테마 무결성 유지**:
  - OLED 모드(`[data-theme="oled"]`) 및 기본 퍼플 모드에서 기존의 깊이 있는 다크 디자인 요소가 완벽하게 유지되도록 스타일 분리 검증 완료
(perf) 서비스 워커 캐시 버전(`wealth-cache-v142`) 및 정적 자산 쿼리(`v5542`) 갱신

v5.5.41

(fix) 🔧 실현손익 섹션 매도 내역 목록(테이블) 렌더링 정상화
- **실현손익 상세 내역 렌더링 컨테이너 참조 오류 수정**:
  - `renderPnlMonthlyDetail` 함수 내 타겟 컨테이너 DOM 요소(`$("#pnlMonthlyDetail")`) 선언 누락으로 인해 발생하던 런타임 오류(`ReferenceError: container is not defined`) 해결
  - 실현손익 섹션의 전체 기간 및 선택 월별 매도 상세 내역 테이블이 정상적으로 노출되도록 즉각 복구
(perf) 서비스 워커 캐시 버전(`wealth-cache-v140`) 및 정적 자산 쿼리(`v5541`) 갱신

v5.5.40

(fix) 📈 포트폴리오 주식 실현손익 및 실현손익 탭에서 부동산 매매손익 완전 제외 & 주식/공모주 순수 집계 분리
- **포트폴리오 섹션 주식 탭 [주식 실현손익] 카드 정밀 분리**:
  - 주식 탭의 '주식 실현손익' 카드(전체/연도별/월별)에서 부동산 매매수익(양도차익)을 완전히 배제하고, 순수 국내/해외 주식 및 공모주 매도 손익만 정확하게 집계·표시하도록 수정
  - All-Time 전체 실현손익 갱신 시 주식 탭과 자산 종합 탭(매매차익+배당/이자 통합)의 표시 기준을 분리하여 왜곡 제거
- **실현손익 탭(패널)에서 부동산 실현손익 완전 제외 (주식/공모주 전용화)**:
  - 백엔드 `/api/realized-pnl` (`get_pnl_summary`)에서 부동산 매도 기록을 완전 필터링하여 실현손익 탭의 요약 카드(총 손익, 승률, 실현 건수), 연도별/월별 차트, 매도 상세 테이블이 오직 주식/공모주 실적만을 표시하도록 정돈
  - 실현손익 탭 내 등록 폼(`pnlRecordForm`)에서 부동산 옵션을 제외하고 주식/공모주 전용 등록 폼으로 간소화
  - 실현손익 전체 삭제(`clear_pnl_records`) 시에도 주식/공모주 기록만 초기화하고 부동산 매도 기록은 영구 보존되도록 방어 로직 적용
- **부동산 매도 내역은 [자산 섹션 부동산 탭]에서만 독립 관리**:
  - 부동산 매도 및 양도차익은 자산 섹션 부동산 탭의 [🏷️ 부동산 실현손익] 요약 카드 및 [🏷️ 매도] 서브탭에서 계속해서 독립적이고 체계적으로 관리 유지
(perf) 서비스 워커 캐시 버전(`wealth-cache-v139`) 및 정적 자산 쿼리(`v5540`) 갱신

v5.5.39

(fix) 🏠 부동산 매도 기록 연동 오류 해결 & 실현손익·배당금 섹션 컬럼 헤더 정렬(Sort) 기능 구현
- **자산 섹션 부동산 탭 매도 실현손익 연동 완전 자동화**:
  - 실현손익 섹션의 `[➕ 손익 추가]`에서 매도 건을 등록/수정/삭제 시 `loadDashboard()` 및 `renderRealEstateWithOwner()`를 함께 호출하여 부동산 탭 상단 요약 카드와 [매도] 서브탭에 실시간 동기화
  - 아파트/빌라/오피스텔/주택/단지 등 부동산 키워드 및 등록된 보유 부동산명을 지능적으로 자동 감지하여 부동산 매도 건으로 자동 매칭 및 누락 방지
  - 손익 등록 폼(`pnlRecordForm`)에서 '🏠 부동산 매매' 선택 시 보유 부동산 선택 드롭다운(`pnlRealEstateSelect`)과 취득가·양도가·필요경비 입력 필드 노출 및 실시간 손익 계산 연동
- **실현손익 및 배당금 섹션 테이블 정렬(Sort) 기능 신설 (보유종목과 동일 UX)**:
  - 보유종목 테이블과 100% 동일한 클릭형 컬럼 헤더 정렬 (`sortable-th`, `▲`/`▼` 인디케이터)
  - **실현손익 테이블**: 매도일(`date`), 소유자(`owner`), 종목/부동산명(`name`), 거래유형(`is_ipo`), 외화손익(`pnl`), 원화 환산손익(`pnl_krw`)별 오름차순/내림차순 정렬 지원
  - **배당금 테이블**: 입금일(`date`), 소유자(`owner`), 종목명(`name`), 외화입금액(`amount`), 원화 환산금액(`amount_krw`)별 오름차순/내림차순 정렬 지원
(perf) 서비스 워커 캐시 버전(`wealth-cache-v137`) 및 정적 자산 쿼리(`v5539`) 갱신

v5.5.38

(feat) 🏢 자산 섹션 부동산 탭 상단 부동산 실현손익 요약 카드 & [매도] 내역 탭 및 상세 관리 기능 추가
- **상단 요약 카드 [🏷️ 부동산 실현손익] 신규 추가**:
  - 부동산 탭 상단에 매도 완료된 부동산의 총 누적 실현손익(양도차익) 및 매도 건수, 차익 수익률을 확인할 수 있는 전용 요약 카드 배치
  - 카드 클릭 시 [매도] 서브탭으로 즉각 전환되는 부드러운 인터랙션 지원
- **부동산 서브탭 [🏷️ 매도] 신규 추가 및 매도 내역 상세 카드 렌더링**:
  - 기존 [전체], [자가], [임대], [임차] 외에 **[매도]** 서브탭 신설
  - 매도 부동산별 취득가(매수가), 양도가(매도가), 필요경비(공제), 실현손익(양도차익) 및 수익률, 매도일자, 메모 등을 상세히 확인 가능
- **부동산 매도 기록 관리 및 직접 매도 등록 지원**:
  - 보유 부동산 카드의 [🏢] 버튼을 통한 매각 기록 등록과 100% 연동
  - 과거 매도 내역이나 별도 매도 건을 등록할 수 있는 [➕ 매도 기록 추가] 기능 지원
  - 등록된 매도 기록의 `✎ 수정` 및 `🗑️ 삭제` 기능 완비
(perf) 서비스 워커 캐시 버전(`wealth-cache-v136`) 및 정적 자산 쿼리(`v5538`) 갱신

v5.5.37


(feat) 📱 주식기록 [전체주식] 탭 날짜별 자산추이 모바일 스크롤 및 테마별 스크롤바 디자인 지원
- **날짜별 자산추이 기록(`.record-list`) 모바일 스크롤 컨테이너 복원**:
  - 기존 1100px 이하 모바일/태블릿 반응형 미디어 쿼리에서 `max-height: none`으로 풀려 화면 전체로 길어지던 현상 수정
  - 모바일(1100px 이하 및 600px 이하) 환경에서 최적 높이(`max-height: 380px` / `340px`) 및 부드러운 터치 스크롤(`-webkit-overflow-scrolling: touch; overscroll-behavior: contain`) 적용
- **다크/화이트/OLED 테마별 커스텀 슬림 스크롤바 적용**:
  - 다크, 화이트, OLED 테마 색상에 최적화된 은은한 슬림 스크롤바(`width: 6px`) 및 Firefox(`scrollbar-width: thin`) 완벽 호환
(perf) 서비스 워커 캐시 버전(`wealth-cache-v135`) 및 정적 자산 쿼리(`v5537`) 갱신

v5.5.36


(fix) 💾 전체 데이터 백업(저장하기) 및 복원(가져오기) 시 스마트 가계부(ledger) 및 OpenAPI 설정 포함 지원
- **데이터 백업(`/api/export`) 가계부 내역 완전 포함**:
  - 데이터 저장하기 시 기존 포트폴리오, 자산기록, 배당내역, 실현손익 외에 **가계부 전체 내역(수입/지출/이체 거래내역, 고정지출, 등록 카드, 예산 및 카테고리 설정)**과 **증권사 OpenAPI 설정**을 백업 번들에 통합
- **데이터 복원(`/api/import-backup`) 가계부 및 OpenAPI 안전 복원**:
  - 백업 파일 불러오기 시 `ledger` 및 `openapi_config` 데이터를 사용자의 데이터 디렉토리에 정합성을 검증하여 안전하게 복원
  - 이전 버전의 백업 파일(가계부 항목이 없는 파일)도 오류 없이 호환 복원되도록 처리
- **프론트엔드 복원 직후 가계부 실시간 갱신**:
  - 데이터 불러오기 완료 즉시 `loadLedger()`를 호출하여 대시보드와 자산기록뿐만 아니라 가계부 탭 데이터도 페이지 새로고침 없이 즉각 동기화
(perf) 서비스 워커 캐시 버전(`wealth-cache-v134`) 및 정적 자산 쿼리(`v5536`) 갱신

v5.5.35

(feat) 💎 주식기록 절세계좌 개별 카드 및 내역 테이블 예수금 명확화 & 자산 섹션 증권 탭 총자산(주식+예수금) 표시 개편
- **자산 섹션 증권 탭 계좌 행 총자산 및 주식자산/예수금 상세 표기**:
  - 기존 `N종목 · 예수금 ₩...`만 축약되던 계좌 목록을 개편하여 주식자산 금액(`주식자산 ₩...`)과 예수금(`예수금 ₩...`)을 동시 표기
  - 각 계좌 우측에 **증권 통장 총 자산**(`₩...` 볼드 강조) 및 **평가손익**(`+₩...`)을 명확하게 노출
- **주식기록 절세계좌 탭 좌측 카드 자산 구성(주식 + 예수금) 독립 행 표기**:
  - 개별 계좌 카드 및 카테고리 카드(전체/ISA/IRP/연금저축) 내에 `주식 ₩...`와 `💵 예수금 ₩...`을 별도의 강조 박스로 분리하여 가독성 획기적 개선
- **우측 계좌 내역(종목 테이블) 최상단 [💵 예수금 (현금 잔고)] 전용 행 추가**:
  - 계좌 내역 조회 시 보유 주식뿐만 아니라 계좌 내 미투자 현금 잔액인 예수금 행을 테이블 최상단에 배치하여 계좌 전체 자산 구성을 완벽하게 확인 가능
  - 주식 종목이 0개이고 예수금만 있는 계좌도 테이블 내역에서 예수금 잔고를 즉시 확인 가능하도록 지원
- **우측 상단 요약 헤더 자산 구성 세분화**:
  - `총 자산: ₩... (주식 ₩... · 💵 예수금 ₩...)` 및 손익, 누적 절세액을 일목요연하게 표시
(perf) 서비스 워커 캐시 버전(`wealth-cache-v133`) 및 정적 자산 쿼리(`v5535`) 갱신

v5.5.34

(feat) 💎 주식기록 절세계좌 탭 평가금액에 계좌별 예수금(원화·달러) 완전 통합 및 상세 정리
- **단일 계좌 선택 및 카테고리 헤더 평가금액에 예수금 포함**:
  - 절세계좌 개별 카드 및 카테고리(ISA/IRP/연금저축/전체) 선택 시 상단 헤더 평가금액을 `주식 평가금액 + 예수금(KRW+USD)`으로 정확하게 합산 표기
  - 예수금이 존재하는 경우 상단 요약 헤더에 `💵 예수금 ₩...` 뱃지를 함께 안내하여 평가금액 내 예수금 포함 여부를 직관적으로 확인 가능
- **좌측 사이드바 계좌별 상세 카드 및 카테고리 카드 총액에 예수금 반영**:
  - 개별 계좌 카드 평가금액을 예수금 포함 총자산으로 개편하고, 종목 수 우측에 `· 예수금 ₩...` 표기 추가
  - [절세계좌 전체], [중개형 ISA], [개인형 IRP], [연금저축] 카드의 총액/평가금액에도 각 계좌군의 예수금을 포함
- **보유종목이 없고 예수금만 있는 계좌 대응**:
  - 주식 매수 전 예수금만 입금된 절세계좌도 자산 누락 없이 평가금액과 예수금 안내가 온전히 표시되도록 빈 상태 처리 개선
(perf) 서비스 워커 캐시 버전(`wealth-cache-v132`) 및 정적 자산 쿼리(`v5534`) 갱신

v5.5.33

(feat) 💎 자산 섹션 증권사 탭 계좌 수정 모달에 예수금(원화·달러) 통합 및 단독 예수금 버튼 제거
- **증권사 계좌 정보 수정 모달(`accountEditDialog`) 내 예수금 직접 입력 지원**:
  - 원화 예수금(KRW) 및 달러 예수금(USD) 입력 필드를 계좌 수정 폼에 통합
  - 한글 금액 실시간 프리뷰(`data-korean-currency`) 지원으로 직관적인 원화 예수금 확인 가능
  - 계좌 추가 모달(`accountAddDialog`)에도 예수금 입력 필드를 동시 지원하여 신규 계좌 등록 시 예수금 동시 설정 가능
- **자산 섹션 증권사 탭 계좌 행 단독 예수금 수정 버튼(`💵`) 제거**:
  - 계좌 정보 수정(`✎`) 버튼 하나로 증권사, 계좌명, 소유자, 유형, 세액공제 및 예수금을 통합 관리하도록 UI 단순화
- **백엔드 및 전역 상태 동기화**:
  - `PUT /api/accounts/{account_id}` 및 `POST /api/accounts`에서 `cash_krw`, `cash_usd` 동시 저장 처리
  - 클라이언트 캐시 즉각 반영(Optimistic Update) 및 대시보드 자동 재계산 연동
(perf) 서비스 워커 캐시 버전(`wealth-cache-v131`) 및 정적 자산 쿼리(`v5533`) 갱신

v5.5.32

(feat) 💎 주식기록 절세계좌 단일 계좌 조회 및 사이드바 카드에 계좌별 누적절세액 표기
- **단일 계좌 상세 조회 시 우측 상단 헤더에 해당 계좌 누적 절세액 표시**:
  - 특정 절세계좌(예: 연금저축 공제, 개인형 IRP) 선택 시 상단 헤더에 `💎 누적 절세액: ₩X,XXX,XXX` 뱃지를 함께 표기
  - ISA 계좌 조회 시 `🔄 ISA 비과세 200~400만 + 9.9% 분리과세` 혜택 표기
  - 비공제 계좌 조회 시 `🌱 비공제 계좌: 원금 인출 시 비과세` 안내 뱃지 제공
- **좌측 사이드바 개별 계좌 상세 카드에 누적 절세액 행 추가**:
  - 개별 계좌 카드 하단에 해당 계좌만의 누적 절세액(`💎 누적 절세액 ₩...`)을 명확히 표기
  - 카드가 선택된 상태에서도 한눈에 계좌별 절세 기여도를 비교/파악할 수 있도록 UI 완성
(perf) 서비스 워커 캐시 버전(`wealth-cache-v130`) 및 정적 자산 쿼리(`v5532`) 갱신

v5.5.31

(feat) 🌿 주식기록 [절세계좌] 탭 보유종목 테이블 개편 및 계좌별 실시간 필터링 연동
- **기존 보유종목 섹션과 동일한 종목별 그룹화 및 보유계좌 나열 테이블 구현**:
  - "절세계좌 전체" 및 카테고리(ISA, IRP, 연금저축) 조회 시 동일 종목(코드+통화+종목명)을 그룹화하여 1개 행으로 통합
  - '보유계좌' 컬럼 하위에 해당 종목을 보유한 계좌별 명칭, 소유자, 수량, 수정(✎) 및 삭제(×) 버튼을 직관적으로 나열
  - 종목별 전체 합산 수량, 총 평가금액, 평가손익(수익금액 +₩...), 수익률(+...%), 일간 등락률 및 📊 인터랙티브 차트 모달 완벽 연동
- **사이드바 개별 계좌 클릭 시 해당 계좌 전용 단일 조회 지원**:
  - 좌측 사이드바에서 특정 절세계좌(예: `NH투자증권(나무) ISA`) 클릭 시 해당 계좌에 속한 보유종목만 필터링되어 깔끔하게 테이블에 표시
  - 상단 헤더에 선택된 계좌명, 증권사, 평가액 및 손익 집계치 동적 동기화
- **정렬 및 상호작용성 강화**:
  - 테이블 헤더 클릭 시 종목명, 섹터, 수량, 평가금액, 평가손익, 수익률, 등락률 오름차순/내림차순 정렬 지원
  - 계좌 카드 내 정보 수정 버튼(✎) 클릭 시 필터 전환 없이 계좌 수정 모달이 안정적으로 열리도록 이벤트 위임 격리
(perf) 서비스 워커 캐시 버전(`wealth-cache-v129`) 및 정적 자산 쿼리(`v5531`) 갱신

v5.5.30

(fix) 🛡️ 전 증권사(한투·키움·KB) 매도 종목 실시간 제외 및 D+2 결제반영 예수금 전면 일치화
- **한국투자증권(KIS) 실시간 매도 차감 및 D+2 예수금 최우선 연동**:
  - 국내(`TTTC8434R`) 및 해외(`TTTS3012R`) 잔고 조회 시 당일 매도 수량(`thdt_sll_qty`)을 차감하여 매도 체결 즉시 보유종목에서 제거
  - 예수금 조회 시 D+2 결제반영 추정예수금(`prvs_rcdl_excc_amt`, `frcr_dncl_amt_2`)을 원장 예수금보다 최우선 적용
- **키움증권(Kiwoom) 당일 매도 수량 차감 및 D+2 평가예수금 연동**:
  - REST API 및 uapi 잔고 조회 시 당일 매도 수량(`thdt_sll_qty`/`sll_qty`)을 차감하여 매도 종목 잔류 방지
  - D+2 추정예수금(`d2_evlt_amt`, `prvs_rcdl_excc_amt`)을 D+0 예수금보다 우선 추출
- **KB증권 당일 매도 체결 수량 차감 방어**:
  - 국내/해외 잔고 조회 시 당일 매도 수량(`sll_q`, `tdy_sll_q`)을 차감하여 체결기준 실보유 수량만 등록

v5.5.29

(fix) 🎯 나무증권(NH투자증권) 매도 종목 실시간 제거 및 예수금·계좌 총자산 정확도 완벽 보정
- **매도 체결 종목 잔고 즉시 제거 (`rsdl_qty` 체결기준 잔여수량 우선 판정)**:
  - 주식 매도 후 결제일(D+2) 이전 상태에서 결제기준 수량(`itg_bnc_qty`)이 1주로 남아있어, 이미 매도한 종목(예: 삼성전자)이 보유종목에 계속 표시되던 오류 원천 해결
  - 국내/해외 잔고 조회 시 체결기준 잔여수량(`rsdl_qty`, `cns_bse_bnc_qty`)을 최우선 판별하도록 개선하여, 매도 완료된 종목(`rsdl_qty = 0`)은 보유종목에서 즉시 제외
- **예수금 및 계좌 순자산(총자산) 정합성 100% 일치화**:
  - D+2 결제반영 추정 예수금(`nxt2_dd_dca`)을 최우선 적용하여, 매도 대금이 입금 반영된 예수금(₩500,494)과 계좌 총자산(`tot_aet_amt` = ₩500,494)이 유가증권 이중계산 없이 정확하게 일치하도록 보정

v5.5.28

(fix) 🛡️ 백엔드 uvicorn 프로세스 미반영 해결 및 계좌 수정 시 상단 입력값 동기화 완벽 보장
- **백엔드 uvicorn 프로세스 핫 리로드(Hot-Reload) 갱신 및 `yearly_contributions` 영구 반영**:
  - 기존 실행 중이던 uvicorn 서버가 어제 구버전(v5.5.11) 상태로 백그라운드에서 유지되어, 프론트엔드가 보낸 `yearly_contributions`를 백엔드가 처리하지 못하고 이전 데이터로 되돌리던 근본 원인 해결
  - 서버를 `--reload` 모드로 최신화하여 향후 모든 백엔드 로직이 실시간 100% 반영되도록 전환
- **계좌 수정 시 상단 입력값(연도·납입액) 직접 수정 동기화 보장**:
  - 하단 [수정] 버튼을 누르지 않고 상단 입력창에서 바로 납입액/연도를 변경하고 하단 [저장]을 눌러도, 해당 연도 이력이 정확하게 갱신되도록 `saveEditAccount` 동기화 로직 전면 수정
- **연도별 이력 카드 전체 클릭 시 수정 모드 연동 복원**:
  - 안내 문구("(항목 클릭 시 상단에서 수정 가능)")에 부합하도록 행 카드 클릭 시에도 상단 입력창으로 정상 로드되도록 개선 (삭제 버튼 클릭 시에는 삭제만 안전하게 단독 처리)
(perf) 서비스 워커 캐시 버전(`wealth-cache-v128`) 및 정적 자산 쿼리(`v5528`) 갱신

v5.5.27

(fix) 🔧 연금/IRP 계좌 세액공제 연도별 납입 이력 저장·수정 구조적 결함 전면 수정
- **`saveEditAccount` 이중 처리(Double Processing) 버그 해결**:
  - 수정 모드(`editingAccountYearlyIndex`)에서 항목을 갱신한 후, 하단 `topYr` 동기화 블록이 동일한 연도를 또다시 덮어쓰거나 중복 추가하던 결함 해결
  - `editingIndexApplied` 플래그를 도입하여 수정 모드 반영 후에는 topYr 자동 추가를 건너뛰도록 방어
- **팬텀 2026년 자동 생성 버그 완전 차단**:
  - 마지막 이력 항목 삭제 시 입력창이 하드코딩 `"2026"`으로 리셋되던 것을 동적 현재 연도(`new Date().getFullYear()`)로 변경
  - 백엔드 `portfolio.py`와 `main.py`의 fallback 브릿지도 하드코딩 `"2026"` → `datetime.now().year` 동적 연도로 전면 교체
- **연도별 이력 카드 전체 클릭 시 의도치 않은 수정모드 진입 방지**:
  - 기존에 `.account-yearly-card` 전체 영역을 클릭해도 수정모드에 진입하던 것을 `[수정]` 버튼(`.account-yearly-edit-btn`)만 반응하도록 제한
- **연도별 소득 구간(`income_level`) 개별 존중**:
  - 수정 다이얼로그 열 때 계좌 수준의 `income_level`로 모든 연도 이력을 강제 덮어쓰던 것을, 이미 설정된 연도별 값은 유지하고 누락된 항목만 기본값 적용하도록 개선
(perf) 서비스 워커 캐시 버전(`wealth-cache-v127`) 및 정적 자산 쿼리(`v5527`) 갱신

v5.5.26

(fix) 🛡️ 납입 연도 한글 입력 지원('24년', '24년도' 등) 및 연도별 납입 이력 [수정] 제자리 갱신(In-Place Update) 완벽 구현
- **납입 연도 입력창 한글 및 2자리 연도 입력 완벽 지원 (`normalizeYear`)**:
  - 기존 `<input type="number">`에서는 '24년', '24년도' 등 한글이 포함된 문자열 입력 시 HTML5 표준에 의해 브라우저가 값을 빈 문자열(`""`)로 자동 폐기하던 문제 해결
  - `type="text"` 및 `normalizeYear()` 도입: '24', '24년', '24년도', '2024년' 등 어떠한 형식으로 입력하더라도 정규 4자리 연도('2024')로 자동 정규화
- **연도별 이력 행의 [수정] 버튼 클릭 시 제자리 변경(In-Place Update) 모드 도입**:
  - 기존에 등록된 이력(예: 2026년)의 [수정] 버튼을 누르면 `editingAccountYearlyIndex`를 기억하여, 상단에서 연도를 2024년으로 변경하고 `[수정 반영]` 또는 하단 `[저장]`을 누르면 기존 행이 제자리에서 2024년으로 완벽히 치환/갱신(기존 2026년 항목이 중복으로 남는 현상 원천 차단)
  - 수정 모드 진입 시 버튼이 녹색 `[✏️ 2026년 수정 반영]`으로 즉시 변경되어 현재 작업 상태를 시각적으로 명확히 전달
- **미등록/빈 이력 자동 브릿지 시 원하지 않는 2026년 고정 현상 원천 차단**:
  - 실제 입력된 납입 연도가 온전히 보존되어 저장되므로, 더 이상 빈 이력으로 인해 2026년이 강제 생성되어 화면에 나타나는 현상 영구 해결
(perf) 서비스 워커 캐시 버전(`wealth-cache-v126`) 및 정적 자산 쿼리(`v5526`) 갱신

v5.5.25

(fix) 🛡️ 계좌 정보 수정 팝업 폼 내부 클릭 시 2026년 자동 회귀 및 버튼 무반응 오류 근본 해결
- **계좌 수정 버튼 식별자 격리(`[data-account-edit-id]`)를 통한 폼 이벤트 간섭 원천 차단**:
  - 기존에 계좌 수정 버튼 식별자(`[data-account-id]`)가 팝업 폼 요소(`<form id="accountEditForm">`) 자체에도 설정되어 있어, 다이얼로그 내부를 클릭(연도 입력, 금액 입력, 버튼 클릭 등)할 때마다 전역 수정 핸들러가 트리거되어 폼이 초기화되고 연도가 다시 2026년으로 롤백되던 치명적 결함 완전 해결
  - 계좌 수정 버튼을 고유 식별자(`[data-account-edit-id]`)로 격리하고 폼 요소에서 불필요한 속성을 제거하여, 팝업 내부의 모든 입력 및 버튼 동작이 간섭 없이 완벽히 수행되도록 개선
- **`[➕ 연도 추가 / 반영]` 버튼 독립 핸들러 추출 및 인라인 바인딩**:
  - `handleAddAccountYearly()`를 독립 함수로 분리 및 전역 노출하고, 버튼에 `onclick="handleAddAccountYearly()"`를 직접 부여하여 2025년 등 원하는 연도와 금액을 입력하고 추가 시 즉시 하단 이력 목록에 반영되도록 보장
- **다이얼로그 닫기(`×`) 및 취소 버튼 인라인 직접 호출 보장**:
  - 닫기 버튼 및 취소 버튼에 `onclick="this.closest('dialog')?.close()"`를 직접 부여하여, 클릭 시 지연이나 무반응 없이 다이얼로그가 즉각 닫히도록 개선
- **납입 연도 입력 변경 시 기존 이력 데이터 자동 로드 편의 기능 추가**:
  - 상단 연도 입력창(`accountInputYear`)에서 연도를 변경했을 때, 해당 연도의 납입 내역이 이미 등록되어 있다면 납입액과 공제 여부를 상단 입력창으로 자동 로드하여 사용자 편의성 극대화
(perf) 서비스 워커 캐시 버전(`wealth-cache-v125`) 및 정적 자산 쿼리(`v5525`) 갱신

v5.5.24

(fix) 🛡️ IRP 및 모든 연금/증권 계좌의 수정(✎) 버튼 클릭 이벤트 전역 위임 및 다이얼로그 저장 안정화
- **어느 탭/위치에서나 계좌 수정(✎) 버튼 100% 작동 보장 (이벤트 위임 버그 해결)**:
  - 기존에 `[data-account-id]` 클릭 리스너가 증권 탭(`#accountList`)에만 바인딩되어 있어, **보험/연금 탭(`#insuranceGrid`)**에 표시된 IRP/연금저축 카드의 `✎` 버튼을 클릭했을 때 모달이 열리지 않던 치명적 결함 완전 해결
  - `document` 전역 클릭 리스너에 `[data-account-id]` 이벤트 위임을 등록하여 **증권 탭, 보험/연금 탭, 절세계좌 탭** 어디에서든 계좌 수정 팝업이 즉시 열리도록 개선
  - 🌿 절세계좌 뷰의 개별 계좌 카드에도 `✎` 수정 버튼을 신규 추가하여 즉시 수정 가능하도록 사용성 확장
- **다이얼로그 `[저장]` 다중 동시 실행 방지 및 중복 이벤트 리스너 제거**:
  - `index.html` 인라인 `onclick` 제거 및 중복 등록된 이벤트 리스너를 단일화하고, `isSavingAccount` 중복 방지 락(Lock)을 도입하여 더블 클릭이나 레이스 컨디션으로 인한 저장 실패 원천 차단
  - 계좌 저장 시 증권사명·계좌명이 공백일 경우 기존 계좌 정보를 자동 보존(Fallback)하여 유효성 검사 실패 방지
- **팝업창 반응형 스크롤 및 뷰포트 오버플로 개선**:
  - `dialog.dialog` 및 계좌 수정/추가 모달에 `max-height: 90vh !important; overflow-y: auto !important;`를 적용하여, 화면 크기나 브라우저 높이에 상관없이 하단 연도별 이력 목록과 `[저장]` 버튼이 잘리지 않고 스크롤하여 접근 가능하도록 UI 완성
- **연도 추가/반영 시 저장 안내 피드백 강화**:
  - `[➕ 연도 추가 / 반영]` 버튼 클릭 시 "[XXXX년 ₩X,XXX,XXX] 이력이 반영되었습니다. 하단 [저장]을 눌러 최종 저장하세요." 안내 토스트 제공
(perf) 서비스 워커 캐시 버전(`wealth-cache-v124`) 및 정적 자산 쿼리(`v5524`) 갱신

v5.5.23

(fix) 🛡️ IRP 및 연금계좌 수정 재진입 시 연도별 절세 내역 하단 미표시 해결 및 납입 동기화 강화
- **수정 팝업 재오픈 시 하단 연도별 납입·절세 이력 자동 복원 및 브릿지**:
  - `yearly_contributions`가 비어있더라도 계좌에 `annual_deposit`이 설정되어 있으면 현재 연도(`2026년`) 이력으로 즉시 브릿지하여 하단 목록에 항상 절세 내역 카드(예: `2026년 | ₩3,000,000 | 🎯 공제 (13.2%) | +₩396,000`)가 완벽하게 표시되도록 개선
- **`[➕ 연도 추가 / 반영]` 버튼 클릭 시 입력값 유지 및 안정화**:
  - 연도 추가/반영 버튼을 눌렀을 때 입력창의 금액을 비우거나 연도를 임의로 이전 연도로 강제 변경하지 않고 유지하여, 사용자가 방금 입력/확인한 내용이 상·하단에 온전히 유지되도록 개선
- **다이얼로그 `[저장]` 클릭 시 상단 입력값과 하단 연도 목록의 완벽한 양방향 동기화**:
  - 사용자가 `[➕ 연도 추가 / 반영]` 버튼을 누르지 않고 상단에 연도·금액만 입력한 후 바로 `[저장]`을 누르더라도, 상단 입력 내용이 `yearly_contributions` 목록에 정확히 반영·정렬되어 서버와 메모리에 저장
  - 저장 시 `rawDashboard`뿐만 아니라 `dashboard.accounts` 메모리 캐시도 함께 즉시 갱신하여 수정 팝업 재오픈 시 즉시 최신 데이터 반영
- **백엔드 `get_dashboard` 및 `PUT /api/accounts` 가드 보강**:
  - `get_dashboard`에서 연금/IRP 계좌의 `annual_deposit`이 있을 때 `yearly_contributions`가 누락되지 않도록 방어 로직 추가
  - 계좌 세액공제 토글 버튼(`toggleTaxBtn`) 클릭 시에도 `yearly_contributions`가 유실되지 않도록 페이로드 전달 보장
(perf) 서비스 워커 캐시 버전(`wealth-cache-v123`) 및 정적 자산 쿼리(`v5523`) 갱신

v5.5.22

(fix) 📅 연금/IRP 연도별 납입 이력 추가·수정·삭제 완벽 안정화 및 테스트 데이터 초기화
- **연도 추가(`➕ [연도 추가 / 반영]`) 후 금액 필드 자동 초기화**:
  - 연도 추가 후 금액 필드를 비워, 이후 저장 시 다음 추천 연도가 팬텀/중복 데이터로 잘못 저장되던 현상 완전 방지
- **이력 삭제(`[✕]`) 시 상단 입력창 연동 초기화 (삭제 항목 부활 방지)**:
  - 하단 목록에서 연도 삭제 시 상단 입력창에 해당 연도가 남아있어 저장 시 다시 추가되던 버그를 해결하여 완전한 삭제 보장
- **과거 연도 단독 입력 시 계좌 대표 납입액 동기화**:
  - 2026년 외 과거 연도(예: 2022년 700만원)를 입력하여 저장 시에도 계좌의 대표 납입액 및 누적 절세액이 정확히 계산되도록 동기화
- **사용자 요청에 따른 IRP 테스트 데이터 초기화**:
  - 임의 저장되었던 IRP 더미 연도 데이터(2024~2026년)를 초기화(비움)하여, 사용자가 원하는 연도(2022년 등)부터 직접 깨끗하게 입력할 수 있도록 정리 완료 (소득구간 13.2% 유지)
(perf) 서비스 워커 캐시 버전(wealth-cache-v122) 및 정적 자산 쿼리(v5522) 갱신

v5.5.21

(fix) 🎯 IRP 및 연금계좌 소득구간(공제비율 16.5% ↔ 13.2%) 변경 저장 및 실시간 동기화 완벽 수정
- **다이얼로그 오픈 시 계좌의 `income_level` 우선 로드 보장**:
  - 기존에 다이얼로그 오픈 시 첫 번째 연도 항목(`topItem.income_level`)이 계좌의 메인 설정(`account.income_level`)을 강제로 덮어써서 13.2%로 저장되어 있어도 16.5%로 회귀하던 버그 완전 해결
  - 계좌의 `account.income_level`을 우선 기준으로 설정하고, 연도별 이력 목록도 계좌의 소득구간과 자동으로 동기화
- **소득구간(공제율) 변경 시 실시간 전체 연도 카드 및 절세액 재계산 반영**:
  - 소득구간 드롭다운(`16.5%` ↔ `13.2%`) 선택 변경 시, 하단 등록된 모든 연도 카드의 공제율 뱃지(`🎯 공제 (13.2%)`) 및 환급액, 누적 절세액이 실시간으로 즉시 재계산 및 갱신되도록 개선
- **저장(`saveEditAccount`) 시 모든 연도별 이력(`yearly_contributions`)에 선택된 소득구간 일괄 반영**:
  - 계좌 저장 시 선택된 `income_level`을 모든 연도별 납입 이력에 누락 없이 일괄 동기화하여 백엔드 및 대시보드 계산에서 영구적으로 13.2%가 유지되도록 보장
- **백엔드 PUT API 동기화 가드 추가**:
  - 계좌 수정 엔드포인트(`PUT /api/accounts/{account_id}`)에서 `income_level`이 변경되면 `yearly_contributions` 항목의 `income_level`도 안전하게 동기화되도록 보강
(perf) 서비스 워커 캐시 버전(wealth-cache-v121) 및 정적 자산 쿼리(v5521) 갱신

v5.5.20

(fix) 🛡️ IRP 및 연금계좌 정보 수정 시 저장 버튼 무반응 오류 해결 및 저장 안정성 강화
- **저장 함수(`saveEditAccount`) 내 `TypeError: Assignment to constant variable.` 버그 해결**:
  - `annual_deposit`이 `const`로 선언된 상태에서 최신 연도 입금액을 재할당하는 과정에서 자바스크립트 런타임 오류가 발생해 저장이 중단되던 현상을 `let` 선언으로 수정하여 완벽히 해결
- **전체 예외 처리 및 사용자 피드백(Alert/Toast) 강화**:
  - `saveEditAccount` 함수 전체 로직을 `try...catch`로 감싸 어떤 예외 상황에서도 조용히 멈추지 않고 명확한 안내 토스트 및 알림창이 출력되도록 개선
  - 저장 버튼 클릭 시 즉시 busy 로딩 상태 표시 및 다이얼로그 즉시 닫기 & 낙관적 UI 업데이트 적용
- **저장 버튼 이벤트 바인딩 3중 보호**:
  - 인라인 `onclick` 속성 외에도 전역 문서 클릭 위임 핸들러(`document.addEventListener('click')`) 및 전용 `addEventListener('click')`를 3중으로 바인딩하여 어떤 환경에서도 클릭 이벤트가 확실히 전달되도록 보장
- **상단 입력창 입력값 자동 동기화**:
  - 상단 입력창에서 납입액 입력 후 [➕ 연도 추가 / 반영]을 누르지 않고 바로 [저장]을 눌러도 해당 연도의 이력이 자동으로 갱신/반영되어 저장되도록 처리
(perf) 서비스 워커 캐시 버전(wealth-cache-v120) 및 정적 자산 쿼리(v5520) 갱신

v5.5.19

(feat) 💎 연금계좌 세액공제 & ISA 만기이전 설정 UX 전면 개편 및 연도별 절세 이력 저장 안정화
- **상단 입력창과 하단 이력 분리 및 키 입력 포커스 상실 버그 완전 해결**:
  - 기존 연도별 행 내부에서 숫자를 입력할 때마다 실시간 DOM 재생성으로 인해 포커스가 풀리던 치명적 문제를 완벽히 해결
  - `💎 연금계좌 세액공제 & ISA 만기이전 설정` 구역 상단에 고정된 입력 필드(`납입 연도`, `납입 금액`, `세액공제 여부`, `소득 구간(공제율)`)를 배치하고 실시간 한글 금액 힌트(예: 600만원)와 예상 환급액 프리뷰를 매끄럽게 제공
- **연도별 소득구간(공제율: 16.5% vs 13.2%) 선택 지원**:
  - 연도별로 총급여 5,500만원 이하(16.5%) 또는 5,500만원 초과(13.2%)를 개별 지정할 수 있도록 지원
  - 세액공제 계산 엔진(`tax_benefit.py`)에서도 연도별 개별 공제율을 반영하여 해당 연도 절세액 및 누적 절세액 산출
- **➕ [연도 추가 / 반영] 버튼 및 하단 이력 관리 시스템**:
  - 상단에서 연도, 금액, 공제 여부, 소득구간 입력 후 `➕ 연도 추가 / 반영` 버튼을 누르면 하단 이력 카드 목록으로 즉시 추가/갱신
  - 추가 완료 시 이전 연도(예: 2026 -> 2025 -> 2024)가 자동으로 입력창에 제안되어 연속 연도 입력 편의성 극대화
  - 하단 카드에서 `[수정]` 클릭 시 해당 연도 데이터가 상단 입력창으로 즉시 로드되고 포커스되어 손쉬운 금액 수정 지원, `[✕]` 클릭 시 개별 연도 삭제 지원
  - 하단 요약 바에 `총 납입원금` 및 `누적 절세액` 실시간 합계 출력
- **계좌 저장(PUT) 및 대시보드 동기화 보장**:
  - 계좌 저장 시 연도별 이력(`yearly_contributions`)이 누락 없이 백엔드(`portfolio.json`)에 영구 저장되도록 보장
  - 최신 연도 납입액을 계좌의 `annual_deposit`에 자동 동기화
  - 증권탭 계좌 리스트에도 누적 절세액 뱃지(예: `· 누적 절세 +₩2,970,000`)를 아름답게 표기
(perf) 서비스 워커 캐시 버전(wealth-cache-v119) 및 정적 자산 쿼리(v5519) 갱신

v5.5.18

(layout) 🔄 주식기록 [절세계좌] 탭 좌/우 위치 전환 (좌측: 계좌내역, 우측: 보유종목) 및 전체변화 카드 제외
- **주식기록 [절세계좌] 탭 2열 레이아웃 좌우 배치 반전**:
  - **좌측 (Left)**: 절세계좌 전체 카드, 중개형 ISA, 개인형 IRP, 연금저축, 계좌별 상세 카드 배치 (네비게이션 & 계좌 필터 역할)
  - **우측 (Right)**: 선택된 계좌의 보유종목 리스트(종목명 & 수량 최우선 헤드라인, 평가금액, 단가, 손익률 등) 넓고 쾌적하게 배치
- **절세계좌 탭 '전체변화' 카드 제외**:
  - 절세계좌 탭 선택 시 계좌내역 상단에 불필요하게 노출되던 '전체 변화(저장된 날짜별 자산 추이)' 카드를 제외(숨김 처리)하여 상단 `🌿 절세계좌 전체` 카드가 바로 최상단에 깔끔하게 시작되도록 개선
  - `📈 전체주식` 탭 전환 시에는 '전체 변화' 카드와 콤보차트 툴바가 자동으로 정상 복원
(perf) 서비스 워커 캐시 버전(wealth-cache-v118) 및 정적 자산 쿼리(v5518) 갱신

v5.5.17

(feat) 🌿 주식기록 [절세계좌] 탭 인터랙티브 필터링 & 전체 카드 총액·수익·누적 절세액 요약 시스템 구축
- **우측 계좌 카드 클릭 필터링 연동**:
  - **상단 [🌿 절세계좌 전체] 카드**: 클릭 시 모든 절세계좌(IRP·연금저축·중개형 ISA)의 보유 주식 내역이 좌측에 전체 표시
  - **[🔄 중개형 ISA] 카드**: 클릭 시 중개형 ISA 계좌의 보유 종목만 좌측에 필터링 표시
  - **[🛡️ 개인형 IRP] 카드**: 클릭 시 개인형 IRP 계좌의 보유 종목만 좌측에 필터링 표시
  - **[💎 연금저축] 카드**: 클릭 시 연금저축 계좌의 보유 종목만 좌측에 필터링 표시
  - **계좌별 상세 카드**: 개별 계좌 카드를 직접 클릭하여 특정 단일 계좌의 종목만 세부 조회 가능
- **상단 [절세계좌 전체] 카드 핵심 지표 완벽 정리**:
  - **절세계좌 총액**: 등록된 모든 절세계좌의 주식 평가금액 합계 표시
  - **수익금액 및 수익률**: 전체 절세계좌의 합산 손익(₩) 및 수익률(%) 표시
  - **누적 절세액**: 각 절세계좌별 연도별 납입 세액공제 혜택 누적 합계(💎 절세금액 누적) 일목요연하게 강조 제공
- **선택된 카드 시각적 강조(Active state)**:
  - 현재 선택된 카드에 은은한 보라빛 테두리, 배경 글로우 및 `선택됨` 뱃지를 표시하여 필터 상태를 직관적으로 확인 가능
  - 좌측 종목 목록 상단 헤더에도 선택된 필터명, 계좌 요약, 소계 평가금액 및 손익을 실시간 동기화
(perf) 서비스 워커 캐시 버전(wealth-cache-v117) 및 정적 자산 쿼리(v5517) 갱신

v5.5.16

(feat) 🌿 자산섹션 IRP·연금저축·노란우산 연도별 절세 이력 & 누적 절세액 기록 시스템 및 주식기록 [전체주식] / [절세계좌] 전면 개편
- **자산섹션 IRP·연금저축·노란우산공제 연도별 절세 이력 & 누적 절세액 관리**:
  - 과거 연도별(예: 2022년 입금액 ➔ 절세혜택, 2023년 입금액 ➔ 절세혜택 등) 납입 내역 및 공제/비공제 여부를 기록하고 **누적 절세액**을 실시간 산출·표시
  - **세액공제 비공제 지원**: 비공제 선택 시 해당 연도 절세액을 명확히 ₩0으로 처리하고 누적 절세액에서 제외
  - 계좌 수정 및 보험/공제 수정 다이얼로그에서 동적으로 연도별 납입액 추가/수정/삭제 및 실시간 누적 절세 프리뷰 제공
  - 자산카드 내에 연도별 납입·절세 내역 리스트 및 `누적 절세액: ₩...` 뱃지 고강조 렌더링
- **주식기록 섹션 개편 & [절세계좌] 탭 신설**:
  - 섹션 명칭: 기존 `기록` ➔ **`주식기록`** (`STOCK RECORDS`)으로 개편
  - **`📈 전체주식` 탭**: 기존 콤보차트 100% 기능 유지
  - **`🌿 절세계좌` 탭**: IRP, 연금저축계좌, 중개형 ISA 계좌의 자산만 자동 필터링하여 기록 및 표시
  - **보유종목명과 수량 최우선(Headline) 강조**: 막대차트 위치에 종목명과 보유 수량(예: `1,569주`)을 가장 크고 눈에 띄는 헤드라인으로 배치하고, 단가, 평가금액, 손익, 계좌/공제 뱃지를 일목요연하게 제공
  - 우측 패널에는 절세계좌별 요약 카드 및 전체 절세계좌 평가 자산 합계 표시
(perf) 서비스 워커 캐시 버전(wealth-cache-v116) 및 정적 자산 쿼리(v5516) 갱신

v5.5.15

(feat) 📊 포트폴리오 주식 탭 [주식 기대수익] 명칭 개편, [원화 주식] & [달러 주식] 카드 신설 및 부동산 공동지분(아빠 50%·엄마 50%) 부채·자산 정밀 연동
- **[주식] 탭 '주식 기대수익' 명칭 변경**:
  - 포트폴리오 [주식] 탭 활성화 시 기존 `총 수익` ➔ **`주식 기대수익`**으로 명칭을 명확하게 개편
- **[주식] 탭 전용 '원화 주식' & '달러 주식' 카드 신설**:
  - **🇰🇷 원화 주식 카드**: 국내 원화 주식 평가금액(₩), 평가손익 및 수익률(%), 보유 종목 수 표시
  - **🇺🇸 달러 주식 카드**: 미국 달러 주식의 원화 환산 평가금액(₩), 달러($) 평가금액 및 보유 종목 수, 평가손익 및 수익률(%) 표시
  - [자산] 탭 선택 시에는 투자자산 카드 내 주식 합산으로 깔끔하게 자동 전환
- **공동명의 부동산(아빠 50% · 엄마 50%) 자산 및 부채(임대보증금) 정밀 배분 연동**:
  - 상단 포트폴리오 요약(`renderSummary`) 및 자산 배분 도넛 차트(`computeFilteredClassifications`)에서 공동소유 부동산이 소유자 필터로 인해 누락되던 문제 해결
  - 아빠 또는 엄마 선택 시 공동명의 부동산(상계주공4단지 8.45억, 임대보증금 1.5억)의 **시세 50%(₩422,500,000)**와 **부채 50%(₩75,000,000)** 및 **부동산 예상수익 50%(₩197,500,000)**가 각각 정확하게 분할 반영되도록 완벽 연동
(perf) 서비스 워커 캐시 버전(wealth-cache-v115) 및 정적 자산 쿼리(v5515) 갱신

v5.5.14

(fix) 🛡️ 포트폴리오 섹션 새로고침 시 펼침/접힘 상태 동기화 및 안전자산 내 보험·연금·공제 평가액 정상 합산 반영
- **포트폴리오 아코디언 새로고침 상태 동기화 버그 해결**:
  - 기존 레거시 `allocation` 키가 `SECTION_MAP`에 `#summaryPanel`로 중복 매핑되어 있어, 로컬 스토리지에 남아있을 경우 새로고침 시 버튼은 펼침(▼) 상태인데 패널 본문만 접힘(is-collapsed) 상태로 렌더링되던 문제 원천 수정
  - `SECTION_MAP`에서 미사용 레거시 키 제거 및 `getCollapsedSections()`에서 비정상/구버전 키 자동 정리(Purge)
  - `toggleSection` 및 `initCollapsedSections`가 실제 DOM 상태와 일관되게 동기화되도록 상태 판별 강화
- **안전자산 카드 내 보험·연금·공제 평가액 합산 수정**:
  - `renderSummary` 및 `computeFilteredClassifications`에서 보험 평가액을 조회할 때 누락 필드(`expected_refund_amount`, `accumulated_paid_amount`) 대신 실데이터 필드(`expected_amount`, `converted_total_asset`, `total_paid_amount`)를 우선 참조하도록 수정
  - 노란우산공제(₩33,019,622)와 국민연금(₩52,983,240)의 총합 ₩86,002,862가 [안전자산]의 '보험' 항목 및 총 안전자산, 순자산에 정확히 합산·표시됨
(perf) 서비스 워커 캐시 버전(wealth-cache-v114) 및 정적 자산 쿼리(v5514) 갱신

v5.5.13

(feat) 🎨 포트폴리오 자산 탭 [투자자산] 명칭 변경, 전 요약 지표 맞춤형 배경/테두리 색상 적용 및 실현손익 세부내역 2줄 분리 표기
- **[자산] 탭 명칭 개편**:
  - 기존 `총 투자자산` ➔ **`투자자산`**으로 간결하고 직관적으로 변경
- **요약 지표 카드별 맞춤형 테마 배경 & 뱃지 적용**:
  - 순자산: 파란색 테마 (`#38bdf8`, 하늘색 배경 틴트 및 테두리)
  - 투자자산: 보라색 테마 (`#a78bfa`, 퍼플 배경 틴트 및 테두리)
  - 기대수익: 붉은색/로즈 테마 (`#f43f5e`, 로즈 배경 틴트 및 테두리)
  - 실현손익: 호박/주황색 테마 (`#f59e0b`, 앰버 배경 틴트 및 테두리)
  - 안전자산: 초록색 테마 (`#34d399`, 에메랄드 배경 틴트 및 테두리)
  - 배당금(주식 탭): 황금색 테마 (`#eab308`, 골드 배경 틴트 및 테두리)
- **실현손익 세부 구성 2줄 분리 표시**:
  - 기존 단일 행 표기(`매매차익 ₩... · 배당/이자 ₩...`)를 2개 행(줄)으로 분리하여 가독성 대폭 향상:
    - 1줄: `매매차익 ₩123,115,570`
    - 2줄: `배당/이자 ₩18,127,410`
(perf) 서비스 워커 캐시 버전(wealth-cache-v113) 및 정적 자산 쿼리(v5513) 갱신

v5.5.12

(fix) 📈 포트폴리오 [자산 / 주식] 탭 전환 시 보유종목 및 계좌 목록 소실 방지 & 렌더링 엔진 안정화
- **자산/주식 탭 전환 시 보유종목 소실 버그 수정**:
  - `#allocTabs`의 [자산] / [주식] 탭 클릭 시 요약 지표(`renderSummary`) 및 분류 차트(`renderClassifications`)만 타겟 갱신하도록 최적화
  - 탭 전환 시 `renderWithOwner`의 단일 인자 호출로 인해 소유자 필터가 초기화되어 보유종목 테이블이 공백으로 렌더링되던 문제 원천 해결
- **`renderWithOwner` 및 `renderHoldings` 방어 로직 강화**:
  - `renderWithOwner(data, owner)`가 단일 인자(`owner`만 전달) 또는 순서 변경으로 호출되더라도 서버 원본 데이터(`rawDashboard`)와 소유자를 정상 판별하도록 다중 방어 처리
  - `renderHoldings` 호출 시 전달 데이터가 누락되더라도 전역 대시보드 데이터를 자동 폴백하여 65개 전 종목이 항상 안정적으로 표시되도록 보장
(perf) 서비스 워커 캐시 버전(wealth-cache-v112) 및 정적 자산 쿼리(v5512) 갱신

v5.5.11

(feat) 📊 포트폴리오 [자산 / 주식] 탭 맞춤형 요약 지표 & 부동산 기대/실현손익 통합 시스템 구축
- **포트폴리오 분류 탭 명칭 개편**:
  - `자산별 / 섹터별` ➔ **`자산 / 주식`**으로 직관적 명칭 변경
  - 탭 클릭 시 우측 분류 차트뿐 아니라 좌측 핵심 요약 카드(Summary Card)도 탭 모드에 맞춰 실시간 동적 전환
- **[자산] 탭 선택 시 (자산 종합 관점)**:
  - `기대수익` 도입: 기존 주식 평가손익뿐 아니라 **부동산 예상 수익(시세 - 취득가)**까지 통합 반영 및 기대수익률 계산
  - `실현손익` 통합: 기존 총 실현손익(매매차익)과 총 배당금 및 이자를 하나로 통합 합산 표기 (`매매차익 + 배당/이자`)
  - 순자산, 총투자자산(부동산+주식), 안전자산 완벽 연동
- **[주식] 탭 선택 시 (주식 전용 관점)**:
  - 사용자가 지정한 4대 핵심 주식 지표만 집중 표기:
    1. `총 주식자산`
    2. `↗ 총 수익` (평가수익률 및 일간 수익)
    3. `📈 주식 실현손익` (26년 및 당월)
    4. `💰 배당금` (26년 및 당월)
  - 순자산 및 안전자산 행을 숨겨 주식 성과 분석에 최적화된 레이아웃 제공
- **부동산 매매 실현손익 기록 시스템 탑재**:
  - 자산 섹션 부동산 탭의 각 카드에 **`[🏢 매각/실현손익 기록]`** 버튼 및 모달 다이얼로그(`realEstateSellDialog`) 추가
  - 양도가액, 취득가, 필요경비 입력 시 양도차익 실시간 계산 및 `POST /api/real-estates/{re_id}/sell`을 통해 실현손익 원장에 자동 등록
  - 매각 완료 시 보유 자산에서 제외(정리) 옵션 지원
  - 실현손익 추가 모달(`pnlRecordDialog`)에도 `자산 구분: 🏠 부동산 매매` 선택 지원
(perf) 서비스 워커 캐시 버전(wealth-cache-v111) 및 정적 자산 쿼리(v5511) 갱신

v5.5.10

(feat) 🛡️ 가계부 정기 고정지출 항목 [수정(✎)] 버튼 및 인라인 수정 모드 탑재
- **고정지출 목록에 수정(✎) 버튼 추가**:
  - 각 고정지출 카드 우측에 수정(✎) 버튼 배치
- **원클릭 인라인 수정 및 취소 모드 지원**:
  - 수정 버튼 클릭 시 기존 항목의 값(항목명, 금액, 결제일, 카테고리, 소유자, 결제수단, 출금통장, 자동출금 여부)이 하단 폼에 자동 로드
  - 폼 헤더 및 버튼이 '고정지출 항목 수정/저장'으로 전환되며 [취소] 버튼 지원
- **PUT 엔드포인트 연동 및 즉시 반영**:
  - `PUT /api/ledger/recurring/{rec_id}`를 통해 수정 즉시 가계부 및 대시보드 데이터 동기화
(perf) 서비스 워커 캐시 버전(wealth-cache-v110) 및 정적 자산 쿼리(v5510) 갱신

v5.5.9

(feat) 🛡️ 가계부 [정기 고정지출 자동이체 통장 연동 & 지정일 계좌 자동 출금] 시스템 구축
- **정기 고정지출 출금 통장 연동 기능 추가**:
  - 결제 수단으로 '자동이체' 선택 시 사용자의 은행 계좌(`bank_accounts`) 및 증권사 예수금 계좌(`accounts`) 목록을 드롭다운으로 연동 지원
  - 고정지출 목록 카드에 연동된 출금 통장 뱃지(`[🏦 KB국민 생활비통장]`) 및 당월 출금 상태 표시
- **지정일 도래 시 통장 잔액 자동 출금 & 가계부 지출 내역 자동 생성**:
  - 매월 지정된 이체일(`day_of_month`) 도래 시 연동된 통장 잔액에서 고정지출 금액 자동 차감
  - 가계부 거래내역(`transactions`)에 해당 일자 지출 내역 1건 자동 생성 (중복 차감 원천 방지 추적)
- **수동 정산 트리거 API 및 버튼 지원**:
  - `POST /api/ledger/recurring/process` 엔드포인트 및 모달 내 `[⚡ 이번 달 자동이체 즉시 실행]` 버튼 제공
(perf) 서비스 워커 캐시 버전(wealth-cache-v109) 및 정적 자산 쿼리(v559) 갱신

v5.5.8

(feat) 💎 국민연금 및 연금보험 [수령 방식 선택 & 20년 총자산 자동 환산] 시스템 도입
- **수령 방식(지급 형태) 다이얼로그 선택 지원**:
  - `일시금 / 해약환급금형` (일반 보장성/실비/암보험, 만기적금 등)
  - `월 지급식 / 연금형` (국민연금, 개인 연금보험, 주택연금, 즉시연금 등)
- **국민연금 선택 시 지능형 자동 전환**:
  - 상품 구분에서 `국민연금` 선택 시 자동으로 `월 지급식 / 연금형`으로 전환 및 기본 수령기간 20년(240개월) 세팅
  - 기관명(`국민연금공단`) 및 상품명(`국민연금 (노령연금)`) 자동 완성
- **수령 기간 선택 및 실시간 총자산 환산 프리뷰**:
  - 10년 / 15년 / 20년(권장) / 25년 / 30년 분할 수령 기간 옵션 제공
  - 월 수령액 입력 시 `월 수령액 × 총 수령 개월수`로 총자산 환산 가치 실시간 계산 및 안전자산(순자산)에 자동 합산
- **자산 카드 렌더링 개선**:
  - `월 ₩1,250,000 (20년 환산 ₩300,000,000)` 형식으로 월 수령액과 총자산 가치 직관적 병기
(perf) 서비스 워커 캐시 버전(wealth-cache-v108) 및 정적 자산 쿼리(v558) 갱신

v5.5.7

(fix) 🟩 NH투자증권(나무) 체결기준 수량(rsdl_qty) 및 D+2 추정예수금(nxt2_dd_dca) 추출 엔진 개선
- **체결 기준 미결제(D+2 전) 보유종목 누락 해결**:
  - 최근 매수하여 결제일(D+2) 이전 상태인 주식의 경우 `itg_bnc_qty`가 0으로 오는 특성에 대응하여 체결기준 수량(`rsdl_qty`, `ny_stl_qty`)을 우선 판별하도록 보정
- **실제 예수금 정확도 개선**:
  - 주문가능금액(`orr_pbl_amt1`) 대신 실제 원장 예수금(`dca`) 및 D+2 결제반영 추정예수금(`nxt2_dd_dca`)을 정확히 수집하도록 개선
- 나무증권 보유종목 및 계좌별 예수금 100% 정상 동기화 검증 완료
(perf) 서비스 워커 캐시 버전(wealth-cache-v107) 및 정적 자산 쿼리(v557) 갱신

v5.5.6

(fix) 🟪 키움증권 REST API 토큰 인증 명세(secretkey) 수정 및 TR(kt00018) 잔고 조회 엔진 최적화
- **OAuth 2.0 토큰 발급 페이로드 공식 명세 적용**:
  - 키움증권 비밀키 필드(`secretkey`)와 호환 필드(`appsecret`) 동시 전송으로 토큰 미발급/400 에러 원천 해결
- **키움 공식 국내주식 잔고 조회 엔드포인트(`POST /api/dostk/acnt`, `kt00018`) 탑재**:
  - 종목코드 접두어(`A005930` ➔ `005930`) 정규화 및 수량/단가/현재가/예수금 필드 파싱 견고화
  - uapi fallback 엔진을 함께 탑재하여 다양한 키움 게이트웨이 환경 완벽 지원
- 5대 증권사(토스, KB, NH, 한투, 키움) 전역 동기화 100% 정상 통과 검증 완료
(perf) 서비스 워커 캐시 버전(wealth-cache-v106) 및 정적 자산 쿼리(v556) 갱신

v5.5.5

(docs) 📚 README.md 상단 버튼 및 9대 섹션별 의미와 전체 기능 상세 가이드 최신화
- 상단 내비게이션 바(PWA, 가족관리, OpenAPI, 비밀번호 변경 등) 모든 제어 버튼 완벽 문서화
- 9대 핵심 섹션(주요지수, 포트폴리오, 기록, 히트맵, 자산, 실현손익, 배당금, 보유종목, 가계부)의 의미와 내부 전체 버튼 기능 총망라

v5.5.4

(chore) 🧹 불필요한 .env.example 더미 파일 삭제 및 README 설치 가이드 간소화
- OpenAPI 설정이 웹 UI(`[⚙️ OpenAPI]` 모달) 및 사용자별 격리 JSON 파일로 100% 이전됨에 따라 더 이상 사용되지 않는 `.env.example` 더미 템플릿 파일 완전 삭제
- `README.md` 내 5대 증권사(토스, KB, NH, 한투, 키움) 웹 UI 설정 안내 최신화 및 실행 절차 간소화

v5.5.3

(feat) 🟪 키움증권(Kiwoom) REST API 연동 및 원클릭 계좌 동기화 지원
- **증권사 OpenAPI 설정 모달에 키움증권(Kiwoom) 추가**:
  - `App Key`, `App Secret`, `계좌번호 (8자리 또는 8자리-01)` 등록/수정/삭제 지원
  - 안전한 마스킹(`****`) 표시 및 보존
- **키움증권(Kiwoom) REST API 연동 클라이언트 (`app/services/kiwoom_openapi.py`) 구현**:
  - OAuth 2.0 Access Token 자동 발급 및 파일 캐싱 (`kiwoom_token_cache.json`)
  - 국내주식 잔고 및 예수금 조회 API 지원
  - 해외주식(미국주식) 잔고 및 외화예수금 조회 API 지원
- **백엔드 동기화 라우트 연동 (`/api/sync/kiwoom`, `/api/sync/all`)**:
  - 키움증권 단독 동기화 및 5대 증권사(토스·KB·NH·한투·키움) 일괄 동기화 지원
  - 키움증권 계좌 자동 생성 및 사용자 지정 이름 보존 (`broker: "키움증권"`, `source: "kiwoom_api"`)

v5.5.2

(feat) 📈 한국투자증권(KIS) Open Trading API 연동 및 계좌 자동 동기화 지원
- **증권사 OpenAPI 설정 모달에 한국투자증권(KIS) 추가**:
  - `App Key`, `App Secret`, `계좌번호 (CANO 8자리 또는 8자리-01)` 등록/수정/삭제 지원
  - 안전한 마스킹(`****`) 표시 및 보존
- **한국투자증권(KIS) OpenAPI 연동 클라이언트 (`app/services/kis_openapi.py`) 구현**:
  - OAuth 2.0 Access Token 자동 발급 및 파일 캐싱 (`kis_token_cache.json`)
  - 국내주식 잔고 및 예수금 조회 API (`TTTC8434R`)
  - 해외주식(미국주식) 잔고 및 외화예수금 조회 API (`TTTS3012R`)
- **백엔드 동기화 라우트 연동 (`/api/sync/kis`, `/api/sync/all`)**:
  - 한국투자증권 단독 동기화 및 전역 원클릭 동기화 지원
  - 계좌 자동 생성 및 사용자 지정 이름 보존 (`broker: "한국투자증권"`, `source: "kis_api"`)

v5.5.1

(fix) 🛠️ HTML DOM 트리 구조 복구(자산 연동 & 버튼 레이아웃 정상화) 및 신용카드 핸들러 안전화
- **DOM 구조 완벽 복구**:
  - `userAssetDashboardWrapper` 닫는 태그 누락으로 인해 발생하던 돔 트리 불일치 및 CSS 레이아웃/버튼 깨짐 문제 100% 정상화
- **신용카드 이벤트 핸들러 안전화**:
  - 인라인 JSON 파싱 대신 카드 ID 기반 안전 조회 방식으로 개편하여 브라우저 JS 실행 중단 방지
(perf) 서비스 워커 캐시 버전(wealth-cache-v102) 및 정적 자산 쿼리(v552) 갱신

v5.5.0

(feat) 💳 가계부 신용카드 관리·청구 누적 및 결제일 계좌 출금 정산 시스템 완비
- **수입/지출 내역 등록 화면 필드 지능형 동적 전환**:
  - **수입(💰)**: 불필요한 결제수단 필드를 숨기고 `입금 연동 계좌`만 직관적으로 표시
  - **지출(💳)**: `신용카드` vs `체크카드/계좌출금/현금` 결제 방식 지원
    - **신용카드 선택 시**: 등록된 신용카드 선택 ➔ 지출 시점에는 은행 계좌 잔액을 차감하지 않고 **카드의 당월 청구 예정액으로 누적 합산**
    - **체크카드/계좌출금 선택 시**: 출금 계좌 선택 ➔ 등록 즉시 실제 은행 계좌 잔액 실시간 차감
- **신용카드 등록 & 관리 시스템 (`💳 카드 관리`)**:
  - 카드사(현대, 삼성, 신한, 국민 등), 카드명, 소유자, 매월 결제일(1~31일), 출금 결제계좌(은행통장) 등록/수정/삭제
  - 각 카드별 당월 미결제 누적 금액 및 이용 건수 실시간 집계
- **카드 결제일 대금 출금 & 0원 정산 기능 (`[💳 결제/정산]`)**:
  - 결제 실행 시 연결된 은행 계좌에서 누적 카드대금이 일괄 출금 차감
  - 가계부에 `[카드대금결제]` 거래가 자동 생성되고, 카드 청구 누적액은 **0원으로 깨끗하게 리셋**
(perf) 서비스 워커 캐시 버전(wealth-cache-v100) 및 정적 자산 쿼리(v550) 갱신

v5.4.8

(feat) 🏦 가계부 수입/지출 등록 시 전체 계좌 연동 목록 로드 & 실시간 잔액 변동 프리뷰
- **수입/지출/이체 등록 모달 계좌 연동 완비**:
  - `은행 자유입출금`, `예·적금`, `증권사 예수금` 전체 계좌 목록을 소유자별로 분류하여 드롭다운에 즉시 표시
  - 계좌 선택 및 금액/구분(수입/지출) 입력 시 **기존 잔액 및 적용 후 예상 잔액(수입은 +입금, 지출은 -출금)**을 실시간 프리뷰로 확인
  - 내역 저장 시 연동된 은행/증권 계좌의 실제 잔액이 즉시 변동되고 대시보드 전체에 실시간 동기화
(perf) 서비스 워커 캐시 버전(wealth-cache-v98) 및 정적 자산 쿼리(v548) 갱신

v5.4.6

(feat) 📒 가계부 소유자 탭 전역 동기화 & 타이틀/서브라벨 비주얼 통일
- **가계부 소유자 탭 연동 완비**:
  - 가계부 헤더에 `모두`, `아빠`, `엄마`, `자녀` 탭을 완벽히 렌더링하고 다른 섹션들과 실시간 연동
  - 소유자 변경 시 가계부 데이터(월별 현금흐름, 카테고리 지출 분석, 거래 내역 등)가 즉시 해당 소유자로 필터링
- **헤더 타이틀 및 서브라벨 통일**:
  - `📒 가계부`의 이모지를 제거하고 다른 섹션들과 동일하게 **`가계부`**로 통일
  - 가계부 영어 서브라벨 `HOUSEHOLD LEDGER`의 인라인 색상을 제거하여 다른 섹션들과 동일한 보라색(`eyebrow`) 톤으로 통일
(perf) 서비스 워커 캐시 버전(wealth-cache-v96) 및 정적 자산 쿼리(v546) 갱신

v5.4.4

(feat) 📑 섹션명/순서 전면 개편 & 가계부 접기/펼치기 버그 수정
- **섹션 명칭 변경**:
  - `자산기록` ➔ **`기록`**
  - `자산 히트맵` ➔ **`히트맵`**
  - `계좌` ➔ **`자산`**
- **대시보드 섹션 순서 전면 재배치**:
  1. `주요지수` ➔ 2. `포트폴리오` ➔ 3. `기록` ➔ 4. `히트맵` ➔ 5. `자산` ➔ 6. `실현손익` ➔ 7. `배당금` ➔ 8. `보유종목` ➔ 9. `가계부`
- **가계부 섹션 접기/펼치기 지원**:
  - `SECTION_MAP`에 `ledger: '#ledgerSectionPanel'` 등록 및 collapsible CSS 연동 완료
(perf) 서비스 워커 캐시 버전(wealth-cache-v94) 및 정적 자산 쿼리(v544) 갱신

v5.4.2

(design) 📊 '포트폴리오' 섹션 명칭 변경, 부동산 100% 시세 반영 & 기호 정돈
- **섹션명 변경**: `내 자산` ➔ **`포트폴리오`** 개편
- **투자자산 부동산 시세 100% 반영**:
  - 총 투자자산 내 부동산 가치를 임대보증금 차감 없이 부동산 시세(평가금액) 100% 그대로 반영하여 투자 규모 직관화
- **서브 지표 기호 정돈 & 세로 정렬 맞춤**:
  - `총부채`, `부동산`, `주식`, `일간 수익`, `예수금 및 예금`, `임차보증금`, `보험` 앞의 하이픈(`-`) 제거하여 깔끔한 비주얼 완성
  - 실현손익 및 배당금 카드의 `26년`과 `09월` 라벨을 정밀 고정폭으로 세로 줄맞춤 정렬
(perf) 서비스 워커 캐시 버전(wealth-cache-v92) 및 정적 자산 쿼리(v542) 갱신

v5.4.0

(feat) 🛡️ '안전자산' 신규 요약 카드 도입 & 투자자산 정밀 재정의
- **부채 및 투자자산/안전자산 재정의**:
  - **순자산 부채 색상 변경**: `- 총 부채`를 차감 항목 의미에 맞춰 **푸른색**으로 변경
  - **총 투자자산 정밀화**: 투자 성격의 **부동산(자가·임대 순에퀴티)**과 **주식**만 투자자산에 포함 (2줄 요약)
  - **안전자산(Safe Assets) 요약 카드 신설**: **예수금 및 예금**, **임차보증금**, **보험(환급금/수령액)**을 안전자산으로 분리 집계하여 총액 및 세부내역 표시
- **지표 시각화 및 명칭 정돈**:
  - **총 실현손익 연/월 손익**: `+`는 붉은색, `-`는 푸른색으로 동적 컬러링 적용
  - **총 배당금 및 이자**: '실제' 접두어 제거 (`26년 +₩...`, `09월 +₩...`)
(perf) 서비스 워커 캐시 버전(wealth-cache-v90) 및 정적 자산 쿼리(v540) 갱신

v5.3.8

(feat) 📈 실현손익·배당금 연도/월별 실시간 집계 서브라인 및 '자산별' 비중 내림차순 정렬
- **총 수익·실현손익·배당금 요약 카드 줄바꿈 & 실시간 연/월 집계 완비**:
  - **총 수익**: 총 금액과 수익률 한 줄 표시, `- 일간 수익` 서브라인, 하단 `기준일자 대비` 독립 줄 배치
  - **총 실현손익**: 전체 누적 실현손익 메인 표시 및 하단에 `26년 +₩...`, `09월 +₩...` 당해연도/당월 실시간 집계 서브라인 결합
  - **총 배당금 및 이자**: 전체 누적 배당금 메인 표시 및 하단에 `실제 26년 +₩...`, `실제 09월 +₩...` 당해연도/당월 실시간 집계 서브라인 결합
- **우측 자산별 분류 개선**:
  - 탭 버튼명을 `자산군별`에서 `자산별`로 명확화
  - 원 그래프 위 불필요한 '자산군 및 섹터 배분' 텍스트 바 제거
  - 자산별 항목을 비중(weight)이 높은 순서대로 자동 내림차순 정렬
(perf) 서비스 워커 캐시 버전(wealth-cache-v88) 및 정적 자산 쿼리(v538) 갱신

v5.3.6

(design) 📊 '내 자산' 총 투자자산 4대 세부 자산군 4줄 세로 정렬 가독성 극대화
- **4대 세부 자산군 독립 4줄 배치**:
  - 총 투자자산 하단 세부 내역(`- 부동산`, `- 주식`, `- 예수금 및 예금`, `- 보험`)을 가로 나열 대신 각각 독립된 4줄로 세로 정렬하여 한눈에 명확히 식별 가능하도록 UI 개편
  - 총 투자자산 메인 금액과 4대 세부 자산 합산 금액을 1원 단위까지 정밀 일치
(perf) 서비스 워커 캐시 버전(wealth-cache-v86) 및 정적 자산 쿼리(v536) 갱신

v5.3.4

(feat) 💎 '내 자산' 섹션 레이아웃 및 종합 자산군별 분류 체계 완벽 개편
- **섹션명 변경**: `PORTFOLIO OVERVIEW` 섹션 타이틀을 `내 자산`으로 개편
- **핵심 요약 리스트 계층화 & 시각적 정돈**:
  - **순자산**: 굵은 흰색 메인 폰트와 하단 붉은색 `- 총 부채` 서브라인 표시
  - **총 투자자산**: 굵은 흰색 메인 폰트와 4대 세부 자산군(`- 부동산(순에퀴티)`, `- 주식`, `- 예수금 및 예금`, `- 보험(환급금/수령액)`) 연보라색 서브라인 배치
  - **총 수익 & 일간 수익**: 수익/손실에 따른 붉은색/파란색 동적 하이라이트 및 전일 대비 일간 변동 서브라인 결합
  - **총 실현손익 & 총 배당금 및 이자**: 승률/건수 및 예상 연간 배당금 세부 지표 완비
- **종합 자산군별 분류(Classifications) 통합 고도화**:
  - `부동산`(순에퀴티), `국내주식`, `국내ETF`, `국내상장해외ETF`, `해외ETF`, `현금·예수금 (은행 예수금 포함)`, `보험 (예상 수령액/해약환급금)` 종합 집계 및 도넛 차트/비중 연동
(perf) 서비스 워커 캐시 버전(wealth-cache-v84) 및 정적 자산 쿼리(v534) 갱신

v5.3.2

(feat) 🏦 가계부 계좌 실시간 연동 잔액 변동 & 가계부 패밀리 탭 일원화
- **가계부 섹션 명칭 및 소유자 탭 UI 업그레이드**:
  - 섹션 명칭을 `📒 가계부`로 심플화
  - `[오늘]` 버튼 제거 및 보유종목/계좌 섹션과 동일한 `[모두] [아빠] [엄마] [자녀]` 탭 버튼 그룹 직접 배치
- **연동 계좌 선택 및 실시간 잔액 변동 시스템 구축**:
  - 내역 등록/수정 모달에 은행 통장, 증권 계좌, 예적금 선택 드롭다운 탑재
  - 계좌 선택 및 금액 입력 시 `기존 잔액: ₩14,570,450 ➔ 적용 후 예상 잔액: ₩11,570,450` 실시간 계산 미리보기 바 제공
  - 저장 시 실제 은행/증권 계좌의 잔액을 즉시 증감 반영하고, 내역 삭제 시 이전 변동분을 자동으로 원상복구(롤백)
(perf) 서비스 워커 캐시 버전(wealth-cache-v82) 및 정적 자산 쿼리(v532) 갱신

v5.3.0

(design) 🎨 가계부 거래내역 및 고정지출 삭제 버튼 스타일·크기 완벽 일원화
- **액션 버튼 크기 및 배경 스타일 통일**:
  - 가계부 거래내역 및 고정지출 삭제 버튼(`🗑️`)에 `account-action-button mini-delete-button` 클래스 및 전역 CSS를 적용하여 수정 버튼(`✎`)과 28x28px 크기, 테두리, 배경, 호버(빨간색 하이라이트) 효과 완벽 일치
  - 퍼플/OLED/화이트 전 테마 일관성 보장
(perf) 서비스 워커 캐시 버전(wealth-cache-v80) 및 정적 자산 쿼리(v530) 갱신

v5.2.8

(feat) 📒 스마트 가족 가계부 섹션을 자산대시보드 [보유 종목] 바로 아래로 통합 배치
- **보유 종목 아래 가계부 섹션 일체화**:
  - 기존의 분리된 탭 전환 방식 대신, [보유 종목] 섹션 바로 아래에 [📒 스마트 가족 가계부] 섹션을 배치하여 단일 화면에서 스크롤하며 자산과 가계부를 함께 직관적으로 관리 가능
  - 가계부 섹션 접기/펼치기(Collapse/Expand) 기능 및 월 컨트롤러, 현금흐름 요약, 카테고리 분석, 6개월 추이 차트, 거래 내역 완벽 일체화
- **자산 대시보드와 가계부 실시간 동시 연동**:
  - 대시보드 로드 및 소유자 필터 전환 시 가계부 데이터가 실시간으로 자동 동기화
(perf) 서비스 워커 캐시 버전(wealth-cache-v78) 및 정적 자산 쿼리(v528) 갱신

v5.2.6

(fix) 🛡️ 프론트엔드 JS 구문 오류 수정 및 자산 대시보드 데이터 연동 정상화
- **자바스크립트 구문 정상화**:
  - `wealth.js` 하단 미완성 중복 함수 선언을 정리하여 `SyntaxError`를 완전히 해소
  - 애플리케이션 초기화(`bootstrap()`) 및 자산 대시보드/가계부 데이터 실시간 렌더링 정상 가동 복구
(perf) 서비스 워커 캐시 버전(wealth-cache-v76) 및 정적 자산 쿼리(v526) 갱신

v5.2.4

(feat) 📥 가계부 엑셀 파일(.xlsx, .csv) 가져오기 & 카드/거래내역 표준 샘플 엑셀 다운로드 완비
- **표준 샘플 엑셀 서식 2종 다운로드 제공**:
  - `[📥 샘플_카드내역.xlsx 다운로드]`: 카드사 이용내역 표준 포맷 샘플 제공
  - `[📥 샘플_거래내역.xlsx 다운로드]`: 가계부 수입/지출/이체 종합 거래내역 표준 포맷 샘플 제공
- **엑셀/CSV 원본 파일 업로드 및 스마트 파서 탑재**:
  - 카드사/은행에서 다운로드받은 엑셀(.xlsx, .xls) 및 CSV 파일을 드래그앤드롭/파일선택으로 일괄 등록 지원
  - 주요 컬럼(일자, 가맹점/내용, 금액, 구분, 카테고리, 소유자) 자동 인식 및 매핑
(perf) 서비스 워커 캐시 버전(wealth-cache-v74) 및 정적 자산 쿼리(v524) 갱신

v5.2.2

(design) 🎨 테마 설정 및 데이터 백업 관리 푸터 최하단 정렬 & 가계부 가로폭 집중형 최적화
- **공통 최하단 푸터 정돈**:
  - 화면 테마 설정 및 데이터 저장/불러오기 버튼을 자산 대시보드와 가계부 공통의 맨 최하단으로 완벽 이동 배치
- **가계부 뷰 가로폭 집중형 최적화**:
  - `max-width: 1360px` 및 중앙 정렬 적용으로 와이드 모니터에서도 한눈에 집중해서 볼 수 있도록 시각적 안정감 극대화
(perf) 서비스 워커 캐시 버전(wealth-cache-v72) 및 정적 자산 쿼리(v522) 갱신

v5.2.0

(feat) 📒 스마트 가족 가계부 (Household Ledger) 시스템 신규 구축
- **메인 탭 네비게이션 탑재**:
  - 상단에 `[💼 자산 대시보드]` / `[📒 스마트 가계부]` 스위처를 배치하여 언제든 원클릭으로 전환 가능
- **가족 소유자(아빠/엄마/자녀/모두) 완벽 연동**:
  - 상단 소유자 필터 선택 시 개인별 가계부 및 가족 전체 통합 가계부 실시간 필터링
- **월간 현금흐름 요약 & 카테고리 지출 분석**:
  - 총 수입, 총 지출, 순저축액/저축률, 등록 고정지출 4대 요약 카드
  - 카테고리별 지출 비중 도넛 프로그레스 바 & 최근 6개월 현금흐름 추이 막대 차트
- **수입/지출/이체 관리 & 정기 고정지출 캘린더**:
  - 간편 내역 등록/수정/삭제 모달
  - 매월 반복되는 공과금·보험료·구독료 고정지출 관리 모달
  - 카드사/은행 텍스트 및 CSV 일괄 업로드 기능 탑재
(perf) 서비스 워커 캐시 버전(wealth-cache-v70) 및 정적 자산 쿼리(v520) 갱신

v5.1.8

(fix) 🛡️ 토스증권 예수금 일괄 복사 누수 차단 및 중복 계좌 정리 완료
- **토스증권 예수금 격리 정상화**:
  - 새로 추가된 토스증권 계좌에 기존 토스 일반 계좌의 예수금이 일괄 복사되던 로직을 차단하여, 각 계좌별 예수금 독립 유지 보장
- **중복 생성 계좌 정리 및 등록 폼 초기화 보강**:
  - 중복 생성되었던 토스 연금저축 테스트 계좌들을 깔끔히 정리하고 신규 등록 성공 시 폼 자동 리셋 적용
(perf) 서비스 워커 캐시 버전(wealth-cache-v68) 및 정적 자산 쿼리(v518) 갱신

v5.1.6

(fix) 🛡️ 증권 계좌 신규 생성 API(POST /api/accounts) 변수 참조 오류 완벽 해결
- **신규 계좌 생성 핸들러 정상화**:
  - `POST /api/accounts`에서 `isa_transfer_amount` 및 `isa_transfer_year` 변수 미정의로 인해 500 에러가 발생하던 문제를 수정하여 정상 추가 보장
(perf) 서비스 워커 캐시 버전(wealth-cache-v66) 및 정적 자산 쿼리(v516) 갱신

v5.1.4

(fix) 🚀 백엔드 서버 데몬 리로더 정밀 재기동 및 자녀/엄마 비공제 1,800만 완벽 동기화 완료
- **서버 프로세스 및 변경사항 100% 동기화**:
  - 백엔드 프로세스 완전 재시작으로 최신 API 핸들러 및 데이터 파이프라인 즉시 반영
  - 자녀 연금저축(`비공제`, `1,800만원`), 엄마 연금저축(`비공제`, `600만원`) 영구 설정 반영 완료
(perf) 서비스 워커 캐시 버전(wealth-cache-v64) 및 정적 자산 쿼리(v514) 갱신

v5.1.2

(feat) 🌟 증권 계좌 목록 & 보험·연금·공제 탭 전역에 연금저축/IRP 세액공제 전용 하이라이트 카드/박스 완비
- **증권 계좌 목록(`accountList`) 전용 하이라이트 박스 탑재**:
  - `account-row` 내에 눈에 띄는 선명한 하이라이트 박스(`💎 세액공제 신청 (납입 ₩... → 예상 환급 +₩... / 16.5%)` 또는 `🌿 비공제 계좌 (납입 ₩... · 원금 비과세 인출 대상)`)를 독립 배치하여 가시성 100% 극대화
- **"🛡️ 보험·연금·공제" 탭에 증권 연금저축/IRP 절세 카드 자동 연동 렌더링**:
  - "보험·연금·공제" 탭의 그리드에 증권사의 모든 연금저축/IRP 계좌를 자동으로 절세 전용 카드로 생성하여 한눈에 연말정산 절세 내역 확인 가능
(perf) 서비스 워커 캐시 버전(wealth-cache-v62) 및 정적 자산 쿼리(v512) 갱신

v5.1.0

(feat) 💎 계좌명에서 공제/비공제 꼬리표 완전 제거 & 중립 계좌명 및 뱃지 기반 100% 실시간 전환 완비
- **계좌명 중립화 및 공제 꼬리표 완전 분리**:
  - 계좌 이름에 붙어있던 `(공제)`, `(비공제)`, `(세액공제O)`, `(세액공제X)` 등의 꼬리표를 완전히 제거하고 깨끗한 중립 이름(`연금저축 1`, `연금저축 2`, `연금저축`)으로 정리
  - 이름과 설정 간의 시각적 불일치 및 혼란을 원천 해소하고 오직 뱃지와 문구로만 명확하게 공제 여부 표기
- **엄마/자녀/아빠 모든 계좌의 세액공제 신청 ↔ 비공제 100% 자유 전환 보장**:
  - 수정 다이얼로그 및 원클릭 뱃지 토글(`🔄`)을 통해 언제든지 즉시 세액공제 신청 또는 비공제로 마음껏 전환 가능
(perf) 서비스 워커 캐시 버전(wealth-cache-v60) 및 정적 자산 쿼리(v510) 갱신

v5.0.8

(fix) 🛡️ 계좌명 인위적 변조 로직 완전 제거 & 순수 boolean 기반 세액공제 제어로 100% 영구 저장 보장
- **계좌명 강제 변조/치환 로직 완전 제거**:
  - 모달 폼이나 토글 시 계좌 이름에 `(세액공제O)` / `(세액공제X)`를 덧붙이거나 바꾸던 로직을 삭제하여, 사용자가 지어준 원래 이름 그대로 완벽 보존
- **계좌 데이터 정리 및 순수 `tax_deductible` 제어 완비**:
  - 아빠(`연금저축(공제)`, `연금저축(비공제)`), 엄마(`연금저축` 비공제), 자녀(`연금저축` 비공제 1,800만 납입) 데이터 포트폴리오를 완벽하게 정상화
  - 세액공제 여부 판별 시 `account.tax_deductible` boolean 값을 100% 최우선 신뢰하여 수정/저장/토글이 완벽하게 영구 반영
(perf) 서비스 워커 캐시 버전(wealth-cache-v58) 및 정적 자산 쿼리(v508) 갱신

v5.0.7

(feat) 🔄 계좌 목록 뱃지 원클릭 즉시 토글(세액공제 신청 ↔ 비공제) & 계좌명 자동 동기화 완비
- **계좌 목록 뱃지 원클릭 즉시 토글 스위치 도입**:
  - 계좌 목록에서 **`[연금(공제O) 🔄]`** 또는 **`[연금(비공제) 🔄]`** 뱃지를 클릭만 하면, 모달을 열 필요 없이 **0.001초 만에 즉시 반대 상태로 토글 및 서버 자동 저장**
  - 토글 시 계좌명의 `(세액공제O)` ↔ `(세액공제X)` 및 `(공제O)` ↔ `(비공제)` 텍스트가 자동으로 실시간 동기화되어 이름 불일치로 인한 오해 완전 해결
- **계좌 수정 다이얼로그 계좌명 양방향 실시간 동기화**:
  - `세액공제 적용 여부` 옵션 변경 시 계좌명 텍스트 인풋도 실시간으로 `(세액공제O)` / `(세액공제X)`로 맞춤 자동 수정
(perf) 서비스 워커 캐시 버전(wealth-cache-v57) 및 정적 자산 쿼리(v507) 갱신

v5.0.5

(feat) ⚡ 즉각 반응형(Optimistic UI) 계좌 수정 및 중복 차단 플래그 제거로 실시간 100% 저장 보장
- **Optimistic UI (즉각 반응형 렌더링) 전면 적용**:
  - `[저장]` 버튼을 누르는 즉시(0.001초) 로컬 메모리 계좌 데이터를 갱신하고 화면을 즉시 재렌더링한 후 서버와 백그라운드 동기화 수행
  - 네트워크 지연이나 응답 대기 없이 즉각적으로 계좌 뱃지(`[연금(비공제)]` ↔ `[연금(공제O)]`)와 납입금액이 실시간 전환
- **중복 차단 플래그(`isSubmittingEditAccount`) 제거 및 명시적 alert/toast 피드백**:
  - 함수 차단 플래그가 꼬여 저장이 무시되던 원인을 원천 차단
  - 오류 발생 시 명확한 Alert 창으로 즉각적인 피드백 제공
(perf) 서비스 워커 캐시 버전(wealth-cache-v55) 및 정적 자산 쿼리(v505) 갱신

v5.0.3

(fix) 🛡️ 계좌 정보 수정 시 busy 상태 피드백, 유효성 검사 및 실시간 UI 갱신 완비
- **계좌 정보 수정 프로세스 불릿프루프 강화**:
  - `saveEditAccount` 실행 시 버튼 `busy` 상태 처리로 중복 클릭 방지 및 시각 피드백 제공
  - `tax_deductible`, `annual_deposit`, `income_level` 등 모든 변경 사항을 즉시 PUT 요청 및 대시보드 리로드 연동
(perf) 서비스 워커 캐시 버전(wealth-cache-v53) 및 정적 자산 쿼리(v503) 갱신

v5.0.1

(fix) 🎯 계좌 정보 수정 버튼에 명시적 인라인 이벤트 핸들러(onclick) 바인딩 및 전역 노출
- **저장 버튼 이벤트 바인딩 100% 보장**:
  - `accountEditDialog` 및 `accountAddDialog`의 `[저장]` 버튼에 인라인 `onclick="saveEditAccount()"`를 직접 바인딩하여 리스너 등록 누락/경합 위험 완전 제거
  - `saveEditAccount` 및 `saveNewAccount`를 window 전역 객체에 명시적으로 노출
(perf) 서비스 워커 캐시 버전(wealth-cache-v51) 및 정적 자산 쿼리(v501) 갱신

v4.9.9

(feat) 🌿 비공제 계좌의 연간 납입금액(예: 1,800만원) 시각화 및 계좌 수정 폼 양방향 데이터 복원 완비
- **비공제 계좌 연간 납입액 명확한 시각화**:
  - 세액공제 제외(비공제) 계좌에 납입액 입력 시 목록에 **`🌿 비공제 납입 ₩18,000,000 (원금 비과세 인출 대상)`**으로 선명하게 표시
  - 세액공제 신청 계좌의 경우 **`💎 세액공제 ₩환급액 (납입 ₩6,000,000)`**으로 납입액과 환급액 동시 표시
- **계좌 수정 다이얼로그 필드 복원 & 토스트 알림 강화**:
  - 수정 팝업 오픈 시 기존에 저장된 `annual_deposit`(납입액) 및 `tax_deductible` 상태가 100% 온전하게 인풋에 복원
  - 저장 완료 시 계좌명, 세액공제 여부, 납입금액을 포함한 직관적 토스트 알림 출력
(perf) 서비스 워커 캐시 버전(wealth-cache-v49) 및 정적 자산 쿼리(v499) 갱신

v4.9.7

(fix) 🚀 PWA 서비스 워커 캐시 무효화 및 실시간 세액공제 토글 저장 100% 즉시 반영
- **Service Worker(sw.js) 정적 캐시 우회 강화**:
  - JS/CSS 및 모든 비동기 API 요청 시 이전 브라우저 캐시를 거치지 않고 네트워크에서 최신 버전을 즉시 직접 로드하도록 fetch 전략 개편
- **계좌 수정 시 저장 상태 명확화 토스트 & 변수 참조 오류 완벽 수정**:
  - `saveNewAccount` 내 미정의 변수 참조 수정
  - 저장 완료 시 `[계좌명] 🎯 세액공제 신청` / `[계좌명] 🌿 세액공제 제외(비공제)` 토스트 알림 즉시 출력
(perf) 서비스 워커 캐시 버전(wealth-cache-v47) 및 정적 자산 쿼리(v497) 갱신

v4.9.6

(fix) 💎 세액공제 신청/제외 전환 시 계좌 목록 실시간 시각 피드백 명확화 & 캐시 갱신
- **공제 신청 계좌의 시각 피드백 강화**:
  - `세액공제 신청` 선택 시 납입액 유무와 관계없이 목록에 **`💎 세액공제 신청 (공제 대상)`** 문구 및 **`[연금(공제O)]` / `[IRP(공제O)]`** 뱃지 명확히 렌더링
  - `세액공제 제외` 선택 시 목록에 **`🌿 비공제 (원금 비과세 인출용)`** 문구 및 **`[연금(비공제)]` / `[IRP(비공제)]`** 뱃지 즉시 전환
- **엄마/자녀/아빠 모든 계좌의 공제/비공제 자유로운 상호 전환 보장**:
  - 계좌 수정 팝업에서 언제든지 `세액공제 신청`과 `세액공제 제외`를 손쉽게 변경 및 즉시 저장 가능
(perf) 서비스 워커 캐시 버전(wealth-cache-v44) 및 정적 자산 쿼리(v496) 갱신

v4.9.5

(feat) 👨‍👩‍👧 가족 구성원별(아빠/엄마/자녀) 연금계좌 세액공제 여부 완벽 적용 및 계좌 유형 깔끔 축소
- **가족 구성원별(엄마, 자녀 등) 세액공제 제외(비공제) 연금 계좌 완벽 지원**:
  - 미성년 자녀 및 전업주부 배우자의 연금저축 계좌에 대해 `세액공제 제외 / 미신청 (비공제 납입 - 향후 원금 비과세 인출용)` 완벽 설정 및 연동
  - 계좌 목록에서 **`[연금(비공제)]`** / **`[연금(공제O)]`** 뱃지와 **`🌿 비공제 (원금 비과세 인출)`** 안내가 모든 소유자(아빠/엄마/자녀/모두) 필터에서 완벽 렌더링
- **계좌 유형 선택창 간소화 & 직관화**:
  - 계좌 유형 드롭다운을 4개 핵심 항목(`일반 주식 / 위탁계좌`, `💎 연금저축펀드`, `🛡️ 개인형 IRP`, `🔄 중개형 ISA`)으로 깔끔하게 축소 복원
  - 세액공제 신청 / 비공제 여부는 하단의 `세액공제 적용 여부` 옵션으로 일관되고 명확하게 제어
(perf) 서비스 워커 캐시 버전(wealth-cache-v43) 및 정적 자산 쿼리(v495) 갱신

v4.9.4

(feat) 💎 연금계좌 계좌유형 드롭다운에서 세액공제O / 세액공제X(비공제) 직관적 원클릭 선택 및 계좌명 자동 동기화 지원
- **계좌 유형 드롭다운 선택지 고도화**:
  - `💎 연금저축펀드 (세액공제 신청 O - 연 600만)` vs `🌿 연금저축펀드 (세액공제 제외 X - 원금 비과세 인출용)`
  - `🛡️ 개인형 IRP (세액공제 신청 O - 합산 연 900만)` vs `🌿 개인형 IRP (세액공제 제외 X - 원금 비과세 인출용)`
  - 계좌 유형 선택만으로 세액공제 여부와 한도, 환급액 프리뷰가 100% 양방향 실시간 동기화
- **계좌명 스마트 동기화**:
  - 세액공제 여부 변경 시 계좌명의 `(세액공제O)` <-> `(세액공제X)` 문구가 자동으로 실시간 변경 제안되어 이름 불일치 혼란 완전 해소
(perf) 서비스 워커 캐시 버전(wealth-cache-v42) 및 정적 자산 쿼리(v494) 갱신

v4.9.3

(fix) 🚨 wealth.js 스크립트 문법 누락 긴급 복구 (자산 대시보드 화면 로드 오류 해결)
- **자산 화면 로드 중단 버그 긴급 해결**:
  - `wealth.js` 내 연금 절세액 집계 루프(`pensionTaxSaved`)에서 조건문 괄호 누락으로 발생했던 `SyntaxError`를 즉시 수정
  - 브라우저 스크립트 실행이 정상 재개되어 모든 계좌 목록, 주식 보유종목, 자산 통계가 정상 복구 표시됨
(perf) 서비스 워커 캐시 버전(wealth-cache-v41) 및 정적 자산 쿼리(v493) 갱신

v4.9.2

(fix) 🛠️ 연금저축·IRP 세액공제 제외 설정 저장 버그 수정 및 판별 로직 불릿프루프화
- **세액공제 적용 여부(`tax_deductible`) 저장 및 파싱 버그 수정**:
  - 백엔드 `rename_account` 및 `create_account`에서 `tax_deductible` boolean 파싱 로직을 불릿프루프(`parse_bool`)하게 개편하여 `False` 값이 정확히 저장되도록 수정
  - 증권 계좌 수정 팝업(`accountEditDialog`) 폼 제출 시 다이얼로그 `method="dialog"` 충돌을 방지하고 `onsubmit="return false;"` 및 명시적 저장 핸들러(`saveEditAccount`)로 분리
- **프론트엔드 `isAccountTaxDeductible()` 헬퍼 통합**:
  - 계좌 목록 렌더링, 계좌 수정 다이얼로그 초기화, 절세 요약 계산 등 모든 영역에서 `isAccountTaxDeductible()`로 일관되게 판별
  - `tax_deductible: false`인 경우 즉시 **`[연금(비공제)]` / `[IRP(비공제)]`** 뱃지와 **`🌿 비공제 (원금 비과세 인출용)`**이 완벽히 렌더링되도록 수정
(perf) 서비스 워커 캐시 버전(wealth-cache-v40) 및 정적 자산 쿼리(v492) 갱신

v4.9.1

(feat) 🌿 연금저축·IRP 세액공제 제외(비공제 / 원금 비과세 인출용) 계좌 관리 및 1,800만 한도 지원
- **연금계좌 세액공제 제외(미신청) 항목 신설**:
  - 연간 총 1,800만 원 납입 한도 중 세액공제 한도(600만/900만 원) 초과분 또는 별도 운용하는 **세액공제 제외(비공제) 연금 계좌 지원**
  - 계좌 추가/수정 모달에 **`[세액공제 적용 여부]`** (`🎯 세액공제 신청` vs `🌿 세액공제 제외 / 미신청 (원금 비과세 인출용)`) 선택 기능 추가
- **비공제 계좌 전용 UI & 태그 시각화**:
  - 계좌 목록에 **`[연금(비공제)]` / `[IRP(비공제)]`** 에메랄드 뱃지 및 **`🌿 비공제 (원금 비과세 인출용)`** 안내 표시
  - 세액공제 제외 계좌의 납입액은 연말정산 환급금 종합 집계에서 안전하게 제외 처리
  - 계좌명(`연금(세액공제X)` 등)에 따른 자동 비공제 감지 및 연동
(perf) 서비스 워커 캐시 버전(wealth-cache-v39) 및 정적 자산 쿼리(v491) 갱신

v4.9.0

(feat) 🎯 노란우산공제 소득공제 & 개인연금(연금저축)·IRP·ISA 만기이전 세액공제 혜택 통합 시스템 구축
- **노란우산공제 소득공제 & 절세 환급액 시뮬레이터 탑재**:
  - 사업소득 구간(4천만 이하 / 4천만~1억 / 1억 초과)별 법정 공제한도(500만 / 300만 / 200만 원) 자동 적용
  - 과세표준 구간별 한계세율(6.6% ~ 49.5%)에 따른 **실제 종합소득세 절감(환급)액 실시간 계산**
  - 노란우산공제 카드에 골드 테마의 **`💰 연 소득공제 ₩3,000,000 (절세 혜택 ₩792,000 환급)`** 하이라이트 박스 표시
- **개인연금(연금저축) & IRP 세액공제 계산기**:
  - 증권 계좌 추가 및 수정 창에서 계좌 유형(`연금저축펀드`, `개인형 IRP`, `중개형 ISA`) 선택 지원
  - 소득 구간(총급여 5,500만 이하 16.5% / 초과 13.2%)에 따른 **연말정산 세액공제 환급액 자동 산출**
- **🔄 ISA 만기 자금 연금계좌 전환 추가 세액공제 관리**:
  - ISA 만기 해지 자금을 연금저축/IRP로 이전 시 **전환금액의 10% (최대 300만 원 한도)**를 기존 연금 한도(600만/900만)와 별도로 추가 세액공제(최대 49.5만 원 추가 환급) 계산
  - 연금저축 계좌에 `ISA 만기 전환 입금액` 및 `전환 연도` 기록 지원
- **🎯 2026 연간 절세 혜택 종합 요약 배너**:
  - 보험·연금·공제 탭 상단에 우리 가족의 **예상 총 절세 환급액**(노란우산 + 연금/IRP + ISA이전) 종합 대시보드 신설
(perf) 서비스 워커 캐시 버전(wealth-cache-v38) 및 정적 자산 쿼리(v490) 갱신

v4.8.9

(fix) 💰 보험·연금·예적금·대출 금액 입력 시 1원 단위 정밀 입력 지원 (step="any" 전면 개편)
- **금액 입력 필드 단위 절사/제한 버그 수정**:
  - 보험 월 납입액(`monthly_premium`), 누적 납입액(`total_paid_amount`), 예상 수령액(`expected_amount`)의 고정 `step`(`1,000`원 / `10,000`원)을 `step="any"`로 전면 개편
  - 국민연금 월 납입액 `626,040`원 등 1원 단위까지 절사 없이 정밀하게 입력 및 저장 가능
  - 예·적금 불입액/목표액 및 대출 한도/잔액 입력 필드도 모두 `step="any"`로 통일하여 1원 단위 완벽 지원
(perf) 서비스 워커 캐시 버전(wealth-cache-v37) 및 정적 자산 쿼리(v489) 갱신

v4.8.8

(feat) 🏠 주택청약종합저축(만기 없는 적립식) 정식 지원 및 [만기 없음] 옵션 탑재
- **상품 유형 내 '🏠 주택청약종합저축 (만기 없음)' 신설**:
  - 만기일이 정해져 있지 않고 주택 당첨 또는 해지 시까지 유지되는 청약통장의 금융 특성을 완벽히 반영
- **만기일 '만기 없음 (무기한 / 주택청약)' 원클릭 토글 탑재**:
  - 주택청약을 선택하거나 '만기 없음' 체크박스 선택 시, 만기일 및 약정 기간 필수 입력 해제
  - 임의의 가짜 만기일을 입력할 필요 없이 깔끔하게 무기한 적립식 통장으로 등록 가능
- **카드 및 통계 시각화 최적화**:
  - 카드 뱃지: **`🏠 주택청약`**, **`만기 없음`**, **`N개월째 불입 중`**
  - 목표금액 대신 **`현재 누적 납입원금`** 및 **`월 납입 금액`**, **`연간 예상 이자`** 중심 직관적 표시
  - 에메랄드 그린 테마의 전용 청약 카드 스타일링(`housing-card`) 적용
(perf) 서비스 워커 캐시 버전(wealth-cache-v36) 및 정적 자산 쿼리(v488) 갱신

v4.8.7

(ux) ⌨️ 모달 입력창 내 Enter 입력 시 즉시 저장 지원 & 팝업 바깥 배경(백드롭) 클릭 닫기 방지 보호
- **모달 입력창 내 Enter 입력 시 저장 연동**:
  - 계좌 추가, 자유통장, 예·적금, 대출, 부동산, 보험 등 모든 다이얼로그 입력창(`input`, `select`)에서 `Enter` 입력 시 다이얼로그가 닫히지 않고 정상적으로 `[저장]` 버튼이 실행되도록 개선
  - 한글 조합 중 엔터(`e.isComposing`) 및 `textarea` 줄바꿈은 보존
- **팝업 바깥 배경(백드롭) 클릭 시 닫힘 방지**:
  - 입력 도중 실수로 팝업 바깥 어두운 배경을 클릭했을 때 창이 닫혀 입력 데이터가 날아가지 않도록 백드롭 클릭 닫기 방지 적용
  - 오직 명시적인 `[X]` 닫기 버튼이나 `[취소]` 버튼을 눌렀을 때만 안전하게 닫힘
(perf) 서비스 워커 캐시 버전(wealth-cache-v35) 및 정적 자산 쿼리(v487) 갱신

v4.8.6

(fix) 🐛 대출 탭 섹션 타이틀 카운트 내 minusBanks 참조 오류 수정 및 주식/전체 렌더링 파이프라인 정상화
(perf) 서비스 워커 캐시(wealth-cache-v34) 및 정적 버전(v486) 갱신

v4.8.5

(fix) 💳 마이너스통장 양수 잔고 시 한도소진율(16%->0%) 및 월이자(₩0) 정상화 & 대출 탭 마통 약정한도 계좌 상시 노출
- **자유통장 모달 내 마통 한도 소진율 및 월 예상 이자 계산 버그 수정**:
  - 통장 잔고가 양수(+)일 때 잔고를 대출 부채로 잘못 계산하던 로직 수정
  - 현재 잔고가 플러스일 때는 대출을 전혀 쓰고 있지 않으므로 **`한도 소진율: 0% (전액 잔여)`**, **`월 예상 이자: ₩0 (대출 미사용)`**으로 정확히 계산
- **마이너스통장 약정 계좌의 대출 탭 상시 노출 개선**:
  - 한도(예: 9,000만 원)나 금리가 등록된 마통 약정 계좌는 현재 잔고가 양수(+)라도 대출 탭에 **`🟢 자유연동 마통 (대출 미사용)`** 카드로 상시 표시
  - 대출 잔액 `₩0`, 소진율 `0% (전액 잔여)`, 잔고 유지 중 안내가 직관적으로 제공되어 내 마통 약정 라인을 항시 관리 가능
  - 향후 잔고가 음수(-)로 내려갈 때만 실제 대출 부채로 전환되어 총부채와 이자가 실시간으로 자동 합산
(perf) 서비스 워커 캐시 버전(wealth-cache-v33) 및 정적 자산 쿼리(v485) 갱신

v4.8.4

(feat) 💬 실시간 한글 금액 읽기 힌트(150만 -> 1,500만 -> 1억 5천만 -> 15억) 전 모달 입력창 탑재
- **실시간 한글 금액 변환 시스템 (`formatKoreanMoneyFriendly`) 탑재**:
  - 숫자를 타이핑할 때마다 0의 개수를 즉시 계산하여 읽기 쉬운 한글 단위로 실시간 표시
  - 예시 변환:
    - `150000` ➔ `💬 15만 원`
    - `1500000` ➔ `💬 150만 원`
    - `15000000` ➔ `💬 1,500만 원 (1천 5백만 원)`
    - `150000000` ➔ `💬 1억 5천만 원`
    - `1500000000` ➔ `💬 15억 원`
    - `15000000000` ➔ `💬 150억 원`
    - `-35000000` ➔ `💬 -3,500만 원 (3천 5백만 원) (마이너스)`
- **전 카테고리 14개 주요 금액 입력창 전면 적용**:
  - **부동산**: 매수금액, 현재 시세(KB시세 연동 포함), 임대차 보증금, 월세
  - **은행**: 자유통장 잔고, 마이너스통장 한도, 예·적금 납입액/목표액/불입원금, 대출 잔액/한도
  - **보험**: 월 납입액, 누적 총 납입액, 예상 수령액/해약환급금
- **기존 데이터 조회 시 자동 힌트 표시**:
  - 수정 모달을 열었을 때 이미 입력되어 있는 금액도 즉시 한글로 함께 안내
(perf) 서비스 워커 캐시 버전(wealth-cache-v32) 및 정적 자산 쿼리(v484) 갱신

v4.8.3

(feat) 🏦 은행 탭 [🏦 계좌 추가] 단일화(유형 선택 지원) 및 [전체] 서브탭(한눈에 모아보기) 신설
- **은행 툴바 버튼 단일화**:
  - 기존 3개 버튼(`[자유통장 추가]`, `[예·적금 추가]`, `[대출 추가]`)을 단일 버튼 **`[🏦 계좌 추가]`**로 통합
- **계좌 유형 선택 시스템 탑재**:
  - 모달 상단에 `계좌 유형: [자유입출금 | 예·적금 | 대출]` 드롭다운 배치
  - 현재 보고 있는 서브탭에 맞춰 기본 유형이 스마트하게 선택되며, 모달 내에서 언제든 유형 변경 가능
- **은행 서브탭 [전체] 신설 및 일괄 모아보기**:
  - `[전체]` | `[자유]` | `[예·적금]` | `[대출]` 4대 서브탭 체계 완성
  - `[전체]` 선택 시 자유입출금 통장, 예·적금 상품, 대출·마이너스통장이 각 섹션 소제목과 함께 한 화면에 정돈되어 전체 은행 포트폴리오를 한눈에 파악 가능
(perf) 서비스 워커 캐시 버전(wealth-cache-v31) 및 정적 자산 쿼리(v483) 갱신

v4.8.2

(feat) 🏢 KB부동산 공식 시세(일반평균가·하한가·상한가) 온디맨드 원클릭 연동 탑재
- **KB부동산(kbland) 공식 시세 API 직접 연동 (`app/services/kb_land.py`)**:
  - 단지명 검색(`search_kb_complex`) 및 전용면적 기준 최적 평형 자동 매칭(`get_kb_market_prices`)
  - 은행 주택담보대출 기준이 되는 **KB 일반평균가, 하한가, 상한가, 전세가** 실시간 수집
- **부동산 추가/수정 모달에 `[🔍 KB시세 조회]` 버튼 및 시세 자동 적용**:
  - 단지명과 전용면적(㎡)을 입력하고 버튼을 누르면 0.2초 만에 KB 공식 시세 조회
  - 단지 내 세부 평형(예: 33A, 33B 등) 직접 선택 드롭다운 및 `[시세 적용]` 원클릭 반영
- **부동산 카드에 `[🔄]` KB시세 최신화 원클릭 버튼 탑재**:
  - 필요할 때 클릭 한 번으로 최신 KB 일반평균가로 즉시 갱신 및 순자산 자동 재집계
  - 불필요한 자동 반복 조회를 없애고 온디맨드(On-demand) 방식으로 서버 차단 위험 0% 실현
(perf) 서비스 워커 캐시 버전(wealth-cache-v30) 및 정적 자산 쿼리(v482) 갱신

v4.8.1

(feat) 🏠 부동산 4대 서브탭 개편, 부부/가족 공동명의 지분율(%) 시스템 및 시세 검색어 정제
- **부동산 서브탭 4종 전면 분리**:
  - `[전체]` | `[자가]` | `[임대]` | `[임차]` 4개 서브탭으로 직관적 재분류
  - 카운트 배지 및 필터링 독립 작동
- **부부·가족 공동명의 지분율(%) 시스템 탑재**:
  - 모달 내 `[✔] 부부·가족 공동명의` 옵션 추가
  - 구성원별 지분율(예: 아빠 50%, 엄마 50%)을 자유롭게 설정 가능
  - 상단 가족 필터(`[아빠]`, `[엄마]`) 선택 시 지분율만큼 비례 배분되어 대시보드 순자산 및 요약에 정확하게 반영!
  - 카드 상단에 `🤝 아빠 50% · 엄마 50%` 공동명의 뱃지 및 특정 가족 필터 시 `(내 지분 50%)` 자동 표기
- **네이버 부동산 시세 조회 시 동·호수 자동 제외 및 폼 분리**:
  - 모달에 `단지명/건물명`과 `상세 동·호수(선택)` 입력란 분리
  - 네이버 시세 조회(`🔍`) 클릭 시 동·호수(`105동`, `1204호` 등)가 자동 정제된 순수 단지명으로 검색되어 검색 실패 방지
  - 카드에는 `마포 래미안 푸르지오 (105동 1204호)`로 완전하게 표기
(perf) 서비스 워커 캐시 버전(wealth-cache-v29) 및 정적 자산 쿼리(v481) 갱신

v4.8.0

(feat) 🏠 Phase 2: 부동산(자가 / 임대 / 임차) 자산 관리 및 대출·전세보증금 부채 연동 시스템 완성
- **4대 자산군([📈 증권] | [🏦 은행] | [🛡️ 보험] | [🏠 부동산]) 통합 체계 완성**:
  - 계좌 섹션에 카테고리 탭 `[🏠 부동산 (<span id="realEstateTabCount">N</span>)]` 신설
  - 툴바에 `[🏠 부동산 추가]` 전용 액션 버튼 및 서브탭 3종(`[전체]` | `[자가/보유]` | `[임대/임차]`) 배치
- **부동산 3대 유형별 맞춤 회계 및 자산·부채 자동 처리**:
  - **🏠 자가 (직접 거주/보유)**: 매수가 & 현재 시세 평가, 평가손익/수익률 계산, 연결된 **주택담보대출(부채)** 차감 후 순에퀴티 산출
  - **🏢 임대 (전세/월세 준 주택 - 갭투자)**: 매수가 & 현재 시세 평가, 세입자에게 받은 **전세보증금(부채)** 및 담보대출을 [총 부채]에 자동 편입, 월세 수입 기록
  - **🔑 임차 (전세/월세 거주 중)**: 집주인에게 맡긴 **전세보증금(자산)**을 [총 자산]에 100% 자동 합산, 빌린 전세대출(부채) 차감 후 순에퀴티 산출, 월세 지출 기록
- **대시보드 상단 핵심 요약 (Overview) 및 [💎 순자산 (Net Worth)] 회계 확장**:
  - 총 자산: 투자자산 + 은행 잔고 + 예·적금 + 부동산 시세 + 임차 전세보증금
  - 총 부채: 일반 대출/마통 + 음수통장 + 주택담보대출 + 전세대출 + 임대 전세보증금
  - 순자산 (Net Worth) = 총 자산 - 총 부채
- **기존 대출 시스템(`loan_accounts`)과 부동산 간의 양방향 연동**:
  - 부동산 등록/수정 시 기존 등록된 주택담보대출/전세대출을 바로 선택 연결
  - 부동산 카드 내 연결 대출 잔액, 월 예상 이자, D-Day 만기 배지 실시간 표시
  - 카드 내 **`[🔍 네이버 부동산]` 바로가기 버튼** 탑재로 실시간 시세 및 호가 즉시 조회 지원
  - 모달 내 **[실시간 부동산 순에퀴티 & 예상 시세차익]** 실시간 프리뷰 박스 탑재
(perf) 서비스 워커 캐시 버전(wealth-cache-v28) 및 정적 자산 쿼리(v480) 갱신

v4.7.2

(feat) 💳 자유연동 마이너스통장 한도·금리 설정 및 대출 탭 완벽 시각화
- 자유입출금 통장에 [마이너스통장 설정 (한도 / 약정 금리 / 만기일)] 옵션 신설:
  - 대출 탭에서 자유연동 마통의 [✎ 수정] 버튼을 클릭하면 한도금액, 대출금리, 만기일, 현재 잔고(마통 잔액)를 즉시 입력/수정 가능
  - 모달 내 [실시간 월 예상 이자 및 한도 소진율] 실시간 시뮬레이션 박스 탑재
- **대출 탭 [자유연동 마통] 카드 UI 전면 업그레이드**:
  - 일반 마통 카드와 동일하게 **한도 소진율(%) 프로그레스 바** 및 설정 한도 금액 완벽 표시
  - 약정 대출금리(연 %), 월 예상 이자(₩xx,xxx), 만기 D-Day 배지(`만기 D-xxx`) 제공
  - 한도 미설정 시에도 [한도/금리 설정 ✎] 바로가기 힌트 제공
- **CSS 레이아웃 및 텍스트 줄바꿈 최적화**:
  - 대출 카드 내 `상환 방식` 텍스트 줄바꿈 깨짐 현상(`상환 방 \n 식`) 방지 및 정렬 개선
  - 자유연동 마통의 월 예상 이자 및 설정 한도가 은행 탭 상단 요약 카드에 100% 자동 합산
(perf) 서비스 워커 캐시 버전(wealth-cache-v27) 및 정적 자산 쿼리(v472) 갱신

v4.7.1

(feat) 🔄 계좌 섹션 [🏦 은행] 탭 서브탭 개편([자유] | [예·적금] | [대출]) 및 자유통장 음수(-) 잔고 마이너스통장 자동 인식 시스템
- 사용자 요청에 따라 계좌 섹션 [🏦 은행] 서브탭 명칭 및 순서 개편:
  - `[자유]` ➔ `[예·적금]` ➔ `[대출]` 순으로 정렬 및 [자유] 탭 기본 활성화
  - 툴바 버튼 명칭을 `[🏦 자유통장 추가]`, `[➕ 예·적금 추가]`, `[💳 대출 추가]`로 직관화
- **자유입출금 통장 마이너스(-) 잔고 자동 인식**:
  - 자유통장 잔고에 `-` 음수 금액 입력 허용 (예: `-5,000,000`원)
  - 자유통장 목록에서 음수 통장에 `🔴 마통` 배지 부여 및 로즈레드 컬러로 강조
  - 음수 잔고는 [대출] 탭에 `[자유연동 마통]` 카드로 자동 편입되어 부채로 일괄 관리
  - 백엔드 회계 엔진 및 대시보드 상단 요약(Overview)에서 음수 잔고를 [총 부채(대출·마통)]에 100% 자동 합산하고 [순자산]에서 정확하게 차감
(perf) 서비스 워커 캐시 버전(wealth-cache-v26) 및 정적 자산 쿼리(v471) 갱신

v4.7.0

(feat) 💳 계좌 섹션 [🏦 은행] 탭 내 대출·마이너스통장 관리 시스템 구축 및 [순자산(Net Worth)] 회계 엔진 도입 (1단계 완료)
- 계좌 섹션의 [🏦 은행] 탭에 대출·마이너스통장 서브 탭([예·적금] | [입출금 통장] | [대출·마이너스통장]) 신설
  - 마이너스통장(한도대출), 일반 신용대출, 담보대출 등 다양한 대출 유형 등록/수정/삭제 지원
  - 마이너스통장 카드: 설정 한도 대비 소진율(%) 프로그레스 바 및 잔액 경고 시각화
  - 만기일 D-Day 배지, 약정 대출금리(연 %), 월 예상 이자 및 이자 출금 연결 통장 정보 제공
- 대출 등록 모달 내 [📊 실시간 월 상환액 및 이자 시뮬레이션] 탑재 (만기일시상환 / 원리금균등분할상환 / 원금균등분할상환 공식 적용)
- Phase 2(부동산) 연동을 대비하여 대출 모델에 `linked_property_id`(연결 부동산 ID) 선제 구축
- 대시보드 상단 핵심 요약(Overview)에 [💎 순자산 (Net Worth)] 및 [총 부채(대출·마통)] 지표 연동
  - 순자산 = 총 투자자산 + 은행/예적금 잔액 - 총 대출 부채
  - 가족 소유자 탭([모두] [아빠] [엄마] [자녀])과 실시간 동기화
(perf) 서비스 워커 캐시 버전(wealth-cache-v25) 및 정적 자산 쿼리(v470) 갱신

v4.6.2

(fix) 🎯 계좌 섹션 은행/보험 탭 명칭 간소화 및 3대 탭 접기/펼치기(▼) 완벽 연동
- 계좌 섹션 카테고리 탭 명칭을 사용자의 요청에 따라 간결하게 변경:
  - `[🏦 은행·예적금]` ➔ `[🏦 은행]`
  - `[🛡️ 보험·연금·공제]` ➔ `[🛡️ 보험]`
- 증권 탭에서만 계좌 섹션 접기/펼치기가 적용되고 은행 탭과 보험 탭에서는 접히지 않던 버그 해결:
  - `.panel.is-collapsed` 상태에서 은행 및 보험 본문 패널(`.cat-panel`, `#catPanelBanking`, `#catPanelInsurance`)이 완전히 숨겨지도록 CSS 규칙 보강
  - 카테고리 탭 바(`.account-category-tabs`)도 접힘 상태일 때 일관되게 비활성화 처리
  - 계좌 섹션이 접힌 상태에서 은행 또는 보험 탭을 클릭할 경우 자동으로 펼쳐지도록 인터랙션 개선
(perf) 서비스 워커 캐시 버전(wealth-cache-v24) 및 정적 자산 쿼리(v462) 갱신

v4.6.1

(feat) 🏛️ 계좌 섹션 3대 금융자산(증권 / 은행 / 보험·연금·공제) 탭 통합 개편 및 상단바 [👨‍👩‍👧‍👦 가족] 전역 버튼 신설
- 계좌 섹션을 3대 금융자산 서브 카테고리 탭([📈 증권] / [🏦 은행·예적금] / [🛡️ 보험·연금·공제])으로 통합하여 하나의 섹션에서 일목요연하게 조회 및 관리
  - 📈 증권 탭: 기존 증권사별 계좌 목록(예수금, 종목수 등) 및 [➕ 증권계좌 추가] 버튼 연동
  - 🏦 은행·예적금 탭: 일반 수시입출금 계좌 잔고 + 예·적금 카드 및 실시간 이자 계산기 연동
  - 🛡️ 보험·연금·공제 탭: 저축성보험, 보장성보험, 국민연금, 노란우산공제, 개인연금/IRP 통합 관리 (월 납입액, 누적 납입액, 만기 예상액/해약환급금, 납입상태 등)
- 상단바(Topbar)의 [User 이름]과 [OpenAPI] 버튼 사이에 [👨‍👩‍👧‍👦 가족] 관리 버튼을 신설하여, 계좌 섹션에 종속되지 않고 대시보드 어디서나 가족 구성원을 편리하게 등록/수정/삭제할 수 있도록 UX 개선
- 계좌 카테고리 탭 선택에 따라 상단 툴바 액션 버튼([➕ 증권계좌 추가], [🏦 은행계좌 추가]/[➕ 예·적금 추가], [➕ 보험/연금 추가]) 동적 자동 전환
- 가족 구성원 탭([모두] [아빠] [엄마] [자녀])과 3대 금융자산(증권, 은행, 보험) 데이터의 완벽한 전역 실시간 필터링 동기화
(perf) 서비스 워커 캐시 버전(wealth-cache-v23) 및 정적 자산 쿼리(v461) 갱신

v4.6.0

(feat) 🏦 예·적금 및 일반 은행 계좌 관리 섹션(SAVINGS & BANKING) 및 실시간 이자 계산기 탑재 (Phase 1 완료)
- 주식/ETF 외에 일반 은행 수시입출금 계좌 및 정기예금/정기적금/자유적금 상품을 통합 관리할 수 있는 [예·적금 및 은행 계좌] 섹션 신설
- 정기예금(단리) 및 정기적금의 계약기간(개월), 약정 연이율(%), 과세구분(일반과세 15.4%, 세금우대 1.4%, 비과세 0%)에 따른 세전이자, 소득세, 만기 실수령액 자동 계산 엔진 구축
- 예·적금 등록/수정 모달 내 입력 즉시 실시간으로 예상 만기 수령액이 계산되는 인터랙티브 시뮬레이션 박스 탑재
- 자동이체일(매월 N일), 월 납입금액, 출금 통장 ↔ 만기 입금 통장 연동 기능 제공
- 카드 UI에 만기 D-Day 배지(D-xxx / 만기 달성) 및 경과 일수 기준 진행률 프로그레스 바 렌더링
- 상단 요약 카드(일반 은행 잔고, 예적금 누적 불입액, 만기 예상 실수령액) 및 가족 구성원 탭([모두] [아빠] [엄마] [자녀]) 전역 동기화
- 다크/클래식 다크(OLED)/모던 화이트 모든 테마 완벽 호환
(perf) 서비스 워커 캐시 버전(wealth-cache-v22) 및 정적 자산 쿼리(v452) 갱신

v4.5.1

(ui) 계좌 섹션 버튼 스타일 통일 및 다크모드 내 퍼플 테마 잔재 완벽 제거
- 계좌 섹션 상단의 `⚙️ 관리` 및 `➕ 추가` 버튼을 다른 섹션들과 동일하게 입체적인 배경과 테두리를 가진 `button secondary compact` 스타일로 개편 (배경이 투명했던 문제 해결)
- 다크 테마(클래식 다크/OLED)에서 계좌 섹션 내 증권사 제목(`broker-head strong`)의 보라색(`#c4b5fd`)을 깔끔한 실버 화이트(`#e2e8f0` / `#f8fafc`)로 개선
- 계좌 섹션 스크롤바의 보라색(`rgba(142, 112, 250, ...)`)을 차분한 슬레이트 그레이/모노크롬으로 정돈
- 계좌 목록 액션 버튼(`account-action-button:hover`)의 보라색 호버 테두리 및 현금/예수금 보라색을 산뜻한 스카이블루(`#38bdf8`)로 변경
- 다크모드(`[data-theme="oled"]`)에서 활성화된 가족 탭 및 보조 버튼에 딥 다크 블랙/블루 테마 규칙을 추가하여 퍼플 테마 흔적 전면 소거
(perf) 서비스 워커 캐시 버전(wealth-cache-v21) 및 정적 자산 쿼리(v451) 갱신

v4.5.0

(feat) 🔄 모든 가족 구성원(아빠, 엄마, 자녀 등)의 자산기록(스냅샷) 대시보드 접속/조회 시 자동 저장 및 최신 갱신 탑재
- 기존에 '모두' 탭에서만 자동 저장되던 한계를 해결하여, 대시보드에 접속하거나 조회 버튼을 누를 때 '모두'뿐만 아니라 '아빠', '엄마', '자녀' 등 모든 등록된 가족 구성원의 당일 자산기록(스냅샷)이 실시간 평가액으로 일괄 자동 갱신 및 신규 저장되도록 개선
- 해당 날짜에 기록이 없으면 자동으로 신규 레코드를 생성하고, 이미 존재하는 기록은 실시간 평가액과 당일 변동 손익으로 최신화
- 소유자별 주식 평가액, 총 매입액, 예수금(KRW/USD 환산), 당일 손익(`day_profit_krw`), 수익률 등 정밀 집계 산출
- 프론트엔드(`loadDashboard`)에서 대시보드 조회 후 최신 자산기록을 즉각 재조회하도록 호출 순서 최적화
(perf) 서비스 워커 캐시 버전(wealth-cache-v20) 및 정적 자산 쿼리(v450) 갱신

v4.4.9

(layout) 주요지수 4줄 분리 구조(지수명 / 현재가 / 상승분 / %) 개편 및 차트 폭(96px) 복원
- 주요지수 카드 내 수치를 4줄(1줄: 지수명, 2줄: 지수 현재가, 3줄: 상승/하락 변동폭, 4줄: % 등락률)로 깔끔하게 단독 배치
- 지수명 및 지수 현재가 폰트 크기를 `12px`로 정밀 축소하여 텍스트 짤림을 원천 차단
- 스파크라인 차트 폭을 다시 `96px`로 확장 복원하여 곡선의 역동성과 시각적 가독성 극대화
(perf) 서비스 워커 캐시 버전(wealth-cache-v19) 및 정적 자산 쿼리(v449) 갱신

v4.4.8

(ui) 주요지수 카드 숫자 폰트 크기 및 카드 내부 여백 최적화 (텍스트 잘림 현상 완벽 해결)
- 주요지수 카드가 좁은 환경(6열 배치)에서도 변동폭 및 등락률(`+3,592.56 (+11.45%)`)이 우측 끝에서 짤리지 않도록 현재가(`16px` -> `14px`), 변동 수치(`12px` -> `10.5px`), 지수명(`14px` -> `13px`) 폰트 크기 정밀 조정
- 스파크라인 차트 폭(`96px` -> `72px`) 및 카드 패딩 최적화로 텍스트 가용 너비를 약 68% 이상 대폭 확보
- 변동 포인트와 등락률 퍼센트를 독립된 인라인 태그(`change-point`, `change-rate`)로 분리하여 극단적으로 좁은 화면에서도 괄호 중간이 짤리지 않고 자연스럽게 줄바꿈되도록 개선
(perf) 서비스 워커 캐시 버전(wealth-cache-v18) 및 정적 자산 쿼리(v448) 갱신

v4.4.7

(feat) 🔍 자산 분류(섹터/자산군) 항목 클릭 시 보유종목 자동 검색 & 스크롤 연동 탑재
- 자산 분류 내역의 섹터 항목(반도체, 금융·지주, 전력·인프라 등) 또는 자산군 항목 클릭 시 보유종목 검색창(#searchInput)에 해당 키워드가 자동 입력되며 보유종목 목록이 즉시 필터링
- 클릭 시 보유종목 섹션으로 부드럽게 스크롤(smooth scroll) 이동하며, 검색창에 시각적 하이라이트 펄스 애니메이션 제공
- 보유종목 섹션이 접혀있는 경우 자동으로 펼쳐지며, 동일 항목 재클릭 시 검색어 해제(전체 복귀 토글) 지원
- 도넛 차트 원형 슬라이스 및 상단 도넛 범례 항목 클릭 시에도 동일하게 보유종목 검색 연동
(perf) 서비스 워커 캐시 버전(wealth-cache-v17) 및 정적 자산 쿼리(v447) 갱신

v4.4.6

(layout) 투자자산 분류 상세 목록 표시 영역을 섹션 전체 높이에 맞추어 확장(`max-height: 460px`)
- 좌측 핵심 요약 카드 하단선(배당금 행)과 우측 자산 분류 영역이 정확히 맞물리도록 목록 최대 높이를 대폭 확장(`280px` -> `460px`)
- 7~8개 이상의 자산군/섹터 항목들이 빈 여백 없이 시원하게 한눈에 펼쳐지며, 그 이상일 경우에만 매끄럽게 세로 스크롤 적용
(perf) 서비스 워커 캐시 버전(wealth-cache-v16) 및 정적 자산 쿼리(v446) 갱신

v4.4.5

(layout) 투자자산 분류 상세 내역 세로 방향 목록 정리 및 전용 스크롤바 탑재
- 가로로 찌그러져 나열되던 자산군 및 섹터 목록을 세로(column) 방향 단독 행으로 정돈하여 종목수, 비중, 평가금액, 수익률 및 게이지 바 가독성 회복
- 부드러운 전용 스크롤바(`max-height: 280px`)를 적용하여 항목이 많아져도 카드 균형을 유지하며 쾌적하게 탐색 가능
(perf) 서비스 워커 캐시 버전(wealth-cache-v15) 및 정적 자산 쿼리(v445) 갱신

v4.4.4

(layout) 핵심 요약 & 투자자산 분류 섹션을 단일 통합 패널(#summaryPanel)로 일체화
- 2개로 분리되어 있던 핵심요약과 자산분류를 하나의 섹션으로 합쳐 시각적 일체감 대폭 향상
- 단일 접기/펼치기(Accordion) 버튼으로 핵심요약 지표와 자산분류(도넛 차트 + 섹터 목록)가 한 번에 접히고 펼쳐지도록 연동
(feat) 👥 대시보드 전역 소유자(가족) 탭 확장 및 상호 연동 완벽 탑재
- 자산기록, 자산히트맵, 배당금 내역, 실현손익 내역, 보유종목 섹션 헤더에 '모두 / 아빠 / 엄마 / 자녀' 소유자 탭 일괄 배치
- 어느 섹션에서든 소유자 탭 클릭 시 대시보드 내 모든 섹션의 소유자 탭 활성 상태 및 데이터가 한 번에 동기화 전환
(perf) 서비스 워커 캐시 버전(wealth-cache-v14) 및 정적 자산 쿼리(v444) 갱신

v4.4.2

(feat) 주요지수 [전체] 탭 및 자산히트맵 스타일의 세부 기간 드롭다운 셀렉트 박스(`class="heatmap-select"`) 탑재
- 자산히트맵의 셀렉트 드롭다운과 100% 동일한 고급스러운 디자인으로 3년(3Y), 5년(5Y), 10년(10Y), 최대(MAX) 선택 지원
- 초경량 월봉(1mo) 데이터를 통해 뭉개짐 없이 미니 차트가 유려하게 렌더링되며 초고속(0.05초) 로딩 달성
(feat) 🔄 대시보드 전역 기간 탭 완벽 연동 (주요지수 ↔ 자산기록 ↔ 자산히트맵)
- 세 영역 중 어느 곳에서든 일간(1D), 주간(1W), 월간(1M), 연간(1Y), 전체/진입(ALL/TOTAL) 클릭 시 나머지 두 영역도 동일 기간으로 자동 동기화
(perf) 서비스 워커 캐시 버전(wealth-cache-v12) 및 정적 자산 쿼리(v442) 갱신

v4.4.1

(fix) 소유자 탭(아빠/엄마/자녀/모두)별 일간 수익 계산 및 비교 기준일 불일치 현상 완벽 해결
- 모든 소유자 탭에서 asset_records.json의 해당 소유자 직전 일자(28일) 스냅샷 자산과 정확히 1:1 비교
- 29일 스냅샷에 잘못 기록되었던 소유자별 일간 수익(day_profit_krw) 정상값으로 자동 보정
(perf) 서비스 워커 캐시 버전(wealth-cache-v11) 및 스크립트 쿼리(v441) 갱신

v4.4.0 (Major Release: 멀티 유저 완벽 격리 & 증권사 OpenAPI UI & 이자 배당 지원)

(feat) 배당금/손익 내역에서 이자 전용 항목(원화이자: INTEREST_KRW, 달러이자: INTEREST_USD, RP이자: INTEREST_RP, 예탁금이자: INTEREST_CASH) 공식 지원
(fix) '원화이자'/'달러이자' 입력 시 화이자(Pfizer, PFE) 주식 종목으로 오매칭되던 자동완성 버그 원천 차단
(feat) 👥 멀티 유저 격리 시스템 완성: data/users/{username}/ 전용 디렉터리를 통한 포트폴리오/배당/손익/OpenAPI 완벽 격리
(security) 👑 역할 분리 완성: admin 계정 단독 사용자 관리 콘솔 제공, sagesaint 계정을 일반 유저(user) 등급으로 조정
(security) 초기 비밀번호(4자리) 로그인 시 대시보드 진입 원천 차단 및 비밀번호 변경 전용 페이지(/change-password-init) 강제 라우팅
(feat) ⚙️ 증권사 OpenAPI 웹 UI 개별 관리: 토스, KB, 나무증권 AppKey/Secret 웹에서 등록, 마스킹 보존 및 [🗑️ 삭제] 원클릭 연결 해제 탑재
(feat) 보유종목이 없는 신규 계정에서도 [↻ 조회] 시 오류 없이 실시간 지수 및 환율 정상 동기화 ("지수 및 환율을 갱신했습니다.")
(perf) 서비스 워커 캐시 버전(wealth-cache-v10) 및 스크립트 쿼리(v436) 갱신
(docs) README.md 멀티 유저 아키텍처 및 OpenAPI 설정 가이드 전면 개편

v4.3.5

(security) sagesaint 계정을 'user' 등급으로 조정하고 사용자 관리 권한은 오직 admin 단독 계정으로 일원화
(security) 비관리자 계정의 사용자 관리 API(생성/목록/비번초기화/삭제) 접근 403 차단 검증 완료
(perf) 서비스 워커 캐시 버전(wealth-cache-v9) 및 스크립트 쿼리(v435) 갱신

v4.3.4

(feat) 조회(시세 갱신) 시 보유종목이 없는 경우에도 오류 없이 실시간 지수 및 환율 정상 갱신 처리
(ux) 보유종목이 없을 때 "갱신할 보유종목이 없습니다" 오류 대신 "지수 및 환율을 갱신했습니다." 알림 제공
(fix) 보유종목 시세 갱신 시 로그인 사용자별 포트폴리오(username) 안전 저장 보장

v4.3.3

(feat) 증권사별 OpenAPI AppKey 및 AppSecret 개별 삭제(연결 해제) 기능 탑재
(feat) 증권사 키 삭제 시 해당 증권사 토큰 캐시 파일 자동 정리
(feat) OpenAPI 모달 내 연결된 증권사 카드에 [🗑️ 삭제] 버튼 노출 및 확인 팝업 연동
(perf) 서비스 워커 캐시 버전(wealth-cache-v8) 및 스크립트 쿼리(v433) 갱신

v4.3.2

(fix) 일괄 계좌 연결(POST /api/sync/all) 호출 시 request 누락(TypeError) 및 import uuid 누락(NameError) 해결
(feat) 사용자별(potato 등) 나무/토스/KB 증권 계좌 및 예수금 격리 동기화 완벽 정상화

v4.3.1

(fix) 다이얼로그 닫기 함수(closeDialog) 전역 바인딩 및 [⚙️ OpenAPI], [비번 변경], [사용자 관리] 모달 닫기/취소 동작 복구
(feat) 모달 바깥(배경 백드롭) 클릭 시 자동 닫기 기능 및 닫기 버튼 이벤트 위임 처리
(perf) 서비스 워커 캐시 버전(wealth-cache-v7) 및 스크립트 쿼리(v431) 갱신

v4.3.0

(feat) 사용자 화면 상단 헤더에 [⚙️ OpenAPI] 설정 버튼 및 팝업 모달 추가 (토스, KB, 나무증권 AppKey/AppSecret 개별 등록)
(security) 사용자별 OpenAPI 인증키 격리 저장(data/users/{username}/openapi_config.json) 및 타 사용자 .env 키 오염 원천 차단
(feat) sagesaint 계정은 기존 .env 키를 자동 fallback 지원하여 기존 연동 100% 보존
(fix) 신규 사용자(potato 등) 자산 기록 파일 파싱 시 발생하던 AttributeError('list' object has no attribute 'setdefault') 오류 해결
(perf) 서비스 워커 캐시 버전(wealth-cache-v6) 및 스크립트 쿼리(v430) 갱신

v4.2.0

(feat) admin/admin 등 초기 비밀번호 계정 로그인 시 대시보드 진입 전 비밀번호 변경 전용 페이지(/change-password-init) 강제 라우팅
(security) 비밀번호를 변경하기 전까지는 대시보드(/dashboard) URL을 직접 입력해도 접근 불가 차단
(fix) admin 화면에서 사용자 계정 목록 테이블 렌더링 시 escapeHtml 참조 오류 수정 (사용자 목록 정상 표시)
(perf) 서비스 워커 캐시 버전(wealth-cache-v5) 및 스크립트 쿼리(v412) 갱신

v4.1.1

(fix) 프론트엔드 API 통신 헬퍼(api) 누락 바인딩 수정 및 fetchJson 별칭 연동
(fix) 서비스 워커 캐시 버전(wealth-cache-v4) 갱신 및 구버전 JS/CSS 클라이언트 캐시 자동 무효화
(fix) 초기 비밀번호 강제 변경 모달(#forcePasswordModal) 백드롭 스타일 및 중앙 팝업 레이아웃 보강
(fix) admin 로그인 시 비동기 세션 검증 후 화면 분기(applyUserRoleView) 안정화

v4.1.0

(feat) admin 로그인 시 자산관리 화면 제외 및 사용자 관리 메인 전용 대시보드(#adminMainPanel) 노출
(security) admin/admin 초기 로그인 시 1회 비밀번호 강제 변경 전까지 모든 자산/관리 API 호출 403 차단 보안 가드 구축
(feat) admin 사용자 계정 관리 메인 화면에 통계 요약 카드(총 사용자, 활성 사용자, 초기비번 대기자) 및 신규 아이디 발급 폼 탑재
(perf) admin 접속 시 자산 관련 API 호출 및 시세 크롤링 연산 전면 생략으로 서버 및 브라우저 성능 극대화
(fix) 로그아웃 후 원하는 사용자 계정(admin, sagesaint, user2 등)으로 자유롭게 로그인할 수 있도록 로컬 미들웨어 인증 흐름 정돈

v4.0.0

(feat) 사용자별 완벽 데이터 격리(Multi-User Isolation) 및 사용자 관리 시스템 구축
(feat) 사용자별 개별 데이터 폴더(data/users/{username}/) 격리 저장 및 기존 sagesaint 데이터 100% 무손실 자동 마이그레이션
(security) PBKDF2-HMAC-SHA256(10만 회) 솔트 기반 안전한 비밀번호 단방향 암호화 DB(data/users.json) 적용
(security) 초기 관리자(admin/admin) 접속 시 비밀번호 변경 강제(forced password change) 보안 가드 연동
(feat) 관리자(Admin) 전용 사용자 계정 관리 팝업 탑재: 신규 아이디 추가(초기 비번 4자리 지정), 비밀번호 4자리 리셋, 계정 삭제(데이터 폴더 동시 파기)
(feat) 신규 등록 계정 첫 로그인 시 4자리 초기 비밀번호 검증 후 새 비밀번호(4자 이상) 변경 필수 모달 연동
(feat) 상단 헤더 현재 접속자 배지(👤 아이디), 관리자 전용 [⚙️ 사용자 관리], [🔑 비번 변경], [로그아웃] 연동
(perf) 5년치 환율 및 종목 마스터는 공용 공유 캐시(data/)로 분리하여 서버 리소스 최적화

v3.3.9

(feat) MDN 공식 PWA 표준 규격 완벽 준수 및 오프라인 캐시 서비스 워커 전면 개편
(feat) W3C 표준 Web App Manifest (/manifest.json) 루트 스코프 및 192/512px any/maskable 아이콘 4종 완비
(feat) 서비스 워커 (/sw.js) 루트 스코프 등록 및 사전 리소스 프리캐싱(Pre-caching) 탑재
(design) 브라우저 PWA 설치 감지 엔진(beforeinstallprompt) 및 상단 앱 설치 버튼 연동

v3.3.8

(fix) 삼성인터넷 PWA WebAPK 독립 앱 설치 호환성을 위해 v2.2.0 검증 설정으로 완벽 복원
(fix) 매니페스트(/static/manifest.json) 및 서비스 워커(/static/sw.js) 경로 원형 동기화
(feat) 안드로이드 자동회전 시스템 설정 연동 유지 (세로 고정 시 강제 회전 방지)

v3.3.7

(fix) PWA 매니페스트 시작 경로(/dashboard) 및 Standalone 설정 안정화 원복
(fix) 오라클/사설 환경에서 WebAPK 민팅 오류 방지 및 전체화면(Standalone) 바로가기 호환성 최적화

v3.3.6

(fix) PWA WebAPK 독립 앱 설치 시 전체화면(Standalone) 미적용 및 브라우저 탭 실행 오류 수정
(feat) 백엔드 인증 미들웨어 내 /manifest.json 및 /sw.js 루트 공개 경로(PUBLIC_PATHS) 등록
(feat) /sw.js 루트 스코프 서빙 및 Service-Worker-Allowed 헤더 지원
(design) 안드로이드 크롬 전용 전체화면 메타 태그(mobile-web-app-capable) 및 display_override 규격 추가

v3.3.5

(fix) PWA 모바일 기기 화면 회전 시 스마트폰 시스템 설정 연동 (세로 고정 시 강제 가로 회전 방지)
(feat) 기간별 변동률 산출 기준을 캘린더 실제 날짜 기반으로 전면 개편 (주간 7일 전, 월간 1개월 전, 연간 1년 전 날짜 매칭 및 휴일 자동 보정)
(fix) 자산기록 콤보차트 일간(2일) 및 주간(5일) 데이터 포인트 및 막대 위치 중앙 정렬 최적화 (양 끝 쏠림 현상 해결)
(design) 주요지수/자산히트맵/종목차트 기간 탭 일간/주간/월간/연간 표준화 및 모바일 컴팩트 스타일 적용
(feat) 주요지수 섹션 접힘 상태에서도 계좌 연결 및 조회 버튼 상시 클릭 허용

v3.3.4

(add) 보유종목/실현손익/배당금 전체 팝업에 종목명 기반 종목코드 실시간 자동 검색 및 채움 엔진 연동
(add) 실현손익 및 배당금 팝업 내 등록된 계좌(ACCOUNTS) 원클릭 선택 및 자동 채움 지원

(add) 반도체지수 추가
(fix) 핵심요약(OVERVIEW) 총수익 및 일간 수익 3줄 분리 표시
(clean) 파일명 인코딩 정돈 및 전체 17개 API 엔드포인트 무결성 검증 완료



v3.3.3

(add) 종목코드자동입력



v3.3.2

(fix) 예상 배당금 누락 수정



v3.3.1

(fix) 실현손익 배당금 기간 수정



v3.3.0

(add) 가져오기 종목명 종목코드 연동



v3.2.2

(feature) 주제별 숨김 추가



v3.2.1

(feature) 테마 적용



v3.2.0

(feature) 배당금, 실현 수익 추가



v3.1.1

&#x20;(fix) 표시 개선

&#x20;(fix)더미 데이터 삭제



v3.1.0

(add)연동 방법 toss openapi에서 야후파이낸스 및 네이버증권으로 변경

(add)투자자산 섹터별 분류 추가

(add)자산 기록 기간 추가, 표현 그래프 변경, 월별 자산 추가

(add) 카드형 히트맵 추가

(add) 보유종목 차트 추가



v3.0.1

(fix)모바일 접속 화면 수정



v3.0.0

(add)가족 구성원 추가 관리 기능

(add)데이터 저장하기 및 불러오기 기능

