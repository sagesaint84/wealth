(() => {
  'use strict';

  const HEALTH = {
    success: ['정상', 'success'],
    failed: ['실패', 'failed'],
    running: ['실행 중', 'running'],
    stale: ['멈춤 의심', 'failed'],
    missed: ['실행 누락', 'failed'],
    never_run: ['실행 이력 없음', 'neutral'],
    disabled: ['사용 안 함', 'neutral'],
    unconfigured: ['미설정', 'neutral'],
    unknown: ['확인 필요', 'neutral'],
  };

  const DETAIL_LABELS = {
    total_ipos: 'IPO 수',
    notifications_sent_count: '전송',
    eligible_ipos: '대상 IPO',
    all_applied_count: '전체 신청',
    notification_status: '알림',
    notification_dispatch_status: '채널 결과',
    stock_record_saved: '주식 기록',
    net_record_saved: '순자산 기록',
    action: '세션 작업',
    active: '세션 활성',
    valid: '세션 유효',
    hours_remaining: '남은 시간',
    extension_attempted: '연장 시도',
    extension_succeeded: '연장 성공',
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function addStyles() {
    if (byId('wealthAutomationStatusStyles')) return;
    const style = document.createElement('style');
    style.id = 'wealthAutomationStatusStyles';
    style.textContent = `
      .automation-status-panel{margin-top:14px;padding:13px;border:1px solid #2a3859;border-radius:9px;background:#0a1226}
      .automation-status-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap}
      .automation-status-head h4{margin:0;font-size:13px}.automation-status-head p{margin:4px 0 0;color:#91a0c1;font-size:11px;line-height:1.5}
      .automation-status-summary{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
      .automation-status-summary span,.automation-status-badge{display:inline-flex;align-items:center;border:1px solid #334155;border-radius:999px;padding:3px 7px;font-size:10.5px;color:#cbd5e1;background:#111b31}
      .automation-status-badge.success{border-color:#166534;color:#86efac}.automation-status-badge.failed{border-color:#9f1239;color:#fda4af}.automation-status-badge.running{border-color:#1d4ed8;color:#93c5fd}
      .automation-status-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
      .automation-status-card{display:grid;gap:7px;padding:10px;border:1px solid #263558;border-radius:8px;background:#081022;min-width:0}
      .automation-status-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.automation-status-card-title{font-size:11.5px;font-weight:700;color:#e2e8f0;min-width:0}
      .automation-status-meta{display:grid;gap:3px;font-size:10.5px;color:#94a3b8}.automation-status-meta-row{display:flex;justify-content:space-between;gap:10px}.automation-status-meta-row strong{font-weight:500;color:#cbd5e1;text-align:right;overflow-wrap:anywhere}
      .automation-status-details{display:flex;gap:5px;flex-wrap:wrap}.automation-status-detail{font-size:10px;padding:2px 5px;border-radius:5px;background:#111b31;color:#94a3b8}
      .automation-status-error{font-size:10px;color:#fda4af;overflow-wrap:anywhere}
      .automation-status-recent{margin-top:10px;border-top:1px solid #263558;padding-top:9px}.automation-status-recent summary{cursor:pointer;font-size:11px;color:#cbd5e1;font-weight:600}
      .automation-status-recent-list{display:grid;gap:5px;margin-top:7px}.automation-status-recent-item{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;padding:6px 7px;border-radius:6px;background:#111b31;font-size:10.5px}.automation-status-recent-main{display:grid;gap:2px;min-width:0}.automation-status-recent-main strong{font-size:10.5px;color:#cbd5e1}.automation-status-recent-main span{color:#94a3b8}
      .automation-status-empty{padding:12px;border:1px dashed #31415f;border-radius:7px;text-align:center;color:#94a3b8;font-size:11px}
      [data-theme="white"] .automation-status-panel,[data-theme="white"] .automation-status-card{background:#f8fafc}[data-theme="white"] .automation-status-card-title{color:#1e293b}[data-theme="white"] .automation-status-meta-row strong{color:#334155}[data-theme="white"] .automation-status-summary span,[data-theme="white"] .automation-status-badge,[data-theme="white"] .automation-status-detail,[data-theme="white"] .automation-status-recent-item{background:#eef2f7;color:#475569}
      @media(max-width:620px){.automation-status-grid{grid-template-columns:1fr}.automation-status-head .button{width:auto}.automation-status-meta-row{align-items:flex-start}}
    `;
    document.head.append(style);
  }

  function createPanel() {
    let panel = byId('settingsAutomationStatusPanel');
    if (panel) return panel;
    const ownerSection = byId('settingsAutomationOwnerSection');
    const tossSection = byId('settingsTossSessionSection');
    const anchor = ownerSection || tossSection;
    if (!anchor || !anchor.parentElement) return null;

    panel = document.createElement('div');
    panel.id = 'settingsAutomationStatusPanel';
    panel.className = 'automation-status-panel';

    const head = document.createElement('div');
    head.className = 'automation-status-head';
    const titleWrap = document.createElement('div');
    const title = document.createElement('h4');
    title.textContent = '자동화 실행 상태';
    const help = document.createElement('p');
    help.textContent = '최근 실행 결과와 다음 예정 시간을 표시합니다. 원문 오류·비밀정보는 표시하지 않습니다.';
    titleWrap.append(title, help);
    const refresh = document.createElement('button');
    refresh.id = 'settingsAutomationStatusRefresh';
    refresh.type = 'button';
    refresh.className = 'button secondary compact';
    refresh.textContent = '새로고침';
    refresh.addEventListener('click', () => refreshStatus(true));
    head.append(titleWrap, refresh);

    const summary = document.createElement('div');
    summary.id = 'settingsAutomationStatusSummary';
    summary.className = 'automation-status-summary';
    const grid = document.createElement('div');
    grid.id = 'settingsAutomationStatusGrid';
    grid.className = 'automation-status-grid';
    const recent = document.createElement('details');
    recent.className = 'automation-status-recent';
    const recentSummary = document.createElement('summary');
    recentSummary.textContent = '최근 실행 기록';
    const recentList = document.createElement('div');
    recentList.id = 'settingsAutomationStatusRecent';
    recentList.className = 'automation-status-recent-list';
    recent.append(recentSummary, recentList);
    const error = document.createElement('p');
    error.id = 'settingsAutomationStatusError';
    error.className = 'settings-error';
    error.hidden = true;
    error.setAttribute('role', 'alert');

    panel.append(head, summary, grid, recent, error);
    anchor.parentElement.insertBefore(panel, anchor);
    return panel;
  }

  function formatTime(value) {
    if (!value) return '없음';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return '확인 불가';
    return parsed.toLocaleString('ko-KR', {
      timeZone: 'Asia/Seoul',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }

  function formatDuration(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds)) return null;
    if (seconds < 60) return seconds.toFixed(seconds < 10 ? 1 : 0) + '초';
    return (seconds / 60).toFixed(1) + '분';
  }

  function formatDetail(key, value) {
    if (typeof value === 'boolean') return value ? '예' : '아니오';
    if (key === 'hours_remaining' && Number.isFinite(Number(value))) return Number(value).toFixed(1) + '시간';
    if (value === null || value === undefined || value === '') return '없음';
    return String(value);
  }

  function healthInfo(value) {
    return HEALTH[value] || HEALTH.unknown;
  }

  function makeBadge(health) {
    const info = healthInfo(health);
    const badge = document.createElement('span');
    badge.className = 'automation-status-badge ' + info[1];
    badge.textContent = info[0];
    return badge;
  }

  function addMeta(container, label, value) {
    const row = document.createElement('div');
    row.className = 'automation-status-meta-row';
    const left = document.createElement('span');
    left.textContent = label;
    const right = document.createElement('strong');
    right.textContent = value;
    row.append(left, right);
    container.append(row);
  }

  function renderJob(job) {
    const card = document.createElement('div');
    card.className = 'automation-status-card';
    const head = document.createElement('div');
    head.className = 'automation-status-card-head';
    const title = document.createElement('div');
    title.className = 'automation-status-card-title';
    title.textContent = job.label || job.job || '자동화';
    head.append(title, makeBadge(job.health));
    card.append(head);

    const meta = document.createElement('div');
    meta.className = 'automation-status-meta';
    const schedule = Array.isArray(job.schedules) && job.schedules.length ? job.schedules.join(', ') : '없음';
    addMeta(meta, '설정 시간', schedule);
    addMeta(meta, '마지막 결과', job.last_execution ? formatTime(job.last_execution.completed_at || job.last_execution.last_attempt_at) : '실행 이력 없음');
    addMeta(meta, '다음 예정', job.next_run_at ? formatTime(job.next_run_at) : '없음');
    if (job.last_execution) {
      const duration = formatDuration(job.last_execution.duration_seconds);
      if (duration) addMeta(meta, '소요 시간', duration);
      addMeta(meta, '시도 횟수', String(job.last_execution.attempt_count || 0));
    }
    card.append(meta);

    const details = job.last_execution && job.last_execution.details;
    if (details && typeof details === 'object') {
      const detailRow = document.createElement('div');
      detailRow.className = 'automation-status-details';
      for (const [key, value] of Object.entries(details)) {
        if (!(key in DETAIL_LABELS)) continue;
        const item = document.createElement('span');
        item.className = 'automation-status-detail';
        item.textContent = DETAIL_LABELS[key] + ' ' + formatDetail(key, value);
        detailRow.append(item);
      }
      if (detailRow.children.length) card.append(detailRow);
    }

    const errorCode = job.last_execution && job.last_execution.error_code;
    if (errorCode) {
      const error = document.createElement('div');
      error.className = 'automation-status-error';
      error.textContent = '오류 코드 · ' + errorCode;
      card.append(error);
    } else if (job.reason) {
      const reason = document.createElement('div');
      reason.className = 'automation-status-error';
      reason.textContent = '상태 코드 · ' + job.reason;
      card.append(reason);
    }
    return card;
  }

  function renderRecent(items) {
    const list = byId('settingsAutomationStatusRecent');
    if (!list) return;
    list.replaceChildren();
    const records = Array.isArray(items) ? items.slice(0, 10) : [];
    if (!records.length) {
      const empty = document.createElement('div');
      empty.className = 'automation-status-empty';
      empty.textContent = '아직 기록된 자동화 실행이 없습니다.';
      list.append(empty);
      return;
    }
    for (const item of records) {
      const row = document.createElement('div');
      row.className = 'automation-status-recent-item';
      const main = document.createElement('div');
      main.className = 'automation-status-recent-main';
      const title = document.createElement('strong');
      title.textContent = item.label || item.job || '자동화';
      const meta = document.createElement('span');
      const duration = formatDuration(item.duration_seconds);
      meta.textContent = formatTime(item.completed_at || item.last_attempt_at || item.scheduled_at) + (duration ? ' · ' + duration : '') + ' · 시도 ' + String(item.attempt_count || 0) + '회';
      main.append(title, meta);
      const health = item.status === 'SUCCESS' ? 'success' : item.status === 'RUNNING' ? 'running' : item.status === 'FAILED' ? 'failed' : 'unknown';
      row.append(main, makeBadge(health));
      list.append(row);
    }
  }

  function renderStatus(status) {
    createPanel();
    const summary = byId('settingsAutomationStatusSummary');
    const grid = byId('settingsAutomationStatusGrid');
    const error = byId('settingsAutomationStatusError');
    if (!summary || !grid || !error) return;
    error.hidden = true;
    error.textContent = '';
    summary.replaceChildren();
    grid.replaceChildren();

    if (!status || status.unavailable) {
      const empty = document.createElement('div');
      empty.className = 'automation-status-empty';
      empty.textContent = '자동화 실행 상태를 확인할 수 없습니다.';
      grid.append(empty);
      error.textContent = '상태 코드 · ' + (status && status.code ? status.code : 'AUTOMATION_STATUS_UNAVAILABLE');
      error.hidden = false;
      renderRecent([]);
      return;
    }

    const counts = status.counts || {};
    for (const text of [
      '사용 ' + String(counts.enabled || 0),
      '정상 ' + String(counts.success || 0),
      '주의 ' + String(counts.warning || 0),
      '실행 중 ' + String(counts.running || 0),
    ]) {
      const item = document.createElement('span');
      item.textContent = text;
      summary.append(item);
    }
    const jobs = Array.isArray(status.jobs) ? status.jobs : [];
    for (const job of jobs) grid.append(renderJob(job));
    if (!jobs.length) {
      const empty = document.createElement('div');
      empty.className = 'automation-status-empty';
      empty.textContent = '표시할 자동화 작업이 없습니다.';
      grid.append(empty);
    }
    renderRecent(status.recent);
  }

  async function refreshStatus(showError) {
    const panel = createPanel();
    if (!panel || typeof window.api !== 'function') return;
    const button = byId('settingsAutomationStatusRefresh');
    const error = byId('settingsAutomationStatusError');
    if (button) button.disabled = true;
    try {
      const result = await window.api('/api/settings/automation');
      renderStatus(result && result.automation && result.automation._status);
    } catch (_error) {
      if (showError && error) {
        error.textContent = '자동화 실행 상태를 새로고침하지 못했습니다.';
        error.hidden = false;
      }
    } finally {
      if (button) button.disabled = false;
    }
  }

  function watchDialog() {
    addStyles();
    createPanel();
    const dialog = byId('notificationSettingsDialog');
    if (!dialog) return;
    const observer = new MutationObserver(() => {
      if (dialog.hasAttribute('open')) refreshStatus(false);
    });
    observer.observe(dialog, {attributes: true, attributeFilter: ['open']});
    byId('settingsSaveAutomation')?.addEventListener('click', () => {
      window.setTimeout(() => refreshStatus(false), 400);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', watchDialog, {once: true});
  } else {
    watchDialog();
  }

  window.WealthAutomationStatus = {renderStatus, refreshStatus};
})();
