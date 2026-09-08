# Linux에서 codex-refactor 브랜치 설치 / 업데이트

이 브랜치는 GHCR `latest`에 자동 배포되지 않습니다. `latest`는 main 빌드이므로 브랜치를 직접 빌드합니다. Docker Engine과 Compose 플러그인이 설치되어 있어야 합니다 (`docker version`, `docker compose version`). 아래 명령은 서버에서 직접 실행하며 오류가 나면 다음 단계로 진행하지 마세요.

## 기존 설치 업데이트 (권장)

1. 기존 컨테이너의 mount와 Compose 프로젝트명을 확인합니다. `.env` 내용이나 credential을 출력하지 않습니다.

```bash
docker inspect wealth --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
docker inspect wealth --format '{{index .Config.Labels "com.docker.compose.project"}}'
```

`/app/data`와 `/app/.env`의 호스트 경로를 메모합니다. **아래 작업 폴더의 data/.env가 그 경로와 같아야 합니다.** 다르면 중단하고 실제 기존 경로를 연결하도록 설정해야 합니다. 새 빈 data로 시작하지 마세요. 기존 컨테이너가 Compose 관리가 아니라면 이 절차를 그대로 적용하지 말고 컨테이너 전환 계획부터 확인하세요.

2. 기존 소스 폴더에서 브랜치를 확인·갱신합니다. `/실제/wealth`는 위에서 확인한 설치 폴더로 바꿉니다. 변경사항이 있으면 자동 초기화/덮어쓰기하지 말고 중단합니다.

```bash
cd /실제/wealth
git status --short --branch
git fetch origin
git switch codex-refactor
git pull --ff-only origin codex-refactor
git log -1 --oneline
test -f .env && test -d data
```

브랜치가 로컬에 없다면 `git switch --track origin/codex-refactor`로 생성합니다. 기존 서버가 image-only 설치라 Git 저장소가 없다면 별도 폴더에 clone한 뒤 기존 mount 경로를 명시적으로 재사용해야 합니다. 기존 폴더에 clone/복사하여 운영 데이터를 덮어쓰지 마세요.

3. 기존 Compose 프로젝트명으로 빌드합니다. 명시적으로 `-f docker-compose.yml`을 사용하여 GHCR 파일과 자동 override가 섞이지 않게 합니다.

```bash
WEALTH_PROJECT=$(docker inspect wealth --format '{{index .Config.Labels "com.docker.compose.project"}}')
test -n "$WEALTH_PROJECT"
docker compose -p "$WEALTH_PROJECT" -f docker-compose.yml build dashboard
```

4. 빌드 성공 후 서비스를 잠시 정지하고 호스트 전체 백업을 만듭니다. 백업에는 credential도 포함되므로 비공개 경로/권한으로 보관합니다. 앱 export에는 credential이 없으므로 이것과 용도가 다릅니다.

```bash
docker stop wealth
umask 077
WEALTH_BACKUP=$(mktemp -d /var/tmp/wealth-backup.XXXXXX)
tar -czf "$WEALTH_BACKUP/wealth-data-env.tar.gz" data .env
tar -tzf "$WEALTH_BACKUP/wealth-data-env.tar.gz" >/dev/null
```

백업 실패 시 새 버전 실행을 중단하고 `docker start wealth`로 기존 컨테이너를 재시작합니다. 백업 경로는 별도로 안전하게 기록하세요.

5. 새 컨테이너를 실행하고 확인합니다.

```bash
docker compose -p "$WEALTH_PROJECT" -f docker-compose.yml up -d --no-build dashboard
docker compose -p "$WEALTH_PROJECT" -f docker-compose.yml ps
docker compose -p "$WEALTH_PROJECT" -f docker-compose.yml logs --tail=80 dashboard
curl -I http://127.0.0.1:4829/
```

로그에 민감한 정보가 있을 수 있으므로 그대로 외부에 붙여넣지 마세요. 브라우저에서 로그인, 기존 가족/계좌/기록을 확인한 후 사용합니다. 예기치 않은 빈 계좌가 보이면 **동기화·저장하지 말고 mount 경로부터 재확인**하세요. 4829를 인터넷에 직접 공개하기보다는 기존 HTTPS reverse proxy/접근제어를 유지하세요.

`docker compose down -v`, `docker system prune --volumes`, `git reset --hard`는 이 작업에 필요하지 않습니다. 여러 컨테이너/uvicorn worker가 같은 data를 쓰는 구성은 지원하지 않습니다. 현 Dockerfile의 단일 worker를 유지하세요.

## 완전 신규 설치

```bash
git clone --branch codex-refactor --single-branch https://github.com/sagesaint84/wealth.git wealth
cd wealth
mkdir -p data
```

README 환경변수 안내에 따라 이 폴더에 실제 `.env` **파일**을 먼저 만듭니다. 기존 사용자라면 신규 설치 절차 대신 위의 기존 데이터 경로 보존 절차를 따르세요.

```bash
test -f .env
docker compose -f docker-compose.yml up -d --build dashboard
```

현재 Compose는 `./data:/app/data`, `./.env:/app/.env:ro`, `4829:4829`를 사용합니다. 서버에서 GitHub에 push할 필요는 없습니다. 브랜치 소스를 pull하고 이미지를 다시 빌드해야 코드가 반영됩니다.

공식 동작 참고: https://docs.docker.com/reference/cli/docker/compose/up/ — 변경된 이미지로 컨테이너를 재생성하며 연결된 볼륨을 유지합니다.
