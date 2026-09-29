# Phase 10.6A — AccountInfo PDF 계좌 가져오기

## 목표

어카운트인포에서 저장한 `계좌통합 현황` PDF를 브라우저에서 읽어 Wealth의 증권계좌와 은행계좌를 안전하게 추가한다.

이번 increment의 형식 기준은 2026-09-25 조회 AccountInfo PDF 두 종류다.

- 증권: 20개 금융기관 / 36개 계좌
- 은행: 12개 금융기관 / 28개 계좌

개인 식별정보와 실제 계좌번호가 들어 있는 원본 PDF는 repository/test fixture에 저장하지 않는다.

## Import flow

1. 기존 `계좌 가져오기` dialog에서 CSV/XLSX와 함께 PDF를 선택할 수 있다.
2. 은행 탭에도 `AccountInfo PDF` 진입 버튼을 제공한다.
3. PDF는 현재 브라우저에서 PDF.js로 text layer만 읽는다.
4. 사용자가 계좌 소유자를 명시적으로 선택한다. PDF의 문서 소유자 이름으로 owner를 자동 추론하지 않는다.
5. 저장 전에 마스킹된 Import Preview를 표시한다.
6. 금융기관 + 정규화 계좌번호 기준으로 기존 계좌와 비교한다.
7. 사용자가 선택한 신규 계좌만 기존 Wealth API로 저장한다.

## Privacy / safety

- PDF bytes 자체는 Wealth 서버나 외부 분석 API로 전송하지 않는다.
- PDF.js 실행 코드만 고정 버전 CDN에서 내려받는다.
- preview에는 전체 계좌번호를 표시하지 않는다.
- console/log에 전체 계좌번호를 기록하지 않는다.
- 실제 계좌번호는 사용자가 저장을 확정한 행에 대해서만 기존 Wealth 저장 API payload에 포함된다.
- 원본 PDF와 실제 계좌번호를 source/test fixture로 commit하지 않는다.

## 증권계좌 계약

AccountInfo `잔액`은 증권계좌의 계좌평가액일 수 있으므로 예수금으로 간주하지 않는다.

- PDF 잔액 → `cash_krw` / `cash_usd`로 자동 반영하지 않음
- 신규 증권계좌의 예수금은 0으로 시작
- 중개형 ISA → `isa`
- 연금저축 → `pension_savings`
- 명시적 개인형 IRP → `irp`
- 그 외 일반 위탁/종합/CMA → `general`
- 퇴직연금, 선물·옵션, 금현물, 금융상품 등은 `확인 필요`로 기본 선택하지 않음
- 세액공제 적용 여부는 PDF로 확인할 수 없으므로 자동 적용하지 않음

## 은행계좌 계약

일반 입출금/저축 계좌는 기존 `bank_accounts`로 추가하며 AccountInfo 잔액을 기준일 현재 잔액으로 저장한다.

다음 상품은 제품 분류가 애매하므로 `확인 필요`로 기본 선택하지 않는다.

- 주택청약/청약
- 적금/정기예금
- 외화 상품

사용자가 명시적으로 선택하면 이번 increment에서는 일반 은행계좌 reference balance로 저장한다. 별도 예·적금 상세(금리/만기/자동이체 등)는 PDF가 제공하지 않으므로 추정하지 않는다.

## Duplicate / owner contract

- 증권: canonical broker identity + normalized account number
- 은행: normalized institution identity + normalized account number
- 같은 계좌가 같은 owner에 이미 있으면 `이미 등록됨`으로 저장 차단
- 같은 계좌번호가 다른 owner와 충돌하면 `다른 소유자와 충돌`로 저장 차단
- 비활동성 신규계좌는 preview에 표시하되 기본 선택하지 않음

## Parsing contract

AccountInfo 표의 text layer 구조를 사용한다.

- `조회기준일: YYYY-MM-DD`
- 행 번호 anchor
- 금융기관명 / 계좌번호
- 지점명 / 상품정보
- 개설일 / 최종거래일
- 활동성 / 비활동성
- 잔액

페이지 경계에서 다음 페이지 상단으로 이어지는 날짜도 다음 행 anchor가 나오기 전까지 앞 행의 일부로 처리한다. OCR이나 지급/상품 정보를 새로 추론하지 않는다.

## Scope 밖

- AccountInfo PDF 잔액을 증권 예수금으로 간주
- 증권 평가잔액을 holdings로 생성
- 은행 금리/만기 추정
- 청약/적금 자동 분류를 확정값으로 처리
- PDF 문서의 이름으로 가족 owner 자동 지정
- raw PDF 영구 저장

## Validation

- parser/static regression
- 기존 money-input UX regression
- 기존 CSV/XLSX brokerage account import regression
- full unittest
- `node --check` for AccountInfo importer and loader file
- `git diff --check`
- clean status / exact-head gate
- production deploy 후 실제 AccountInfo PDF preview browser smoke
