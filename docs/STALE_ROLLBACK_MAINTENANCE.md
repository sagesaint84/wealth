# #189 — 존재하지 않는 rollback 참조의 안전한 해제

## 2026-10-28 — v2.1.7 저장소 통합 후보 / 호스트 미적용

- 원본 #190의 코드 `fd8b7045d267d9ffbad4cf77518f5f780575c0c7`·문서 `d8d8434cb63ed6a121b14e299bc7dd16727abbe6`를 #191 CNN 커밋 `3897f0bea3806732553eaf01da16b0c961f23363`과 함께 새 `codex/v217-release-integration`에 커밋 없이 통합했다. 기준 main/커밋 HEAD는 `bfdc874ec9f4e802604d452dcc5368d4348edc0e`다. APP_VERSION=2.1.7 후보이며 현재 운영은 v2.1.6이다.
- #190 Windows **256 PASS/1 SKIP/1 warning**, 유지보수 64건, Linux synthetic-web-and-ipc **304 PASS**·isolated-docker-compose **2 PASS**·정적 검토 PASS는 원본 검증 근거로 유지한다. #191 Windows 96 unit/66 Chromium PASS 및 원본 HEAD CI 전체 SUCCESS도 사용자 제공 근거다. **새 통합 후보 테스트/CI는 NOT_RUN**이며 별도 사용자 재검증을 기다린다.
- root/서비스 정지/배타 잠금/이미지·설치 이력 감사/atomic 백업·복원 및 정상 자동 rollback 계약은 변경하지 않았다. 소스 통합은 Oracle `/opt/wealth-updater` 갱신이나 운영 rollback 참조 해제를 실행했다는 뜻이 아니다.
- HOST_CODE_APPLY=NOT_RUN, USER_OPERATION_APPROVAL=NOT_RUN, ORACLE_APPLY=NOT_RUN, WORKER_RESTART=NOT_RUN, GHCR_PUBLISH=NOT_RUN, MERGE=HOLD. 승인 전 worker 재설치·교체·재시작/systemd/state/Compose/pin/IPC key 변경·이미지 정리는 금지한다.
- 원본 #190/#191 Draft와 worktree를 보존한다. 실제 릴리스 및 호스트 적용은 사용자 승인 이후 별도 단계다. 현재 운영 v2.1.6 고정 이미지를 유지한다.

이하 PR #190 단독 개발·검증·운영 전략은 **당시 이력 및 승인 후 절차**로 보존한다. 현재 통합 후보 상태는 위 항목을 우선한다.

## 상태와 정책 (2026-10-27)

v2.1.6 운영·사용자 수락 PASS와 8.08 GiB 확보는 사용자 제공 사실이다. 현재 불필요한 이미지 0개이며, 삭제된 v2.1.5 이미지의 rollback 참조만 남아 있다. **그 이미지로의 자동 복구는 이미 불가능하다.** 참조를 지운다고 이미지나 저장공간이 추가 삭제되지는 않는다. v2.1.5를 재다운로드하거나 보존용 이미지를 새로 만들지 않는다.

서버 용량 우선 정책은 존재하는 현재/정상 롤백 이미지의 자동 삭제 허가가 아니다. 이번 도구는 **이미 없는 특정 참조만** 해제한다. 존재하는 롤백 이미지는 거부하며 기존 설치 중 자동 rollback, 이미지 정리 보호 정책을 유지한다. 향후 장기 보존 해제 정책은 별도 승인·테스트가 필요하다. 전역 prune, 강제 삭제 및 금융/Toss/볼륨 정리는 이 절차에 없다.

개발 기준 main: `bfdc874ec9f4e802604d452dcc5368d4348edc0e`, APP_VERSION=2.1.6 유지. 운영 실행 SHA/digest/image ID는 적용 시 실제 읽기 전용 감사로 확인한다. 이 문서의 알려진 SHA만으로 현재 운영을 추정하지 않는다.

## 구현 경계

- `python3 -m app.updater.maintenance`: root 전용 **오프라인** CLI. 브라우저/API/IPC 메서드 추가 없음. worker 서비스가 정확히 inactive이고 기존 worker.lock을 배타적으로 획득해야 한다. active/failed/unknown 서비스, 잠금 실패, active/rollback_failed/알 수 없는 작업은 거부한다.
- root 소유 비공개 state 경로, 정확한 current/rollback SHA·digest·image ID·마지막 install job ID를 요구한다. 마지막 install succeeded+confirmed, baseline rollback 일치, managed 기록, 현재 정상 실행·재시작 0·Compose/mounts/다른 컨테이너도 확인한다. 다른 컨테이너는 중지된 것까지 검사한다.
- Docker image inspect의 정확한 `No such image` 응답만 부재 증거다. Docker 연결/권한/시간 초과/기타 오류를 부재로 해석하지 않는다. 실제 이미지가 존재하면 거부한다.
- Engine의 기본 자동 복구 동작은 유지한다. 이 오프라인 CLI만 `recover=False`로 읽어서 감사 중 자동 replace/rollback을 실행하지 않는다. 기존 `--recover-failed` 경로 불변.
- apply 전 원본 state 바이트를 root-only `rollback-retire-<uuid>.json`에 atomic/fsync 백업하고 동일 감사와 파일 바이트를 재확인한다. `state.rollback=None` 한 필드만 바꾸고 기존 Engine.save()를 호출한다. jobs/managed/nonces/기타 필드, pin/IPC/Compose, 데이터/Toss, 이미지/컨테이너/볼륨은 변경하지 않는다.
- apply 실패 시 원본 바이트를 atomic 복원한다. 복원 자체가 실패하면 `MAINTENANCE_RESTORE_REQUIRED`로 중단하며 백업을 보존한다. 성공 후에도 백업은 승인된 감사 자료로 보존한다(이미지 백업이 아니며 작은 JSON 파일이다).

## 승인 후에만 사용할 운영 절차 — 이번 코딩 작업에서는 NOT_RUN

현재 운영 승인 전이므로 아래 서비스 중지·CLI 적용·다시 시작을 실행하지 않는다. 코드 HEAD `fd8b7045d267d9ffbad4cf77518f5f780575c0c7`의 Linux CI·Windows 검증 결과는 아래에 기록했다. 운영 적용에 대한 명시적 사용자 승인은 아직 NOT_RUN이다. host 코드 설치/업그레이드 자체도 별도 승인 대상이며 앱 이미지만 바꿔서는 이미 설치된 worker 코드가 갱신되지 않는다. 기존 설치기를 무작정 재실행하지 않는다.

1. 승인된 코드/호스트 런타임 경로와 파일 해시를 확인하고 기존 호스트 코드 복구본을 준비한다. 기존 서비스 정의·IPC key·Compose·pin·금융/Toss 경로를 덮어쓰지 않는다. worker 설치/재시작은 이 PR의 자동 동작이 아니다.
2. 읽기 전용으로 `docker inspect wealth`, 현재 image inspect, `docker ps -a`, updater status와 root state의 설치 기록을 대조한다. 토큰·환경·전체 state를 터미널/채팅에 출력하지 않는다. 아래 기대값 7개만 기록한다. 작업 중/rollback_failed이면 중단한다.
3. 승인된 유지보수 창에서 root가 `systemctl stop wealth-updater.service`를 실행하고 `systemctl is-active wealth-updater.service`의 inactive를 확인한다. Wealth 앱과 다른 컨테이너는 계속 실행한다. CLI는 스스로 서비스를 중지하거나 시작하지 않는다.
4. `/opt/wealth-updater`에서 다음 argv로 **dry-run**한다. 모든 값은 2단계 실제 감사값으로 바꾼다. 토큰/PAT 인자는 없다.

```sh
cd /opt/wealth-updater
/usr/bin/python3 -m app.updater.maintenance \
  --expect-current-sha '<CURRENT_SHA_40_HEX>' \
  --expect-current-digest 'sha256:<CURRENT_DIGEST_64_HEX>' \
  --expect-current-image-id 'sha256:<CURRENT_IMAGE_ID_64_HEX>' \
  --expect-rollback-sha '<MISSING_ROLLBACK_SHA_40_HEX>' \
  --expect-rollback-digest 'sha256:<MISSING_ROLLBACK_DIGEST_64_HEX>' \
  --expect-rollback-image-id 'sha256:<MISSING_ROLLBACK_IMAGE_ID_64_HEX>' \
  --expect-install-job '<LAST_CONFIRMED_INSTALL_JOB_ID_32_HEX>'
```

5. `action=dry-run`, `changed=false`, `rollback_image_exists=false`, `automatic_rollback_available=false`가 맞을 때에만 **동일 argv**에 `--apply --confirm-forget-missing-rollback`을 추가한다. 두 플래그가 모두 있어야 실제 저장한다. 대상이 바뀌면 이전 dry-run 결과를 재사용하지 않는다. 성공 결과는 `action=retired`, `changed=true`와 백업 경로다.
6. 읽기 전용으로 current 이미지 SHA/digest/ID·마운트·Compose·다른 컨테이너 전후 동일, state의 rollback만 null, 나머지 jobs/managed/nonces 동일, pin/IPC key 동일을 확인한다. state.json을 직접 편집하지 않는다. 이미지는 한 개도 새로 받거나 지우지 않는다.
7. 성공·사후 확인 후에만 운영자가 승인된 절차로 기존 worker를 시작한다. updater status의 rollback=null과 현재 정상 상태, 앱 UI에서 과거 이미지 rollback이 더 이상 제공되는 것처럼 보이지 않는지 확인한다. 현재 앱 health/이미지/마운트 및 다른 컨테이너 재확인. 이후 정상 update는 새로운 current baseline을 rollback 후보로 다시 기록한다.

## 실패·복구

- 감사/서비스/잠금/기대값 실패: 원인 조사 후 중단. state 수정·이미지 다운로드·Docker 변경을 시도하지 않는다. active/rollback_failed 작업은 이 도구로 해결하지 않는다. 기존 복구 정책/운영자 판단 대상이다.
- `MAINTENANCE_ABORTED_STATE_RESTORED`: 원본 state 바이트 자동 복원 완료다. 백업과 현재 state의 해시 및 current 이미지 불변을 root 읽기 전용으로 확인하고 추가 적용을 보류한다. 실패 원인 확인 전 worker를 시작하지 않는다.
- `MAINTENANCE_RESTORE_REQUIRED`: worker를 중지한 채 백업과 현재 파일을 보존하고 별도 복구 승인을 요청한다. 자동 복원 성공으로 취급하지 않는다. 백업은 참조 기록일 뿐 삭제된 이미지를 되살리지 않는다. `cp`/텍스트 편집으로 운영 state를 덮어쓰거나 `--recover-failed`를 임의 실행하지 않는다. 원인·파일 상태를 확인한 승인된 복구 코드/절차가 필요하다.
- 유지보수 성공을 되돌리기 위해 존재하지 않는 이미지 참조를 재등록할 필요는 없다. 운영 앱 롤백이 실제 필요하면 사용자가 별도 승인한 검증된 이미지/배포 절차를 사용한다. 이번 기능은 이미지 복구 도구가 아니다.

## PR·검증 결과와 운영 미적용 상태

- [Draft PR #190](https://github.com/sagesaint84/wealth/pull/190), branch `codex/issue189-stale-rollback`.
- 검증된 코드 commit/HEAD: `fd8b7045d267d9ffbad4cf77518f5f780575c0c7`. 단일 코드 커밋은 origin에 push 완료했다. 이 문서 후속 커밋은 코드·테스트·워크플로를 변경하지 않는다.
- 사용자 제공 최종 GitHub CI 결과: Linux `synthetic-web-and-ipc` **304 PASS**, Linux `isolated-docker-compose` **2 PASS** (위 코드 HEAD 기준).
- 사용자 Windows PowerShell 결과: **256 PASS / 1 SKIP / 1 warning**, `MAINTENANCE_CASES=64`. Windows Unix IPC skip은 예상 결과이며 Linux IPC는 위 CI에서 검증됐다. 경고는 기존 Starlette 경고다.
- 정적 코드 검토 PASS. synthetic 상태 보존·이미지 부재/존재·컨테이너 참조·잠금·atomic 백업/복원·CLI·다음 업데이트 및 자동 rollback 테스트를 안전성 workflow에 등록했다.
- Codex는 이번 후속 정리에서 pytest/Chromium/전체 회귀를 재실행하지 않았다. 위 PASS는 사용자 제공 결과이며 운영 state를 바꿨다는 의미가 아니다. 문서 변경 후 새 PR HEAD의 CI는 별도로 확인해야 하며 과거 HEAD의 결과를 새 HEAD 결과로 표시하지 않는다.

CODE_STATUS=COMMITTED_PUSHED, CODE_HEAD_CI=PASS_BY_USER_REPORT, DOC_HEAD_CI=PENDING, DRAFT_PR=190, USER_OPERATION_APPROVAL=NOT_RUN, MERGE_GATE=HOLD, ORACLE_APPLY=NOT_RUN, WORKER_RESTART=NOT_RUN.

## 같은 v2.1.6의 불필요한 앱 재배포를 피하는 전략

정적 분석 대상은 `.github/workflows/docker-publish.yml`이다. `push.branches: [main]`에 paths 필터나 앱 버전 조건이 없고 `push: true`, `platforms: linux/amd64,linux/arm64`다. 따라서 문서/호스트 도구만 바뀌어도 **main에 push하면 GHCR 발행 작업이 실행**되며, 성공 시 `latest`와 짧은 SHA 태그를 게시한다. APP_VERSION=2.1.6 유지는 발행 억제 조건이 아니다. 현재 feature 브랜치 문서 push는 이 main 발행 트리거에 해당하지 않는다.

GHCR 발행과 Oracle 배포는 별개다. 발행된 이미지를 Oracle이 다운로드/실행하지 않으면 현재 앱 이미지와 로컬 디스크 사용은 바뀌지 않는다. 다만 기존 verifier는 최신 main SHA의 성공한 발행을 요구하고, 업데이트 유무는 버전 문자열 대신 SHA/digest 차이로 판단한다. 같은 2.1.6이라도 새 main 이미지가 업데이트로 표시될 수 있으므로 버전 표시만 보고 설치하면 안 된다.

**현재 권장:** PR #190을 Draft·미병합으로 유지하고 현재 정상 v2.1.6 고정 digest/image ID를 그대로 운영한다. `latest` pull·동일 버전 원클릭 설치·앱 컨테이너 재생성을 하지 않는다. 유지보수 도구를 긴급히 적용할 필요가 없다면 다음 실제 앱 릴리스의 버전·범위·CI를 승인할 때 함께 반영한다. 이번 문서 작업에서 다음 버전을 정하거나 올리지 않는다.

유지보수가 먼저 필요하면 별도 운영 승인 후 **검증된 코드 커밋에 고정한 최소 호스트 파일**(`maintenance.py` 및 호환 `host.py`)의 해시·복구본·Linux 호환성을 확인하여 호스트 도구만 적용하는 계획을 검토한다. 앱 이미지 설치를 대신 요구하지 않으며, 서비스 중지/재시작 및 state 변경에는 별도의 사용자 승인이 필요하다. 이는 현재 실행 허가가 아니다.

추후 이 PR을 독립적으로 main에 병합하기로 승인하면 현행 워크플로상 동일 버전 GHCR 이미지가 발행될 수 있음을 수용하되, 그 이유만으로 운영 앱을 재배포하지 않는다. 기존 고정 digest를 계속 사용하고 다음 실제 앱 릴리스에서만 승인된 새 digest를 설치한다. 병합·발행 완료를 Oracle 적용 완료로 기록하지 않는다.

발행 자체도 건너뛰어야 한다면 단순 paths 필터 또는 `[skip ci]`를 즉시 적용하지 않는다. 최신 main SHA의 발행 증거를 요구하는 `ReleaseVerifier._latest()`와 맞지 않아 `BUILD_NOT_READY` 등 업데이트 확인 실패를 만들 수 있다. 별도 설계·승인 범위는 발행 트리거/릴리스 자격 정책, verifier의 신뢰할 수 있는 릴리스 선택, 관련 합성 테스트·운영 문서다. 이번 PR에서는 배포 워크플로·verifier·버전 정책을 변경하지 않는다.
