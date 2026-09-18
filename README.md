# Wealth

Wealth는 개인과 가족이 보유한 금융자산, 부동산, 부채, 투자 성과와 생활 가계부를 한곳에서 통합 관리하는 self-hosted 자산관리 웹 애플리케이션입니다.

데이터는 외부 클라우드나 별도 데이터베이스가 아닌 서버 로컬의 `data/` 디렉터리에 사용자별 JSON 파일로 안전하게 저장됩니다. 다중 사용자 및 가족 단위 자산 관리를 지원하며, 일반 사용자는 자신의 권한 내 데이터만 안전하게 조회하고 관리합니다.

> [!CAUTION]
> **실제 금융정보와 증권사 API 인증정보(Credential)를 다루는 애플리케이션입니다.**
> 인터넷에 임의로 직접 노출하지 마시고, 운영 전 반드시 강력한 세션 서명 키(`DASHBOARD_SECRET_KEY`)와 안전한 비밀번호를 설정하세요.

---

## 1. 주요 기능

### A. 주식 투자 및 포트폴리오
- **국내/해외 주식 및 ETF 관리**: KRX 국내주식 및 미국(US) 등 해외주식의 보유종목, 수량, 매입단가, 현재가, 평가금액 통합 관리
- **실시간 시세 및 환율 갱신**: 네이버 금융, 구글 파이낸스 및 웹 금융 데이터를 통한 주식 현재가, 시장지수(코스피/코스닥/S&P500/나스닥) 및 원/달러(USD/KRW) 환율 갱신
- **시각화 히트맵 & 자산배분**: 보유종목별 평가금액 및 수익률 기반 트리맵(Heatmap), 시장·통화·자산군별 배분 비중 차트
- **전략 버킷 (Strategy Buckets)**: 사용자 정의 투자 목적/전략별 버킷 관리, 목표 비중 실시간 검증(합계 100% 한도), 카드별 색상 액센트 및 계좌 기본값/예외 종목 매핑 지원
- **절세계좌 세액공제 관리**: 연금저축 및 IRP(개인형 퇴직연금) 계좌의 소유자별·과세연도별 세액공제 한도 적용 및 누적 절세액 계산

### B. 종합 자산 관리 (Net Worth)
- **다양한 자산군 통합**: 증권, 은행 계좌(수시입출금, 예·적금), 대출(부채), 보험(보장성/저축성), 부동산 통합 관리
- **마이너스통장 안전 상계**: `overdraft_bank_account_id`로 지정된 마이너스통장의 마이너스 잔고는 부채와 은행 잔고 간의 이중계상을 방지하도록 안전하게 상계 처리
- **부동산 및 KB시세 연동**: 보유 부동산의 시세 등록 및 KB부동산 시세 연계, 담보대출/전세보증금 부채 연동 관리
- **순자산 스냅샷 (Net Worth History)**: '오늘 기록' 및 '과거 기록 추가/수정'을 통한 일자별 총자산·총부채·순자산·환율 스냅샷 보존 및 반응형 순자산 추이 차트 제공

### C. 머니 로그 (Money Log) & 통합 캘린더
- **일원화된 탭 내비게이션**: 캘린더, 실현손익, 배당금, 가계부, 공모주 탭을 하나의 화면에서 유기적으로 탐색하고 URL 해시와 연동
- **통합 캘린더 (Calendar)**: 월별 실현손익, 배당·이자 수령일, 가계부 지출/수입 및 공모주 청약·상장 일정을 한눈에 조망 (공모주 시장 일정은 개인 소유자 필터와 독립적으로 전체 시장 일정 표시)
- **공모주 관리 (IPO & SPAC)**: 일반 기업 IPO 및 스팩(SPAC)의 청약·납입·환불·상장 일정 통합 조회, 가족 구성원별 청약 참여 여부 관리(전체/일부/미청약 표시), 최초 청약 상태 변경 또는 마감 시점의 가족 구성원을 대상(`target_owners`)으로 고정 보존, 공모주 화면 내 Wealth IPO Score(BETA 참고 지표) 제공
- **매도 실현손익**: 국내/해외 매도 실현손익 기록, 수익률 및 제비용(수수료/제세금) 관리, 외화 손익의 원통화 보존 및 역사적 환율(Historical FX) 기반 원화 환산
- **배당 및 이자 내역**: 국내/해외 주식 배당금 및 은행 예적금 이자 수령 내역 관리, 세전/세후 배당 및 월별/연도별 배당 흐름 집계
- **생활 가계부 (Ledger)**: 수입/지출 내역 기록, 카테고리 관리, 신용카드 결제일/결제계좌 연동 및 고정지출 관리

### D. 데이터 가져오기 (Import) & 중복 방지
- **파일 가져오기 (Excel/CSV)**: 주요 증권사(삼성, 신한, 미래에셋, KB, KIS, 토스, 키움 등)의 잔고/거래 엑셀 파일 및 뱅크샐러드 등의 가계부 CSV 가져오기
- **멱등성 및 지문(Fingerprint) 검증**: `file_import_identity.py`를 통한 정규화 지문 검증으로 동일 파일 중복 가져오기 방지
- **실현손익 선택 가져오기 (Selective Import)**: 증권사 API 피드에서 사용자가 원하는 항목을 선택하여 가져오는 사전 미리보기(Preview-before-write) 파이프라인 및 HMAC 서명/티켓 기반 Replay 방지 적용

### E. 공모주 시장 데이터 파이프라인 (Multi-Source Pipeline)
- **다원화 데이터 소스 연계**:
  - **한국투자증권(KIS) OpenAPI**: 공모주 청약일, 환불일, 납입일, 공모가 등 기본 시장 일정의 Primary Authority로 활용
  - **KIND (기업공시채널)**: KIS 응답 중 상장예정일 공백 건을 공모기업현황 매칭으로 보완 (Blank Fallback)
  - **네이버 금융 & KRX 상장 마스터**: 네이버 상장완료(`LISTING`) 일자와 KRX 공개 상장종목 마스터(`finder_stkisu`) 단축코드/시장구분을 교차 검증(AND)하여 실제 상장 완료일(`actual_listing_date`) 확정
  - **DART 기업공시 연계 기반**: DART 클라이언트 및 공시 보고서 파서 기반을 내장하여 향후 심층 분석 확장 준비
- **Fail-Closed 및 안전 매칭**: 네트워크 오류나 zero-row 비정상 응답 시 기존 시장 데이터 보존, 스팩(SPAC) 기수 오매칭 방지 및 ASCII 6자리 단축코드 검증

---

## 2. 화면 구성 및 UI/UX

- **데스크톱 & 모바일 반응형 내비게이션**: PC 환경에서는 좌측 사이드바, 모바일 환경에서는 하단 내비게이션 바로 최적화된 동선 제공
- **가족/소유자 필터**: 상단 헤더에서 가족 구성원 전체 또는 개별 소유자별 자산 범위를 즉시 전환하여 조회
- **2차 서브 내비게이션**: 자산(증권/은행/보험/부동산), 머니 로그(캘린더/실현손익/배당/가계부/공모주) 등 2차 탭의 타이포그래피 표준화
- **설정 화면**: 가족 구성원 관리, 사용자별 증권사 OpenAPI 인증정보 등록, 비밀번호 변경, JSON 데이터 백업/복원, 다크/라이트 테마 전환 및 현재 앱 버전 표시
- **안전한 화면 미리보기 (Preview Server)**:
  ```powershell
  .\.venv\Scripts\python.exe tests/ui_preview.py
  ```
  `http://127.0.0.1:8765`에서 가상 데이터로 화면 UI를 안전하게 체험할 수 있습니다 (실제 데이터 및 `.env` 접근 불가).

---

## 3. 지원 증권사 및 OpenAPI 기능 현황

Wealth는 실제 검증된 증권사 공식 OpenAPI 및 전용 어댑터를 통해 데이터를 연동합니다. 주문, 청약, 이체 등 자산 변경을 수반하는 API는 보안상 일절 지원하지 않으며 오직 **조회 전용(Read-Only)**으로만 동작합니다.

| 증권사 | 보유종목 (Holdings) | 예수금 (Cash) | 실현손익 (Realized P/L) | 해외주식 (Overseas) | 배당금 (Dividend) | 연동 방식 및 비고 |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **토스증권 (Toss)** | 지원 | 지원 | 지원 (선택 가져오기) | 지원 (보유/손익) | 미지원 | OpenAPI 잔고 조회 + Toss WTS(`tossctl`) 실현손익 피드 연동 |
| **KB증권** | 지원 | 미지원 | 지원 (선택 가져오기) | 부분 지원 (보유만) | 미지원 | 잔고조회 `8092`/`1861` 빈 계좌 안전 처리, 국내 실현손익(`SSQM2442`) |
| **NH투자증권 (나무)** | 지원 | 지원 | 지원 (선택 가져오기) | 지원 (보유/손익) | 미지원 | 공식 OpenAPI 기반 국내/해외 잔고 및 기간별 실현손익 연동 |
| **한국투자증권 (KIS)** | 지원 | 지원 | 지원 (선택 가져오기) | 지원 (보유/손익) | 미지원 | 공식 OpenAPI 기반 국내/해외 잔고 및 기간별 실현손익 연동 |
| **키움증권 (Kiwoom)** | 부분 지원 (국내) | 지원 | 지원 (선택 가져오기) | 부분 지원 (손익만) | 미지원 | 국내 잔고/예수금 동기화, 토큰 만료 자동 복구, 국내/해외 실현손익 |

> [!NOTE]
> - 배당금의 경우 공식 API 지원 계약이 검증된 브로커에 한해 차후 확장을 검토 중이며, 현재는 엑셀/CSV 파일 가져오기 및 수동 등록으로 정확하게 관리됩니다.
> - 토스 WTS 연동은 `tossctl` 로컬 브릿지를 통한 선택적 피드 가져오기로 동작합니다.

---

## 4. 증권사 연동 안전 모델 (Fail-Closed Sync)

Wealth는 단순히 API 응답에서 `holdings = []`가 반환되었다는 이유만으로 기존 사용자 잔고를 삭제하지 않습니다.

1. **상태 머신 분류**:
   - `SUCCESS`: 정상적으로 보유종목 및 예수금 동기화 완료
   - `CONFIRMED_EMPTY` (`AUTHORITATIVE_EMPTY`): 증권사 제공자가 공식 비즈니스 코드로 "해당 계좌에 잔고가 없음"을 명확히 확증한 경우에만 보유종목을 비움
   - `API_ERROR`: 네트워크 실패, 세션 만료, 알 수 없는 오류 코드, 스키마 불일치 등
2. **기존 데이터 보존 (Fail-Closed Data Preservation)**:
   - 동기화 중 오류나 비정상 상태가 감지되면 즉시 동기화를 중단하고 기존 등록된 포트폴리오 데이터를 그대로 유지(`data_preserved = True`)합니다.
3. **KB증권 빈 잔고 호환성**:
   - 잔고조회 전용 화이트리스트 TR(`/api/v1/ssqm1801`, `/api/v1/spqm2226`)에서만 실제 빈 계좌 응답 코드(`8092` "잔고 내역이 존재하지 않습니다", `1861` "조회할 자료가 없습니다")를 authoritative empty로 인정합니다.
   - 비잔고 TR(실현손익 등)에서는 8092/1861 수신 시 오류로 fail-closed 처리됩니다.
   - 빈 잔고 코드임에도 실제 레코드가 포함된 비정상/모순 응답은 즉시 거부됩니다.
4. **키움증권 토큰 자동 복구**:
   - 읽기 요청 중 토큰 무효화(`8005: Token이 유효하지 않습니다` 또는 HTTP 401) 발생 시, 즉시 토큰을 강제 재발급(`force_refresh=True`)하고 요청을 1회 자동 재시도합니다.
   - 키움 공식 `expires_dt` 필드를 직접 파싱하여 토큰 캐시 만료 시각을 정밀하게 관리합니다.
5. **계좌번호 보호 및 무결성**:
   - OpenAPI 응답 및 화면에 표시되는 계좌번호는 마스킹(`XXXX****-YY`) 처리되며, 시스템 내부에서는 `HMAC-SHA256` 불투명 계좌 키를 사용합니다.
   - 피드에서 실현손익을 선택하여 가져올 때 행 단위 HMAC 서명(`selection_token`)과 커밋 티켓(`preview_ticket`)을 검증하여 파라미터 변조 및 중복 저장을 원천 차단합니다.

---

## 5. 설치 및 로컬 실행

### 요구사항
- Python 3.11 이상
- Windows PowerShell 또는 Linux/macOS 셸

### 1) 소스코드 설치
```powershell
# 가상환경 생성 및 활성화
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1   # Linux/macOS: source .venv/bin/activate

# 의존성 패키지 설치
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2) 필수 환경변수 설정
프로젝트 루트에 `.env.example`을 복사하여 `.env`를 생성합니다.

```bash
cp .env.example .env
```

`.env` 파일에 최소한 다음 값을 설정해야 합니다.
```dotenv
# [필수] 애플리케이션 세션 서명 키 (누락 시 서버가 시작되지 않습니다)
DASHBOARD_SECRET_KEY=your-random-secret-key-here

# [선택] 최초 관리자 비밀번호 (미설정 시 기본값 안내 후 첫 로그인 시 변경 요구)
DASHBOARD_PASSWORD=your-admin-password
```

무작위 세션 키 생성 예시:
```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 3) 실행
```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 4829
```
Windows에서는 `대시보드_실행.cmd`를 더블클릭하여 바로 실행할 수도 있습니다.
웹 브라우저에서 `http://127.0.0.1:4829`에 접속합니다.

---

## 6. Docker 및 운영 배포

Wealth는 Docker Compose를 통한 손쉬운 컨테이너 실행을 지원합니다.

### A. 로컬 Docker 빌드 및 실행
- Docker 서비스명: `dashboard`
- 컨테이너명: `wealth`
- 포트: `4829:4829`
- 데이터 볼륨: 호스트의 `./data`를 컨테이너 내부 `/app/data`로 바인드 마운트

```bash
# 컨테이너 빌드 및 백그라운드 실행
docker compose up -d --build

# 로그 확인 (서비스명 dashboard 지정)
docker compose logs -f dashboard

# 설정 검증
docker compose config

# 컨테이너 중지 (데이터는 호스트 ./data에 보존됨)
docker compose down
```

### B. GHCR 공식 이미지 배포
GitHub Container Registry(GHCR)에 빌드된 공식 멀티아키텍처(`linux/amd64`, `linux/arm64`) 이미지를 사용합니다.

```text
ghcr.io/sagesaint84/wealth:latest
```

운영 서버 배포 시:
```bash
# GHCR 이미지 pull 및 컨테이너 실행
docker compose -f docker-compose.ghcr.yml -f docker-compose.override.yml pull
docker compose -f docker-compose.ghcr.yml -f docker-compose.override.yml up -d
```

> [!TIP]
> 배포 시 `docker-compose.override.yml`을 활용하여 호스트별 포트, 볼륨 및 재시작 정책을 유연하게 오버라이드할 수 있습니다.

---

## 7. 환경변수 가이드

사용 가능한 환경변수 템플릿은 [`.env.example`](.env.example)에 정의되어 있습니다.

| 변수명 | 필수 여부 | 기본값 / 예시 | 설명 |
| :--- | :---: | :--- | :--- |
| `DASHBOARD_SECRET_KEY` | **필수** | *(무작위 32자 이상)* | 세션 쿠키 서명용 비밀키. **누락 시 앱 실행 거부** |
| `DASHBOARD_PASSWORD` | 선택 | *(초기 비밀번호)* | 최초 설치 시 관리자 계정 초기 비밀번호 |
| `TOSSINVEST_CLIENT_ID` | 선택 | - | 토스증권 OpenAPI Client ID (기본 사용자 fallback) |
| `TOSSINVEST_CLIENT_SECRET` | 선택 | - | 토스증권 OpenAPI Client Secret |
| `KB_OPENAPI_APP_KEY` | 선택 | - | KB증권 OpenAPI App Key |
| `KB_OPENAPI_APP_SECRET` | 선택 | - | KB증권 OpenAPI App Secret |
| `NHPLUG_APP_KEY` | 선택 | - | NH투자증권 OpenAPI App Key |
| `NHPLUG_APP_SECRET` | 선택 | - | NH투자증권 OpenAPI App Secret |
| `KIS_APP_KEY` | 선택 | - | 한국투자증권 OpenAPI App Key |
| `KIS_APP_SECRET` | 선택 | - | 한국투자증권 OpenAPI App Secret |
| `KIS_ACCOUNT_NO` | 선택 | - | 한국투자증권 계좌번호 |
| `KIWOOM_APP_KEY` | 선택 | - | 키움증권 OpenAPI App Key |
| `KIWOOM_APP_SECRET` | 선택 | - | 키움증권 OpenAPI App Secret |
| `KIWOOM_ACCOUNT_NO` | 선택 | - | 키움증권 계좌번호 |
| `WEALTH_TOSS_WTS_ENABLED` | 선택 | `false` | 토스 WTS 읽기 전용 피드 어댑터 활성화 여부 |
| `WEALTH_TOSSCTL_PATH` | 선택 | `/usr/local/bin/tossctl` | `tossctl` 바이너리 실행 경로 |
| `WEALTH_TOSSCTL_CONFIG_DIR` | 선택 | - | `tossctl` 세션 설정 디렉터리 경로 |
| `WEALTH_TOSSCTL_EXPECTED_VERSION` | 선택 | `v0.50.3` | `tossctl` 고정 검증 버전 (임의 변경 금지) |
| `WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID` | 선택 | - | WTS 피드 접근이 허용된 사용자의 UUID (`data/users.json`) |

> 증권사 OpenAPI 인증키는 시스템 환경변수에 넣지 않고도, 로그인 후 웹 UI의 **[설정] → [OpenAPI 설정]**에서 사용자별로 안전하게 직접 등록할 수 있습니다.

---

## 8. 데이터 저장 및 보안 정책

### 파일시스템 구조
데이터는 호스트 파일시스템의 `data/` 디렉터리에 계정별로 격리되어 저장됩니다.
```text
data/
├─ users.json                  # 사용자 계정, 비밀번호 해시, 권한 메타데이터
└─ users/<username>/
   ├─ portfolio.json           # 포트폴리오, 계좌, 보유종목, 전략 버킷 설정
   ├─ asset_records.json       # 순자산 이력 및 시점별 스냅샷 기록
   ├─ dividend_records.json    # 배당금 및 이자 수령 기록
   ├─ realized_pnl_records.json# 매도 실현손익 기록
   ├─ ledger.json              # 수입/지출 가계부 및 신용카드 데이터
   ├─ openapi_config.json      # 사용자별 증권사 API 인증정보 (호스트 보호 필요)
   └─ *_token_cache.json       # 브로커 API 발급 토큰 캐시
```

### 보안 및 백업 원칙
1. **백업 내 민감정보 배제 (v2.2 규격)**:
   - 웹 UI의 데이터 백업(`general_data_only`) 기능은 순수 자산·거래 내역만 JSON으로 내보냅니다.
   - OpenAPI App Key, App Secret, 세션 Secret, 토큰 캐시, 비밀번호 해시는 백업 파일에 **일절 포함되지 않습니다**.
2. **세션 보안**:
   - 브라우저 쿠키는 `HttpOnly` 및 `SameSite=Lax` 속성이 적용되며, `itsdangerous` 기반의 URLSafe 서명을 검증합니다.
   - `DASHBOARD_SECRET_KEY`가 설정되지 않은 경우 서버 시작 자체가 차단되어 기본 키를 사용하는 취약점을 방지합니다.
3. **호스트 보안 책임**:
   - `data/` 디렉터리와 `.env` 파일은 호스트의 파일 권한(`chmod 600`) 및 볼륨 암호화로 보호해야 합니다.
   - Git 저장소에는 실제 `.env`, `data/`, 개인 엑셀 파일이 포함되지 않도록 `.gitignore` 및 `.dockerignore`가 엄격히 적용되어 있습니다.

---

## 9. 자동화 및 서버 운영 (`ops/`)

저장소의 `ops/` 디렉터리에는 정기 마감 및 세션 관리를 위한 스크립트 템플릿이 포함되어 있습니다.
- `ops/crontab.example`: 일일 자동화 cron 스케줄 예시
- `ops/wealth-daily-close.sh`: 장 마감 후 시세 갱신, 증권사 동기화, 일일 순자산 스냅샷을 기록하는 일일 마감 자동화 스크립트
- `ops/toss-session-check.sh`: Toss WTS 어댑터 세션 상태 점검 및 갱신 스크립트
- `ops/wealth-automation.env.example`: 자동화 전용 환경변수 템플릿

---

## 10. 개발 및 테스트

Python 표준 `unittest` 기반으로 실행되며 외부 테스트 러너 종속성 없이 즉시 검증할 수 있습니다.

```powershell
# 전체 단위 및 회귀 테스트 실행 (1,057 테스트)
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"

# 브로커 동기화 안전성 테스트
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_broker_sync_safety.py"

# 릴리스 버전 정합성 테스트
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_release_version.py"
```

### 핵심 테스트 영역
- **금융 계산 무결성**: 마이너스통장 부채 상계, 연금/IRP 세액공제 한도, 외화 실현손익 환산, 평가금액 집계 검증
- **브로커 동기화 안전성**: Fail-closed 원칙, authoritative empty 판정, 모순 응답 차단, KB 8092/1861 호환성 검증
- **토큰 자동 복구**: 키움증권 8005/401 만료 시 자동 재시도 및 공식 `expires_dt` 파싱 검증
- **가져오기 멱등성**: CSV/Excel 및 실현손익 피드 가져오기 시 중복 방지 및 HMAC 서명 검증
- **공모주 다원화 파이프라인 및 캘린더 통합**: KIS/KIND/NAVER/KRX 데이터 소스 검증, SPAC 안전 매칭, 비정상 응답 시 기존 데이터 보존(Fail-Closed), socket 수준 외부망 차단(`tests/__init__.py`) 및 캘린더·청약 상태 관리 검증
- **버전 정합성**: 백엔드, 프론트엔드 메타, 정적 캐시, Service Worker 및 문서 버전 일치 검증

---

## 11. 버전 및 변경 이력

현재 애플리케이션 버전은 **Wealth v1.3.0** (직전 릴리스: **Wealth v1.2.7**)입니다.

### 최근 릴리스 요약
- **v1.3.0 (2026-09-19)**: 머니 로그 통합 캘린더(실현손익·배당·가계부·공모주 일정 연계) 및 공모주(IPO/SPAC) 청약 관리 추가, KIS/KIND/NAVER/KRX 다원화 상장 파이프라인 및 fail-closed 무결성 체계 구축
- **v1.2.7 (2026-09-18)**: Docker 빌드 보안 보완(.dockerignore에 `toss-wts/` 제외 추가)으로 런타임 세션 설정 및 실행 파일이 이미지 레이어에 포함되는 것을 방지
- **v1.2.6 (2026-09-18)**: 주식기록 및 순자산기록의 전 가족(모두/아빠/엄마/자녀) 일괄 스냅샷 자동/수동 저장 체계 도입, 부동산 단독지분 반영 및 0원 구성원 날짜축 동기화, 서버 일일 마감 및 세션 체크 자동화 스크립트 추가
- **v1.2.5 (2026-09-18)**: 주식기록을 순수 보유 주식 기준으로 정돈하고 예수금 입출금·공모주 청약·분할매수·매도 현금화가 일간 투자성과로 오인되는 문제를 방지했으며, 주식기록 UI 및 등락률 fallback 안정성을 개선
- **v1.2.4 (2026-09-17)**: 전략 버킷 semantic color 체계 도입, 배당/현금 및 전술/방어 색상 식별성 개선, 추천 버킷 칩 컬러 스와치 dot 표시, Asset Allocation 기존 팔레트 유지
- **v1.2.3 (2026-09-17)**: KB증권 OpenAPI 실제 빈 잔고 응답(`1861 / 조회할 자료가 없습니다`) 안전 처리, 비어있지 않은 데이터 모순 응답 방어 및 회귀 테스트 확장
- **v1.2.2 (2026-09-17)**: KB증권 빈 잔고(`8092`) 처리, 키움증권 토큰 무효화(`8005`/HTTP 401) 자동 복구 및 공식 `expires_dt` 관리, 설정 화면 앱 버전 표시
- **v1.2.1 (2026-09-16)**: 머니 로그 통합 탭 내비게이션, 전략 버킷 목표 비중 실시간 검증 및 프리셋, 2차 탭 반응형 타이포그래피 표준화
- **v1.2.0 (2026-09-15)**: 마이너스통장 이중계상 방지, 연금저축/IRP 세액공제 한도 적용, 파일 가져오기 멱등화, 브로커 동기화 fail-closed 강화, 세션 시크릿 키 필수화
- **v1.1.4 (2026-09-13)**: 키움증권 공식 OpenAPI 실현손익(국내/해외) 선택 가져오기 연동
- **v1.1.3 (2026-09-13)**: NH투자증권 공식 OpenAPI 실현손익(국내/해외) 선택 가져오기 연동
- **v1.1.2 (2026-09-12)**: 한국투자증권(KIS) 공식 OpenAPI 실현손익(국내/해외) 선택 가져오기 연동
- **v1.1.1 (2026-09-12)**: 토스 WTS 실현손익 선택 가져오기 연동

전체 상세 변경 기록은 [CHANGELOG.md](CHANGELOG.md)를 참고하세요.

---

## 12. 주의사항

Wealth는 개인의 자산 관리를 돕기 위한 보조 도구입니다. 화면에 표시되는 시세, 자산 평가, 수익률 및 절세 계산 금액은 지연되거나 실제 금융기관의 정산 자료와 차이가 발생할 수 있으며, 어떠한 경우에도 투자·세무·법률 자문을 대신하지 않습니다. 금융 거래 및 세무 신고 전에는 반드시 금융기관 원본 자료와 전문가의 조언을 확인하시기 바랍니다.
