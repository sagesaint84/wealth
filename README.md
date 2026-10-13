# Wealth

Wealth는 개인과 가족의 자산, 투자 성과, 생활 수입·지출을 한곳에서 관리하는 self-hosted 웹 애플리케이션입니다. 데이터는 서버의 `data/`에 사용자별로 저장됩니다. 현재 앱 버전은 **Wealth v2.0.0**입니다.

v2.0.0은 사용자 확인 Windows 전체 pytest **3,568 passed / 5 skipped / 0 failed**, **798 subtests passed**, 신규 Chrome UI 테스트 **14 passed**를 기록했습니다. 27개 파일의 commit·push와 PR #142 생성이 완료됐습니다. GitHub Actions 결과, merge, GHCR 게시 및 Oracle 운영 배포 상태는 별도 검증이 필요합니다.

## 주요 기능

- **자산과 계좌**: 증권·은행·예적금·보험·부동산·대출을 모아 순자산과 자산 구성을 표시합니다. 계좌별 보유종목과 평가금액을 관리합니다.
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

v2 UI 변경의 사용자 실행용 검증 목록, 자산 비중/수익률 표시 정책과 cleanup 근거는 [v2 UI 마감 기록](docs/v2-ui-cleanup.md)에 정리했습니다. 앱 버전·service-worker cache는 `2.0.0`이며 static asset의 `?v=`는 파일별 cache revision입니다. 이번에 바꾸지 않은 파일의 과거 revision은 의도적으로 유지합니다.

## 프로젝트 문서

- [현재 상태](docs/PROJECT_STATE.md): main에 반영된 범위와 운영·검증 관례
- [ROADMAP](docs/ROADMAP.md): 완료 영역, 다음 후보, 보류 항목
- [보안 및 설정](docs/SECURITY_AND_CONFIG.md): 데이터 위치와 인증정보 해석 계약
- [CHANGELOG](CHANGELOG.md): 상세 변경 이력
- [docs/](docs/): 기능별 계산·가져오기·외부 공급자 계약

## 주의사항

Wealth의 시세·평가·수익률·세금 추정은 금융기관의 최종 정산이나 법적 신고 결과와 다를 수 있습니다. 금융 거래와 세무 신고 전에는 원본 자료를 확인하세요.
