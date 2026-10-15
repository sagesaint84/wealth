# Wealth Project State

> 이 문서는 Wealth 프로젝트의 **현재 상태를 복구하기 위한 첫 진입점**입니다.
> 새 대화, 새 작업 세션, 새 개발자가 시작할 때 가장 먼저 이 문서를 읽습니다.
> 세부 계획은 `docs/ROADMAP.md`, 비밀값·환경설정 원칙은 `docs/SECURITY_AND_CONFIG.md`를 참조합니다.

현재 운영 기준: Wealth v2.0.2, main `d98336aea7514cea205ef82ed184398015bff5f9` (PR #145 Squash Merge 및 Oracle ARM64 배포·운영 브라우저 확인 완료; 2026-10-14).

## 1. 현재 개발 상태

### PR #147 TXT/TSV evidence hotfix — 2026-10-15

기준 feature `e30190d`, Draft/Open PR #147의 native run 38710555716은 두 플랫폼 모두
은행 PNG 거래처명에서 실패했다. 기존 278 PASS는 로컬 회귀이며 native 전체 성공이 아니다.
같은 PSM 7 출력의 정상 TXT와 음절별 TSV를 합성해 기존 경로의 실패 4건을 먼저 재현했다.
현재 PC에는 실제 Tesseract/Docker가 없어 실제 native 결과는 새 커밋의 Actions로 확인한다.

최소 보정은 가계부의 기존 한 행 재인식만 대상으로 한다. 한 번의 Tesseract 실행에서 TXT/TSV를
동시에 만들고, TXT 문장을 보존하며 TSV로 위치·신뢰도를 검증한다. 비공백 문자열은 문자 일치
비교에만 사용하고 후보 문자열을 만드는 데 쓰지 않는다. 정상 단어 공백은 유지하고, 빈/복수 행·
금액/숫자·불명 특수문자·서로 모순되는 근거는 미확인이다. 금액은 TXT/TSV 양쪽 strict 해석과
기존 전체 페이지 금액/부호 근거가 충돌하지 않아야 한다. 항상 review_required·Owner/계좌 미추정이다.

각 출력은 private 디렉터리의 0600 파일이며 20KB/UTF-8/TSV 열을 검사하고 symlink를 거부한다.
crop/TXT/TSV는 finally에서 제거하며 부분 생성 후 도구 오류/timeout도 정리한다.
8회/12초/3초/55초/75초 및 CPU·메모리·동시 실행 상한은 유지한다.
국민연금 파서·공통 decoder·합성 fixture·smoke 기대값·금융 API/저장·JS는 변경하지 않는다.
APP_VERSION 2.0.2, 원본 감액배당 worktree 및 운영 이미지 d98336a는 유지한다.
최종 격리 집중 **308 passed / 0 failed / 0 skipped / 2 warnings**, 148.53초(기존 278 + 신규 30),
Python syntax·git diff --check PASS, 테스트 임시 경로 제거 확인. JS는 미변경이다.
Native 정확도는 새 커밋의 실제 Actions 결과로 구분한다.
전체 pytest·O2 저장·공모주 OCR·Merge·Deploy는 진행하지 않는다.

### PR #147 bounded line OCR 2차 보정 — 2026-10-15

Draft/Open PR #147의 `61f8740` native run 38706993038은 두 플랫폼 모두 은행 PNG 거래처명
정확 일치에서 실패했다. 은행 유형/2행 조건 및 기존 국민연금 worker는 통과했으나
금액·잔액·은행 PDF·카드 JPG/PDF는 완료로 간주하지 않는다. 아래 245 PASS는 로컬 회귀 이력이다.

가계부에서만 원본 페이지 TSV의 좌표와 동일한 정규화/방향 보정 이미지의 단일 행을 PSM 7로
재인식한다. 공통 decoder에는 페이지별 opt-in hook만 추가하며 국민연금은 사용하지 않는다.
이미지/TSV 크기 일치, 폭 320px 이상, 최대 16M pixels, bbox/글자 높이/잘림/다른 행과 겹침을
확인한다. 원본 confidence 30 미만은 재시도하지 않고, 재인식 confidence 90 미만·다중 행·숫자/부호
충돌은 미확인이다. 정상 단어 공백을 문자열 치환으로 합치지 않으며, 날짜/시간이 포함된 복합 행은
기존 파싱 경로를 유지한다. 합계·잔액·거래처·금액의 역할을 서로 바꾸지 않는다.

문서 전체 최대 8회/재인식 누적 12초/1회 3초/출력 20KB, 도구 실행 전체 기한 55초다.
외부 75초 회수·CPU 60초·512MiB·동시 슬롯 2개는 유지하고, 초과/timeout 시 저장 없이 실패한다.
페이지 교체 전에 좌표를 적용해 다른 PDF 페이지를 재사용하지 않으며 crop은 0600으로 생성/제거한다.
새로운 금융 writer·사용자 데이터 경로는 없고, 전부 review_required·Owner/계좌 미추정이다.

기존 합성 입력과 모든 exact-value 단언은 유지한다. 최종 격리 집중 **278 passed / 0 failed /
0 skipped / 2 warnings**, 134.14초(기존 245 + 신규 33), Python syntax·git diff --check PASS.
생성한 테스트 임시 경로 제거 확인. JS는 미변경이다. Native CI 결과는 이 커밋의 실제 Actions로
별도 확인하며 Windows의 실제 Tesseract·로컬 Docker·전체 pytest는 미실행이다.
APP_VERSION 2.0.2 및 운영 이미지 d98336a는 유지한다. 원본 감액배당 worktree는 변경하지 않으며
O2 저장·공모주 OCR·Merge·운영 배포는 진행하지 않는다.

### PR #147 Native OCR hotfix — 2026-10-15

현재 `wealth-ocr` / `codex/v202-ledger-ipo-ocr-import`의 Draft PR #147은 미병합·운영 미배포다.
기존 feature commit `b55e1f4d09b14880012a83ab88ab14c47e8afcf9`의
[native CI](https://github.com/sagesaint84/wealth/actions/runs/38705054241)는 두 플랫폼 모두
이미지 빌드·Chromium·국민연금 PNG/PDF OCR 이후 은행 PNG 문서 유형 단언에서 실패했다.
이전 PENDING과 221 PASS 기록은 제출 직전 로컬 이력이며 native 가계부 성공을 뜻하지 않는다.

공백이 들어간 합성 날짜 TSV 3건의 unknown 분류와 음절 분리 거래처의 무검증 채택 1건을
수정 전 재현했다. 월/일 앞뒤 수평 공백만 허용하고 거래처 음절은 합쳐 복원하지 않는다.
합성 화면은 Bold 80px/금액-단위 간격으로 개선하되 금액과 정확한 기대값을 바꾸지 않는다.
유형 실패 때에만 실제 decoder의 Boolean 구조 근거를 출력하며 원문·preview JSON은 출력하지 않는다.
기존 CI의 전체 OCR 문자열은 확인되지 않아 과거 실패의 모든 원인을 공백으로 단정하지 않는다.
이번 수정 후 실제 은행 PNG/PDF·카드 JPG/PDF 성공 여부는 새 native CI로 확인해야 한다.

hotfix 최종 격리 집중 검증은 **245 passed / 0 failed / 0 skipped / 2 warnings**, 137.58초다.
기존 221건과 신규 24건을 포함하고 Python syntax·git diff --check PASS, 테스트 임시 경로 제거 확인.
JS 미변경으로 Node 재검사는 생략했다. 새 native CI 결과는 이 커밋의 실제 Actions를 따른다.
로컬 실제 Tesseract·Docker·전체 pytest는 미실행이며,
국민연금 도메인·금융 계산·저장 API·공통 decoder·APP_VERSION 2.0.2는 유지한다.
감액배당 원본 worktree는 변경하지 않는다. O2 저장·공모주 OCR·Merge·Deploy는 범위 밖이다.

### Phase O1.2 — OCR Draft PR 검증 준비 (운영 미배포, native CI PENDING)

`wealth-ocr` / `codex/v202-ledger-ipo-ocr-import`, 기준 main
`d7e06de24bc48e728b89adec09fa75da697d22e5`에서 O1/O1.1의 15개 변경을 보존했다.
이번에는 ops 3개와 기존 문서 2개를 수정하고 `tests/test_pension_ocr_smoke.py` 1개를 추가했다.
앱/파서/저장 함수/JS/CSS/Dockerfile/workflow는 이번 단계에서 변경하지 않았다.
APP_VERSION 2.0.2 유지. 기존 PR #145/#146 운영 완료 기록과 이번 미배포 개발 작업을 구분한다.
운영 이미지는 사용자 제공 기록의 `ghcr.io/sagesaint84/wealth:d98336a`이며 이번 작업에서 운영 서버에 접속하지 않는다.
이 영역은 Draft PR 제출 직전 기록이고 이후 Commit/Push/PR 및 최종 native CI 상태는 해당 PR/Actions를 따른다.
공개 fixture와 정확한 기대값은 화면 예시와 연관되지 않는 가상 숫자 패턴으로 변경했으며,
실거래 원본·실명·계좌번호를 사용하지 않는다. 아래 O1/O1.1 기록은 각 구현 당시 이력이다.
가상 값 교체 후 PR 제출 직전 재검증: **221 passed / 0 failed / 0 skipped / 2 warnings**, 141.84초.
Python 문법·Node 문법·git diff --check PASS. 격리 테스트 임시 디렉터리 정리 확인.
아래 155.94초 결과는 최초 O1.2 구현 시점의 기록이다. 전체 pytest는 실행하지 않았다.

- 생성: 기존 공개 NanumGothic/Pillow를 사용한다. 은행은 다크 PNG와 스캔 PDF,
  카드는 화이트 JPEG와 스캔 PDF이며 모두 연도 없는 10월 14일/13일의 두 거래를 담는다.
  은행 원금액은 +1,234,567원 / -234,567원, 거래 후 잔액은 11,234,567원 / 11,000,000원,
  상단 현재 잔액은 11,000,000원이다. 카드 승인금액은 12,345원 / 23,456원, 상단 합계는 35,801원이다.
  이름과 숫자는 허구이며 생성 결과는 CI 임시 경로에만 둔다.
- 기존 국민연금 smoke 전체를 먼저 실행한 뒤 실제 가계부 preview coordinator를 호출한다.
  production worker가 Poppler/Tesseract와 공통 추출/파서를 실행하며 JSON의 정확한 값과 두 행을 비교한다.
  PDF 문자층 부재, 거래금액/잔액/합계 분리, 부호, 거래처, 부분 날짜와 year=null,
  `year_missing`·검토 상태·Owner/계좌 null·OCR 좌표를 요구한다. 오인식 값 수용이나 파서 변경은 없다.
- 금융 안전성: 실제 데이터 경로 대신 private 합성 경로를 설정하고 ledger/portfolio 센티널 파일의
  byte 불변 및 추가 사용자/금융 경로 미생성을 검사한다. 요청별 OCR 입력이 정리됐는지와
  smoke의 입력 복사본이 제거됐는지를 구분해 확인한 후 PASS를 출력한다. 원래 read-only fixture는
  CI 작업 수명을 따르며 smoke가 변경·삭제하지 않는다. 원문·미리보기 JSON·개인정보 artifact는 출력하지 않는다.
- CI 재사용: `ops/pension-ocr/**` trigger와 동일한 native amd64/arm64 이미지 빌드/실행 단계가
  이미 있으므로 workflow를 수정하지 않는다. 기존 네트워크 차단·read-only·cap-drop·no-new-privileges·
  비특권 UID·private /tmp 조건, 국민연금/Chromium 검증을 보존하며 이미지 중복 빌드나 새 패키지는 없다.
- 로컬 실제 실행 결과: **221 passed / 0 failed / 0 skipped / 2 warnings**, 155.94초.
  기존 O1.1 178건 모두 유지하고 신규 smoke 계약/생성/실패/정리 검증 43건 통과.
  기존 국민연금·가계부 CSV/Excel·IPO·Chrome 320/390/1280px 세 테마 회귀를 포함한다.
  새 생성 테스트는 Pillow의 내장 대체 폰트로 인코딩/파일 구조만 검사하며 한국어 인식률 검증이 아니다.
  실제 Tesseract가 없는 Windows에서 도구/preview 응답을 mock으로 검사한 결과를 native 성공으로 기록하지 않는다.
- 실제 AMD64 OCR: **PENDING**. 실제 ARM64 OCR: **PENDING**. Docker build/CI/전체 pytest는 실행하지 않았다.
  후속 PR의 기존 native job에서 은행/카드 정확한 금액·문자 인식이 실패하면 CI가 실패해야 하며,
  원인을 조사하기 전에 기대값/파서를 완화하지 않는다. 기관별 형식·저해상도/잘림·운영 자원 검증과
  연도/Owner/계좌 확인·중복 대조·revision/RMW 설계도 O2 저장 구현 전의 미완료 항목이다.
- 이번 두 격리 테스트 디렉터리는 생성/정리를 같은 TemporaryDirectory 수명으로 제한했고 실제 제거를 확인했다.
  이전 O1/O1.1 정책 차단 디렉터리 두 개는 재사용·삭제 재시도하지 않았다.
  PR 제출 이후 상태는 해당 Draft PR/Actions를 따른다. Merge/Deploy는 이번 작업 범위 밖이다.
  아래 O1.1의 native 확장 계획은 당시 이력이며 위 구현으로 보완됐다.

### Phase O1.1 — 가계부 OCR 날짜·금액 안전성 보완 (미커밋·운영 미배포)

동일 `codex/v202-ledger-ipo-ocr-import` / `wealth-ocr`, HEAD
`d7e06de24bc48e728b89adec09fa75da697d22e5`에서 O1의 수정 8개·신규 7개 상태를 유지했다.
이번 보완은 기존 15개 안에서만 수행하며 국민연금 도메인 파서·금융 저장 함수·공모주 기능은 변경하지 않는다.
아래 O1 검증 기록은 최초 구현 시점이며 현재 회귀 결과는 다음과 같다.

- 최종 집중 실행 **178 passed / 0 failed / 0 skipped / 2 warnings**, 130.83초.
  기존 O1 122건 모두 유지, 추가 56건(파서/안전성 47 + Chrome 9) 통과.
  국민연금 document/import/API·Chrome, 가계부 CSV/Excel 중복 방지, IPO 신청·배정 회귀 포함.
  기존 Starlette/httpx 안내와 Pillow 픽셀 경고는 유지하고 경고를 전역 억제하지 않았다.
- 날짜 계약: `transaction_date_parts`(year/month/day)와 `review_reasons`를 기존 행에 추가한다.
  연도 없는 `10월 14일`은 month/day만 보존하고 year 및 `transaction_date`는 null,
  `year_missing`·검토 필요를 표시한다. 촬영일/발급일/조회일/현재 연도를 대입하지 않는다.
  명시된 거래 연도 또는 조회 기간에서 일치하는 날짜가 정확히 하나인 경우만 ISO 날짜를 제공한다.
  기간 불일치·중복/충돌 연도·페이지 경계에서는 임의로 연도를 채우지 않는다.
- 금액 계약: 부호 없는 금액은 방향 미확인이다. 쉼표·자리수가 비정상인 토큰을 보정하거나
  정상 숫자 접미부만 사용하지 않는다. 거래 후 무표시 금액은 잔액/추가 거래 모두 확정하지 않는다.
  잔액의 연결 근거가 없으면 null로 유지하며 상단 잔액·카드 합계를 제외한다.
  같은 날짜·거래처·금액의 정상 복수 거래를 삭제하지 않는다.
- 이체는 `bank_transfer` 후보로만 구분하며 수입/지출로 확정하지 않는다. 카드 취소·환불·대금 납부는
  방향 unknown·검토 필요를 유지한다. 문서 유형 제목과 날짜/금액 근거가 부족하거나 충돌하면
  사용자가 유형을 선택했어도 unknown을 반환한다. 기관별 모든 화면 구조를 지원한다고 주장하지 않는다.
- TSV 안전성: 폭 320px 미만, 단어 높이 12px 미만, 가장자리 접촉, 신뢰도 80 미만 등은
  `review_reasons`로 구분하고 관련 금액/거래처를 null로 둔다. 좌표 크기 정보가 없으면 확인 불가 경고를
  제공한다. 이 기준은 휴리스틱이며 고해상도/높은 신뢰도도 정확도 보증이 아니다. PDF 래스터의 크기가
  원래 삽입 이미지 해상도를 보증하지 않으며 모든 숫자 누락·잘림을 자동 탐지할 수 없다.
- UI는 미완성 날짜를 `10월 14일 · 연도 미확인`으로 표시하고 이체 후보를 구분한다.
  신규 Chrome 9건에서 세 테마·세 너비, 금액/잔액 분리, 읽기 전용, overflow를 검증했다.
  APP_VERSION 2.0.2 유지, JS만 `2.0.2-o1.1`, 미변경 CSS는 `2.0.2-o1`이다.
- preview의 금융 writer 및 금융 경로 생성 함수 호출 0, 합성 금융 JSON byte 불변,
  새 사용자 디렉터리 생성 0, 비공개 임시 파일 cleanup과 로그 미노출을 회귀 테스트로 확인했다.
  O1의 인증/동일 출처/no-store/자원 제한/timeout과 사용자 A/B 응답 분리도 유지한다.
- 실제 사용자 문서·개인정보는 사용하지 않았다. 로컬 Tesseract 부재로 실제 OCR은 미실행이며
  Windows mock/합성 및 네이티브 Chrome 검증 결과를 운영 OCR 성공으로 해석하지 않는다.
  전체 pytest·Docker·GitHub Actions·Commit·Push·PR·Merge·Deploy 미실행.
- O1에서 남은 격리 테스트 디렉터리는 재사용·삭제 재시도하지 않았다. 이번에 만든 테스트 부모
  디렉터리도 삭제가 `blocked by policy`로 거부되어 남아 있다. 정책을 우회하지 않았으며
  요청별 private OCR 임시 파일 cleanup 테스트 결과와 부모 테스트 디렉터리 정리 상태를 구분한다.

네이티브 OCR 검증 확장 계획(이번에는 코드 변경 없음): 기존 `ops/pension-ocr/generate_fixtures.py`에
공개 Nanum 폰트로 가상 은행(다크)/카드(화이트) PNG/JPEG 및 이미지 PDF를 생성한다.
월·일만 있는 행, 명확한 연도/기간, 상단 합계, 부호/잔액 분리, 낮은 폭·잘린 행의 음성 사례를 포함한다.
기존 `smoke.py`의 국민연금 검사는 그대로 두고 실제 `app.services.ledger_document` worker의 JSON에서
후보 개수·금액·부분 날짜·검토 상태·Owner/계좌 null·원문 미노출을 검사하는 경로를 추가한다.
기존 native amd64/arm64 러너가 빌드한 같은 이미지를 재사용하고 네트워크 차단·read-only fixture 마운트·
비특권 사용자·임시 디렉터리·고정 오류 출력·실패 시 CI 차단을 유지한다. QEMU·새 이미지 중복 빌드·
실제 금융 볼륨·Secrets·원문 artifact는 사용하지 않는다. workflow의 engine/ledger/tests path 감지도
추가 검토해야 한다. 현재 workflow 및 smoke 파일은 수정하지 않았다.

O2 저장 구현은 아직 진행하지 않는다. 실제 Tesseract/native ARM64 검증, 사용자 연도·Owner·계좌 확인,
불명확한 행 수정, 은행 카드대금과 카드 승인 중복 방지, idempotency 및 revision/RMW 충돌 계약이
선행 검토 사항이다. OCR 출력만으로 금융 기록이나 잔액을 갱신하지 않는다.

### Phase O1 — 가계부 이미지/PDF 읽기 전용 미리보기 (미커밋·운영 미배포)

2026-10-15 개발 기준은 main `d7e06de24bc48e728b89adec09fa75da697d22e5`다.
`codex/v202-ledger-ipo-ocr-import` / `C:\Users\USER\Desktop\wealth-ocr`를 별도 worktree로 사용하며,
원래 `codex/v202-capital-dividend-evidence-a`의 4개 미커밋 파일은 읽기·복사·수정하지 않는다
(보존 확인에는 Git 상태와 파일 SHA256만 사용). 상단 운영 배포 설명과 기존 PR #145/#146 완료 이력은
기존 운영 이력이며 이번 개발 변경의 배포를 뜻하지 않는다.

- 진입점: 가계부 기존 가져오기 창 → 이미지/PDF 가져오기 → 자료 종류/파일 선택 → 읽기 전용 후보 목록.
  저장 버튼·저장 API·공모주 OCR은 없다. 기존 CSV/Excel/텍스트 가져오기는 유지한다.
- API: `POST /api/ledger/document-import/preview?document_type=auto|bank_transactions|card_transactions`.
  파일 bytes를 요청 본문으로 받는다. 인증을 먼저 확인하고 Origin/Referer의 출처를 서버 요청 URL과
  대조한다. reverse proxy에서 scheme/host 전달 설정이 맞는지는 배포 전 확인해야 한다.
  결과는 `no-store`이며 서버 캐시·preview ticket·사용자 디렉터리·금융 저장 경로를 사용하지 않는다.
- 데이터: `document_type`, `status=review_required`, `rows`, `warnings`.
  행은 `transaction_date`, `transaction_time`, `counterparty`/`merchant`, 정수 십진 문자열 `amount`,
  `direction=inflow|outflow|unknown`, 별도 `balance_after`, 거래 유형 후보,
  `source_location`(페이지/행/TSV 좌표/추출 방식)과 검토 사유를 제공한다.
  Owner·계좌 ID는 null이며 income/expense나 정확한 거래로 확정하지 않는다.
- 파서 범위: 연도 포함 날짜, 원 단위 금액, 날짜별 은행 행과 카드 행의 제한된 순차 구조.
  상단 현재 잔액·사용합계·날짜 구분행은 거래로 저장하지 않는다. 낮은 TSV 신뢰도·비정상 숫자는
  금액 미확인, 부호 누락은 방향 미확인으로 둔다. 페이지 경계에서 날짜를 이어 붙이지 않는다.
  반복 후보는 경고만 제공한다. 모든 잘림·오기·기관별 양식의 자동 판별을 보장하지 않는다.
- 추출: `document_extraction.py`에 기존 Poppler/Pillow/Tesseract 처리만 공통화했다.
  국민연금 전용 파서 및 한글 판정 기준은 유지하며 가계부는 날짜/금액 단서를 사용한다.
  PNG/JPEG, 텍스트/스캔/혼합 PDF에 대한 합성 처리 경로를 검증했다.
- 보안/자원: 최대 10MiB, 8페이지, 1,600만 픽셀; 암호화 PDF·다중 프레임 거부.
  입력·중간 파일은 private 임시 디렉터리(0700)와 POSIX 0600 권한을 사용하고 원문 로그/영구 저장은 없다.
  분석 75초, 개별 외부 명령별 timeout, Linux worker의 CPU/메모리/파일 크기 제한을 사용한다.
  동일 웹 프로세스의 국민연금·가계부는 동시 실행 2개를 공유한다. 다중 worker 전체 합산 자원 제한은
  미구현이며 RLIMIT은 자식 전체의 합산 메모리를 보장하지 않는다. Linux timeout은 worker 프로세스
  그룹을 회수하고 Windows는 직접 자식만 종료한다. UI 닫기 후 서버 작업은 완료/timeout까지 지속될 수 있다.
- 금융 영향: 신규 preview의 ledger/portfolio writer 미호출, 금융 파일 불변, 새 사용자 디렉터리 미생성,
  사용자 A/B 응답 분리와 임시 파일 정리를 합성 테스트로 확인했다. 금융 계산·잔액·IPO 저장은 변경 없다.
- 실제 실행 결과: 집중 pytest **102 passed / 0 failed / 0 skipped**, 신규 가계부 Chrome
  **11 passed / 0 failed / 0 skipped**. 기존 국민연금 decoder/import/API 및 CSV/Excel·IPO 신청/배정
  회귀가 집중 결과에 포함된다. 320/390/1280px와 Purple/White/OLED 미리보기·지연 응답 폐기를 확인했다.
  집중 pytest의 경고 2건은 설치된 Starlette/httpx 안내와 기존 Pillow 픽셀 경고이며 전역 경고 무시는 없다.
- 추가 국민연금 가져오기 Chrome 회귀 **9 passed / 0 failed / 0 skipped**. 이번 집중 실행 총합은
  **122 passed / 0 failed / 0 skipped**이며 전체 pytest 결과가 아니다.
- 미검증: 로컬 Tesseract 부재로 OCR 출력은 mock이다. 실제 OCR 인식률·새 Linux/ARM64 worker·운영 자원·배포,
  전체 pytest는 확인하지 않았다. Python 문법·신규 JS의 `node --check`·`git diff --check` PASS,
  원래 감액배당 worktree 4개 파일의 작업 전후 SHA256 일치를 확인했다.
  APP_VERSION 2.0.2 유지, 신규 JS/CSS만 `2.0.2-o1` revision. CI/Commit/Push/PR/Merge/Deploy 미실행.

O2에서는 읽기 전용 후보와 저장 모델을 분리한 채 Owner/계좌 명시 선택, 행 수정·선택,
기존 `file_import_identity` 중복 대조, revision/RMW 충돌 검사, 사용자 최종 확인 후 저장을 설계해야 한다.
은행 카드대금과 카드 승인 내역의 중복 지출 방지를 먼저 결정하며 OCR 잔액으로 계좌 잔액을 자동 갱신하지 않는다.

### 배당 실제/예상 모드 후속 수정 — PR #145 운영 배포 및 브라우저 검증 완료

개발 이력: `codex/v202-dividend-mode-fix`는 기준 main `c35060b3e61cebac3d17f43fa0df8039a7ab03e3`에서 시작했다. 변경 파일 10개의 Commit `11b25f21adc16a3fddefe60c3774db5a882811b2`를 [PR #145](https://github.com/sagesaint84/wealth/pull/145)로 Squash Merge하여 현 main `d98336aea7514cea205ef82ed184398015bff5f9`에 반영했다. 사용자가 로컬 main Fast-forward·작업 브랜치 로컬/원격 삭제를 확인했다. PR #144의 Draft·운영 v2.0.1 설명은 과거 시점의 이력이다.

PR #145 [GitHub Actions](https://github.com/sagesaint84/wealth/actions/runs/38535666859)는 native amd64/arm64 두 Job 모두 Success. Oracle ARM64의 배포 이미지 `ghcr.io/sagesaint84/wealth:d98336a`에서 정확한 Git revision, 아키텍처, 정적 asset revision, 데이터/Toss 마운트 및 HTTP 307을 확인하고 rollback-before-pr145 태그를 보존했다. 사용자 보고로 실제/예상 배당·자산 세금 Workspace 운영 화면 정상도 확인했다. APP_VERSION은 2.0.2를 유지한다.

사용자 직접 확인한 현재 검증 결과:

- 실패했던 320/390/1280px Chrome 6개 재검증: 6 PASS / 0 FAIL / 0 SKIP.
- 집중 pytest(Chrome 회귀 포함): 40 PASS / 0 FAIL / 0 SKIP.
- Windows 전체 pytest: **3,707 passed / 5 skipped / 0 failed / 5 warnings**,
  **798 subtests passed**, 1182.80초.
- 격리 소스 검증·Python/JavaScript 문법·git diff --check PASS. 테스트 임시 소스 정리 완료.

전체 pytest 초기 8건 실패는 로컬 Python에 Pillow가 없었던 환경 문제다.
requirements.txt에 지정된 Pillow==12.3.0 설치 후 해당 8건과 전체 pytest가 통과했으며
소스 코드 결함으로 분류하지 않는다. PR #145의 CI·Merge·Deploy·운영 브라우저 점검은 위 기록대로 완료됐다. Codex는 최종 코드 감사에서 테스트를 재실행하지 않았다.
이전 집중 결과 33 passed / 6 failed (174.53초)는 보완 전 이력이며 현재 실패 상태가 아니다.

정적 리뷰에서 오래된 요청의 finally가 새 요청의 버튼을 활성화하는 경합을 확인하여
유효 revision/Owner만 완료 상태를 변경하도록 보완했다. 모드/Owner 변경 시 요청을
무효화하고 버튼·상태를 초기화한다. Observer는 모드/자산 탭의 class만 감시하고
페이지 복원·전환은 기존 wealth:view 이벤트를 사용한다. What-if Observer는 body 전체와 결과 DOM 이동을
감시하지 않는다. 역순 응답, 계산 중 모드/Owner 전환 및 세금 탭 왕복 합성 테스트를
추가했으며 사용자 재검증에서 통과했다. request revision 및 finally 방어는 유지한다.

기존 catPanelTax가 먼저 생성되면 taxWorkspaceBody가 없어서 초기 mount가 중단되는 경로와,
상품 정보 renderer가 panel.replaceChildren()으로 분석 workspace까지 제거하는 충돌을 보완했다.
기존 세금 패널 하나에 assetTaxInformation(상품 정보), taxWorkspaceHeader,
taxWorkspaceBody(What-if·가족 위험·가상 배분)를 분리한다. 정보 renderer는 자기 영역만
갱신하고 분석 패널 노드·입력 초안은 유지한다. 위 사용자 테스트가 보완 후 통과했으며
운영 성공 범위는 상단의 CI·컨테이너·브라우저 검증 결과를 따른다.

실제 배당 모드는 입금 기록·수령액·기존 차트·가져오기·편집을 유지한다.
배당 화면의 추가 배당 What-if/세금 대시보드는 예상 모드에서만 표시한다.
별도 세금 workspace는 기존 가족 screening·가상 배분·What-if 기능을 유지한다.
What-if 표시·이동 제어는 한 모듈이 맡고, 세금 도구가 배당 탭 active 상태를 잠시
바꾸던 경로를 제거한다. Owner/모드 전환 이후 이전 응답은 결과에 반영하지 않는다.
앱/서비스워커 버전은 2.0.2 유지. wealth.js와 family-risk JS는 2.0.2-r7,
What-if JS는 기존 후속 변경의 2.0.2-r6을 유지한다. application-assets-revision은
core JS와 같은 2.0.2-r7이며 나머지 리소스는 유지한다.
Chrome 회귀 코드는 기존 파일에 320/390/1280px 초기 실제 진입, 반복 전환, 세금 탭
방문 후 복원, 새로고침 및 데스크톱 크기 전환을 추가했다. 이번 보완에는 workspace 단일성,
상품 카드 유지, 재렌더링 후 분석 노드·What-if 초안 보존 검증도 사용자 실행에서 통과했다.

캐시 정적 감사: HTML 참조·asset metadata·정적 테스트의 revision은 일치한다.
서비스워커는 JS/CSS를 캐시 대상에서 제외하고 HTML을 network-first로 제공한다.
온라인 새 문서 로드는 새 revision URL을 사용하지만 이미 열린 탭·오프라인 HTML은 이전
참조를 유지할 수 있다. 운영 브라우저에서 해당 모드·탭 표시 정상은 확인했으나 모든 클라이언트의 오프라인 HTML과 캐시 경로까지 검증한 것은 아니다.

감액배당·비과세 계산은 구현하지 않는다. 기존 `dividend_official_sources.py`의
OpenDART 목록·문서 조회와 `dividend_confirmed_disclosures.py`의 확정 현금배당 파싱은
공시 근거 경로로 검토할 수 있지만 비과세 적격 판정의 근거로 바로 사용하지 않는다.
추가 설계에는 공시의 재원·감액 성격, 지급/귀속 시점, 투자자별 적용 요건,
2026년 적용 법령·예외의 공식 확인, 미확인 상태와 신고/원천징수 구분이 필요하다.
이번 작업에서 법령 확인이나 새로운 세금 규칙 등록은 하지 않았다.

### v2.0.2 PR #144 당시 기록

당시 개발 브랜치는 `codex/v201-pension-tax-tab-hotfix`, 기준 main은 `fe0af51640c60ac6919a71186093040b6a8c5b88`이었다. [PR #144](https://github.com/sagesaint84/wealth/pull/144)는 2026-10-14 조회 당시 Draft/main 반영 전이었다. 당시 개발 소스의 APP_VERSION·HTML·service-worker cache는 2.0.2, layout CSS revision은 2.0.2-r5였다. 당시 main·Oracle ARM64 운영은 v2.0.1을 유지했고 v2.0.2 운영 검증·배포는 미실행이었다. 이후 사용자 보고로 PR #144 머지·v2.0.2 운영 배포 완료를 확인했으며 이번 배당 수정의 배포 완료를 뜻하지 않는다.

v2.0.2 사용자 확인 Windows 검증: 전체 pytest **3,699 passed / 5 skipped / 0 failed / 5 warnings**, **798 subtests passed**, Python·JavaScript 문법 **PASS**. [Actions run 38493482329, attempt #8](https://github.com/sagesaint84/wealth/actions/runs/38493482329/attempts/8)은 Success이며 Toss auth native amd64/arm64 모두 성공했다. 네이티브 Docker 빌드·network-disabled Chromium·Poppler/Tesseract kor/eng/osd·합성 한국어 OCR·production document worker smoke를 검증했다. 실제 개인 국민연금 문서를 사용하지 않았고 실제 양식 인식률·Oracle 자원 사용량·이미지 크기 측정은 완료하지 않았다. 이 문서 정리에서는 실행 검증을 반복하지 않았다.

### 이전 v2.0.0 작업 당시 기록 (현재 상태 아님)

기준 main `55e3dcb`에는 Toss WTS ARM64 인증 런타임 PR #141까지 반영됐다. `codex/v2-ui-cleanup`의 v2.0.0 표시, 절세계좌/가져오기 UI와 자산 구성 표시 정리는 구현을 완료했으며, 27개 파일 commit·push 및 PR #142 생성이 완료됐다. HEAD는 `d847dc5f3127c50842bbaa704e890a5db12e6e30`이다. 다음 기능은 미정이며 후보와 보류 항목은 `docs/ROADMAP.md`에 둔다.

사용자 확인 Windows 검증: 전체 pytest **3,568 passed / 5 skipped / 0 failed**, **798 subtests passed**; 신규 Chrome UI 테스트 **14 passed**. GitHub Actions 결과, merge, GHCR 게시 및 Oracle 운영 배포 상태는 별도 검증이 필요하며 Windows 결과로 완료를 판단하지 않는다.

### 현재 제품/운영 기준

- UI는 dialog sizing/hierarchy, 모바일 density, 자산/투자 탭 복원과 공용 8색 picker 및 직접 색상 편집을 사용한다.
- 가져오기 기본계좌와 가계부 defaults·은행이자 mirror는 기존 사용자별 저장 계약을 유지한다.
- 예적금 납입 이력과 금융 JSON atomicity는 별도 서비스의 계약이며 이번 UI 정리에서 변경하지 않는다.
- IPO는 DART/OpenDART·KIND·NAVER/Npay·Metalogos 160과 기존 시장 기록을 사용한다. KIS는 일반 broker 기능에만 남으며 IPO credential/token 요청에는 쓰이지 않는다.
- Docker Toss QR 인증은 별도 venv의 Playwright/Chromium과 공식 v0.50.3 vendor helper를 사용한다. 사용자별 세션·비공개 확인 문자·Linux subreaper guard 제약은 [인증 런타임 문서](../ops/toss-auth/README.md)를 따른다.
- 관련 main PR에는 네이티브 AMD64/ARM64 프로세스 통합 테스트와 Docker build smoke가 추가됐다. PR #144의 양쪽 native CI 성공은 위 검증 기록을 따르며 운영 성공과 구분한다.
- v2 UI 표시 정책·cleanup 근거·사용자 검증 명령은 [v2 UI 마감 기록](v2-ui-cleanup.md)을 참고한다.

아래 10.5~10.6 기록과 운영 확인 수치는 당시의 역사이며 현재 branch 검증 결과를 뜻하지 않는다.

Phase 10.5G는 기존 forecast 및 알려진 세금 후 계산을 재사용해 선택 연도 12개월 배당 현금흐름과 사용자 월배당 목표 비교를 제공하도록 완료됐다.

1. 기존 `monthly_schedule`을 월별 gross forecast의 authoritative schedule로 재사용
2. 기존 종목별 `after_known_tax_cash_krw`를 각 종목의 월별 gross 비중으로 배분
3. 월평균, 최대/최소 월, 최대월 편중, 상위 예상수령 기여 종목 표시
4. owner별 사용자 월배당 목표를 browser localStorage에만 보관하고 충족 월/연간 부족·초과 표시
5. 기존 세후 계산이 complete가 아니거나 residual/월별 attribution/reconciliation이 불완전하면 `목표 비교 보류`로 fail-closed

10.5F는 PR #52 merge `ed10883728a97fca71baa29ad8c28f41cb4b4298`, GHCR #135, 운영 배포 및 browser smoke까지 완료했다.

C-7 가족별 배당 분산 보기 단순화는 삭제하지 않고, 기존 Family Risk / Allocation Simulation과 기능 중복이 커서 **추후 UX 정리 후보**로 계속 보류한다.

최근 완료/정리:

- 10.5C-5 Portfolio after-known-tax dividend yield — PR #46 merge (`b5e8cbaa`).
- 세금 도구 전용 `🧾 세금` workspace 이동 — PR #47 merge (`8f490c0`).
- 10.5C-6 2천만원 접근 What-if 개선 — PR #48 merge 및 운영 확인 완료 (`0d87fd9c`).
- C-7 보류 및 roadmap 재정렬 — PR #49 merge (`ba1d3349`).
- 10.5D Dividend Intelligence 통합 — PR #50 merge (`e18408d6`), 운영 배포 및 browser smoke 확인.
- 10.5E Dividend Intelligence 디자인 / 고배당기업 공식 자격 — PR #51 merge (`3d23a504`), GHCR #120, 운영 배포 및 browser smoke 확인.
- 10.5F Dividend detail UX polish + USD amount helper — PR #52 merge (`ed108837`), GHCR #135, 운영 배포 및 browser smoke 확인.
- 10.5G 배당 현금흐름 목표/의사결정 — PR #53 merge (`076e81a`).
- 10.5H 월별 알려진 세금 후 attribution — PR #54 merge (`3f3f141`).
- 10.5I 월별 attribution 진단 및 목표 UX — PR #55 merge (`19a294d`).
- 10.6A AccountInfo PDF 계좌 가져오기 — PR #56 merge (`8bb3dcb`), 후속 UX/observer 보강 PR #57~#59 반영.
- 10.6B 증권·은행 계좌 섹션 요약 — PR #60 merge (`e0573d1`), 후속 보강 PR #61 반영.
- 이후 기간·증권사 필터와 금융 시계열 화면 통합, IPO source/history/DART/score, Toss WTS 실현손익 가져오기 안정화가 main에 반영됨.
- 초기 자산 표시 경로 성능 개선 — PR #89 merge (`9ecc356`).
- 절세계좌 보유종목 상세 복구 및 IPO 캘린더 청약 색상 첫 페인트 수정 — PR #90 merge (`faefa4d`).

C-4.1 운영 확인:

- PR #45 merge `5edb9388`.
- GHCR 배포 완료.
- 운영 사용자에서 최초 `dividend_forecast_snapshots.json` point-in-time snapshot 생성 확인.
- snapshot schema_version 1, 12개 월 bucket, owner/date canonical upsert 기반이 운영에서 확인됨.
- 10.5E browser smoke 시 snapshot 2개 누적 확인.

방향 전환:

- Phase 10.5B-4.9까지의 정밀 세금 backend는 유지한다.
- 토지등 예정신고세액, 수시부과세액, 가산세 등 **종합소득세 신고서 완성 목적의 후속 확장은 현재 제품 우선순위에서 중단**한다.
- 앞으로 기본 UX는 `예상 금융소득 / 2천만원까지 여유 / 추가 배당 What-if / 원천징수 후 현금흐름 / 배당수익률`을 중심으로 한다.
- 세무 상세 기능은 계산 근거 또는 고급 비교 영역으로 남긴다.

## 2. 주요 완료 현황 (10.5~10.6)

- [x] 10.5A-1 금융소득 projection 기반
- [x] 10.5A-2 stateless 금융소득 simulation API
- [x] 10.5A-2.5 개인 vs 가족법인 투자 세금 비교 엔진
- [x] 10.5A-3 금융소득 What-if / 퀵 시뮬레이터
- [x] 10.5A-3.1 공통 KRW 금액 입력 UX 정비
- [x] 10.5A-4 2026 고배당기업 배당소득 분리과세 규칙 엔진
- [x] 10.5A-4.1 공식 공시 기반 배당예상 Source 계층 — PR #22 merge (`19b0af2`)
- [x] 10.5A-4.2 고배당 분리과세 What-if 연결 — PR #23 merge (`0f5f25a`)
- [x] 10.5A-4.3 미래 배당 확정공시 구조화 — PR #24 merge (`86a07ea`)
- [x] 10.5A-4.4 국내 ETF 분배금 공식 Source 개선 — PR #25 merge (`39ca928`)
- [x] 10.5B-1 가족 금융소득 위험 보기 — PR #26 merge (`a8883c2`)
- [x] 10.5B-2 추가 배당/매매 What-if 확장 — PR #27 merge (`404059a`)
- [x] 10.5B-3 배우자/자녀 분산 시뮬레이션 — PR #28 merge (`6d71cc2`)
- [x] 10.5B-4 개인 종합과세 정밀화 first increment — PR #29 merge (`2a98442`)
- [x] 10.5B-4.1 금융소득 종합과세 비교산출세액 — PR #30 merge (`c65afa9`)
- [x] 10.5B-4.2 배당세액공제 — PR #31 merge (`90867ae`)
- [x] 10.5B-4.3 금융소득 기납부 원천징수세액 — PR #32 merge (`4281a31`)
- [x] 10.5B-4.4 개인지방소득세 비교산출세액 — PR #33 merge (`9cd0d83`)
- [x] 10.5B-4.4.1 개인지방소득세 배당세액공제 — PR #34 merge (`78499b09`)
- [x] 10.5B-4.4.2 금융소득 지방 특별징수 기납부세액 — PR #35 merge (`22c40a9b`)
- [x] 10.5B-4.5 국세 외국납부세액공제 — PR #36 merge (`28607378`)
- [x] 10.5B-4.6 개인지방소득세 외국납부세액공제 — PR #37 merge (`e6232566`)
- [x] 10.5B-4.7 국세 중간예납세액 반영 — PR #38 merge (`91407565`)
- [x] 10.5B-4.8 다른 종합소득 원천징수·납세조합 징수 기납부세액 — PR #39 merge (`ee893fc9`)
- [x] 10.5B-4.9 납세조합공제 선행 세액공제 — PR #40 merge (`7d97cd4a`)
- [x] 10.5C-1 배당 세금 대시보드 — PR #41 merge (`f046f22d`), 운영 배포 확인
- [x] 10.5C-2 세후 배당 현금흐름 보기 — PR #42 merge (`fcf14ba`)
- [x] 10.5C-3 일간 가격손익과 평가액 변화 분리 — PR #43 merge (`89ad76a`)
- [x] 10.5C-4 official confirmed dividend event identity와 high-confidence actual/forecast dedup — PR #44 merge (`b235934d`)
- [x] 10.5C-4.1 Dividend forecast point-in-time snapshots & evaluation foundation — PR #45 merge (`5edb9388`), 운영 배포 및 최초 snapshot 생성 확인
- [x] 10.5C-5 Portfolio after-known-tax dividend yield — PR #46 merge (`b5e8cbaa`)
- [x] 세금 도구 전용 workspace 이동 — PR #47 merge (`8f490c0`)
- [x] 10.5C-6 2천만원 접근 What-if 개선 — PR #48, 운영 확인 완료
- [ ] 10.5C-7 가족별 배당 분산 보기 단순화 — 추후 진행 후보로 보류
- [x] 10.5D Dividend Intelligence — PR #50 merge (`e18408d6`), 운영 배포 및 browser smoke 확인
- [x] 10.5E Dividend Intelligence 디자인 / 고배당기업 공식 자격 — PR #51 merge (`3d23a504`), GHCR #120, 운영 배포 및 browser smoke 확인
- [x] 10.5F Dividend detail UX polish + USD amount helper — PR #52 merge (`ed108837`), GHCR #135, 운영 배포 및 browser smoke 확인
- [x] 10.5G 배당 현금흐름 목표/의사결정 — PR #53 merge (`076e81a`)
- [x] 10.5H 월별 알려진 세금 후 attribution — PR #54 merge (`3f3f141`)
- [x] 10.5I 월별 attribution 진단 및 목표 UX — PR #55 merge (`19a294d`)
- [x] 10.6A AccountInfo PDF 계좌 가져오기 — PR #56 merge (`8bb3dcb`)
- [x] 10.6B 증권·은행 계좌 섹션 요약 — PR #60 merge (`e0573d1`)

향후 후보와 보류 항목은 `docs/ROADMAP.md`를 따른다. 완료된 phase의 계산·저장 계약은 각 `docs/PHASE_*.md`에 보존한다.

## 3. 현재 금융소득/세금 제품 원칙

### 제품 방향

- Wealth의 세금 기능은 **자산관리 의사결정을 돕는 screening**이 기본 목적이다.
- 종합소득세 신고서의 모든 칸을 채우는 신고 프로그램을 목표로 하지 않는다.
- 세금 backend의 기존 정밀 계산은 버리지 않고 고급 근거/비교 기능으로 유지한다.
- 기본 화면에서는 예상 금융소득, 2천만원 기준 여유, 추가 배당 영향, 원천징수 후 현금흐름을 우선한다.
- `세후`라는 표현은 최종 신고세액이 아니라 현재 계산 가능한 원천징수·알려진 세금 기준일 때 그 범위를 함께 표시한다.
- 가족 금융소득 risk/allocation과 금융소득 What-if 같은 세금 도구는 전용 `🧾 세금` workspace에 두고, 배당 forecast·요약·포트폴리오 알려진 세금 후 수익률은 배당 forecast 영역에 유지한다.
- 2천만원 What-if UI는 서버가 계산한 threshold flags를 사용하며 정확히 2천만원에 도달한 상태를 안전 상태로 표시하지 않는다.
- 고배당기업 자격 표시는 issuer 공식 공시의 구조화된 상태만 사용하고, Wealth가 배당성향/증가율 등으로 자격을 독립 추론하지 않는다.
- 공식 고배당기업 자격과 실제 고배당 분리과세 적용 여부는 별개이며, 공식 자격 확인만으로 세제특례를 자동 적용하지 않는다.

### 금융소득 projection

- 실제 YTD 배당/이자 + 미래 예상 배당 + 사용자가 입력한 예상 이자를 결합한다.
- 제품 주의 기준은 1,000만원이다.
- 법정 금융소득 종합과세 screening 기준은 2,000만원이다.
- 계산 결과는 screening 목적이며 최종 세법 판단으로 표시하지 않는다.
- 현재 월 자동 예상은 실제 수령 기록과 중복될 수 있어 기본적으로 제외한다.

### 가족 금융소득 위험 보기

- 법정 금융소득 종합과세 기준은 개인별 기준으로만 평가한다.
- 가족 합계는 자산배분 참고용이며 법정 threshold 판정값이 아니다.
- 가족 구성원은 `settings.family_members` 순서를 따른다.
- `모두`/미등록 소유자의 데이터는 구성원에게 임의 배분하지 않는다.
- 자동 미래 이자 forecast는 아직 없으며 B-1은 기존 projection 기본값(추가 이자 0원)을 사용한다.

### 배우자/자녀 분산 시뮬레이션

- 등록된 `settings.family_members` 사이의 미래 금융소득 가상 배분만 request 단위로 비교한다.
- 배분 가능액은 미래 월 예상 배당, 명시적 현재월 잔여 배당 조정, 예상 잔여 이자 등 아직 발생하지 않은 gross component만 사용한다.
- 이미 발생한 YTD 금융소득의 귀속은 변경하지 않는다.
- 실제 portfolio, holding owner, 배당 기록, 가족 설정을 변경하거나 scenario를 저장하지 않는다.
- source의 미래 배분 가능액을 초과하는 금액과 미확정 source forecast 배분은 fail-closed로 거부한다.
- B-1에서 미분류/소유자 충돌 등으로 가족 reference가 불완전하면 B-3도 완전한 가족 합계로 승격하지 않는다.
- 가족 합계는 보존 확인용 참고값이며 법정 threshold를 적용하지 않는다.
- 이 결과는 미래 금융소득 배분 가정에 따른 screening 비교이며, 실제 증여·명의·소득 귀속의 법률/세무 판단을 포함하지 않는다.

### 개인 종합과세 정밀화

- B-4 first increment는 2026 소득세법 제55조 기본세율과 사용자가 명시한 과세표준 전/후 비교를 제공한다.
- B-4.1은 명시 입력 금융소득 category, 출자공동사업자 배당소득을 제외한 다른 종합소득, 소득공제를 이용해 소득세법 제62조 A/B 비교산출세액을 계산한다.
- B-4.1의 배당가산은 사용자가 명시한 Gross-Up 적격 배당 중 종합과세기준금액 초과분에만 10%를 적용한다.
- B-4.1은 출자공동사업자 배당소득의 제62조 특수 비교를 구현하지 않으며 해당 금액은 다른 종합소득 입력에서 제외한다.
- B-4.2는 배당가산액과 `종합소득산출세액 - 비교산출세액 B` 중 작은 금액을 소득세법 제56조 배당세액공제로 계산한다.
- B-4.3은 종합과세 금융소득에 대해 실제 원천징수된 이자·배당 국세 소득세를 명시 입력으로 받아 배당세액공제 후 국세 참고값에서 차감한다.
- B-4.3은 지방소득세 원천징수액을 포함하지 않고, gross 금융소득만으로 실제 기납부세액을 추정하지 않는다.
- B-4.4는 지방세법 제91조의 과세표준 연결, 제92조 제1항 표준세율, 제93조 제2항 금융소득 A/B 비교를 독립 계산한다.
- B-4.4.1은 지방세특례제한법 제95조에 따라 기존 배당가산액의 10%를 지방 배당세액공제로 반영한다.
- B-4.4.2는 지방세법 제95조 제3항 제4호 및 제103조의13에 따라 금융소득에서 실제 특별징수된 개인지방소득세를 명시 입력으로 받아 지방 배당세액공제 후 부분값에서 차감한다.
- B-4.4.2는 국세 원천징수액의 10%나 gross 금융소득으로 실제 지방 특별징수액을 자동 추정하지 않는다.
- B-4.5는 소득세법 제57조에 따라 국가별 기준 국외원천소득과 종합소득금액으로 국세 외국납부세액공제 한도를 계산하고, 당기 공제대상 외국소득세액을 한도 내에서 반영한다.
- B-4.5의 국가별 기준 국외원천소득은 대응비용·감면·결손국가 조정이 완료된 신고서 기준값을 명시 입력으로 받으며, 조세조약상 공제 가능 세액 여부도 제품이 자동 판정하지 않는다.
- B-4.5는 전기 이월액·이월배제액·10년 이월공제액을 계산하지 않으며, 당기 미공제 외국세액을 곧바로 이월공제액으로 표시하지 않는다.
- B-4.6은 지방세특례제한법 제97조 제1항에 따라 B-4.5에서 실제 공제된 국세 외국납부세액공제액의 10%를 개인지방소득세 외국납부세액공제로 반영한다.
- B-4.6은 국세 필요경비 산입 방식을 자동 추론하지 않으며, 제97조 제2항의 5년 이월액·전기 이월액·당기 이월가능액을 계산하지 않는다.
- B-4.7은 소득세법 제65조의 실제 중간예납세액을 사용자 명시 입력으로 받아 제76조 제3항 제1호의 확정신고 기납부세액으로 국세 partial balance에서 차감한다.
- B-4.7은 전년도 세액 2분의 1이나 중간예납추계액을 자동 계산하지 않고, 기존 국세 partial balance 필드와 지방소득세 결과의 의미를 변경하지 않는다.
- B-4.8은 금융소득 외 종합소득의 실제 원천징수세액과 납세조합의 실제 징수세액을 사용자 명시 입력으로 받아 제76조 제3항의 기납부세액으로 국세 partial balance에서 차감한다.
- B-4.8은 gross 소득에서 원천징수·납세조합 징수세액을 자동 추정하지 않고, 납세조합공제는 기납부세액 단계에서 차감하지 않는다.
- B-4.9는 납세조합영수증/신고서의 실제 납세조합공제액을 명시 입력으로 받아 제60조 순서에 따라 외국납부세액공제보다 먼저 반영한다.
- B-4.9는 법정 3%를 자동 계산하지 않으며, 납세조합공제가 국세 외국납부세액공제의 가용세액을 줄이면 지방 외국납부세액공제도 실제 국세 공제액의 10% 기준으로 연동한다.
- 지방자치단체 조례에 따른 표준세율 가감, 다른 지방 세액공제·감면, 다른 기납부 지방소득세 및 최종 지방소득세 납부·환급액은 아직 계산하지 않는다.
- 현재 결과에는 토지등 예정신고세액, 수시부과세액, 아직 미구현인 다른 국세·지방 세액공제·감면, 가산세·추가납부세액 및 건강보험 영향이 포함되지 않는다.
- 국세와 지방세의 signed partial balance는 screening/계산보조용 부분값이며 신고상 최종 납부 또는 환급세액이 아니다.

### 개인 vs 가족법인 비교

지원 범위:

- 국내 배당주
- 국내상장 미국 ETF
- 미국주식/미국 ETF 직접투자
- 배당/분배금
- 실현차익
- 법인세/지방소득세 screening
- 국내 수입배당금 익금불산입 조건
- 외국자회사 배당 익금불산입 조건
- 외국납부세액공제 screening
- 법인 유보 vs 법인→개인 배당 인출

아직 최종 법률·세무 판단으로 계산하지 않는 항목:

- 개인 종합소득 최종 누진세액
- 건강보험료 영향
- 인적공제 영향
- 급여/상여/퇴직금 형태의 법인 자금 인출
- 증여/상속세
- 복잡한 외국납부세액공제 이월 및 지방세 세부 계산

### 2026 고배당기업 분리과세

- A-4에 규칙 엔진이 존재한다.
- A-4.2에서 금융소득 What-if와 연결됐다.
- 자동 적격 판정을 배당수익률 등으로 임의 추정하지 않는다.
- Phase 10.5E부터 국내 배당주의 고배당기업 자격은 회사의 최신 공식 `기업가치 제고 계획` 공시에 기재된 `해당 / 미해당`을 구조적으로 확인한다.
- 공식 문서가 없거나 필드를 검증하지 못하면 `not_confirmed`, credential/network/upstream 실패는 `source_unavailable`로 유지한다.
- 회사 공시상 자격 확인은 Wealth의 독립 법률판정이 아니며, 실제 적용은 신고 시 신청이 필요한 제도라는 전제를 유지한다.
- 공식 자격을 확인해도 고배당 분리과세를 자동 적용하지 않는다.

## 4. 현재 배당예상 데이터 원칙

기존 배당 예상은 다음 순서를 기본으로 한다.

### 국내

기존 숫자 추정:

1. Naver 금융 데이터
2. Naver 정보가 없을 때 기존 휴리스틱

A-4.1 공식자료 보강:

1. OpenDART 정기보고서의 공식 과거 DPS는 공식 이력으로 보관
2. 기존 Naver DPS가 0/누락일 때만 공식 과거 DPS로 fill
3. 최근 배당결정 공시 존재 여부를 별도로 기록
4. 공시 제목만으로 미래 확정금액을 만들지 않는다

A-4.3 확정공시 구조화:

1. 최근 배당결정 공시의 접수번호로 OpenDART `document.xml` 원문 ZIP을 조회한다.
2. 원문에서 보통주 1주당 현금배당금이 구조적으로 검증된 경우에만 `confirmed_amount=true`로 처리한다.
3. 배당기준일과 지급예정일은 공시에 명시된 값만 보관하며, 미기재 날짜를 추정하지 않는다.
4. 지급예정일이 현재 연도 미래 날짜이고 기존 예상월과 안전하게 매칭되면 해당 월 금액을 확정 공시값으로 교체한다.
5. 기존 예상이 0인 경우에는 확정 주당배당금과 지급월이 확인되면 해당 확정 이벤트를 새 예상으로 반영할 수 있다.
6. 기존 예상이 존재하지만 지급월이 매칭되지 않으면 중복계상을 피하기 위해 자동 금액 override를 하지 않는다.
7. 원문 다운로드/파싱 실패는 기존 예상 전체 실패로 전파하지 않는다.

A-4.4 KIND ETF 분배금 보강:

1. 기존 Naver integration이 ETF로 확인한 종목만 KIND ETF source 대상이 된다.
2. KIND ETF 검색은 별도 API credential 없이 공개 공시 화면을 사용한다.
3. 검색 결과 제목만으로 확정하지 않고 viewer의 공식 `/external/` 문서에서 대상 ISIN 행을 구조 검증한다.
4. 공식 기준일 월에 기존 휴리스틱 항목이 있으면 그 항목을 제거하고 실제 지급예정월에 공식 분배금으로 이동한다.
5. 기존 양수 forecast에 안전하게 매칭되는 월이 없으면 공식 이벤트는 증거로만 남기고 숫자에는 자동 반영하지 않는다.
6. 공식 Source 장애는 기존 Naver/OpenDART/Yahoo forecast를 실패시키지 않는다.

### 미국

- Yahoo Finance 최근 배당 이력을 계속 사용한다.

### 중요

공식 과거 이력과 미래 확정 배당은 같은 의미가 아니다.
`공시가 존재한다`와 `미래 지급액을 구조적으로 검증했다`도 반드시 구분한다.
`confirmed_amount=true`와 `confirmed_numeric_override=true`도 구분한다. 전자는 공시 금액 구조 검증, 후자는 안전한 월별 예상 교체까지 완료됐음을 의미한다.

### C-4 배당 이벤트 identity / actual-forecast 중복 제거

- 경제적 이벤트 identity는 공식적으로 확인된 `종목코드 + 배당기준일`을 최우선으로 사용한다.
- 기준일이 없을 때만 OpenDART/KIND의 공식 event ID를 fallback identity로 사용할 수 있다.
- actual과 forecast의 명시 identity가 같거나, official forecast의 정확한 지급일과 동일 종목 actual 지급일이 같을 때만 자동 제외한다.
- Naver/Yahoo 등 heuristic forecast는 자동 dedup하지 않으며 월·유사금액·근사 날짜 매칭도 사용하지 않는다.
- 공식 확정 DPS에 현재 보유수량을 곱한 값은 entitlement 확정이 아니며 `quantity_basis=current_holding`, `entitlement_confirmed=false`로 표시한다.
- matched item의 금액만 월 bucket에서 차감하고 나머지 heuristic/residual 금액은 유지한다.

### C-4.1 배당예측 point-in-time 측정 기반

- `dividend_forecast_snapshots.json`에 당시 최종 enriched forecast와 최소 portfolio basis를 저장한다.
- daily close의 배당 snapshot 단계는 기존 주식/순자산 기록 및 알림에 영향을 주지 않는 비치명 단계다.
- 동일 owner와 `as_of_date`는 하나의 canonical snapshot으로 upsert한다.
- 평가는 저장 snapshot과 actual record만 사용하며 과거 시점 forecast를 현재 source/holdings로 재생성하지 않는다.
- snapshot 다음 달부터 `through_date` 직전 완료 월까지만 평가하고 진행 중인 월은 제외한다.
- actual gross와 환산 근거가 있을 때만 gross MAE/WAPE를 계산하며 cash-only 기록은 지급월 분석에만 사용한다.
- 기존 과거 snapshot이 없으므로 historical point-in-time accuracy는 아직 unavailable이며, 이번 increment는 향후 측정 기반만 마련한다.

### C-5 포트폴리오 알려진 세금 후 배당수익률

- `summary.total_annual_dividend_krw`를 포트폴리오 gross forecast의 canonical total로 유지한다.
- 종목별 `holding_dividends`는 code/currency 기준 attribution 계층으로만 사용하며 residual을 특정 종목에 임의 귀속하지 않는다.
- 동일 code/currency 다계좌 보유는 quantity, 평가금액, 평균매입가 기준 비용을 instrument 단위로 합산한다.
- 알려진 세금은 새 세율을 만들지 않고 기존 2026 investment-tax screening backend 결과만 재사용한다.
- KRW ETF는 C-5에서 distribution-only로 계산하며 매매차익과 ETF taxable gain은 0으로 고정한다.
- USD 보유자산은 Wealth의 기존 US direct screening 계약을 사용하며 미국 외 USD 상장자산의 개별 조세조약 차이는 계산하지 않는다.
- 평가금액 기준 denominator는 scoped stock holdings의 현재 평가금액 합계이며 현금·예수금은 제외한다.
- 평균매입가 기준 denominator는 `평균매입가 × 수량`을 현재 FX로 원화 환산한 dashboard `cost_value_krw`를 사용한다.
- forecast attribution이나 tax coverage가 불완전하면 계산 가능한 현금과 coverage만 보여주고 전체 포트폴리오 after-known-tax yield는 null로 유지한다.
- UI 표현은 `최종 세후`가 아니라 `원천징수·알려진 세금 후` 범위를 명시한다.

### C-6 2천만원 접근 What-if

- 기존 +100만 / +500만 / +1,000만원 추가 배당 프리셋을 유지한다.
- 2천만원 threshold 상태는 frontend에서 새 금액 기준을 계산하지 않고 backend의 `at_or_above`, `exceeded`, `remaining_krw`, `crossed_by_scenario`와 watch 상태를 재사용한다.
- 적용 후 상태를 `safe / approach / reached / exceeded`로 구분한다.
- 정확히 2천만원에 도달한 경우 `reached`로 표시하고 녹색 안전 상태로 취급하지 않는다.
- 2천만원 초과 시 추가 배당 때문에 새로 넘었는지 기존 예상부터 이미 초과였는지를 구분해 문구를 표시한다.
- scenario는 request 단위 stateless 계산이며 localStorage/sessionStorage에 저장하지 않는다.
- backend API schema, 세법 계산, 세율 상수는 C-6에서 변경하지 않는다.

### D Dividend Intelligence 통합 계약

- 배당 forecast 신뢰도는 기존 `forecast_source` metadata만 해석하며 새로운 숫자 forecast를 만들지 않는다.
- official / official-confirmed / history / market / heuristic 상태와 가능한 경우 공식 원문 링크를 화면에서 구분한다.
- C-5 instrument 결과에 세전 배당 기여도와 계산 가능한 알려진 세금 후 현금 기여도를 파생 표시한다.
- 다계좌 동일 종목은 현재 보유수량 비례로만 계좌별 현금을 추정하고 `entitlement_confirmed=false`를 유지한다.
- residual은 종목·계좌에 임의 배분하지 않는다.
- 정확도는 C-4.1 snapshot evaluator를 재사용한다. 평가 horizon이 없으면 `측정 데이터 누적 중`, gross 비교가 불완전하면 MAE/WAPE를 숫자로 승격하지 않는다.
- 알림은 `automation.dividend_intelligence_alerts.enabled`가 명시적으로 true일 때만 동작하며 기본값은 false다.
- 공식 배당 event는 기존 event identity를 alert dedup key에 사용한다.
- 금융소득 alert는 B-1 family risk의 **각 개인별** threshold 결과만 사용하며 family reference/`모두` 합계에는 법정 threshold를 적용하지 않는다.
- alert 상태는 `dividend_intelligence_alert_state.json`에 deterministic event key를 보관하며 실제 provider 전송 성공 시에만 소비한다.
- alert 실패는 scheduled daily-close 배당 snapshot 저장 실패로 전파하지 않는다.

### E Dividend Intelligence 디자인 / 고배당기업 공식 자격 계약

- source banner는 공식 근거, 확정금액 반영, 이력·시장 추정의 compact 상태와 상세 펼쳐보기로 구성하되 기존 공식 source 장애/미연동 상태를 숨기지 않는다.
- 고배당기업 자격 자동 확인 대상은 KRW 국내 배당주이며 ETF·외국증권은 `not_applicable`로 유지한다.
- issuer의 최신 `기업가치 제고 계획` 공시에서 `고배당기업 여부`가 구조적으로 `해당`이면 `official_qualified`, `미해당`이면 `official_not_qualified`로 표시한다.
- 공시가 없거나 field/value를 구조 검증하지 못하면 `not_confirmed`; credential/network/OpenDART 오류는 `source_unavailable`이다.
- 공식 자격 목록 부재를 미해당으로 추론하지 않는다.
- 회사가 공시한 자격 상태는 company self-determination이며 Wealth의 독립 법률판정으로 승격하지 않는다.
- 공식 자격 종목의 예상 gross 배당 합계와 비중은 자산관리 참고값이며 특례배당소득 확정액이 아니다.
- 공식 자격을 확인해도 10.5A-4 고배당 분리과세 규칙을 자동 적용하지 않는다.
- 새 세율, 새 client threshold, fuzzy matching, forecast event identity 변경을 추가하지 않는다.

### F Dividend detail UX / USD amount helper 계약

- Dividend Intelligence 상세의 backend `calculation_status`는 변경하지 않고 display label만 `계산 완료 / 계산 제외 / 확인 불가 / 부분 계산`으로 한글화한다.
- 고배당기업 `not_applicable`은 상태 badge만 유지하고 고배당기업 공식 근거 링크를 표시하지 않는다.
- USD helper는 `cash_usd` 또는 명시적 `data-auto-usd-preview` numeric input에만 적용한다.
- USD input 자체의 native `type=number`, raw value, 저장/API payload를 변경하지 않는다.
- 원화 환산은 dashboard `wealth:portfolio` event의 `fxRates.USD`를 재사용한다.
- 환율 API를 추가 호출하거나 client-side 환율을 하드코딩하지 않는다.
- 현재 `fx_rates.USD`가 없으면 `원화 환산 대기`로 표시하고 임의 환율을 적용하지 않는다.
- 기존 KRW amount helper 계약과 세금/forecast/persistence 계약을 변경하지 않는다.

### G 배당 현금흐름 목표/의사결정 계약

- gross 월별 기준은 기존 `monthly_schedule`만 사용하며 새 지급월/record-date를 생성하지 않는다.
- 알려진 세금 후 월별 현금은 기존 종목별 `after_known_tax_cash_krw`를 해당 종목의 월별 gross 비중으로만 배분한다.
- 새 세율이나 client-side tax constant를 추가하지 않는다.
- 기존 portfolio after-tax 계산이 complete이고 residual=0이며 월별 gross attribution과 연간 reconciliation이 모두 완전할 때만 월 목표 판단을 확정 표시한다.
- 불완전하면 `목표 비교 보류`로 fail-closed하며 residual을 특정 월이나 종목에 임의 배분하지 않는다.
- 월 목표는 사용자 자산관리 목표이며 법정 threshold가 아니다. 기본값을 하드코딩하지 않고 owner별 browser localStorage에만 보관한다.
- 월별 배분은 현재 forecast 기반 자산관리 projection이며 실제 record-date entitlement 확정이 아니다.

## 5. 사용자별 DART 인증 계약

DART 인증정보는 A-4.1 전용 새 환경변수를 만들지 않는다.
기존 사용자 OpenAPI 설정을 재사용한다.

현재 저장 계약:

```text
data/users/<username>/openapi_config.json
└─ dart.api_key
```

compose 기본 마운트:

```text
host:      ./data
container: /app/data
```

따라서 `/docker/wealth`에서 compose를 실행하는 기본 운영 구조라면 대략 다음과 같다.

```text
host:      /docker/wealth/data/users/<username>/openapi_config.json
container: /app/data/users/<username>/openapi_config.json
```

주의:

- 현재 디렉터리 키는 stable UUID user id가 아니라 **username**이다.
- 코드 변경 없이 `<username>`을 UUID로 바꾸지 않는다.
- stable ID 경로로 마이그레이션하려면 별도 명시적 migration 설계가 필요하다.

DART 해석 우선순위:

1. 사용자별 `dart.api_key`
2. 기존 호환용 `DART_API_KEY`
3. 미설정

A-4.1에서 `WEALTH_OPENDART_API_KEY` 같은 별도 전역 키 계약은 사용하지 않는다.

## 6. 배포 표준

운영 서버는 GHCR 이미지를 사용한다.
표준 배포 명령은 다음 compose 조합이다.

```bash
cd /docker/wealth

docker compose \
  -f docker-compose.ghcr.yml \
  -f docker-compose.override.yml \
  pull dashboard

docker compose \
  -f docker-compose.ghcr.yml \
  -f docker-compose.override.yml \
  up -d dashboard

docker compose \
  -f docker-compose.ghcr.yml \
  -f docker-compose.override.yml \
  ps
```

기본 `docker-compose.yml`은 `build: .` 중심이므로 GHCR 배포 절차와 동일하게 취급하지 않는다.

## 7. 개발/검증 관례

기능 변경 시 기본 순서:

1. 새 branch
2. targeted tests
3. 관련 regression tests
4. full pytest suite (`PYTHONPATH=tests`)
5. Python `py_compile`
6. JavaScript `node --check`
7. `git diff --check`
8. 변경 범위 전체에 대해 `git status --short` 확인
9. PR final review / unresolved thread 확인
10. Ready
11. exact-head merge
12. main SHA verify
13. GHCR build 확인
14. 서버 배포 및 browser smoke

사용자가 해당 세션에서 검증 성공 후 Ready/merge 자동 진행을 명시적으로 위임한 경우에는 추가 확인 없이 10~13단계를 진행할 수 있다. 그렇지 않은 경우 merge는 사용자 명시적 승인 후 진행한다.

## 8. 문서 유지 규칙

다음 상황에서는 이 문서를 반드시 갱신한다.

- Phase 완료/시작
- 주요 PR merge
- 데이터 저장 위치 변경
- secret 해석 우선순위 변경
- 배포 방식 변경
- 세금 계산 범위/법적 의미 변경
- 중요한 설계 결정 변경

업데이트 시 실제 secret, 계좌번호, 토큰, 사용자 개인 금융정보는 절대 기록하지 않는다.
