# #189 — 존재하지 않는 rollback 참조의 안전한 해제

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

현재 승인 전이므로 아래 서비스 중지·CLI 적용·다시 시작을 실행하지 않는다. 새 코드의 Linux IPC/격리 Docker 안전성 CI와 사용자 PowerShell 검증, 명시적 운영 승인이 먼저다. host 코드 설치/업그레이드 자체도 별도 승인 대상이며 앱 이미지만 바꿔서는 이미 설치된 worker 코드가 갱신되지 않는다. 기존 설치기를 무작정 재실행하지 않는다.

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

## 검증 대기

Codex는 pytest/Chromium/전체 회귀를 실행하지 않았다. `tests/test_system_update_maintenance.py`에 synthetic 상태/잠금/부재·존재·사용 중/작업 상태/기대값/atomic 백업·복원/루트 CLI/다음 설치 및 자동 rollback 회귀 코드를 추가했다. 기존 Linux IPC 및 격리 Docker CI를 유지하고 maintenance 합성 테스트를 같은 안전성 workflow에 포함한다. PASS 주장은 사용자 검증과 새 HEAD CI 후에만 가능하다.

CODE_STATUS=LOCAL_UNCOMMITTED, TESTS=NOT_RUN, DRAFT_PR=NOT_CREATED, MERGE_GATE=HOLD, ORACLE_APPLY=NOT_RUN, WORKER_RESTART=NOT_RUN.
