# Wealth

Wealth는 개인과 가족이 보유한 금융자산, 부동산, 부채, 투자 성과와 생활 거래를 한곳에서 관리하는 self-hosted 자산관리 웹 애플리케이션입니다.

데이터는 별도 데이터베이스가 아닌 서버의 `data/` 디렉터리에 JSON 파일로 저장됩니다. 여러 계정을 만들 수 있으며, 일반 사용자는 자신의 사용자 디렉터리에 저장된 데이터만 조회하고 관리합니다.

> 실제 금융정보와 증권사 credential을 다루는 애플리케이션입니다. 인터넷에 직접 공개하지 말고, 운영 전 반드시 강한 비밀번호와 고유한 세션 secret을 설정하세요.

## 주요 기능

### 화면 구성

- **홈**: 순자산, 현금·예적금, 등록 부채, 자산 구성, 관리 바로가기와 시장지수
- **투자**: 기존 포트폴리오 요약, 히트맵, 보유종목, 자산 기록
- **자산·계좌**: 증권, 은행·예적금·대출, 보험, 부동산
- **손익·배당**: 실현손익과 배당 내역
- **가계부**: 수입·지출, 카드 관리, 고정지출
- **설정**: 가족, 증권사 연결, 비밀번호, 백업·복원과 테마

PC에서는 왼쪽 메뉴, 모바일에서는 하단 메뉴를 사용합니다. 가족 조회 범위는 화면 상단에서 선택하며 기존 owner 처리 규칙은 유지됩니다. 홈의 금액은 기존 포트폴리오 계산 결과를 표시하며, 새로운 순자산 이력이나 카드 청구기간 계산은 추가하지 않습니다.

마이너스통장 자동 상계는 `overdraft_bank_account_id`를 명시적으로 설정한 KRW 계좌에만 적용합니다. 기존 `linked_account_id`는 이자 출금계좌 의미를 유지합니다. 과거 v2 거래 및 marker 없는 legacy 거래는 기존 안전 정책을 유지하며 자동 migration하지 않습니다.

### 순자산 기록과 전략 버킷

- 상단 **시세 갱신**은 시세 갱신, **계좌 동기화**는 설정된 증권사의 잔고·보유종목 동기화입니다. OpenAPI 인증정보는 설정에서 관리합니다.
- 홈의 **순자산 추이 → 오늘 기록**으로 현재 조회 범위의 값을 확인 후 저장합니다. 일자 기준은 한국 시간이며 같은 날짜/조회 범위는 명시적으로 확인한 경우만 교체됩니다. 자동 일일 수집이 아니므로 미기록 날짜나 과거 값을 생성하지 않습니다.
- 기록은 당시 총자산·총부채·순자산·환율을 보존합니다. 순자산 증감은 입출금/자산 등록을 포함하므로 투자수익률이 아닙니다. 외부 금융기관이 검증한 결산 기록이 아니라 사용자가 확인한 화면 값입니다.
- 투자 메뉴의 **전략 버킷 → 버킷과 분류 관리**에서 이름·목적·목표 비중을 설정합니다. 초기 버킷이나 분류는 강제로 생성하지 않습니다. 목표 비중 합계는 100% 이하여야 합니다.
- 계좌 기본 버킷을 지정한 뒤 필요한 보유내역만 예외 지정합니다. `계좌 기본값 사용`과 `명시적 미분류`를 구분합니다. 증권 예수금은 계좌 기본 버킷에 포함되고, 주식은 각 보유내역당 한 번만 집계됩니다.
- 대상은 증권 보유종목과 예수금입니다. 은행·부동산·보험은 초기 전략 버킷 대상이 아닙니다. 목표 설정은 사용자 공통이고 평가 비중은 선택한 가족 범위 기준입니다.
- 자동 매매나 잔고 변경은 없습니다. 분류는 ID에 연결되므로 동기화로 ID가 바뀐 경우 이전 분류를 추정해 옮기지 않습니다.
- 데이터는 `portfolio.json`의 optional `settings.wealth_planning`에 저장되어 기존 JSON 백업/복원에 포함됩니다. 과거 데이터 migration은 없습니다.

### 안전한 화면 미리보기

```powershell
.\.venv\Scripts\python.exe tests/ui_preview.py
```

`http://127.0.0.1:8765`에서 완전히 가상인 데이터로 화면을 확인할 수 있습니다. 이 서버는 실제 앱·`.env`·사용자 데이터에 접근하지 않고 저장 요청을 거절합니다. 실제 운영 서버로 사용하지 마세요.

### 기존 자산관리 기능

- 주요 시장지수, 원/달러 환율 및 보유종목 시세 조회
- 전체 자산, 부채, 순자산 및 투자자산 요약
- 국내·해외 주식과 ETF 보유종목 및 계좌 관리
- 자산 배분 차트와 보유종목 히트맵
- 은행 계좌, 예·적금, 보험, 대출 및 부동산 관리
- 자산 스냅샷과 기간별 자산 추이 기록
- 매도 실현손익과 배당·이자 내역 관리
- 수입·지출, 고정거래, 카드와 결제계좌를 포함한 가계부
- 가족 구성원별 자산 소유자 구분
- 관리자 계정의 사용자 생성, 비밀번호 초기화 및 사용자 삭제
- 토스증권, KB증권, NH투자증권, 한국투자증권, 키움증권 OpenAPI 연동
- 보유종목, 배당, 실현손익 및 가계부 Excel/CSV 가져오기
- JSON 데이터 백업과 복원
- 반응형 화면, 테마 전환 및 PWA 설치 지원

## Wealth 1.0.1 보안 변경

1. `/api/export`는 로그인한 사용자만 호출할 수 있습니다.
2. 인증정보가 없는 요청은 기본 사용자로 대체되지 않고 `401 Unauthorized`를 반환합니다.
3. export는 세션에 기록된 현재 사용자의 일반 자산 데이터만 읽습니다.
4. 백업에는 OpenAPI App Key, App Secret, access/refresh token, token cache, 비밀번호 해시 또는 세션 secret을 포함하지 않습니다.
5. 일반 데이터 내부에 token, secret, password, credential 성격의 필드가 중첩되어 있어도 export 전에 제거합니다.
6. `.dockerignore`가 환경파일, 사용자 데이터, 개인 문서와 개발 임시파일을 Docker build context에서 제외합니다.

새 백업 형식은 `2.2`이며 `backup_policy` 값은 `general_data_only`입니다. 백업에는 다음 데이터가 포함됩니다.

- 포트폴리오와 계좌 및 보유종목
- 자산 스냅샷
- 배당·이자 내역
- 매도 실현손익
- 가계부

OpenAPI 설정은 별도로 다시 구성해야 합니다. 기존에 생성한 구버전 백업은 credential이 포함되어 있을 수 있으므로 민감파일로 취급하세요.

## 기술 구성

| 영역 | 구성 |
| --- | --- |
| Backend | Python, FastAPI, Uvicorn |
| Frontend | 정적 HTML, CSS, Vanilla JavaScript |
| Storage | 사용자별 JSON 파일 |
| Authentication | 서명된 HttpOnly 세션 쿠키, PBKDF2-HMAC-SHA256 비밀번호 해시 |
| Import | `openpyxl`, CSV |
| External data | 증권사 OpenAPI, 웹 시세·환율 데이터 |
| Deployment | Docker Compose, GitHub Actions, GHCR |

애플리케이션 진입점은 `app/main.py`이며, 기본 포트는 `4829`입니다.

## 프로젝트 구조

```text
wealth/
├─ app/
│  ├─ main.py                   # FastAPI 앱, 인증 및 API 엔드포인트
│  ├─ services/                 # 자산·손익·배당·가계부·OpenAPI 서비스
│  └─ static/
│     ├─ index.html             # 대시보드 화면
│     ├─ wealth.js              # 화면 상태, 렌더링 및 API 호출
│     ├─ wealth.css             # 기본 스타일
│     ├─ wealth-overrides.css   # 테마와 반응형 보완 스타일
│     ├─ manifest.json          # PWA manifest
│     └─ sw.js                  # Service Worker
├─ data/                        # 실행 중 생성되는 사용자 데이터
├─ tests/                       # 표준 unittest 회귀 테스트
├─ Dockerfile
├─ docker-compose.yml
├─ docker-compose.ghcr.yml
├─ requirements.txt
└─ CHANGELOG.md
```

대표적인 사용자 데이터는 다음 위치에 저장됩니다.

```text
data/
├─ users.json
└─ users/<username>/
   ├─ portfolio.json
   ├─ asset_records.json
   ├─ dividend_records.json
   ├─ realized_pnl_records.json
   ├─ ledger.json
   ├─ openapi_config.json
   └─ *_token_cache.json
```

`openapi_config.json`과 token cache에는 민감정보가 포함될 수 있습니다. `data/` 전체의 접근권한과 백업 위치를 보호해야 합니다.

## 로컬 실행

### 요구사항

- Python 3.11 이상
- Windows PowerShell 또는 호환 셸

### 설치

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 필수 보안 설정

프로젝트 루트에 `.env`를 만들고 최소한 다음 값을 설정합니다. 실제 값은 저장소에 commit하지 마세요.

```dotenv
DASHBOARD_SECRET_KEY=<충분히 길고 무작위인 세션 서명 키>
DASHBOARD_PASSWORD=<초기 일반 사용자 비밀번호>
```

세션 키는 다음과 같이 생성할 수 있습니다.

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

OpenAPI credential은 로그인 후 화면의 OpenAPI 설정에서 사용자별로 등록할 수 있습니다. 기존 `sagesaint` 계정은 사용자 설정 파일이 없을 때 아래 환경변수를 fallback으로 지원합니다.

| 증권사 | 환경변수 |
| --- | --- |
| 토스증권 | `TOSSINVEST_CLIENT_ID`, `TOSSINVEST_CLIENT_SECRET` |
| KB증권 | `KB_OPENAPI_APP_KEY`, `KB_OPENAPI_APP_SECRET` |
| NH투자증권 | `NHPLUG_APP_KEY`, `NHPLUG_APP_SECRET` |
| 한국투자증권 | `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO` |
| 키움증권 | `KIWOOM_APP_KEY`, `KIWOOM_APP_SECRET`, `KIWOOM_ACCOUNT_NO` |

### 실행

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 4829
```

Windows에서는 `대시보드_실행.cmd`를 실행할 수도 있습니다. 브라우저에서 `http://127.0.0.1:4829`에 접속합니다.

최초 데이터 디렉터리 생성 시 관리자 계정이 만들어지며 첫 로그인 후 비밀번호 변경이 요구됩니다. 초기 설정을 마친 뒤에는 모든 기본 비밀번호를 즉시 변경하세요.

## Docker 실행

Docker Compose는 호스트의 `data/`를 `/app/data`에 마운트하고 `.env`를 `/app/.env`에 읽기 전용으로 마운트합니다. 두 항목은 이미지에 포함되지 않습니다.

```bash
docker compose up -d --build
docker compose logs -f dashboard
```

중지하려면 다음을 실행합니다.

```bash
docker compose down
```

`docker compose down`은 bind mount로 연결된 호스트의 `data/`를 삭제하지 않습니다. 운영 데이터를 삭제하려면 별도로 명시적인 백업과 확인 절차를 거치세요.

## GHCR 이미지 사용

GitHub Actions는 `main` 브랜치 push 시 `linux/amd64`와 `linux/arm64` 이미지를 빌드해 다음 위치로 게시하도록 구성되어 있습니다.

```text
ghcr.io/sagesaint84/wealth:latest
```

배포 호스트에서는 다음과 같이 이미지를 갱신할 수 있습니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.yml -f docker-compose.ghcr.yml up -d
```

## 데이터 백업과 복원

로그인 후 화면의 데이터 백업 기능으로 현재 사용자의 일반 자산 데이터를 JSON 파일로 내려받을 수 있습니다. 복원은 같은 화면에서 백업 JSON을 업로드하여 수행합니다.

- 백업 파일은 개인 금융정보를 포함하므로 암호화된 저장장치에 보관하세요.
- 1.0.1 이후 생성한 백업에는 OpenAPI credential과 token이 포함되지 않습니다.
- 복원 대상은 업로드를 수행한 현재 로그인 사용자입니다.
- 복원 전에는 현재 데이터를 별도로 백업하는 것이 좋습니다.
- 과거 버전의 백업은 OpenAPI 설정을 포함할 수 있습니다.

## 테스트

추가 dependency 없이 Python 표준 `unittest`로 실행합니다.

```powershell
python -m unittest discover -s tests -v
```

현재 회귀 테스트는 다음을 검증합니다.

- 미인증 export 차단
- 기본 사용자 fallback 차단
- 사용자 간 export 격리
- export credential 제거와 일반 자산 데이터 보존
- credential 없는 백업 복원
- Docker build context의 민감파일 제외

## 보안 운영 지침

- `.env`, `data/`, 실제 Excel/CSV 및 export 백업을 Git에 추가하지 마세요.
- 서비스는 가능하면 localhost 또는 신뢰할 수 있는 내부망에서만 실행하세요.
- 외부 접근이 필요하면 인증된 HTTPS reverse proxy와 네트워크 접근제어를 사용하세요.
- `DASHBOARD_SECRET_KEY`를 환경마다 다르게 설정하고 정기적으로 교체하세요.
- OpenAPI 권한은 필요한 범위로 제한하고 사용하지 않는 키는 폐기하세요.
- 호스트의 `data/` 디렉터리와 Docker volume을 파일 권한 및 디스크 암호화로 보호하세요.
- 로그, 장애 보고서 또는 화면 캡처에 계좌번호와 credential을 포함하지 마세요.
- OpenAPI 호출 시 credential과 계좌정보는 해당 증권사 API로 전송됩니다. 각 증권사의 이용약관과 보안정책을 확인하세요.

### 현재 보안 경계

- OpenAPI credential과 token cache는 호스트 파일시스템에 평문 JSON으로 저장됩니다.
- `DASHBOARD_SECRET_KEY`가 없으면 애플리케이션 내 기본값을 사용하므로 운영에서는 반드시 환경변수를 설정해야 합니다.
- 세션 쿠키는 HttpOnly 및 SameSite=Lax이지만 현재 `Secure` 속성을 명시하지 않습니다.
- `.dockerignore`는 이미지 포함을 방지하지만 호스트 파일 자체를 암호화하거나 삭제하지는 않습니다.
- 이 애플리케이션은 금융기관 수준의 보안 저장소나 비밀관리 시스템을 제공하지 않습니다.

## 버전

현재 문서 기준 버전은 **Wealth 1.0.1**입니다. 변경 내역은 [CHANGELOG.md](CHANGELOG.md)를 참고하세요.

## 주의사항

Wealth는 개인 자산관리 보조 도구입니다. 표시되는 시세, 수익률, 세금 및 자산 평가는 지연되거나 실제 금융기관 자료와 다를 수 있으며 투자·세무·법률 자문을 제공하지 않습니다. 중요한 의사결정 전에는 원본 금융기관 자료와 전문가의 판단을 확인하세요.
