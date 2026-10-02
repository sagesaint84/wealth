from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def sub_once(path: str, pattern: str, replacement: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one regex match, found {count}")
    target.write_text(updated, encoding="utf-8")


def patch_historical_sync() -> None:
    replace_once(
        "app/services/ipo/historical_online_sync.py",
        "from app.services.ipo.krx_client import KrxClient\n",
        "from app.services.ipo.krx_client import KrxClient\n"
        "from app.services.ipo.krx_authenticated_client import (\n"
        "    AuthenticatedKrxHistoricalClient,\n"
        "    KrxAuthenticationError,\n"
        ")\n",
        "historical auth import",
    )
    replace_once(
        "app/services/ipo/historical_online_sync.py",
        "        try:\n"
        "            fetched = client.fetch_new_listings(start.isoformat(), end.isoformat())\n"
        "        except Exception as exc:\n"
        "            raise HistoricalOnlineSyncError(\n"
        "                \"KRX_HISTORY_FETCH_FAILED\",\n"
        "                f\"KRX {year}년 신규상장 자료 조회에 실패했습니다. 일부 연도만 반영하지 않습니다.\",\n"
        "            ) from exc\n",
        "        try:\n"
        "            fetched = client.fetch_new_listings(start.isoformat(), end.isoformat())\n"
        "        except KrxAuthenticationError as exc:\n"
        "            raise HistoricalOnlineSyncError(\"KRX_AUTH_FAILED\", str(exc)) from exc\n"
        "        except Exception as exc:\n"
        "            raise HistoricalOnlineSyncError(\n"
        "                \"KRX_HISTORY_FETCH_FAILED\",\n"
        "                f\"KRX {year}년 신규상장 자료 조회에 실패했습니다. 일부 연도만 반영하지 않습니다.\",\n"
        "            ) from exc\n",
        "historical auth error mapping",
    )
    replace_once(
        "app/services/ipo/historical_online_sync.py",
        "        client = krx_client or KrxClient()\n"
        "        raw_rows, by_year = _fetch_full_history(\n"
        "            client, from_year=from_year, to_year=end_year, today=current,\n"
        "        )\n",
        "        owned_client: AuthenticatedKrxHistoricalClient | None = None\n"
        "        if krx_client is None:\n"
        "            if not AuthenticatedKrxHistoricalClient.credentials_configured(username):\n"
        "                raise HistoricalOnlineSyncError(\n"
        "                    \"KRX_AUTH_REQUIRED\",\n"
        "                    \"KRX 전체 과거자료 조회에는 KRX Data Marketplace 로그인 정보가 필요합니다. \"\n"
        "                    \"OpenAPI 설정에서 KRX 아이디와 비밀번호를 저장한 뒤 다시 시도해 주세요.\",\n"
        "                )\n"
        "            owned_client = AuthenticatedKrxHistoricalClient(username=username)\n"
        "            client: KrxClient = owned_client\n"
        "        else:\n"
        "            client = krx_client\n"
        "        try:\n"
        "            raw_rows, by_year = _fetch_full_history(\n"
        "                client, from_year=from_year, to_year=end_year, today=current,\n"
        "            )\n"
        "        finally:\n"
        "            if owned_client is not None:\n"
        "                owned_client.close()\n",
        "historical user client",
    )


def three_month_window_function() -> str:
    return '''def _month_window(target_date_str: str) -> tuple[date, date]:\n    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()\n    current = target.replace(day=1)\n\n    def shift(first: date, months: int) -> date:\n        serial = first.year * 12 + (first.month - 1) + months\n        return date(serial // 12, serial % 12 + 1, 1)\n\n    start = shift(current, -1)\n    after = shift(current, 2)\n    return start, after - timedelta(days=1)\n\n\n'''


def patch_source_discovery() -> None:
    sub_once(
        "app/services/ipo/source_discovery.py",
        r"def _month_window\(target_date_str: str\) -> tuple\[date, date\]:\n.*?(?=def _date_in_window)",
        three_month_window_function(),
        "source discovery 3-month window",
    )
    replace_once(
        "app/services/ipo/source_discovery.py",
        "        from_date=(target - timedelta(days=365)).isoformat(),\n",
        "        from_date=(start - timedelta(days=90)).isoformat(),\n",
        "bounded KIND lookup",
    )
    new_func = '''def _apply_dart_schedules(\n    market: dict[str, Any],\n    *,\n    dart: DartClient,\n    target_date_str: str,\n    start: date,\n    end: date,\n) -> tuple[int, int, int]:\n    """Overlay OpenDART schedule facts for only the bounded three-month candidates."""\n    matched = 0\n    failed = 0\n    ignored = 0\n    candidates = [\n        ipo for ipo in market.get("ipos", [])\n        if isinstance(ipo, dict) and _relevant_schedule(ipo, start, end)\n    ]\n    if not candidates:\n        return 0, 0, 0\n\n    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()\n    bgn_de = (start - timedelta(days=120)).strftime("%Y%m%d")\n    end_de = target.strftime("%Y%m%d")\n\n    corp_by_name: dict[str, dict[str, Any]] = {}\n    unresolved = [ipo for ipo in candidates if not str(ipo.get("corp_code") or "").strip()]\n    if unresolved:\n        try:\n            corp_master = dart.get_corp_code_master()\n            for row in corp_master:\n                if not isinstance(row, dict):\n                    continue\n                key = normalize_company_name(str(row.get("corp_name") or ""))\n                if key and key not in corp_by_name:\n                    corp_by_name[key] = row\n        except Exception:\n            failed += 1\n\n    for ipo in candidates:\n        key = normalize_company_name(str(ipo.get("company_name") or ""))\n        master_row = corp_by_name.get(key) or {}\n        corp_code = str(ipo.get("corp_code") or master_row.get("corp_code") or "").strip()\n        if not corp_code:\n            ignored += 1\n            continue\n\n        stock_code = str(master_row.get("stock_code") or "").strip()\n        if not ipo.get("corp_code"):\n            ipo["corp_code"] = corp_code\n        if stock_code and not ipo.get("stock_code"):\n            ipo["stock_code"] = stock_code\n        ipo.setdefault("sources", {})["dart_identity"] = {\n            "source": "OpenDART corpCode.xml" if master_row else "stored corp_code",\n            "corp_code": corp_code,\n            "stock_code": stock_code or ipo.get("stock_code") or None,\n            "observed_at": datetime.now(KST).isoformat(),\n        }\n\n        try:\n            filings_resp = dart.get_filing_list(\n                corp_code=corp_code, bgn_de=bgn_de, end_de=end_de,\n                pblntf_detail_ty="C001", last_reprt_at="N", page_count=100,\n            )\n            filings = filings_resp.get("list", []) if isinstance(filings_resp, dict) else []\n            raw_structured = dart.get_equity_registration_statements(\n                corp_code=corp_code, bgn_de=bgn_de, end_de=end_de,\n            )\n            filing = select_dart_schedule_filing(filings, raw_structured)\n            if not filing:\n                ignored += 1\n                continue\n            filing = copy.deepcopy(filing)\n            filing.setdefault("corp_code", corp_code)\n            filing.setdefault("corp_name", ipo.get("company_name"))\n            if ipo.get("stock_code"):\n                filing.setdefault("stock_code", ipo.get("stock_code"))\n            item = build_dart_offering_schedule(raw_structured, filing=filing)\n            if not item or not _relevant_schedule(item, start, end):\n                ignored += 1\n                continue\n            _apply_observation(market, item, source_name="dart")\n            matched += 1\n        except Exception:\n            failed += 1\n\n    return matched, failed, ignored\n'''
    sub_once(
        "app/services/ipo/source_discovery.py",
        r"def _apply_dart_schedules\(.*?\n    return matched, failed, ignored\n",
        new_func,
        "bounded DART schedule function",
    )


def patch_refresh_adapter() -> None:
    sub_once(
        "app/services/ipo/refresh_adapter.py",
        r"def _month_window\(target_date_str: str\) -> tuple\[date, date\]:\n.*?(?=def _date_in_window)",
        three_month_window_function(),
        "adapter 3-month window",
    )
    new_interactive = '''def refresh_ipo_market(*, username: str | None = None, target_date_str: str | None = None) -> dict[str, Any]:\n    """Interactive refresh: base KIS/NAVER plus bounded 3-month source reconciliation.\n\n    Deep DART document parsing is deliberately excluded from the button path;\n    the scheduled/full refresh retains that work.\n    """\n    resolved_target = _target_date(target_date_str)\n    result = _BASE_REFRESH_MARKET(username=username, target_date_str=resolved_target)\n    supplement: dict[str, Any] = {}\n    try:\n        with _base._refresh_file_lock():\n            supplement = discover_and_merge_primary_sources(\n                username=username, target_date_str=resolved_target,\n            )\n    except _base.IpoRefreshAlreadyRunning:\n        supplement = {"statuses": {"supplemental": "busy"}}\n    targeted = {\n        "status": "not_requested (interactive_bounded_schedule_only)",\n        "reason": "deep DART document parsing is scheduled/full only",\n    }\n    output = _merge_refresh_result(result, supplement, targeted)\n    if supplement.get("window_start"):\n        output["interactive_window_start"] = supplement["window_start"]\n    if supplement.get("window_end"):\n        output["interactive_window_end"] = supplement["window_end"]\n    return output\n\n\n'''
    sub_once(
        "app/services/ipo/refresh_adapter.py",
        r"def refresh_ipo_market\(\*, username: str \| None = None, target_date_str: str \| None = None\) -> dict\[str, Any\]:\n.*?(?=def refresh_ipo_market_enriched)",
        new_interactive,
        "interactive bounded adapter",
    )


def patch_main() -> None:
    block = '''@app.get("/api/user/krx-marketplace-config")\nasync def get_user_krx_marketplace_config(request: Request) -> dict:\n    username = get_current_username(request)\n    from app.services.user_krx_credentials import krx_credential_status\n    return krx_credential_status(username)\n\n\n@app.post("/api/user/krx-marketplace-config")\nasync def save_user_krx_marketplace_config(request: Request) -> dict:\n    username = get_current_username(request)\n    payload = await request.json()\n    from app.services.user_krx_credentials import save_user_krx_credentials\n    try:\n        status = save_user_krx_credentials(username, payload)\n    except ValueError as exc:\n        raise HTTPException(status_code=400, detail=str(exc)) from exc\n    return {"message": "KRX Data Marketplace 로그인 정보가 사용자 설정에 저장되었습니다.", **status}\n\n\n@app.delete("/api/user/krx-marketplace-config")\nasync def delete_user_krx_marketplace_config(request: Request) -> dict:\n    username = get_current_username(request)\n    from app.services.user_krx_credentials import clear_user_krx_credentials\n    clear_user_krx_credentials(username)\n    return {"message": "KRX Data Marketplace 로그인 정보가 삭제되었습니다."}\n\n\n@app.post("/api/user/krx-marketplace-config/test")\nasync def test_user_krx_marketplace_config(request: Request) -> dict:\n    username = get_current_username(request)\n    from app.services.ipo.krx_authenticated_client import (\n        AuthenticatedKrxHistoricalClient, KrxAuthenticationError,\n    )\n    if not AuthenticatedKrxHistoricalClient.credentials_configured(username):\n        return {"configured": False, "valid": False, "error_code": "NOT_CONFIGURED", "message": "KRX 아이디와 비밀번호가 저장되지 않았습니다."}\n    client = AuthenticatedKrxHistoricalClient(username=username)\n    try:\n        await asyncio.to_thread(client.verify_credentials)\n        return {"configured": True, "valid": True, "message": "KRX Data Marketplace 로그인이 정상적으로 확인되었습니다."}\n    except KrxAuthenticationError as exc:\n        return {"configured": True, "valid": False, "error_code": "AUTH_ERROR", "message": str(exc)}\n    except Exception:\n        return {"configured": True, "valid": False, "error_code": "NETWORK_ERROR", "message": "KRX Data Marketplace 연결을 확인할 수 없습니다."}\n    finally:\n        client.close()\n\n\n'''
    replace_once(
        "app/main.py",
        '@app.post("/api/user/openapi-config")\n',
        block + '@app.post("/api/user/openapi-config")\n',
        "KRX user config routes",
    )


def patch_html() -> None:
    section = '''      <section id="openapiKrxSection" class="openapi-broker-section" style="margin-top:14px;">\n        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;">\n          <div><strong>🏛️ KRX Data Marketplace</strong><div class="muted" style="font-size:11px;margin-top:3px;">과거 공모주 전체 조회 전용 로그인 · 사용자별 secrets에 저장</div></div>\n          <span id="openapiKrxBadge" class="badge">미설정</span>\n        </div>\n        <div class="form-grid" style="margin-top:10px;">\n          <label>아이디 <input id="openapiKrxLoginId" type="text" autocomplete="off" placeholder="KRX 아이디" /></label>\n          <label>비밀번호 <input id="openapiKrxPassword" type="password" autocomplete="new-password" placeholder="저장된 비밀번호는 표시하지 않음" /></label>\n        </div>\n        <div id="openapiKrxMessage" class="muted" style="font-size:11px;margin-top:8px;"></div>\n        <div class="dialog-actions" style="margin-top:10px;justify-content:flex-start;">\n          <button type="button" class="button primary compact" onclick="saveKrxMarketplaceConfig()">저장</button>\n          <button type="button" class="button secondary compact" onclick="testKrxMarketplaceConfig()">연결 확인</button>\n          <button type="button" id="openapiKrxDeleteBtn" class="button secondary compact" onclick="deleteKrxMarketplaceConfig()" style="display:none;">삭제</button>\n        </div>\n      </section>\n\n'''
    target = ROOT / "app/static/index.html"
    text = target.read_text(encoding="utf-8")
    anchor = '<section id="openapiDartSection"'
    pos = text.find(anchor)
    if pos < 0:
        raise RuntimeError("KRX UI anchor not found")
    line_start = text.rfind("\n", 0, pos) + 1
    if "openapiKrxSection" in text:
        raise RuntimeError("KRX UI already applied")
    text = text[:line_start] + section + text[line_start:]
    target.write_text(text, encoding="utf-8")


def patch_js() -> None:
    target = ROOT / "app/static/wealth.js"
    text = target.read_text(encoding="utf-8")
    if "WEALTH_KRX_MARKETPLACE_CONFIG_V1" in text:
        raise RuntimeError("KRX JS already applied")
    addition = r'''\n\n// WEALTH_KRX_MARKETPLACE_CONFIG_V1\nasync function loadKrxMarketplaceConfig() {\n  const badge = document.getElementById('openapiKrxBadge');\n  const login = document.getElementById('openapiKrxLoginId');\n  const password = document.getElementById('openapiKrxPassword');\n  const del = document.getElementById('openapiKrxDeleteBtn');\n  const msg = document.getElementById('openapiKrxMessage');\n  if (!badge || !login || !password) return;\n  try {\n    const res = await fetch('/api/user/krx-marketplace-config', { cache: 'no-store' });\n    const data = await res.json();\n    if (!res.ok) throw new Error(data.detail || 'KRX 설정 조회 실패');\n    badge.textContent = data.configured ? '설정됨' : '미설정';\n    badge.classList.toggle('active', Boolean(data.configured));\n    login.value = '';\n    login.placeholder = data.login_id || 'KRX 아이디';\n    password.value = '';\n    password.placeholder = data.password_configured ? '******** (변경 시에만 입력)' : 'KRX 비밀번호';\n    if (del) del.style.display = data.configured || data.login_id_configured ? '' : 'none';\n    if (msg) msg.textContent = '자격증명은 이 사용자 전용 data/users/<username>/secrets에 저장됩니다.';\n  } catch (err) {\n    if (msg) msg.textContent = err?.message || 'KRX 설정을 불러오지 못했습니다.';\n  }\n}\n\nasync function saveKrxMarketplaceConfig() {\n  const login = document.getElementById('openapiKrxLoginId');\n  const password = document.getElementById('openapiKrxPassword');\n  const msg = document.getElementById('openapiKrxMessage');\n  const payload = {};\n  if (login?.value.trim()) payload.login_id = login.value.trim();\n  if (password?.value) payload.password = password.value;\n  if (!Object.keys(payload).length) { if (msg) msg.textContent = '변경할 아이디 또는 비밀번호를 입력해 주세요.'; return; }\n  try {\n    const res = await fetch('/api/user/krx-marketplace-config', {\n      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload),\n    });\n    const data = await res.json();\n    if (!res.ok) throw new Error(data.detail || 'KRX 설정 저장 실패');\n    if (msg) msg.textContent = data.message || '저장되었습니다.';\n    await loadKrxMarketplaceConfig();\n  } catch (err) { if (msg) msg.textContent = err?.message || 'KRX 설정 저장에 실패했습니다.'; }\n}\n\nasync function testKrxMarketplaceConfig() {\n  const msg = document.getElementById('openapiKrxMessage');\n  if (msg) msg.textContent = 'KRX 로그인 확인 중…';\n  try {\n    const res = await fetch('/api/user/krx-marketplace-config/test', { method: 'POST' });\n    const data = await res.json();\n    if (!res.ok) throw new Error(data.detail || 'KRX 연결 확인 실패');\n    if (msg) msg.textContent = data.message || (data.valid ? '연결 정상' : '연결 실패');\n  } catch (err) { if (msg) msg.textContent = err?.message || 'KRX 연결 확인에 실패했습니다.'; }\n}\n\nasync function deleteKrxMarketplaceConfig() {\n  if (!window.confirm('저장된 KRX Data Marketplace 아이디와 비밀번호를 삭제할까요?')) return;\n  const msg = document.getElementById('openapiKrxMessage');\n  try {\n    const res = await fetch('/api/user/krx-marketplace-config', { method: 'DELETE' });\n    const data = await res.json();\n    if (!res.ok) throw new Error(data.detail || 'KRX 설정 삭제 실패');\n    if (msg) msg.textContent = data.message || '삭제되었습니다.';\n    await loadKrxMarketplaceConfig();\n  } catch (err) { if (msg) msg.textContent = err?.message || 'KRX 설정 삭제에 실패했습니다.'; }\n}\n\nwindow.saveKrxMarketplaceConfig = saveKrxMarketplaceConfig;\nwindow.testKrxMarketplaceConfig = testKrxMarketplaceConfig;\nwindow.deleteKrxMarketplaceConfig = deleteKrxMarketplaceConfig;\nconst _openUserOpenApiModalBeforeKrx = window.openUserOpenApiModal;\nif (typeof _openUserOpenApiModalBeforeKrx === 'function') {\n  window.openUserOpenApiModal = async function(...args) {\n    const result = await _openUserOpenApiModalBeforeKrx(...args);\n    await loadKrxMarketplaceConfig();\n    return result;\n  };\n}\n'''
    target.write_text(text + addition.replace('\\n', '\n'), encoding="utf-8")


def patch_tests() -> None:
    test = r'''from __future__ import annotations\n\nfrom contextlib import nullcontext\nfrom datetime import date\nfrom pathlib import Path\nimport tempfile\nfrom unittest.mock import MagicMock, patch\n\nimport pytest\n\nfrom app.services.ipo import historical_online_sync, orchestrator, refresh_adapter, source_discovery\nfrom app.services.ipo.krx_authenticated_client import AuthenticatedKrxHistoricalClient\nfrom app.services.user_krx_credentials import (\n    credential_path, krx_credential_status, load_user_krx_credentials,\n    save_user_krx_credentials,\n)\n\n\nclass _FakeResponse:\n    def __init__(self, *, status_code=200, payload=None, text=''):\n        self.status_code = status_code; self._payload = payload; self.text = text\n    @property\n    def is_error(self): return self.status_code >= 400\n    @property\n    def is_redirect(self): return 300 <= self.status_code < 400\n    def json(self): return self._payload\n\n\nclass _FakeHttpxClient:\n    def __init__(self): self.calls = []; self.closed = False\n    def get(self, url, **kwargs): self.calls.append(('GET', url)); return _FakeResponse(text='ok')\n    def post(self, url, *, data=None, **kwargs):\n        self.calls.append(('POST', url))\n        if url.endswith('MDCCOMS001D1.cmd'):\n            return _FakeResponse(payload={'_error_code':'CD001'}, text='{"_error_code":"CD001"}')\n        return _FakeResponse(text='{"output":[{"ISU_SRT_CD":"250030","ISU_ABBRV":"진코스텍","LIST_DD":"2026/10/14","IPO_PRC":"13500","MKT_NM":"코스닥","LEAD_MGR":"하나증권"}]}')\n    def close(self): self.closed = True\n\n\ndef test_interactive_window_is_previous_current_next_month():\n    assert source_discovery._month_window('2026-10-02') == (date(2026, 9, 1), date(2026, 11, 30))\n    assert refresh_adapter._month_window('2026-10-02') == (date(2026, 9, 1), date(2026, 11, 30))\n\n\ndef test_interactive_refresh_runs_bounded_discovery_without_deep_dart():\n    base = {'status':'ok','sources':{},'total_ipos':1}\n    supplement = {'statuses':{'metalogos160':'sync_ok (matched=1)','dart_schedule':'sync_ok (matched=1, failed=0, ignored=0)'}, 'window_start':'2026-09-01','window_end':'2026-11-30','total_ipos':2}\n    with patch.object(refresh_adapter, '_BASE_REFRESH_MARKET', return_value=base) as base_refresh, \
         patch.object(refresh_adapter, 'discover_and_merge_primary_sources', return_value=supplement) as discover, \
         patch.object(refresh_adapter, '_targeted_dart_enrichment') as deep, \
         patch.object(refresh_adapter._base, '_refresh_file_lock', return_value=nullcontext()):\n        result = refresh_adapter.refresh_ipo_market(username='alice', target_date_str='2026-10-02')\n    base_refresh.assert_called_once_with(username='alice', target_date_str='2026-10-02')\n    discover.assert_called_once_with(username='alice', target_date_str='2026-10-02')\n    deep.assert_not_called()\n    assert result['interactive_window_start'] == '2026-09-01'\n    assert result['interactive_window_end'] == '2026-11-30'\n    assert orchestrator.refresh_ipo_market is refresh_adapter.refresh_ipo_market\n\n\ndef test_metalogos_receives_only_three_month_candidate_names():\n    market = {'ipos':[\n        {'company_name':'9월회사','subscription_start':'2026-09-10'},\n        {'company_name':'11월회사','subscription_start':'2026-11-10'},\n        {'company_name':'12월회사','subscription_start':'2026-12-01'},\n    ]}\n    kind = MagicMock(); kind.fetch_pubofr_schedule_items.return_value = []\n    npay = MagicMock(); npay.fetch_upcoming_ipos.return_value = []\n    naver = MagicMock(); naver.fetch_ipo_discovery_items.return_value = []\n    metalogos = MagicMock(); metalogos.fetch_company_items.return_value = []\n    dart = MagicMock(); dart.is_configured.return_value = False\n    with patch.object(source_discovery, 'read_market_store', return_value=market), patch.object(source_discovery, 'write_market_store'):\n        source_discovery.discover_and_merge_primary_sources(username='alice', target_date_str='2026-10-02', kind_client=kind, npay_client=npay, naver_client=naver, metalogos_client=metalogos, dart_client=dart)\n    names = metalogos.fetch_company_items.call_args.kwargs['company_names']\n    assert names == ['9월회사', '11월회사']\n\n\ndef test_dart_skips_corp_master_when_bounded_candidates_already_have_corp_code():\n    market = {'ipos':[{'company_name':'진코스텍','corp_code':'12345678','subscription_start':'2026-10-02'}]}\n    dart = MagicMock(); dart.get_filing_list.return_value = {'list':[]}; dart.get_equity_registration_statements.return_value = {}\n    source_discovery._apply_dart_schedules(market, dart=dart, target_date_str='2026-10-02', start=date(2026,9,1), end=date(2026,11,30))\n    dart.get_corp_code_master.assert_not_called()\n\n\ndef test_krx_credentials_are_user_scoped_and_masked():\n    with tempfile.TemporaryDirectory() as tmp, patch('app.services.user_krx_credentials.get_user_data_dir', return_value=Path(tmp) / 'alice'):\n        status = save_user_krx_credentials('alice', {'login_id':'mykrxid','password':'super-secret'})\n        assert status['configured'] is True\n        assert status['login_id'] == 'mykr****'\n        assert 'password' not in status\n        raw = load_user_krx_credentials('alice')\n        assert raw == {'login_id':'mykrxid','password':'super-secret'}\n        assert credential_path('alice').parent.name == 'secrets'\n\n\ndef test_online_history_without_user_credentials_fails_before_network():\n    with patch.object(AuthenticatedKrxHistoricalClient, 'credentials_configured', return_value=False):\n        with pytest.raises(historical_online_sync.HistoricalOnlineSyncError) as exc:\n            historical_online_sync.create_online_historical_preview('alice')\n    assert exc.value.code == 'KRX_AUTH_REQUIRED'\n    assert 'OpenAPI 설정' in str(exc.value)\n\n\ndef test_authenticated_krx_history_uses_user_credentials_and_reuses_session():\n    fake = _FakeHttpxClient()\n    with patch('app.services.ipo.krx_authenticated_client.load_user_krx_credentials', return_value={'login_id':'test-user','password':'test-password'}), \
         patch('app.services.ipo.krx_authenticated_client.require_external_network', return_value=None), \
         patch('app.services.ipo.krx_authenticated_client.httpx.Client', return_value=fake):\n        client = AuthenticatedKrxHistoricalClient(username='alice')\n        first = client.fetch_new_listings('2026-01-01','2026-06-30')\n        second = client.fetch_new_listings('2026-07-01','2026-10-02')\n    assert first[0]['stock_code'] == '250030'\n    assert second[0]['actual_listing_date'] == '2026-10-14'\n    assert len([u for m,u in fake.calls if m == 'POST' and u.endswith('MDCCOMS001D1.cmd')]) == 1\n    assert len([u for m,u in fake.calls if m == 'POST' and u.endswith('getJsonData.cmd')]) == 2\n\n\ndef test_krx_credentials_are_not_wired_through_env_or_compose():\n    root = Path(__file__).resolve().parents[1]\n    env = (root / '.env.example').read_text(encoding='utf-8')\n    compose = (root / 'docker-compose.ghcr.yml').read_text(encoding='utf-8')\n    assert 'KRX_ID' not in env and 'KRX_PW' not in env\n    assert 'KRX_ID' not in compose and 'KRX_PW' not in compose\n\n\ndef test_openapi_modal_contains_user_krx_settings_controls():\n    root = Path(__file__).resolve().parents[1]\n    html = (root / 'app/static/index.html').read_text(encoding='utf-8')\n    js = (root / 'app/static/wealth.js').read_text(encoding='utf-8')\n    for token in ('openapiKrxLoginId','openapiKrxPassword','openapiKrxBadge'):\n        assert token in html\n    assert '/api/user/krx-marketplace-config' in js\n    assert 'WEALTH_KRX_MARKETPLACE_CONFIG_V1' in js\n'''
    (ROOT / "tests/test_ipo_fast_refresh_and_krx_auth.py").write_text(test.replace('\\n', '\n'), encoding="utf-8")


def main() -> None:
    patch_historical_sync()
    patch_source_discovery()
    patch_refresh_adapter()
    patch_main()
    patch_html()
    patch_js()
    patch_tests()
    print("PR83_BOUNDED_REFRESH_USER_KRX_PATCHED")


if __name__ == "__main__":
    main()
