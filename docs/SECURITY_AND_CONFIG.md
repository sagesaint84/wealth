# Wealth Security and Configuration Contract

> 현재 개발 상태는 `docs/PROJECT_STATE.md`, 기능 순서는 `docs/ROADMAP.md`를 참조합니다.
> 이 문서는 **비밀값을 어디에 저장하고, 코드가 어떻게 해석해야 하는지**에 대한 프로젝트 계약입니다.

마지막 갱신: 2026-09-26

## 1. 가장 중요한 원칙

실제 secret 값은 GitHub repo에 저장하지 않는다.

repo에 저장해도 되는 것:

- 환경변수 이름
- JSON key 이름
- 저장 경로 규칙
- masking 규칙
- resolver 우선순위
- 테스트용 가짜 값
- 공식 API 문서 URL

repo에 저장하면 안 되는 것:

- 실제 API key
- app secret
- access token / refresh token
- 세션 서명 secret
- 실제 계좌번호 전체값
- webhook secret
- 비밀번호/해시 원본
- 실제 사용자 개인 금융정보

## 2. 사용자별 영구 데이터 저장

현재 사용자 데이터 루트:

```text
data/users/<username>/
```

현재 구현은 stable UUID user id가 아니라 **username**을 디렉터리 키로 사용한다.

compose 기본 마운트:

```text
host:      ./data
container: /app/data
```

운영 디렉터리가 `/docker/wealth`라면 일반적으로:

```text
/docker/wealth/data/users/<username>/
```

가 컨테이너의 다음 경로와 대응한다.

```text
/app/data/users/<username>/
```

서버에 별도 bind mount/symlink를 구성한 경우 물리 경로는 달라질 수 있으므로 compose의 실제 mount를 기준으로 확인한다.

## 3. OpenAPI credential 저장

사용자별 증권사/OpenDART 설정은 기본적으로 다음 파일을 사용한다.

```text
data/users/<username>/openapi_config.json
```

대표 구조 예시 — **실제 값이 아닌 형태만 표현**:

```json
{
  "toss": {
    "app_key": "<secret>",
    "app_secret": "<secret>"
  },
  "kb": {
    "app_key": "<secret>",
    "app_secret": "<secret>",
    "gnl_ac_no": "<account-context>",
    "gds_no": "<product-context>"
  },
  "kis": {
    "app_key": "<secret>",
    "app_secret": "<secret>",
    "account_no": "<account>"
  },
  "kiwoom": {
    "app_key": "<secret>",
    "app_secret": "<secret>",
    "account_no": "<account>"
  },
  "dart": {
    "api_key": "<secret>"
  }
}
```

이 예시는 schema 설명용이다. 실제 credential을 문서/issue/PR/chat에 복사하지 않는다.

## 4. DART credential 계약

### 저장

```text
data/users/<username>/openapi_config.json
└─ dart.api_key
```

### resolver

기존 `app.services.ipo.dart_client.DartClient`를 재사용한다.
새 DART 기능마다 별도 credential resolver를 만들지 않는다.

현재 우선순위:

1. 명시적 `api_key` 인자 — 테스트/내부 명시적 주입용
2. `DartClient(username=...)`의 사용자별 저장 키
3. 기존 `DART_API_KEY` 환경변수 호환 fallback
4. 미설정

일반 사용자 요청 경로에서는 인증된 session username을 반드시 전달한다.

### 금지

다음과 같은 기능별 별도 전역 키를 추가하지 않는다.

```text
WEALTH_OPENDART_API_KEY
DIVIDEND_DART_API_KEY
TAX_DART_API_KEY
```

기존 DART credential 계층을 우회하면 사용자 격리와 설정 UI가 깨질 수 있다.

## 5. DART UI/API 노출 규칙

- 실제 키 전체값 반환 금지
- 키 prefix도 필요하지 않으면 노출하지 않음
- UI에는 configured 여부만 표시
- 교체 입력 화면에는 `********` 등 masking 값 사용
- masked 값을 저장 요청으로 다시 보내도 기존 secret을 의도치 않게 덮어쓰지 않음
- 삭제는 명시적 delete 동작으로 처리

API 오류 메시지에도 credential이 포함되지 않도록 masking한다.

## 6. 환경변수의 역할

환경변수는 두 종류로 구분한다.

### 애플리케이션 전역 설정

예:

- `DASHBOARD_SECRET_KEY`
- 기능 gate
- 운영환경 식별값
- 기존 호환용 전역 provider fallback

### 사용자별 credential

가능하면 `data/users/<username>/openapi_config.json`의 기존 사용자별 저장 계층을 사용한다.

새 기능을 만들 때 단순 편의를 위해 사용자 secret을 `.env` 전역값으로 승격하지 않는다.

## 7. `.env.example` 규칙

`.env.example`에는 실제 secret을 넣지 않는다.

허용:

```dotenv
DASHBOARD_SECRET_KEY=
DART_API_KEY=
```

단, 사용자별 기존 저장 계층으로 충분한 기능에 별도 새 환경변수를 추가하지 않는다.

`.env.example`의 존재는 운영에서 해당 환경변수를 반드시 사용한다는 의미가 아니므로 resolver 문서를 함께 확인한다.

## 8. 파일 권한과 atomic write

credential-bearing JSON은 기존 private/atomic write helper를 사용한다.

목표:

- partial write 방지
- 임시 파일 실패 시 원본 보존
- POSIX 환경에서 제한적인 파일 권한 유지

새 credential 저장 기능에서 일반 `Path.write_text()`로 secret 파일을 직접 덮어쓰는 방식을 새로 만들지 않는다.

## 9. 로그 규칙

로그에 출력 금지:

- API key
- app secret
- bearer token
- access/refresh token
- session cookie
- 전체 계좌번호
- 비밀번호 관련 원문

로그에 허용 가능한 정보:

- provider 이름
- configured 여부
- credential source 종류 (`user_config`, `environment`, `unconfigured`)
- 안전한 오류 코드
- masking된 계좌 식별값

외부 API URL에 query string으로 key가 포함될 수 있으므로 예외 문자열을 그대로 사용자 응답이나 로그에 남기지 않는다.

## 10. 테스트 규칙

credential 테스트에는 실제 키를 사용하지 않는다.

예:

```text
USER_DART_KEY
TEST_API_KEY
EXPLICIT_KEY
```

테스트는 최소 다음을 확인한다.

- 사용자 A/B credential isolation
- 사용자별 키가 전역 fallback보다 우선하는지
- 키 미설정 시 fail-open/fail-closed 정책이 의도와 맞는지
- masking된 API 응답에 실제 secret이 포함되지 않는지
- delete 후 secret이 제거되는지
- 기능 호출자가 인증된 username을 resolver까지 전달하는지

## 11. 금융/세금 기능의 보안 경계

사용자가 브라우저에서 입력 가능한 값으로 서버 소유 데이터나 기존 금융소득을 임의로 덮어쓰지 않는다.

예:

- 금융소득 What-if에서 기존 금융소득은 서버가 계산
- 사용자 입력은 추가 시나리오 값으로만 사용
- caller가 username을 body/query로 공급해 다른 사용자의 데이터를 선택하지 못하게 함
- owner filter는 로그인 사용자의 데이터 범위 안에서만 동작

## 12. 운영 배포에서 secret 보존

표준 GHCR 배포는 컨테이너를 `--force-recreate`할 수 있다.
따라서 secret과 사용자 데이터는 이미지 내부 writable layer에만 저장하면 안 된다.

현재 `./data:/app/data` 영구 마운트가 사용자 데이터와 사용자별 OpenAPI 설정을 보존한다.

배포 전/후 확인 대상:

```text
./data/users/<username>/openapi_config.json
```

단, 내용을 터미널/채팅에 그대로 출력하여 secret을 노출하지 않는다.
configured 여부가 필요하면 애플리케이션의 masked/status API를 우선 사용한다.

## 13. stable user id 전환 시 주의

현재 저장 path가 username 기반이므로 stable UUID 기반으로 전환할 경우 단순 코드 치환으로 처리하지 않는다.

필수 migration 요소:

- 기존 username 디렉터리 → stable id 디렉터리 매핑
- collision/누락 검증
- atomic move/copy 전략
- rollback
- backup
- 모든 서비스 path resolver 일원화
- migration 완료 전 dual-read 여부 결정

이 migration이 완료되기 전 문서와 코드는 `<username>`을 현재 사실로 유지한다.

## 14. 새 외부 API 연동 체크리스트

새 provider/API를 추가하기 전에 확인한다.

1. 기존 credential 저장소로 재사용 가능한가?
2. 사용자별 설정인가, 시스템 전역 설정인가?
3. 실제 secret이 repo에 들어가지 않는가?
4. API 응답/로그에서 masking되는가?
5. network failure 정책은 무엇인가?
6. rate limit/error code를 구분하는가?
7. 테스트에서 실제 secret 없이 검증 가능한가?
8. 컨테이너 재생성 후에도 설정이 유지되는가?
9. `PROJECT_STATE.md`와 이 문서를 갱신했는가?

## 15. 문서 자체의 보안 규칙

이 문서에는 앞으로도 실제 secret을 추가하지 않는다.

문서에 secret 예시가 필요하면 반드시 `<secret>`, `TEST_KEY`, `********`처럼 가짜 표현만 사용한다.
