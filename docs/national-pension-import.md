# 국민연금 자료 가져오기 — v2.0.2

기준 fe0af51640c60ac6919a71186093040b6a8c5b88. 코드·합성 테스트 작성 단계이며 실행 검증·빌드·운영 접근은 수행하지 않았다.

## 오프라인 처리

상품 소유권 확인 후 raw 본문을 10MB까지 읽고 PDF/PNG/JPEG magic과 MIME을 대조한다.
암호화 PDF, 8페이지 초과 PDF, 1,600만 픽셀 초과 이미지는 거부한다.
Poppler pdfinfo/pdftotext의 layout 추출을 우선하며 글자가 부족한 페이지는 최대 3,200px로
래스터화하여 Tesseract kor+eng로 인식한다. EXIF·OSD 회전·명암 보정과 PSM 6 줄 인식을 사용한다.
심한 기울기·원근 왜곡은 자동 복원을 보장하지 않는다.

Docker에 Debian Bookworm poppler-utils, tesseract-ocr 및 kor/eng/osd 자료,
Pillow 12.3.0을 설치한다. amd64/arm64 배포판 패키지를 사용하고 외부 OCR·런타임 다운로드는 없다.
실제 두 아키텍처 빌드 및 이미지 용량 증가량은 아직 검증·측정하지 않았다.
설치 근거: [Tesseract 공식 설치·언어 자료 안내](https://tesseract-ocr.github.io/tessdoc/Installation.html),
[Pillow 12.3.0 배포·Python 및 플랫폼 정보](https://pypi.org/project/Pillow/12.3.0/).
worker 동시 2개, Linux 주소공간 512MiB·CPU 60초·파일 20MiB, 전체 75초와 개별 도구 timeout을 적용한다.
Oracle 소형 인스턴스에서 OCR CPU·메모리 압박과 지연 가능성을 운영 전 확인해야 한다.
0700 임시 폴더/0600 파일은 완료·실패 후 정리한다. stdout은 허용 필드 JSON만,
stderr는 버리고 원문·개인정보는 로그에 남기지 않는다. 도구 부재/손상/timeout은 수동 입력 안내로 처리한다.

## 문서 의미와 지원 범위

가입내역조회: 명시적 라벨의 숫자·날짜·기간·가입종별을 추출한다. 사업장이라는 이유로
근로자·사업주·법인 대표를 판정하지 않으며 personal_paid=null, workplace_role=unknown이다.
기간별 실제납부·미납·기준소득월액·월수를 별도 보관한다. 여러 해 총액은 연도 배분 확인 필요다.
명시적인 연도별 실제 납부액 행만 yearly_contributions 후보이며 기간 총액을 균등 배분하지 않는다.

납부확인서: 귀속연도, 월별 사업장 고지금액/지역 납부금액, 연간 합계를 구별한다.
월별 합계 불일치 및 중복 월은 저장을 거부한다. 추가 보험료는 별도 참고 금액이다.
검토한 기간 합계와 공단 총액이 다른 경우 누락 기간·추납 확인 경고를 표시한다.
고지액을 실제 납부액·본인 부담액·공제 인정액으로 승격하지 않으며 월 합계도 연도 이력에 자동 넣지 않는다.

인식은 명시적 라벨과 확인 가능한 행 의미에 한정된다. 열 제목 없는 표, 줄이 분리된 표,
다른 발급 양식과 OCR 숫자 오인은 완전 추출을 보장하지 않는다. 모든 OCR 값은 확인 필요다.
문서 종류 불확실 시 종류 선택 후 다시 분석하며 인식 실패 부분을 0원으로 채우지 않는다.
성명·사업장 명칭·발급번호·원문 문장은 반환·저장하지 않는다.

## 저장과 보존

POST `/api/insurance-accounts/{id}/national-pension-import/preview`: 추출만 수행.
POST `/apply`: 승인한 fields/periods/monthly/annual과 expected snapshot을 받아 portfolio RMW 안에서 저장.
이력·분석 revision·관련 금액 변경 시 409, 검토 초안 유지. 읽기와 파일 선택만으로 저장하지 않는다.

선택 메타데이터 national_pension_import: document_type, 허용 fields, periods, monthly,
파일 SHA256 fingerprint, revision. 기간별 부담금은 본인 미확인으로 유지한다.
기존 미선택 메타데이터를 보존하며 동일 기간·월·연도는 교체하고 중복 합산하지 않는다.
확인서의 연간 합계는 해당 가져오기 자료의 참고값이다. 연간 합계와 월별 행을 함께
선택하면 선택 월별 합계와 일치해야 한다. 서로 다른 해의 이전 월별 기록을 합산하여
최신 확인서 합계와 다시 비교하지 않는다.
annual은 선택한 연도만 교체한다. total_paid_amount/monthly_payout은 해당 필드 승인 시에만 변경한다.
monthly_premium/maturity_date/expected_amount/converted_total_asset/분석·IRR 가정은 자동 수정하지 않는다.
월 연금액 승인으로 예상총액을 재환산하지 않는다. 기존 평가·집계식은 유지한다.
기존 상품 편집도 import metadata를 보존한다. 분석 reset은 가져오기 자료나 실제 이력을 지우지 않는다.

## 화면과 검증

카드 이력/분석/가져오기는 기존 단일 dialog를 사용한다. 상품 편집 초안이 있으면 분석 이동을 막는다.
미등록 상품 API 요청은 없다. 미저장 이력·분석이 있으면 가져오기 적용을 막는다.
요청 중 닫기·다른 저장을 막고 실패·충돌 시 초안을 유지한다. 저장 후 원본 재조회와 비교한다.
세금은 다섯 번째 자산 탭의 독립 패널이며 국민연금·노란우산 소득공제와 연금저축·IRP 세액공제,
ISA를 구분한다. 새로운 세금 계산식은 없다.

합성 텍스트/PDF/OCR 및 사용자별 임시 portfolio로 인식·합계·부분 선택·재가져오기·충돌을 검증한다.
320/390/1280, Purple/White/OLED에서 진입·키보드·취소·다섯 탭 복원·overflow 및 기존 Toss 2행을 재검증한다.
Linux 전체 timeout은 전용 worker 프로세스 그룹을 종료한다. Windows는 PID 종료만 지원하므로
진행 중 native decoder 자식의 즉시 회수 보장은 Linux 전용이다. Windows는 합성 mock 테스트를 사용한다.
