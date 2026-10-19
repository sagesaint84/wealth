# Wealth

## 정적 전송 최적화 — 개발·합성 검증 / 운영 미배포

기준 main `92956f620e9316b111b419f8c1d01891b7fe2562`에서 공개 `/static` JS/CSS(1KB 이상)에만 표준 gzip(level 5)을 적용한다. API·금융 응답·이미지·저장 형식·계산·스냅샷 순서·인증은 변경하지 않는다. Range·HEAD·ETag/304·MIME·gzip 거부를 보존하고 `Vary: Accept-Encoding`을 설정한다. 디스크 압축 캐시나 영구 파일은 생성하지 않는다.

같은 합성 홈 화면을 새 문서로 각 3회 측정했다(콜드 HTTP 캐시, SW 우회). PC 1280px/4Mbps/20ms에서는 첫 유효 자산 표시 중앙값 **4.06→1.62초**, 초기 준비 **4.56→1.87초**. 모바일 390px/2Mbps/40ms/CPU 4배 제한에서는 **8.54→4.39초**, **9.64→4.96초**였다. JS/CSS 본문 전송량은 **1,835,964→432,675바이트(-76.4%)**, 압축 해제 후 파일 내용은 동일하다. 운영 환경 실측이나 CPU·메모리 절감은 입증하지 않았다. Python 프로세스 CPU는 서버와 CDP 처리가 섞인 대리 지표이며 PC에서 압축 비용 증가가 관측됐다. API 수 차이는 측정 종료 시점 영향이 있어 중복 요청 감소로 주장하지 않는다.

기존 v2.1.3 P0의 가시성·요청 공유·prepare/commit·epoch 방어를 읽기 전용 검토했으며 복제하거나 합치지 않는다. 숨김 탭 렌더·프런트엔드 정리는 P0와 충돌 검토 후 별도로 진행한다. 독립 API의 기존 병렬화와 시세 갱신 성공→대시보드/주식 스냅샷→순자산 스냅샷 의존성은 유지한다. 불확실한 코드/CSS 삭제는 하지 않는다.

앱 버전 **2.1.2**, 정적 원문과 기존 revision **2.1.2-ipo-ui1**은 유지한다(전송 방식만 변경). 원본 P0 27개·기존 worktree를 보존한다. 로컬 집중 회귀 **253 PASS / 1 의존성 경고**, 실제 Chromium **15건** 포함(신규 전송 14건, 기존 관련 239건). Python AST·CI YAML·diff 검사 PASS. 전체 pytest·Oracle 접속은 하지 않았다. 최신 CI 성공 전 머지하지 않고 운영 배포 완료로 기록하지 않는다. 배포 시 고정 Digest 및 영구 데이터/Toss 마운트를 확인하되 롤백 이미지 생성·백업 저장은 하지 않는다.

## IPO·통합 캘린더 UI 보완 — 구현·검증 기록 / 운영 미배포

운영 기준 main `a17ef0681f95a2d874257b796eb25ac9f7840e22`의 PR #156 기능을 유지하면서 안내·출처·기본 링크 스타일 누락과 추가 버튼의 카드 헤더 정렬을 보완한다. 다크 테마 토큰·청약/상장/수익/손실/배당/수입/지출의 기존 색상 의미를 유지한다. 기업명·배지·출처·동작을 분리하고 긴 텍스트와 모바일 월 선택·가족 체크박스의 줄바꿈을 정리한다. 제외·복원·재수집·신청·배정·손익 연결·시장 원본·IPO ID·데이터 판정 로직은 변경하지 않는다.

앱 버전 **2.1.2**, core revision 유지. 수정한 layout CSS·IPO/캘린더 JS와 SW 캐시만 **2.1.2-ipo-ui1**. 별도 `codex/ipo-calendar-ui-polish`에서 작업하며 P0 원본 27개와 기존 worktree를 보존한다. 로컬 관련 회귀 **239 PASS / 1 의존성 경고**, 실제 Chromium **13건** 포함(신규 UI 320·390·768·1280px 4건). 기존 IPO 224건을 유지하고 초기 표시·증권사/과거 필터·공통 레이아웃 검증을 확대했다. 안내/복원 16px·기본 링크색에서 보조정보 10.5~11px·테마색으로 바뀐 합성 화면을 비교했으며 UI 콘솔 오류와 가로 넘침은 없었다. Python/JS·YAML 문법 및 diff 검사 PASS. 전체 pytest·Oracle 운영 확인은 미실행이다. 최신 CI 통과 후 승인 범위에서 Squash Merge하며 미완료 결과를 PASS로 기록하지 않는다. Oracle에는 접속하지 않고 `/docker/wealth`의 기존 Compose와 고정 이미지 파일을 사용하는 배포 명령만 제공한다. 롤백 태그 자동 생성·백업 이미지 저장은 하지 않으며 영구 데이터·Toss 마운트는 유지한다.

## PR #156 구현·검증 당시 기록 — 현재 머지·배포는 사용자 확인 기준

2026-10-19 사용자 운영 정책을 적용한다. Wealth IPO는 편리한 일정 참고·개인 신청 관리 도구다. 목록과 통합 캘린더에서 사용자별 일정을 제외하고, 공모주 **제외 목록 / 다시 표시**에서 복원한다. 제외는 원본 market JSON·IPO ID·가족별 신청·배정·연결을 수정하거나 삭제하지 않는다. 동일 ID·검증된 기업 코드·메타로고스 종목 키로 재수집된 일정은 제외를 유지한다. 날짜가 바뀌면 제외 목록에서 변경 안내를 보고 사용자가 복원한다. 새 날짜를 이유로 자동 재등장시키지 않는다. 제외 목록은 월·진행 상태 필터에 갇히지 않는다.

메타로고스 공개 캘린더는 월별 청약·상장 일정을 제공한다. 우선 활용을 검토했으나 이용 조건·제공 범위의 충분한 확인이 없어 기존 안정적인 수집 경로와 출처 우선순위를 유지한다. 새 외부 수집 경로를 추가하지 않는다. 출처·조회일과 참고용 안내를 표시하며 최신 공시 자동 판정을 완벽하게 보장하지 않는다. 자정 만료·이름 유사도 경고와 접수번호만으로 묶는 처리는 제거했다. 같은 제공자 종목 키 또는 기업 코드와 같은 공모 근거가 일치할 때만 화면에서 묶고 원본 ID별 신청을 보존한다. 운영 엘리스 레코드의 실제 동일성은 미확인이다.

앱 버전 **2.1.2**, core revision 유지. 실제 수정된 IPO·캘린더 JS 및 SW 캐시는 **2.1.2-ipo3**. 원본 v2.1.3 P0는 별도 보존한다. 로컬 관련 회귀 **224 PASS / 1 의존성 경고**(실제 Chromium 목록·캘린더 3건 포함), Python/JS 문법·diff 검사 PASS. 전체 pytest·운영 검증은 미실행이다. 최신 PR CI 통과 후 승인 범위에서 Squash Merge한다. Oracle 직접 접속·배포는 하지 않으며 고정 이미지 배포 명령만 제공한다. 롤백 태그 자동 생성·별도 백업 이미지 저장은 하지 않는다. 기존 이미지·영구 데이터 마운트는 보존한다.

## PR #155 개발 당시 기록 — 사용자 확인 기준 현재 머지·배포 완료

Draft [PR #155](https://github.com/sagesaint84/wealth/pull/155)의 `codex/ipo-schedule-status`에서 정정요구·철회로 무효화된 청약 일정의 캘린더 투영을 보완한다. 운영 v2.1.2와 원본 v2.1.3 P0 작업은 변경하지 않는다. 범위·검증 제한은 [PROJECT_STATE](docs/PROJECT_STATE.md)의 IPO 항목을 따른다.

Wealth는 사용 편의성과 자동화를 우선하는 개인·가족 자산관리 도우미이며 전문 세무·회계·신고 프로그램이 아니다. 합리적인 기본값으로 추정하고 추가 입력은 선택으로 둔다. 공식 근거가 충분한 예상 혜택은 자동 반영하되 제외할 수 있고, 부족한 경우 일반 배당을 기본으로 사용자 가정을 허용한다. 실제 입금·원천징수·금융 원본은 보존하며 기존 계산·저장 구조와 UI를 재사용한다. 별도 전문 세무 엔진·중복 UI·불필요한 확인 절차를 추가하지 않는다.

현재 앱 및 운영 배포 완료 버전은 **Wealth v2.1.2**다. 문서 정리 브랜치 `codex/v212-postdeploy-docs`, 기준 HEAD/main `255d135b8562b5569a11ac7c213787dccbcc2513`.

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
