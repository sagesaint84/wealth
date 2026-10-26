# v2.1.5 — updater 접근성·권한 위임 hotfix (#184)

현재 기준은 [Issue184 최종 요구](https://github.com/sagesaint84/wealth/issues/184)다. **system_update 위임은 이미지 정리 미리보기와 실제 정리까지 포함한다.** 이전 admin-only cleanup 문구는 철회된 이력이며 현재 정책이 아니다. #180 접기 제거는 v2.1.6, #178 미국 CNN은 v2.1.7로 순연하고 그 후 사용자와 상담한다.

## 실제 운영 문제와 UI 수정

v2.1.4 합성 테스트는 username=SYNTHETIC/role=admin을 사용해, 실제 username=admin일 때 자산 래퍼를 숨기는 운영 구조를 놓쳤다. 이 결과는 실제 관리자 진입 PASS 근거가 아니었다. 이번에는 실제 구조인 admin/admin, sagesaint/user 권한 ON/OFF, 다른 일반 계정, 초기 비밀번호 변경 계정을 재현한다.

관리자 콘솔에 사용자 관리 / 시스템 업데이트 tablist를 제공한다. 기존 settingsSystemPanel DOM 하나를 현재 로그인 역할에 맞는 최종 parent로 옮겨 사용한다. 관리자에게 자산 래퍼를 보이게 하거나 업데이트 패널을 복제하지 않는다. 관리자 panel은 실제 보이는 콘솔 슬롯, 허가된 일반 계정은 기존 설정 탭에 연결한다. aria-controls/labelledby/selected, Home/End/좌우, #settings 직접 진입/새로고침, role 이벤트 순서와 실제 getClientRects 가시성을 검증한다. 숨은 페이지에서는 updater 조회·폴링하지 않는다.

사용자 목록의 계정별 토글은 서버 저장 상태를 표시한다. 토글 조작만으로 저장하지 않는다. 선택 계정·부여/회수 내용을 확인하고 관리자 본인 비밀번호와 확인 체크를 제출해야 한다. 저장 결과를 사용자 목록에서 다시 읽는다. 신규/초기 비밀번호 변경·비활성 계정에는 부여하지 않으며, role=user를 admin으로 바꾸지 않는다.

## 권한 및 세션 계약

- users.json의 기존 users[]/불변 UUID4 id를 사용한다. 새 계정 permissions.system_update=false, 기존 필드 부재·문자열 true·잘못된 permission 형식은 default deny. 활성 admin은 기본 허용. 강제 비밀번호 변경/disabled/active=false/is_active=false는 updater 사용 불가.
- status/check/install/confirm/cleanup-preview/cleanup **매 요청 현재 DB record**를 다시 읽는다. 인증 middleware가 확인한 현재 사용자 ID와 일치해야 하고 capability가 유효해야 한다. 쿠키 role, JS can_system_update, 요청의 actor/role/user 값으로 권한을 결정하지 않는다. /api/auth/me는 안전한 can_system_update bool만 추가한다.
- 일반 위임 계정도 여섯 API 모두 허용한다. 사용자 목록/생성/삭제/비밀번호 초기화/permission grant 등 관리자 API는 계속 admin-only다. 금융/가족 소유자 범위는 바꾸지 않는다.
- 위험 POST마다 **호출자 본인 비밀번호**로 재인증, 세션·현재 ID·권한 epoch에 묶인 CSRF, 설정 public origin, JSON/body/schema/rate/명시 확인을 검사한다. 재인증 직후 DB를 다시 확인하여 그 사이 회수된 권한을 차단한다.
- 권한 변경 challenge는 admin-only이며 target UUID+enabled+actor/session을 묶은 5분 일회용 승인이다. POST에서도 현재 admin, 본인 재인증, CSRF/Origin, target UUID/실존/활성을 재검증한다. users.json의 read/validate/write 전체를 기존 reentrant thread+OS file lock으로 직렬화하며 임시 파일+replace+fsync로 저장한다. 생성·초기화·비밀번호 변경 등 기존 사용자 writer도 같은 잠금을 사용하고, 알 수 없는 기존 metadata를 보존한다.
- 권한 부여/회수와 비밀번호 초기화는 epoch를 갱신한다. 초기화는 위임도 해제한다. 권한이 회수되면 다음 요청은403이며 재부여 후에도 이전 CSRF/승인 토큰은 유효하지 않다. 이미 host에 접수된 작업은 취소하지 않고 호스트의 기존 상태/자동 복구 정책으로 완료한다.
- v2.1.5 새 로그인 쿠키는 현재 ID와 keyed credential stamp, 로그인마다 새로운 무작위 sid를 묶는다. 같은 계정의 동시 로그인도 서로 다른 승인 세션이다. 비밀번호 초기화·변경/계정 삭제 후 재생성 시 이전 bound cookie는 무효다. 본인 비밀번호 변경 완료 시 현재 세션은 새 쿠키로 갱신한다. **기존 v2.1.4 로그인은 기존 금융 화면 정책을 유지하지만 updater/권한 변경에는 한 번 로그아웃 후 재로그인해야 한다.** 이전 쿠키에는 ID/credential binding이 없어 이를 임의로 신뢰하지 않는다. 이 안내는 worker 재설치 요구가 아니다.
- 기존 초기 비밀번호 변경 POST 두 경로는 실제 must_change_password=true일 때만 허용한다. 정상 계정이 현재 비밀번호 없이 이 경로로 자기 비밀번호를 바꿔 재인증을 우회하지 못하게 한다. 정당한 초기 변경과 새 세션 발급은 유지하며, 완료 후 UI는 서버 profile/capability를 다시 읽는다. 일반 비밀번호 변경은 기존 현재 비밀번호 검증 경로를 사용한다.

## 정리 승인과 호스트 호환

정리 미리보기는 현재/마지막 정상 rollback 보호 목록과 삭제 후보를 화면에 표시한다. 해당 actor/session/epoch와 정확한 images 목록에 묶인 5분 일회용 preview_token을 발급한다. 실제 cleanup은 본인 비밀번호+CSRF/Origin+확인+이 토큰을 모두 요구한다. 미리보기 생략·다른 사용자 토큰·목록 수정·재사용·권한 회수·app 재시작 후 토큰은 거절하고 다시 미리보기해야 한다.

앱에서 토큰을 검증·제거한 뒤 호스트에는 기존 `{images:[...]}`만 전달한다. 기존 worker는 대상 목록 및 컨테이너 참조를 다시 검사하고 현재/rollback/다른 repo·서비스·보호 tag를 제외한다. managed 기록 외 이미지는 삭제하지 않으며 개별 image rm, no force만 사용한다. Docker prune/volume/금융/Toss 삭제는 추가하지 않는다.

**app/updater/*, ops/wealth-updater/*, 기존 Compose 두 파일, IPC key/runtime/protocol은 변경하지 않는다. worker 재설치/서비스 재시작이 필요하지 않다.** 기존 Linux Unix IPC 및 실제 disposable Docker swap/rollback 테스트를 다시 실행한다. 아직 worker 성공 설치·사용자 정상 확인 기록이 없으면 정리 UI/host가 안전 게이트로 거절하거나 후보가 없을 수 있다. 이를 권한 실패403과 혼동하지 않는다.

## 출시 및 운영 경계

- 기준 main=f6b966b2efaddd76a7def323da45277f8e4651d1 (PR183 병합), 새 codex/v215-updater-permissions worktree. APP_VERSION/HTML 표시/테스트=2.1.5. 변경 core/settings/update JS와 update CSS만 revision2.1.5-update1; 미변경 JS/CSS와 SW cache는 유지한다.
- Issue184의 운영자 제공 근거: v2.1.4 Oracle bootstrap/IPC/data/Toss/image/HTTP/gzip 정상, 관리자 UI 접근은 실패. 이번 Codex 작업이 서버를 직접 점검한 결과가 아니다. 기존 worker 유지, 재설치 명령을 실행하거나 권장하지 않는다.
- 별도 Draft PR, 최신 HEAD CI 및 사용자 승인 전 병합·Oracle 배포·이미지 삭제 금지. v2.1.4 UI가 막혔으므로 2.1.4→2.1.5 원클릭 성공을 주장하지 않는다.
- 승인/병합 후 정확한 main SHA의 GHCR 성공 이미지 digest를 확인하여 **사용자가 앱만 수동 digest-pin 배포**한다. 기존 두 Compose + updater overlay + 기존 pin 설정, data/Toss/IPC mounts, 현재·rollback 이미지를 보존한다. 여기에는 아직 확정된2.1.5 digest가 없으므로 실제 실행 명령/이미지 태그를 추측하지 않는다.
- 사용자 검증: 재로그인 → 실제 admin 콘솔 status/check → 일반 계정 권한 부여/회수 → sagesaint 설정 탭 ON/OFF 및 API거절 → 실제 최신 이미지/SHA/HTTP307/gzip/restarts/mounts → UI. 실제 이미지 정리는 별도 승인 전 수행하지 않는다. 첫 실제 원클릭 업그레이드는 다음 v2.1.6에서 검증한다.
- full pytest, Linux/격리 Docker, production UI/Oracle 실행 여부는 별도로 기록한다. 보호된 이전 worktree·성능 원본249개·실제 금융/인증정보·Compose·이미지를 변경·삭제하지 않는다. PR177 성능 FAIL/HOLD나 그 예외를 이 릴리스 PASS로 옮기지 않는다.
