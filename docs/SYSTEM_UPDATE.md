# Wealth v2.1.4 — 시스템 업데이트 설계·설치·검증

범위: [#181](https://github.com/sagesaint84/wealth/issues/181), [확정 순서 #182](https://github.com/sagesaint84/wealth/issues/182). v2.1.4 독립 Draft PR. v2.1.5 접기 제거와 v2.1.6 CNN은 이 PR에 포함하지 않는다. 사용자 승인 전 main 병합·Oracle 배포 금지.

## 역할과 신뢰 경계

관리자는 설정의 **시스템 업데이트**에서 현재 앱 버전, 실행 Git SHA·실제 Docker RepoDigest, 롤백 이미지, 성공한 최신 main 배포본·변경 내용·공간을 확인한다. 조회는 Docker 변경 없이 명시적인 확인 버튼으로만 외부 GitHub/GHCR 조회를 수행한다. 홈·비활성 설정에서는 외부 조회가 없다. 앱 버전만으로 설치 여부를 판단하지 않는다.

FastAPI는 Docker CLI, docker.sock, root SSH 키, GitHub 토큰을 받지 않는다. 앱이 접근하는 것은 `/run/wealth-updater` 읽기 전용 마운트의 제한 Unix socket 및 전용 32바이트 IPC 키다. POST마다 현재 관리자 권한, 관리자 비밀번호 재인증, 세션·현재 사용자 ID에 묶인 10분 CSRF, 설정된 public_base_url과 Origin/Referer 일치, 명시 확인, 요청 크기·필드·빈도 제한을 검사한다. 로그에는 비밀번호·키·Docker env·금융 내용이 없다. 응답은 no-store다.

호스트 실행기는 root 소유 코드·상태로 별도 systemd에서 동작한다. **Docker 제어 권한 자체는 root와 동등한 강한 권한이다.** systemd hardening이 Docker daemon 권한을 축소한다고 주장하지 않는다. 신뢰하는 최소 호스트 구성요소로 한정하고 웹 앱에는 그 권한을 넘기지 않는 설계다. IPC는 status/check/install/confirm/cleanup_preview/cleanup만 허용하며 경로·셸·Docker 인수·대상 컨테이너를 받지 않는다. 키를 가진 앱이 침해되면 이 제한된 작업을 요청할 수 있으므로 호스트에서도 대상·성공 빌드·mount·digest·작업 잠금을 다시 검사한다. IPC 인증이 최종 사용자 재인증을 대체하지 않는다.

## 상태 및 설치 계약

1. GitHub main SHA → 그 SHA의 push-triggered `docker-publish.yml` 최신 실행 → SUCCESS 및 build-and-push job SUCCESS → 정확한 job 로그의 SHA 태그 manifest digest를 확인한다. GitHub Actions 읽기 토큰이 필요하면 호스트에만 둔다. 실패·취소·누락·로그 접근 실패·rate limit은 설치 거절이다. 로그 redirect는 HTTPS Actions/Blob 호스트만 허용하며 GitHub bearer를 전달하지 않는다.
2. GHCR manifest 원문 SHA256, linux/amd64·linux/arm64 두 manifest/config SHA256 및 OCI revision을 검증한다. mutable latest와 화면 version 문자열은 신뢰 근거가 아니다. 설치 시작 시 다시 조회하여 UI 대상과 정확히 일치해야 한다.
3. 고정 `/docker/wealth`, 서비스 dashboard/container wealth, 원래 두 Compose + 별도 updater overlay, root-owned updater pin 파일만 허용한다. data·Toss 바이너리(ro)·Toss config·IPC(ro), 다른 기존 mounts, 기존 Compose 파일 해시 및 다른 컨테이너 ID·image를 대조한다. 금융 파일 내용은 읽거나 변경하지 않는다. 현재 이미지의 실제 digest·SHA, 로컬 롤백 이미지와 HTTP307/gzip, 디스크 여유를 검사한다.
4. 필요 여유는 max(2GiB, 압축 이미지 크기×3+500MiB). 부족하면 정리로 우회하지 않고 거절한다. 검증된 digest로만 pull, 기존 설정이 달라지면 교체 전 중단한다.
5. 상태를 atomic replace+file/directory fsync로 보존하고 `may_have_replaced`를 교체 **전에** 기록한다. `--no-deps --no-build --pull never --force-recreate dashboard`만 실행한다. 원래 Compose 두 파일과 updater overlay는 변경하지 않고 `/var/lib/wealth-updater/pin.yml`만 갱신한다.
6. 실행 image ID·digest·SHA, Running/restart0, HTTP GET `/`307, JS/CSS GET gzip, mounts·Compose 해시·다른 컨테이너를 3회 연속 검증한다. HTTP 검사에는 HEAD나 redirect follow를 쓰지 않는다. 실패하면 이전 로컬 image ID로 복구하고 같은 검증을 거친다. 자동 롤백도 실패하면 rollback_failed로 남겨 후속 설치를 차단한다.
7. 작업은 앱 재시작과 별개다. 작업 ID·진행·고정 오류 코드·결과·actor는 호스트 `/var/lib/wealth-updater/state.json`에 남는다. worker 재시작 시 교체 가능성이 있던 진행 작업을 먼저 롤백하며, pull 이전 작업은 interrupted로 종료한다. state 손상은 fail closed. cross-process worker lock과 작업 잠금, 영속 nonce replay 방어가 있다. 하위 명령·네트워크 호출에 timeout이 있다.
8. 성공 뒤 자동 정리하지 않는다. 사용자가 실제 화면을 확인하고 재인증해 **실제 화면 정상 확인**을 누른 뒤에만 dry-run 정리가 가능하다. 현재 이미지와 마지막 정상 롤백 이미지는 항상 보존한다. 이 실행기가 기록한 Wealth image ID만 후보이며 다른 컨테이너 참조·다른 repo/tag alias가 있으면 제외한다. 실행 직전 재검사, 개별 `docker image rm`만 사용한다. force/prune/volume/financial/Toss 삭제 명령은 없다.

## 최초 설치 전 읽기 전용 점검 — 사용자 실행

PR177의 Oracle 운영 배포는 아직 NOT_RUN이다. 홈3탭 운영 확인과 이 worker 설치/2.1.4 bootstrap은 별도 사용자 단계다. 이 문서는 실행 명령이며 실행 완료 기록이 아니다.

Oracle에서 현재 설정을 직접 확인한다. 전체 `docker inspect`나 Compose config를 공유하지 말고 다음 제한 출력만 사용한다.

```bash
cd /docker/wealth
uname -m
/usr/bin/python3 --version
/usr/bin/docker compose version
systemctl --version | head -n 1
docker inspect -f '{{.Image}} {{.State.Running}} {{.RestartCount}}' wealth
docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' wealth
docker inspect -f '{{range .Mounts}}{{println .Type .Source .Destination .RW}}{{end}}' wealth
docker image inspect -f '{{json .RepoDigests}}' "$(docker inspect -f '{{.Image}}' wealth)"
docker info --format '{{.DockerRootDir}}'
df -Pk /var/lib/docker
sha256sum docker-compose.ghcr.yml docker-compose.override.yml
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4829/
```

Python>=3.10, systemd, Docker Compose V2, /usr/bin/docker, 기존 Compose 목록·data/Toss 경로 일치를 확인한다. 다른 운영 구성이면 설치를 멈추고 실제 출력 기준으로 검토한다. 정리·볼륨 삭제·Docker prune은 하지 않는다. 현재 이미지와 rollback reference를 운영자가 보존한다. 호스트의 GHCR 접근 권한도 확인하되 비밀값을 로그/UI로 출력하지 않는다.

## 최초 worker 수동 설치 — 사용자 승인 후 한 번

승인된 v2.1.4 소스를 별도 디렉터리에 받아 검토한 뒤 저장소 루트에서:

```bash
bash -n ops/wealth-updater/install-host.sh
sudo bash ops/wealth-updater/install-host.sh
sudo systemctl status wealth-updater --no-pager
```

설치기는 기존 설치가 있으면 덮어쓰지 않고 중단한다. `/opt/wealth-updater`에는 이 릴리스의 protocol/releases/host만 설치한다. 금융 데이터·Toss·원래 Compose는 만지지 않는다. **worker 설치만으로 현재 Wealth 컨테이너는 바뀌지 않는다.** optional `/etc/wealth-updater/github.token`은 최소 Actions/Contents 읽기 권한으로 호스트에서 `sudoedit`로 설정하고 root0600을 유지한다. 셸 인수·환경 출력·UI에 토큰을 넣지 않는다. 필요한 GHCR 로그인은 전용 `/etc/wealth-updater/docker` credential 설정에서 호스트 관리자가 수행한다.

## v2.1.4 최초 앱 bootstrap — 아직 실행 금지

Draft PR 승인·최신 HEAD 필수 CI·병합 후 실제 main SHA의 멀티아키텍처 게시 SUCCESS와 digest가 확인되기 전에는 아래 자리표시자를 채우거나 실행하지 않는다. PR177 digest를 v2.1.4로 오인하지 않는다.

```bash
cd /docker/wealth
# 아래 값은 실제 승인된 2.1.4 Merge SHA/Actions에서 확인한 것으로 교체한다.
RELEASE_REF='ghcr.io/sagesaint84/wealth@sha256:REPLACE_WITH_VERIFIED_214_MANIFEST'
# 기존 정상 이미지 ID와 원래 Compose hash/mount/다른 컨테이너 목록을 먼저 기록한다.
PREVIOUS_IMAGE=$(docker inspect -f '{{.Image}}' wealth)
docker image inspect "$PREVIOUS_IMAGE" >/dev/null
printf '%s\n' "$PREVIOUS_IMAGE" | sudo tee /var/lib/wealth-updater/bootstrap-previous-image >/dev/null
sudo chmod 0600 /var/lib/wealth-updater/bootstrap-previous-image
docker pull "$RELEASE_REF"
sudo /usr/bin/python3 - "$RELEASE_REF" <<'PY'
import re,sys
from pathlib import Path
ref=sys.argv[1]
assert re.fullmatch(r'ghcr.io/sagesaint84/wealth@sha256:[a-f0-9]{64}',ref)
p=Path('/var/lib/wealth-updater/pin.yml')
p.write_text('services:\n  dashboard:\n    image: '+ref+'\n')
p.chmod(0o600)
PY
# 기존 Compose project 이름을 유지한다.
PROJECT=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' wealth)
sudo docker compose -p "$PROJECT" -f docker-compose.ghcr.yml -f docker-compose.override.yml \
  -f docker-compose.updater.yml -f /var/lib/wealth-updater/pin.yml \
  up -d --no-deps --no-build --pull never --force-recreate dashboard
```

초기 bootstrap은 worker 이전 버전에서 시작하므로 worker의 자동 롤백 대상 작업이 아니다. 운영자는 이전 이미지 ID와 동일한 Compose로 rollback pin을 작성해 복구할 준비를 하고 실행한다. 설치 후 app 표시2.1.4, worker 현재 digest/SHA, HTTP307/gzip, restart0, 원래 data/Toss mounts·Compose hash·다른 컨테이너 보존을 직접 확인한다. 문제면 pin의 image를 위 PREVIOUS_IMAGE로 바꾸고 같은 `up` 명령 후 검증한다. 이미지/볼륨은 정리하지 않는다. 운영 복구 실패 시 작업을 중단하고 실제 오류 코드를 보고한다.

초기 bootstrap 롤백 명령 (사용자가 위에서 저장한 정상 이미지가 존재하는지 확인 후):

```bash
cd /docker/wealth
sudo /usr/bin/python3 - <<'PY'
import re
from pathlib import Path
ref=Path('/var/lib/wealth-updater/bootstrap-previous-image').read_text().strip()
assert re.fullmatch(r'sha256:[a-f0-9]{64}',ref)
p=Path('/var/lib/wealth-updater/pin.yml')
p.write_text('services:\n  dashboard:\n    image: '+ref+'\n')
p.chmod(0o600)
PY
PROJECT=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' wealth)
sudo docker compose -p "$PROJECT" -f docker-compose.ghcr.yml -f docker-compose.override.yml \
  -f docker-compose.updater.yml -f /var/lib/wealth-updater/pin.yml \
  up -d --no-deps --no-build --pull never --force-recreate dashboard
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4829/
docker inspect -f '{{.Image}} {{.State.Running}} {{.RestartCount}}' wealth
```

복구 시 원래 이미지에 IPC overlay만 추가되며 data/Toss와 기존 두 Compose는 그대로다. 위 HTTP/이미지 확인 외 mounts·gzip·다른 컨테이너·실제 브라우저도 점검한다.

이후 UI 설치는 자동 rollback을 제공한다. UI 작업이 rollback_failed이면 `state.json`을 삭제/고치거나 반복 클릭하지 않는다. worker를 중지하고 root 소유 상태에서 기록된 baseline image ID·project·Compose/mount hash를 확인한 뒤 동일 설정으로 복구하고 사용자 검증을 거친다. 금융 데이터나 Toss 설정을 복원/삭제 대상으로 삼지 않는다. 호스트 운영자가 복구 원인을 확인한 뒤 아래 명령으로 기록된 rollback을 재검증할 수 있다. process lock이 있으므로 서비스 실행 중에는 거절된다.

```bash
sudo systemctl stop wealth-updater
cd /opt/wealth-updater
sudo /usr/bin/python3 -m app.updater.host --recover-failed
sudo systemctl start wealth-updater
```

RECOVERY_VERIFIED와 실제 화면 확인 전에는 복구 완료로 판단하지 않는다.

## 자동 테스트와 사용자 게이트

- 읽기 전용/웹 보안: synthetic users, CSRF/session/role/rate/body, 외부 조회 실패와 성공 빌드·digest 증거, 실제 Linux Unix IPC. 금융 데이터/비밀키 사용 없음.
- 실행기: injected Docker adapter로 pull 실패·교체 timeout·health 실패·복구 실패·worker restart·state 손상·중복·정리 보호를 검증한다.
- 실제 Docker/Compose: 별도 disposable GitHub VM에서만 합성 A/B 이미지·가짜 data/Toss/IPC mount·별도 sentinel 컨테이너로 실제 교체/HTTP/gzip/자동 rollback을 검사한다. 로컬 빌드에 registry digest가 없으므로 fixture RepoDigest만 테스트 adapter가 보충하며 이 테스트를 실제 GHCR 신뢰 검증으로 오인하지 않는다. 기본 로컬 실행은 NOT_RUN; CI에서 두 case 모두 실행하고 skip을 금지한다.
- Chromium320/360/390/768/1280: 관리자/비관리자, 설치/상태/새로고침/복구 표시/정리, 접근성·키보드·너비 및 기존 설정/홈/차트/가족 회귀. 합성 데이터만 사용한다.
- 사용자: 실제 Oracle 읽기 전용 점검, worker 1회 설치, v2.1.4 수동 bootstrap, 실제 화면·업데이트 버튼·운영 확인/정리 확인. 자동 테스트로 이 단계를 PASS 처리하지 않는다.
- 전체 pytest 여부와 Linux/운영 미실행은 별도로 기록한다. PR177 성능 FAIL/HOLD와 그 한정 예외는 v2.1.4 성능 PASS나 운영 승인으로 승계되지 않는다. v2.1.5/2.1.6은 이 변경 확정·승인 이후 최신 main에서 별도 진행한다.
