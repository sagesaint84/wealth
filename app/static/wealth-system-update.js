(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const stages = {queued:'대기',checking:'사전 검사',pulling:'이미지 다운로드',replacing:'컨테이너 교체',verifying:'서버 검증',succeeded:'완료',failed:'실패',rolling_back:'자동 롤백 중',rolled_back:'이전 이미지 복구 확인',rollback_failed:'자동 복구 실패 · 운영자 확인 필요',interrupted:'재시작으로 중단',cleaning:'선별 이미지 정리'};
  const errors = {UPDATER_UNAVAILABLE:'호스트 실행기에 연결할 수 없습니다. 기존 서버 연결 상태를 확인해 주세요.',UPDATER_NOT_INSTALLED:'기존 호스트 실행기의 연결 상태를 확인해 주세요.',BUILD_NOT_READY:'최신 main 이미지가 아직 준비되지 않았습니다.',BUILD_NOT_SUCCESSFUL:'최신 main 빌드가 성공하지 않아 설치할 수 없습니다.',BUILD_EVIDENCE_UNAVAILABLE:'빌드 증거에 접근할 수 없습니다. 호스트의 GitHub 읽기 권한을 확인해 주세요.',RELEASE_UNAVAILABLE:'최신 배포 정보를 확인하지 못했습니다. 현재 운영은 유지됩니다.',UPDATE_REAUTH_FAILED:'본인 비밀번호를 다시 확인해 주세요.',UPDATE_CSRF_INVALID:'보안 확인이 만료됐습니다. 실행 상태를 새로고침해 주세요.',UPDATE_ORIGIN_FORBIDDEN:'설정의 공개 주소와 현재 접속 주소가 일치하는지 확인해 주세요.',UPDATE_RATE_LIMIT:'요청이 많습니다. 잠시 후 다시 시도해 주세요.',INSUFFICIENT_SPACE:'안전한 설치에 필요한 디스크 여유가 부족합니다.',RELEASE_CHANGED_RECHECK:'배포본이 변경됐습니다. 업데이트 확인을 다시 눌러 주세요.',UPDATE_LOCKED:'다른 작업이 진행 중이거나 복구 확인이 필요합니다.',USER_CONFIRMATION_REQUIRED:'실제 화면의 정상 동작을 먼저 확인해 주세요.'};
  let snapshot = null, latest = null, preview = null, csrf = '', pending = false, timer = null, loading = null, reconnect = false;
  let sessionExpired = false, metadataPending = null, grant = null, grantPending = false;
  const profile = () => typeof currentUserProfile !== 'undefined' ? currentUserProfile : null;
  const consoleAdmin = () => profile()?.username === 'admin' && profile()?.role === 'admin' && !profile()?.must_change_password;
  const allowed = () => profile()?.can_system_update === true && !profile()?.must_change_password;
  const active = () => !document.hidden && !sessionExpired && allowed() && !byId('settingsSystemPanel')?.hidden &&
    (consoleAdmin() ? byId('adminMainPanel')?.style.display !== 'none' : document.querySelector('.wealth-workspace')?.dataset.activeView === 'settings' && byId('userAssetDashboardWrapper')?.style.display !== 'none');
  const text = (id, value) => { if (byId(id)) byId(id).textContent = value ?? '확인 전'; };
  const error = message => { text('updateError', message); byId('updateError').hidden = !message; };
  const message = code => errors[code] || `작업을 완료하지 못했습니다 (${String(code).replace(/[^A-Z0-9_]/g, '').slice(0,80)}). 현재 상태를 확인해 주세요.`;
  async function api(path, body) {
    const response = await fetch('/api/system-update/' + path, {credentials:'same-origin', cache:'no-store', ...(body ? {method:'POST', headers:{'Content-Type':'application/json','X-Wealth-Update-CSRF':csrf}, body:JSON.stringify(body)} : {})});
    const data = await response.json();
    if (!response.ok) {
      const code = data.detail?.code || 'UPDATER_UNAVAILABLE';
      if (response.status === 403 && code === 'SYSTEM_UPDATE_FORBIDDEN') {
        if (profile()) profile().can_system_update = false;
        role();
      }
      if (response.status === 401) {
        sessionExpired = true; reconnect = false; clearTimeout(timer);
        byId('updateRelogin').hidden = false;
      }
      throw Error(code);
    }
    return data;
  }
  function list(id, items) {
    const node = byId(id); node.replaceChildren();
    for (const value of items) { const li = document.createElement('li'); li.textContent = value; node.append(li); }
  }
  function render() {
    if (!snapshot) return;
    text('updateVersion', 'v' + snapshot.app_version);
    text('updateCurrentSha', snapshot.current?.sha);
    text('updateCurrentDigest', snapshot.current?.digest);
    text('updateRollback', snapshot.rollback?.digest || '아직 기록된 롤백 이미지 없음');
    const job = snapshot.jobs?.at(-1);
    text('updateStatus', snapshot.host_available ? (job ? `${stages[job.stage] || job.stage}${job.error ? ' · '+message(job.error) : ''}` : '호스트 실행기 연결됨 · 업데이트 확인을 눌러 주세요.') : message(snapshot.error));
    const busy = pending || snapshot.busy || reconnect || sessionExpired;
    byId('updateCheck').disabled = busy || !snapshot.host_available;
    byId('updateInstall').disabled = busy || !snapshot.host_available || !latest?.available || latest.free_bytes < latest.required_bytes;
    const installed = snapshot.jobs?.filter(j=>j.kind==='install' && j.stage==='succeeded').at(-1);
    byId('updateConfirm').disabled = busy || !installed || installed.confirmed || installed.digest !== snapshot.current?.digest;
    byId('updateCleanupPreview').disabled = busy || !installed?.confirmed;
    byId('updateCleanup').disabled = busy || !preview?.images?.length;
    text('updateCleanupHint', preview && !preview.images.length
      ? '정리할 이미지가 없습니다. 현재 이미지와 롤백 이미지는 보호됩니다.'
      : '현재 이미지와 롤백 이미지는 보호됩니다. 정리 전 미리보기가 필요합니다.');
  }
  function schedule() {
    clearTimeout(timer); timer = null;
    if (active() && (snapshot?.busy || reconnect)) timer = setTimeout(() => void load(), 3000);
  }
  async function load() {
    if (!active()) return;
    if (loading) return loading;
    loading = (async()=>{
      try { snapshot = await api('status'); csrf = snapshot.csrf_token; if (snapshot.host_available) reconnect = false; render(); }
      catch (e) {
        if (sessionExpired) error('로그인 상태가 변경되었습니다. 다시 로그인해 주세요.');
        else if (allowed()) { reconnect = true; text('updateStatus','서버 재연결 대기 중 · 작업은 호스트에서 계속됩니다.'); }
      }
      finally { loading = null; schedule(); }
    })();
    return loading;
  }
  function role() {
    const panel = byId('settingsSystemPanel');
    if (!panel) return;
    if (consoleAdmin()) {
      byId('settingsSystemTab').hidden = true;
      if (panel.parentElement !== byId('adminSystemUpdateSlot')) byId('adminSystemUpdateSlot').append(panel);
      panel.setAttribute('aria-labelledby','adminSystemTab');
      adminView(location.hash === '#settings');
    } else {
      if (panel.parentElement !== byId('settingsSurface')) {
        byId('settingsSurface').append(panel);
        panel.hidden = byId('settingsSystemTab').getAttribute('aria-selected') !== 'true';
      }
      panel.setAttribute('aria-labelledby','settingsSystemTab');
      byId('settingsSystemTab').hidden = !allowed();
      if (!allowed() && !panel.hidden) window.WealthSettings.selectSettingsTab('api');
    }
    if (!allowed()) {
      latest = null; preview = null; csrf = ''; snapshot = null; reconnect = false;
      byId('updatePassword').value = ''; byId('updateConsent').checked = false;
      clearTimeout(timer);
    }
  }
  function adminView(system) {
    if (!consoleAdmin()) return;
    byId('adminUsersView').hidden = system;
    byId('settingsSystemPanel').hidden = !system;
    for (const [id,on] of [['adminUsersTab',!system],['adminSystemTab',system]]) {
      byId(id).setAttribute('aria-selected',String(on)); byId(id).tabIndex = on ? 0 : -1;
    }
    requestAnimationFrame(()=>{ schedule(); if (active()) void load(); });
  }
  async function refreshPermission() {
    if (!profile() || metadataPending) return metadataPending;
    metadataPending = (async()=>{
      try {
        const response = await fetch('/api/auth/me',{credentials:'same-origin',cache:'no-store'});
        if (!response.ok) return;
        const me = await response.json();
        if (me.username !== profile()?.username) return;
        profile().can_system_update = me.can_system_update === true;
        profile().must_change_password = !!me.must_change_password;
        role();
      } finally { metadataPending = null; }
    })();
    return metadataPending;
  }
  async function permissionApi(path, body, token) {
    const response = await fetch(path,{credentials:'same-origin',cache:'no-store',...(body ?
      {method:'POST',headers:{'Content-Type':'application/json','X-Wealth-Update-CSRF':token},body:JSON.stringify(body)} : {})});
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401) byId('adminUpdatePermissionRelogin').hidden = false;
      throw Error(data.detail?.code || 'PERMISSION_CHANGE_FAILED');
    }
    return data;
  }
  function cancelGrant() {
    grant = null; byId('adminUpdatePermissionApproval').hidden = true;
    byId('adminUpdatePermissionPassword').value = ''; byId('adminUpdatePermissionConsent').checked = false;
  }
  async function action(kind) {
    if (pending || !active()) return;
    error('');
    const password = byId('updatePassword').value;
    byId('updatePassword').value = '';
    const consent = byId('updateConsent').checked;
    byId('updateConsent').checked = false;
    if (!password || !consent) { error('본인 비밀번호와 작업 확인이 필요합니다.'); return; }
    let args;
    if (kind === 'install') { if (!latest?.available) return; args = {sha:latest.sha,digest:latest.digest}; }
    else if (kind === 'confirm') { const installed = snapshot.jobs.filter(j=>j.kind==='install'&&j.stage==='succeeded').at(-1); if (!installed) return; args = {job_id:installed.id}; }
    else { if (!preview?.images?.length || !preview.preview_token) return; args = {images:preview.images,preview_token:preview.preview_token}; }
    pending = true; render();
    try {
      await api(kind, {...args,password,confirm:true});
      preview = null; list('updateCleanupImages',[]);
      if (kind === 'install') { latest = null; byId('updateRelease').hidden = true; }
      await load();
    } catch (e) {
      if (e instanceof TypeError || e instanceof SyntaxError) { reconnect = true; text('updateStatus','서버 재연결 대기 중 · 실행 상태에서 결과를 확인해 주세요.'); }
      else error(sessionExpired ? '로그인 상태가 변경되었습니다. 다시 로그인해 주세요.' : message(e.message));
    } finally { pending = false; render(); schedule(); }
  }
  document.addEventListener('DOMContentLoaded', () => {
    role();
    document.addEventListener('change',async event=>{
      const toggle = event.target.closest('input[data-update-user]');
      if (!toggle) return;
      const enabled = toggle.checked;toggle.checked = toggle.dataset.updateStored === 'true';
      if (!consoleAdmin() || grantPending) return;
      cancelGrant();
      text('adminUpdatePermissionMessage','권한 변경 확인을 준비 중입니다.');
      try {
        const challenge = await permissionApi('/api/admin/system-update-permissions/challenge?target_id='+encodeURIComponent(toggle.dataset.updateUser)+'&enabled='+enabled);
        grant = {id:toggle.dataset.updateUser,enabled,name:toggle.dataset.updateName,...challenge};
        text('adminUpdatePermissionTarget',`${grant.name} 계정의 업데이트·이미지 정리 권한을 ${enabled?'부여':'회수'}합니다. 사용자 관리 권한은 변경하지 않습니다.`);
        const modal=toggle.closest('dialog');if(modal?.open)modal.close();
        byId('adminUpdatePermissionApproval').hidden = false;
        byId('adminUpdatePermissionApproval').scrollIntoView({block:'center',behavior:'instant'});
        byId('adminUpdatePermissionPassword').focus();
        text('adminUpdatePermissionMessage','');
      } catch(e) {text('adminUpdatePermissionMessage',e.message==='UPDATE_SESSION_REFRESH_REQUIRED'?'권한을 변경하려면 다시 로그인해 주세요.':message(e.message));}
    });
    byId('adminUpdatePermissionCancel').addEventListener('click',cancelGrant);
    byId('adminUpdatePermissionApproval').addEventListener('submit',async event=>{
      event.preventDefault();if(!grant || grantPending)return;
      const password=byId('adminUpdatePermissionPassword').value;
      const consent=byId('adminUpdatePermissionConsent').checked;
      byId('adminUpdatePermissionPassword').value='';byId('adminUpdatePermissionConsent').checked=false;
      if(!password || !consent){text('adminUpdatePermissionMessage','관리자 본인 비밀번호와 변경 확인이 필요합니다.');return;}
      const selected=grant;grantPending=true;byId('adminUpdatePermissionSave').disabled=true;
      try {
        await permissionApi('/api/admin/users/'+encodeURIComponent(selected.id)+'/system-update',
          {enabled:selected.enabled,intent_token:selected.intent_token,password,confirm:true},selected.csrf_token);
        await refreshAdminUserList();cancelGrant();
        text('adminUpdatePermissionMessage','저장된 시스템 업데이트 권한을 반영했습니다.');
      } catch(e) {cancelGrant();text('adminUpdatePermissionMessage',message(e.message)+' 권한 토글에서 다시 시작해 주세요.');}
      finally {grantPending=false;byId('adminUpdatePermissionSave').disabled=false;}
    });
    byId('updateAuthorization').addEventListener('submit', e=>e.preventDefault());
    byId('updateRefresh').addEventListener('click', () => void load());
    byId('updateCheck').addEventListener('click', async()=>{
      if (pending || !active()) return;
      pending = true; error(''); render();
      latest = null; byId('updateRelease').hidden = true;
      try {
        latest = await api('check');
        text('updateLatestSha',latest.sha); text('updateLatestDigest',latest.digest);
        const link=byId('updateBuild'); link.href=latest.url;
        text('updateChecked',' · '+new Date(latest.checked_at*1000).toLocaleString());
        const mb=v=>(v/1048576).toFixed(0)+' MiB';
        text('updateSpace',[latest.compressed_bytes,latest.required_bytes,latest.free_bytes].map(mb).join(' / '));
        list('updateChanges',latest.changes?.map(c=>c.message) || []);
        byId('updateRelease').hidden=false;
        text('updateStatus',latest.available ? '설치 가능한 검증 배포본입니다.' : '현재 실행 이미지와 최신 배포본이 같습니다.');
      } catch(e) { error(message(e.message)); }
      finally { pending=false; render(); }
    });
    for (const [id,kind] of [['updateInstall','install'],['updateConfirm','confirm'],['updateCleanup','cleanup']]) byId(id).addEventListener('click',()=>void action(kind));
    byId('updateCleanupPreview').addEventListener('click',async()=>{
      if(pending || !active()) return;
      pending=true; error(''); render();
      try {
        preview=await api('cleanup-preview');
        list('updateCleanupImages',preview.images.length ? preview.images : ['정리할 과거 Wealth 이미지가 없습니다.']);
        const protectedList=byId('updateCleanupPreserved');protectedList.replaceChildren();
        for(const id of preview.preserved || []){
          const li=document.createElement('li'),details=document.createElement('details'),label=document.createElement('summary'),full=document.createElement('code');
          const roles=[];
          if(id===snapshot.current?.image_id)roles.push('현재 사용 이미지');
          if(id===snapshot.rollback?.image_id)roles.push('롤백 이미지');
          label.textContent=`${roles.join(' · ') || '보존 이미지'} — 보호 중 · ${id.slice(0,19)}…`;
          full.textContent=id;details.append(label,full);li.append(details);protectedList.append(li);
        }
      }
      catch(e) { preview=null; error(message(e.message)); }
      finally { pending=false; render(); }
    });
    for (const [id,system] of [['adminUsersTab',false],['adminSystemTab',true]]) {
      byId(id).addEventListener('click',()=>{location.hash=system?'#settings':'#home';adminView(system);});
      byId(id).addEventListener('keydown',e=>{
        if (!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
        e.preventDefault();const on=e.key==='End' || e.key!=='Home' && !system;
        byId(on?'adminSystemTab':'adminUsersTab').click();byId(on?'adminSystemTab':'adminUsersTab').focus();
      });
    }
    window.addEventListener('wealth:role',role);
    window.addEventListener('hashchange',()=>{if(consoleAdmin())adminView(location.hash==='#settings');});
    for (const name of ['wealth:view','wealth:settings-tab']) window.addEventListener(name,()=>{schedule(); if(active()) void load();});
    window.addEventListener('wealth:view',({detail})=>{if(detail==='settings')void refreshPermission().catch(()=>{});});
    window.addEventListener('focus',()=>void refreshPermission().catch(()=>{}));
    document.addEventListener('visibilitychange',()=>{schedule(); if(active()) void load();});
  });
  window.WealthSystemUpdate={load};
})();
