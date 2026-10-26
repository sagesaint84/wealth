(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const stages = {queued:'대기',checking:'사전 검사',pulling:'이미지 다운로드',replacing:'컨테이너 교체',verifying:'서버 검증',succeeded:'완료',failed:'실패',rolling_back:'자동 롤백 중',rolled_back:'이전 이미지 복구 확인',rollback_failed:'자동 복구 실패 · 운영자 확인 필요',interrupted:'재시작으로 중단',cleaning:'선별 이미지 정리'};
  const errors = {UPDATER_UNAVAILABLE:'호스트 실행기에 연결할 수 없습니다. 최초 수동 설치 또는 서버 상태 확인이 필요합니다.',UPDATER_NOT_INSTALLED:'호스트 실행기를 먼저 수동 설치해 주세요.',BUILD_NOT_READY:'최신 main 이미지가 아직 준비되지 않았습니다.',BUILD_NOT_SUCCESSFUL:'최신 main 빌드가 성공하지 않아 설치할 수 없습니다.',BUILD_EVIDENCE_UNAVAILABLE:'빌드 증거에 접근할 수 없습니다. 호스트의 GitHub 읽기 권한을 확인해 주세요.',RELEASE_UNAVAILABLE:'최신 배포 정보를 확인하지 못했습니다. 현재 운영은 유지됩니다.',UPDATE_REAUTH_FAILED:'관리자 비밀번호를 다시 확인해 주세요.',UPDATE_CSRF_INVALID:'보안 확인이 만료됐습니다. 실행 상태를 새로고침해 주세요.',UPDATE_ORIGIN_FORBIDDEN:'설정의 공개 주소와 현재 접속 주소가 일치하는지 확인해 주세요.',UPDATE_RATE_LIMIT:'요청이 많습니다. 잠시 후 다시 시도해 주세요.',INSUFFICIENT_SPACE:'안전한 설치에 필요한 디스크 여유가 부족합니다.',RELEASE_CHANGED_RECHECK:'배포본이 변경됐습니다. 업데이트 확인을 다시 눌러 주세요.',UPDATE_LOCKED:'다른 작업이 진행 중이거나 복구 확인이 필요합니다.',USER_CONFIRMATION_REQUIRED:'실제 화면의 정상 동작을 먼저 확인해 주세요.'};
  let snapshot = null, latest = null, preview = null, csrf = '', pending = false, timer = null, loading = null, reconnect = false;
  const active = () => !document.hidden && !byId('settingsSystemPanel')?.hidden && document.querySelector('.wealth-workspace')?.dataset.activeView === 'settings' && !byId('settingsSystemTab')?.hidden;
  const text = (id, value) => { if (byId(id)) byId(id).textContent = value ?? '확인 전'; };
  const error = message => { text('updateError', message); byId('updateError').hidden = !message; };
  const message = code => errors[code] || `작업을 완료하지 못했습니다 (${String(code).replace(/[^A-Z0-9_]/g, '').slice(0,80)}). 현재 작업 기록을 확인해 주세요.`;
  async function api(path, body) {
    const response = await fetch('/api/system-update/' + path, {credentials:'same-origin', cache:'no-store', ...(body ? {method:'POST', headers:{'Content-Type':'application/json','X-Wealth-Update-CSRF':csrf}, body:JSON.stringify(body)} : {})});
    const data = await response.json();
    if (!response.ok) throw Error(data.detail?.code || 'UPDATER_UNAVAILABLE');
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
    list('updateJobs', (snapshot.jobs || []).slice().reverse().map(j => `${new Date(j.created_at*1000).toLocaleString()} · ${j.kind} · ${stages[j.stage] || j.stage}${j.error ? ' · '+message(j.error) : ''}${j.rollback_result ? ' · 복구: '+j.rollback_result : ''}${j.removed ? ' · 정리 '+j.removed.length+'개 / 보존·실패 '+(j.skipped?.length || 0)+'개' : ''}`));
    const busy = pending || snapshot.busy || reconnect;
    byId('updateCheck').disabled = busy || !snapshot.host_available;
    byId('updateInstall').disabled = busy || !snapshot.host_available || !latest?.available || latest.free_bytes < latest.required_bytes;
    const installed = snapshot.jobs?.filter(j=>j.kind==='install' && j.stage==='succeeded').at(-1);
    byId('updateConfirm').disabled = busy || !installed || installed.confirmed || installed.digest !== snapshot.current?.digest;
    byId('updateCleanupPreview').disabled = busy || !installed?.confirmed;
    byId('updateCleanup').disabled = busy || !preview?.images?.length;
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
      catch (_) { reconnect = true; text('updateStatus','서버 재연결 대기 중 · 작업은 호스트에서 계속됩니다.'); }
      finally { loading = null; schedule(); }
    })();
    return loading;
  }
  function role() {
    const admin = typeof currentUserProfile !== 'undefined' && currentUserProfile?.role === 'admin';
    byId('settingsSystemTab').hidden = !admin;
    if (!admin && !byId('settingsSystemPanel').hidden) window.WealthSettings.selectSettingsTab('api');
  }
  async function action(kind) {
    if (pending || !active()) return;
    error('');
    const password = byId('updatePassword').value;
    byId('updatePassword').value = '';
    const consent = byId('updateConsent').checked;
    byId('updateConsent').checked = false;
    if (!password || !consent) { error('현재 관리자 비밀번호와 작업 확인이 필요합니다.'); return; }
    let args;
    if (kind === 'install') { if (!latest?.available) return; args = {sha:latest.sha,digest:latest.digest}; }
    else if (kind === 'confirm') { const installed = snapshot.jobs.filter(j=>j.kind==='install'&&j.stage==='succeeded').at(-1); if (!installed) return; args = {job_id:installed.id}; }
    else { if (!preview?.images?.length) return; args = {images:preview.images}; }
    pending = true; render();
    try {
      await api(kind, {...args,password,confirm:true});
      preview = null; list('updateCleanupImages',[]);
      if (kind === 'install') { latest = null; byId('updateRelease').hidden = true; }
      await load();
    } catch (e) {
      if (e instanceof TypeError || e instanceof SyntaxError) { reconnect = true; text('updateStatus','서버 재연결 대기 중 · 실행 상태에서 결과를 확인해 주세요.'); }
      else error(message(e.message));
    } finally { pending = false; render(); schedule(); }
  }
  document.addEventListener('DOMContentLoaded', () => {
    role();
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
      try { preview=await api('cleanup-preview'); list('updateCleanupImages',preview.images.length ? preview.images : ['정리할 과거 Wealth 이미지가 없습니다.']); }
      catch(e) { preview=null; error(message(e.message)); }
      finally { pending=false; render(); }
    });
    window.addEventListener('wealth:role',role);
    for (const name of ['wealth:view','wealth:settings-tab']) window.addEventListener(name,()=>{schedule(); if(active()) void load();});
    document.addEventListener('visibilitychange',()=>{schedule(); if(active()) void load();});
  });
  window.WealthSystemUpdate={load};
})();
