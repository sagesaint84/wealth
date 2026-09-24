# 공모주 과거 공식자료 가져오기 변경 기록

- 작성일: 2026-09-24
- 대상: Wealth v1.3.0 이후 후속 수정
- 관련 기존 커밋: `e3a5456 feat: add official historical IPO import`
- 수정 범위: `app/services/ipo/historical_import.py`, `app/static/index.html`, `tests/test_ipo_historical_import.py`, `tests/test_ipo_historical_import_frontend.py`

## 배경

초기 과거 IPO 가져오기 기능은 KRX/KIND 공식 파일만 허용하고, 미리보기 후 안전하게 커밋하도록 구현되었다. 실제 KRX와 KIND 원본 파일로 검증하는 과정에서 각 사이트의 다운로드 형식 특성이 확인되었다.

KRX Data Marketplace `[20001] 신규상장종목 현황` XLSX는 실제 데이터가 여러 행·열 존재해도 worksheet XML의 dimension이 `A1`로 기록되는 사례가 있었다. `openpyxl`의 read-only 모드는 이 메타데이터를 신뢰하기 때문에 필수 헤더를 찾지 못할 수 있었다.

KIND `신규상장기업현황` 다운로드 파일은 확장자는 `.xls`이지만 실제 내용은 EUC-KR/CP949 인코딩 HTML table이다. 또한 실제 헤더는 `공모가 (원)`, `공모금액 (천원)` 형태를 사용한다.

## 변경 내용

### 1. KRX XLSX 호환성

`openpyxl` read-only 모드에서 활성 시트의 dimension이 `A1:A1`로 잘못 계산되는 경우 `reset_dimensions()`를 호출한 뒤 전체 행을 읽도록 보완하였다. 사용자는 KRX 원본 XLSX를 Excel에서 다시 저장하거나 CSV로 변환할 필요가 없다.

### 2. KIND 공식 `.xls` 직접 지원

`.xls` 업로드를 허용하고, KIND 공식 파일이 HTML-XLS인지 확인한 뒤 Python 표준 `HTMLParser`로 table을 파싱하도록 추가하였다. 임의의 바이너리 XLS나 출처를 확인할 수 없는 HTML 파일은 fail-closed로 거부한다.

### 3. 실제 KIND 헤더 및 단위 정규화

`공모가 (원)`을 확정 공모가 alias로 추가하고, `공모금액 (천원)`을 공모금액 alias로 추가하였다. 천원 단위 공모금액은 저장 전에 원 단위로 변환한다.

### 4. 프론트 파일 선택 범위

공식 과거자료 업로드 input의 허용 확장자를 `.xlsx,.xlsm,.xls,.csv`로 확장하였다.

### 5. 안전성 유지

기존 preview-before-write 구조, 사용자 바인딩 preview ticket, stale preview 거부, 중복·충돌 분류, 기존 비어 있지 않은 값 비덮어쓰기, 미래 상장일/비신규상장/필수값 누락 행의 fail-closed 정책은 그대로 유지한다.

## 검증 결과

공모주 과거자료 집중 테스트 26개가 모두 통과했다.

```text
Ran 26 tests in 0.524s
OK
```

전체 회귀 테스트도 모두 통과했다.

```text
Ran 1680 tests in 106.524s
OK
```

`git status --short` 기준 의도한 변경 파일은 4개뿐이며, `git diff --check`에서는 Windows 작업 트리의 LF→CRLF 변환 경고만 표시되고 whitespace 오류는 확인되지 않았다.

## 배포 후 확인 항목

배포 후 브라우저에서 `과거자료 가져오기` 모달의 `.xls` 선택 가능 여부를 확인하고, KRX 공식 XLSX와 KIND 공식 XLS 각각에 대해 `미리보기`를 먼저 실행한다. 신규/보완 가능/충돌/검토 필요/유효하지 않음 수량을 확인한 뒤에만 `확인 후 반영`을 실행한다.
