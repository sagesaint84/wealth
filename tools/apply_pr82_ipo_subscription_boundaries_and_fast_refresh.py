from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "app" / "services" / "ipo" / "store.py"
REMINDERS = ROOT / "app" / "services" / "ipo" / "reminders.py"
ORCHESTRATOR = ROOT / "app" / "services" / "ipo" / "orchestrator.py"
MAIN = ROOT / "app" / "main.py"
INDEX = ROOT / "app" / "static" / "index.html"
IPO_JS = ROOT / "app" / "static" / "wealth-ipo.js"
REMINDER_TEST = ROOT / "tests" / "test_ipo_subscription_reminders.py"
MARKET_REFRESH_TEST = ROOT / "tests" / "test_ipo_market_refresh.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {text.count(old)}")
    return text.replace(old, new, 1)


def patch_store() -> None:
    text = STORE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from datetime import datetime, timedelta\n",
        "from datetime import datetime\n",
        "store datetime import",
    )
    start = text.index("        # Project every day of the canonical subscription period.")
    end = text.index("        # 2. Listing event", start)
    new_block = '''        # Project only the canonical subscription boundaries. A provider range
        # may span weekends/holidays, but the integrated calendar must not imply
        # that every intervening calendar date is an actionable subscription day.
        sub_start = str(ipo.get("subscription_start") or "")[:10]
        sub_end = str(ipo.get("subscription_end") or "")[:10]
        try:
            start_day = datetime.strptime(sub_start, "%Y-%m-%d").date()
            end_day = datetime.strptime(sub_end, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            start_day = end_day = None
        if start_day is not None and end_day is not None and start_day <= end_day:
            if start_day == end_day:
                boundary_days = [(start_day, "single", "청약일")]
            else:
                boundary_days = [
                    (start_day, "first", "청약 첫째날"),
                    (end_day, "last", "청약 마지막날"),
                ]
            for event_day, phase, label in boundary_days:
                date_str = event_day.isoformat()
                if not (from_date <= date_str <= to_date):
                    continue
                event_meta = dict(meta_base)
                event_meta["subscription_phase"] = phase
                events.append({
                    "id": f"ipo_subscription:{ipo_id}:{date_str}",
                    "date": date_str,
                    "type": "ipo_subscription",
                    "subtype": "공모주",
                    "owner": "모두",
                    "title": f"🎯 {company} {label}",
                    "amount_krw": None,
                    "source_id": ipo_id,
                    "meta": event_meta,
                })

'''
    text = text[:start] + new_block + text[end:]
    STORE.write_text(text, encoding="utf-8")


def patch_reminders() -> None:
    text = REMINDERS.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''        if end < start or not (start <= current <= end):
            continue
        ipo_id = str(ipo.get("ipo_id") or "").strip()
''',
        '''        if end < start:
            continue
        is_first_day = current == start
        is_last_day = current == end
        if not (is_first_day or is_last_day):
            continue
        if is_first_day and is_last_day:
            phase_label = "청약일"
        elif is_first_day:
            phase_label = "청약 첫째날"
        else:
            phase_label = "청약 마지막날"
        ipo_id = str(ipo.get("ipo_id") or "").strip()
''',
        "reminder boundary eligibility",
    )
    text = replace_once(
        text,
        '            f"📌 <b>공모주 청약 확인 — {reminder_slot[:2]}:{reminder_slot[2:]}</b>\\n"\n',
        '            f"📌 <b>공모주 {phase_label} — {reminder_slot[:2]}:{reminder_slot[2:]}</b>\\n"\n',
        "reminder phase heading",
    )
    text = replace_once(
        text,
        '''        should_warn = is_last_slot if is_last_slot is not None else (reminder_slot == "1500")
        if should_warn:
''',
        '''        should_warn = is_last_slot if is_last_slot is not None else (reminder_slot == "1500")
        if is_last_day and should_warn:
''',
        "reminder deadline warning",
    )
    REMINDERS.write_text(text, encoding="utf-8")


def patch_orchestrator() -> None:
    text = ORCHESTRATOR.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''    async def _fetch() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        subscriptions = await kis.fetch_ipo_subscription_schedule(from_date, to_date)
        listings = await kis.fetch_listing_schedule(from_date, to_date)
        return subscriptions, listings
''',
        '''    async def _fetch() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        subscriptions, listings = await asyncio.gather(
            kis.fetch_ipo_subscription_schedule(from_date, to_date),
            kis.fetch_listing_schedule(from_date, to_date),
        )
        return subscriptions, listings
''',
        "parallel KIS schedule fetch",
    )
    text = replace_once(
        text,
        '''    sources_status: dict[str, str] = {}
    # Refresh always reconciles one immutable in-memory snapshot and writes once.
''',
        '''    sources_status: dict[str, str] = {}
    market_only_touched_ids: set[str] = set()
    # Refresh always reconciles one immutable in-memory snapshot and writes once.
''',
        "market-only touched ids",
    )
    text = replace_once(
        text,
        '''    # Check KRX & NAVER
    sources_status["krx"] = "pending"
    sources_status["naver"] = "pending"
''',
        '''    # Full historical KRX/NAVER scans are intentionally excluded from
    # every routine refresh. They are available only through the explicit
    # Historical Data > KRX full-history reconciliation action.
    sources_status["krx"] = "not_requested (historical_sync_only)"
    sources_status["naver"] = "not_requested (historical_sync_only)"
''',
        "historical source status",
    )
    text = replace_once(
        text,
        '''                _, review_required = merge_ipo_record(market, item)
                review_required_count += int(review_required)
''',
        '''                merged_ipo, review_required = merge_ipo_record(market, item)
                review_required_count += int(review_required)
                if market_only and not review_required:
                    touched_id = str(merged_ipo.get("ipo_id") or "").strip()
                    if touched_id:
                        market_only_touched_ids.add(touched_id)
''',
        "track current KIS rows",
    )

    start = text.index("    # 5. KRX master data fetch")
    end = text.index("    # 6. Reconcile", start)
    new_section = '''    # 5. Historical listing confirmation is explicit-only.
    # Do not fetch the all-listed KRX master or NAVER's paginated completed IPO
    # history during normal/manual/daily refreshes. The historical-import dialog
    # owns full-history reconciliation and actually applies reviewed KRX changes.
    krx_master: list[dict[str, Any]] = []
    krx_fetch_ok = False
    naver_completed: list[dict[str, Any]] = []
    naver_fetch_ok = False

'''
    text = text[:start] + new_section + text[end:]
    text = replace_once(
        text,
        '''    # 7. Canonical feature calculation & 8. Score calculation
    for ipo in ipos:
        score_res = calculate_wealth_ipo_score(ipo, ipos)
        ipo["score"] = score_res
''',
        '''    # 7. Canonical feature calculation & 8. Score calculation.
    # An interactive market-only refresh must not churn every historical score;
    # recalculate only rows actually touched by the current schedule fetch.
    score_targets = ipos if not market_only else [
        ipo for ipo in ipos
        if str(ipo.get("ipo_id") or "").strip() in market_only_touched_ids
    ]
    for ipo in score_targets:
        score_res = calculate_wealth_ipo_score(ipo, ipos)
        ipo["score"] = score_res
''',
        "scope score recalculation",
    )
    ORCHESTRATOR.write_text(text, encoding="utf-8")


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")
    marker = '@app.post("/api/ipo/historical-import/preview")\n'
    routes = '''@app.post("/api/ipo/historical-sync/preview")
async def preview_online_historical_ipo_sync(request: Request) -> JSONResponse:
    """Explicitly query the supported full KRX IPO history and return a no-write preview."""
    import asyncio as _asyncio
    username = get_current_username(request)
    from app.services.ipo.historical_online_sync import (
        HistoricalOnlineSyncAlreadyRunning,
        HistoricalOnlineSyncError,
        create_online_historical_preview,
    )
    try:
        result = await _asyncio.to_thread(create_online_historical_preview, username)
    except HistoricalOnlineSyncAlreadyRunning as exc:
        return JSONResponse(
            {"detail": {"code": exc.code, "message": str(exc)}},
            status_code=409,
            headers={"Cache-Control": "no-store"},
        )
    except HistoricalOnlineSyncError as exc:
        source_failure = exc.code in {"KRX_HISTORY_FETCH_FAILED", "KRX_HISTORY_EMPTY"}
        return JSONResponse(
            {"detail": {"code": exc.code, "message": str(exc)}},
            status_code=502 if source_failure else 400,
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.post("/api/ipo/historical-sync/commit")
async def commit_online_historical_ipo_sync(request: Request) -> JSONResponse:
    """Apply the exact user-reviewed KRX historical reconciliation preview."""
    import asyncio as _asyncio
    username = get_current_username(request)
    payload = await request.json()
    ticket = str(payload.get("preview_ticket") or "").strip() if isinstance(payload, dict) else ""
    if not ticket:
        return JSONResponse(
            {"detail": {"code": "PREVIEW_TICKET_REQUIRED", "message": "과거자료 미리보기를 먼저 실행해 주세요."}},
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )
    from app.services.ipo.historical_online_sync import HistoricalOnlineSyncError, commit_online_historical_preview
    try:
        result = await _asyncio.to_thread(commit_online_historical_preview, ticket, username)
    except HistoricalOnlineSyncError as exc:
        conflict = exc.code in {"PREVIEW_STALE", "PREVIEW_TICKET_EXPIRED", "PREVIEW_TICKET_IN_USE"}
        return JSONResponse(
            {"detail": {"code": exc.code, "message": str(exc)}},
            status_code=409 if conflict else 400,
            headers={"Cache-Control": "no-store"},
        )
    from app.services.ipo.presentation import present_market_store
    from app.services.ipo.store import read_market_store
    return JSONResponse(
        {"market": present_market_store(username, read_market_store()), "commit": result},
        headers={"Cache-Control": "no-store"},
    )


'''
    text = replace_once(text, marker, routes + marker, "online historical API routes")
    MAIN.write_text(text, encoding="utf-8")


def patch_index() -> None:
    text = INDEX.read_text(encoding="utf-8")
    old = '''        <p class="muted">KRX Data Marketplace [20001] 신규상장종목 현황 또는 KIND 신규상장기업현황에서 다운로드한 공식 Excel/CSV를 업로드하세요. KIND는 선택조건에서 <strong>공모가</strong>를 포함해 주세요. 상장일과 확정 공모가를 기준으로 미리 확인한 뒤 반영합니다.</p>
        <label>공식 파일 <input id="ipoHistoricalImportFile" type="file" accept=".xlsx,.xlsm,.xls,.csv" required /></label>
        <div id="ipoHistoricalImportPreview" class="muted" aria-live="polite" aria-atomic="false"></div>
        <p class="muted">미리보기에서 확인된 신규 및 안전하게 보완 가능한 과거 공모주만 반영합니다. 현재 공모주 데이터의 기존 값은 덮어쓰지 않습니다.</p>
        <div class="dialog-actions"><button value="cancel" class="button secondary">취소</button><button type="button" id="ipoHistoricalPreviewBtn" class="button secondary">미리보기</button><button type="button" id="ipoHistoricalCommitBtn" class="button primary" disabled>확인 후 반영</button></div>
'''
    new = '''        <p class="muted">온라인 전체 조회는 KRX Data Marketplace [20001] 신규상장종목 현황의 2020년~현재 자료를 연도별로 조회합니다. 조회 자체는 데이터를 변경하지 않으며, 미리보기 확인 후 반영할 때만 KRX 공식값으로 과거 공모주의 상장시장·실제 상장일·확정 공모가·주관사를 정정/보완합니다.</p>
        <div class="dialog-actions"><button type="button" id="ipoHistoricalOnlinePreviewBtn" class="button secondary">🌐 KRX 전체 과거자료 조회</button></div>
        <p class="muted">또는 KRX Data Marketplace [20001] / KIND에서 직접 다운로드한 공식 Excel/CSV 파일을 불러올 수 있습니다. KIND는 선택조건에서 <strong>공모가</strong>를 포함해 주세요.</p>
        <label>공식 파일 <input id="ipoHistoricalImportFile" type="file" accept=".xlsx,.xlsm,.xls,.csv" /></label>
        <div id="ipoHistoricalImportPreview" class="muted" aria-live="polite" aria-atomic="false"></div>
        <p class="muted">온라인 KRX 조회는 미리보기에 표시된 공식값 변경만 반영합니다. 파일 가져오기는 기존처럼 신규 및 안전하게 보완 가능한 값만 반영하며 기존 비어 있지 않은 값은 덮어쓰지 않습니다.</p>
        <div class="dialog-actions"><button value="cancel" class="button secondary">취소</button><button type="button" id="ipoHistoricalPreviewBtn" class="button secondary">파일 미리보기</button><button type="button" id="ipoHistoricalCommitBtn" class="button primary" disabled>확인 후 반영</button></div>
'''
    text = replace_once(text, old, new, "historical import dialog")
    INDEX.write_text(text, encoding="utf-8")


def patch_ipo_js() -> None:
    text = IPO_JS.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''  let historicalImportTicket = null;
  let historicalImportCanCommit = false;
''',
        '''  let historicalImportTicket = null;
  let historicalImportCanCommit = false;
  let historicalImportMode = null;
''',
        "historical import mode state",
    )
    text = replace_once(
        text,
        '''    preview.replaceChildren();

    const s = payload?.summary || {};
''',
        '''    preview.replaceChildren();

    if (payload?.source === 'KRX_HISTORICAL_ONLINE') {
      const s = payload?.summary || {};
      const summary = document.createElement('p');
      summary.className = 'ipo-historical-preview-summary';
      summary.textContent =
        `KRX 온라인 ${payload?.from_year || ''}~${payload?.to_year || ''} · 조회 ${s.fetched || 0}` +
        ` / 신규 ${s.new || 0} / 정정 ${s.updated || 0} / 동일 ${s.unchanged || 0}` +
        ` / 검토 필요 ${s.review_required || 0} / 무효 ${s.invalid || 0}`;
      preview.appendChild(summary);

      const changes = Array.isArray(payload?.changes) ? payload.changes : [];
      if (changes.length > 0) {
        const title = document.createElement('strong');
        title.textContent = '반영 예정 변경';
        preview.appendChild(title);
        const fieldLabels = {
          market: '상장시장', actual_listing_date: '실제 상장일',
          final_offer_price: '확정 공모가', lead_managers: '주관사', listing_track: '상장유형'
        };
        const valueText = (value) => Array.isArray(value) ? value.join(', ') : (value ?? '—');
        const list = document.createElement('ul');
        list.className = 'ipo-historical-preview-issues';
        changes.forEach((item) => {
          const row = document.createElement('li');
          const identity = [item?.company_name, item?.stock_code].filter(Boolean).join(' · ');
          if (item?.classification === 'NEW') {
            row.textContent = `${identity} · 신규 과거 공모주 추가`;
          } else {
            const diffs = (item?.changes || []).map(change =>
              `${fieldLabels[change.field] || change.field}: ${valueText(change.before)} → ${valueText(change.after)}`
            );
            row.textContent = `${identity} · ${diffs.join(' / ')}`;
          }
          list.appendChild(row);
        });
        preview.appendChild(list);
      }
      if (payload?.changes_truncated) {
        const more = document.createElement('p');
        more.className = 'muted';
        more.textContent = `외 ${payload.changes_truncated}건의 반영 예정 항목이 있습니다.`;
        preview.appendChild(more);
      }
      const issues = Array.isArray(payload?.issues) ? payload.issues : [];
      if (issues.length > 0) {
        const issueTitle = document.createElement('strong');
        issueTitle.textContent = '자동 반영하지 않는 검토 항목';
        preview.appendChild(issueTitle);
        const issueList = document.createElement('ul');
        issueList.className = 'ipo-historical-preview-issues';
        issues.forEach((issue) => {
          const row = document.createElement('li');
          const identity = [issue?.company_name, issue?.stock_code].filter(Boolean).join(' · ');
          row.textContent = `${identity ? `${identity} · ` : ''}${historicalIssueLabel(issue?.reason)}`;
          issueList.appendChild(row);
        });
        preview.appendChild(issueList);
      }
      return;
    }

    const s = payload?.summary || {};
''',
        "online historical preview renderer",
    )
    text = replace_once(
        text,
        '''    const previewButton = document.getElementById('ipoHistoricalPreviewBtn');
    const commitButton = document.getElementById('ipoHistoricalCommitBtn');
    const fileInput = document.getElementById('ipoHistoricalImportFile');

    if (openButton) openButton.disabled = busy || refreshInFlight;
    if (fileInput) fileInput.disabled = busy;
''',
        '''    const previewButton = document.getElementById('ipoHistoricalPreviewBtn');
    const onlineButton = document.getElementById('ipoHistoricalOnlinePreviewBtn');
    const commitButton = document.getElementById('ipoHistoricalCommitBtn');
    const fileInput = document.getElementById('ipoHistoricalImportFile');

    if (openButton) openButton.disabled = busy || refreshInFlight;
    if (fileInput) fileInput.disabled = busy;
    if (onlineButton) {
      onlineButton.disabled = busy;
      if (busy && phase === 'online-preview') {
        onlineButton.setAttribute('aria-busy', 'true');
        onlineButton.textContent = 'KRX 전체 조회 중…';
      } else {
        onlineButton.removeAttribute('aria-busy');
        onlineButton.textContent = '🌐 KRX 전체 과거자료 조회';
      }
    }
''',
        "online button busy state",
    )
    text = replace_once(
        text,
        '''    const input = document.getElementById('ipoHistoricalImportFile');
    historicalImportTicket = null;
    historicalImportCanCommit = false;
''',
        '''    const input = document.getElementById('ipoHistoricalImportFile');
    historicalImportTicket = null;
    historicalImportCanCommit = false;
    historicalImportMode = null;
''',
        "reset historical mode on open",
    )
    text = replace_once(
        text,
        '''      historicalImportTicket = payload.preview_ticket || null;
      const s = payload.summary || {};
''',
        '''      historicalImportTicket = payload.preview_ticket || null;
      historicalImportMode = 'file';
      const s = payload.summary || {};
''',
        "file preview mode",
    )

    start = text.index("  async function commitHistoricalImport()")
    end = text.index("  function renderIpoList()", start)
    new_functions = '''  async function previewHistoricalOnline() {
    if (historicalImportInFlight || refreshInFlight) return;
    const commit = document.getElementById('ipoHistoricalCommitBtn');
    historicalImportTicket = null;
    historicalImportCanCommit = false;
    historicalImportMode = null;
    if (commit) commit.disabled = true;
    setHistoricalImportBusy(true, 'online-preview');
    try {
      const response = await fetch('/api/ipo/historical-sync/preview', { method: 'POST' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.detail?.message || 'KRX 전체 과거자료 조회에 실패했습니다.');
      }
      historicalImportTicket = payload.preview_ticket || null;
      historicalImportMode = 'online';
      const s = payload.summary || {};
      historicalImportCanCommit = Boolean(
        historicalImportTicket && ((s.new || 0) + (s.updated || 0) > 0)
      );
      renderHistoricalImportPreview(payload);
    } catch (err) {
      historicalImportTicket = null;
      historicalImportCanCommit = false;
      historicalImportMode = null;
      setHistoricalPreviewMessage(err?.message || 'KRX 전체 과거자료 조회에 실패했습니다.');
    } finally {
      setHistoricalImportBusy(false);
    }
  }

  async function commitHistoricalImport() {
    if (!historicalImportTicket || !historicalImportCanCommit || historicalImportInFlight || refreshInFlight) return;
    const online = historicalImportMode === 'online';
    const confirmed = window.confirm(
      online
        ? 'KRX 전체 조회 미리보기에 표시된 공식값으로 과거 공모주의 상장시장·실제 상장일·확정 공모가·주관사를 정정/보완합니다. 반영할까요?'
        : '미리보기에서 확인된 신규 및 안전하게 보완 가능한 과거 공모주만 반영합니다. 기존 값은 덮어쓰지 않습니다. 반영할까요?'
    );
    if (!confirmed) return;

    setHistoricalImportBusy(true, 'commit');
    try {
      const endpoint = online ? '/api/ipo/historical-sync/commit' : '/api/ipo/historical-import/commit';
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preview_ticket: historicalImportTicket }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.detail?.message || '반영에 실패했습니다.');
      }

      marketIpos = Array.isArray(payload.market?.ipos) ? payload.market.ipos : marketIpos;
      historicalImportTicket = null;
      historicalImportCanCommit = false;
      historicalImportMode = null;
      ipoFilterGroup = 'PAST';
      ipoMonthExplicitlySelected = false;
      ipoHistoryInitialized = false;
      document.getElementById('ipoHistoricalImportDialog')?.close();
      renderIpoList();
    } catch (err) {
      historicalImportTicket = null;
      historicalImportCanCommit = false;
      historicalImportMode = null;
      setHistoricalPreviewMessage(
        `${err?.message || '반영에 실패했습니다.'} 다시 미리보기를 실행해 주세요.`
      );
    } finally {
      setHistoricalImportBusy(false);
    }
  }

'''
    text = text[:start] + new_functions + text[end:]
    text = replace_once(
        text,
        '''      const historicalOfficial = Boolean(ipo.sources?.official_historical_import);
''',
        '''      const historicalOfficial = Boolean(
        ipo.sources?.official_historical_import || ipo.sources?.official_historical_online
      );
''',
        "online historical presentation marker",
    )
    text = replace_once(
        text,
        '''  document.getElementById('ipoHistoricalPreviewBtn')?.addEventListener('click', previewHistoricalImport);
  document.getElementById('ipoHistoricalCommitBtn')?.addEventListener('click', commitHistoricalImport);
''',
        '''  document.getElementById('ipoHistoricalPreviewBtn')?.addEventListener('click', previewHistoricalImport);
  document.getElementById('ipoHistoricalOnlinePreviewBtn')?.addEventListener('click', previewHistoricalOnline);
  document.getElementById('ipoHistoricalCommitBtn')?.addEventListener('click', commitHistoricalImport);
''',
        "online historical event binding",
    )
    IPO_JS.write_text(text, encoding="utf-8")


def patch_existing_tests() -> None:
    text = REMINDER_TEST.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''        self.assertIn("배우자, 자녀", message)
        self.assertIn("증권사별 실제 청약 접수 마감 시간을 확인", message)
        self.assertNotIn("16:00", message)
''',
        '''        self.assertIn("배우자, 자녀", message)
        self.assertIn("공모주 청약 첫째날 — 15:00", message)
        self.assertNotIn("증권사별 실제 청약 접수 마감 시간을 확인", message)
        self.assertNotIn("16:00", message)
''',
        "existing first-day reminder expectation",
    )
    REMINDER_TEST.write_text(text, encoding="utf-8")

    text = MARKET_REFRESH_TEST.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''                self.assertIn("source_error", result["sources"][client_name.removesuffix("_client")])
                self.assertTrue(any(ipo.get("company_name") == "신규일정" for ipo in read_market_store()["ipos"]))
''',
        '''                self.assertEqual(
                    result["sources"][client_name.removesuffix("_client")],
                    "not_requested (historical_sync_only)",
                )
                getattr(client, method_name).assert_not_called()
                self.assertTrue(any(ipo.get("company_name") == "신규일정" for ipo in read_market_store()["ipos"]))
''',
        "historical secondary sources are explicit-only",
    )
    MARKET_REFRESH_TEST.write_text(text, encoding="utf-8")


def main() -> None:
    patch_store()
    patch_reminders()
    patch_orchestrator()
    patch_main()
    patch_index()
    patch_ipo_js()
    patch_existing_tests()
    print("PR82_IPO_LIVE_REFRESH_AND_HISTORICAL_SYNC_PATCHED")


if __name__ == "__main__":
    main()
