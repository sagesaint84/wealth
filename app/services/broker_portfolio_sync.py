from __future__ import annotations

from types import ModuleType


def create_broker_portfolio_sync(runtime: ModuleType) -> dict[str, object]:
    # Read app bindings at call time for existing callers and patch targets.
    _syncing_users: set[str] = set()

    def _mask_sync_error(error: Exception, client: object | None = None) -> str:
        """Return a user-facing sync error without credentials or full account numbers."""
        detail = error.detail if isinstance(error, runtime.HTTPException) else str(error)
        text = str(detail)
        if client is not None:
            for attr in ("app_key", "app_secret", "account_no"):
                value = str(getattr(client, attr, "") or "")
                if value:
                    text = text.replace(value, f"{value[:4]}****" if attr == "account_no" else "********")
        text = runtime.re.sub(r"(?<!\d)\d{8,12}(?!\d)", lambda m: f"{m.group(0)[:4]}****", text)
        return text[:300]

    def _sync_error_status(error: Exception) -> str:
        if isinstance(error, (runtime.AccountSyncPersistenceError, runtime.FinancialStorageError)):
            return "PERSISTENCE_ERROR"
        text = str(error.detail if isinstance(error, runtime.HTTPException) else error)
        if any(marker in text for marker in ("응답 형식", "올바른 JSON", "항목 형식", "연속조회")):
            return "PARSE_ERROR"
        if isinstance(error, (runtime.HTTPException, runtime.KBOpenAPIError, runtime.TossOpenAPIError, runtime.NhPlugOpenAPIError, runtime.KISOpenAPIError, runtime.KiwoomOpenAPIError)):
            return "API_ERROR"
        return "INTERNAL_ERROR"

    def _unverified_holdings_response(broker: str, records: object) -> dict:
        state = (
            records.state.value
            if isinstance(records, runtime.BrokerHoldingsResult)
            else runtime.HoldingsResultState.UNKNOWN_EMPTY.value
        )
        return {
            "broker": broker,
            "status": "SCOPE_UNVERIFIED",
            "message": "잔고 응답의 계좌·시장 범위를 확인할 수 없어 기존 보유종목을 유지했습니다.",
            "count": 0,
            "holdings_valid": False,
            "holdings_state": state,
            "cash_valid": records.cash_valid if isinstance(records, runtime.BrokerHoldingsResult) else False,
            "cash_updated": False,
            "data_preserved": True,
        }

    def _holdings_success_status(records: BrokerHoldingsResult) -> str:
        return "CONFIRMED_EMPTY" if records.state == runtime.HoldingsResultState.AUTHORITATIVE_EMPTY else "SUCCESS"

    def _mark_sync_success(data: dict, broker: str) -> None:
        data.setdefault("settings", {}).setdefault("sync_last_success", {})[broker] = runtime.datetime.now().astimezone().isoformat(timespec="seconds")

    def _save_account_sync(data: dict, username: str) -> None:
        try:
            runtime.write_portfolio(data, username=username)
        except Exception as exc:
            raise runtime.AccountSyncPersistenceError("ACCOUNT_SYNC_PERSISTENCE_FAILED") from exc

    def _load_account_sync(username: str) -> dict:
        try:
            return runtime.read_portfolio(username=username)
        except Exception as exc:
            raise runtime.AccountSyncPersistenceError("ACCOUNT_SYNC_STORAGE_INVALID") from exc

    def _resolve_kb_sync_account(data: dict):
        # 1. 고유 키(kb_primary) 또는 기존 KB 동기화 계좌 찾기
        primary_matches = [a for a in data["accounts"] if a.get("broker") == "KB증권" and a.get("account_key") == "kb_primary"]
        if len(primary_matches) > 1:
            return None, False
        existing = primary_matches[0] if primary_matches else None
        if not existing:
            source_matches = [a for a in data["accounts"] if a.get("broker") == "KB증권" and a.get("source") == "kb_api"]
            if len(source_matches) > 1:
                return None, False
            existing = source_matches[0] if source_matches else None
        if not existing:
            name_matches = [a for a in data["accounts"] if a.get("broker") == "KB증권" and ("KB" in a.get("name", "") or a.get("name") == "KB OpenAPI 동기화 계좌")]
            if len(name_matches) > 1:
                return None, False
            existing = name_matches[0] if name_matches else None

        return existing, True

    async def sync_kb_for_user(username: str, *, retry_transient: bool = False) -> dict:
        """Retry only read-only holdings fetches, opted in by account pre-sync.

    All authority checks and persistence remain outside the retry loop. The
    sync-all user lock remains held across both fetches and their short delay.
    """
        client = runtime.KBOpenAPI(username=username)
        if not client.configured:
            return {"broker": "KB증권", "status": "CONFIG_REQUIRED", "message": "KB증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True, "warnings": []}
        try:
            records, retry_info = await runtime.fetch_account_holdings(client, "KB", retry_transient=retry_transient)
        except Exception as exc:
            diagnostic = runtime.get_failure_diagnostic(exc)
            failure = runtime.HTTPException(400, diagnostic.get("failure_reason", "KB_FETCH_INTERNAL_ERROR"))
            failure.kb_sync_diagnostic = diagnostic
            raise failure from exc

        def unverified_result() -> dict:
            result = runtime._unverified_holdings_response("KB증권", records)
            if retry_info:
                result.update({**retry_info, "retry_recovered": False})
            return result

        if not isinstance(records, runtime.BrokerHoldingsResult) or not records.authoritative:
            return unverified_result()
        # Preserve scope validation before optional quote reads; revalidate the
        # latest account again inside the commit after those asynchronous reads.
        preview = runtime._load_account_sync(username)
        existing, verified = runtime._resolve_kb_sync_account(preview)
        if not verified or runtime.resolve_scopes(records.scopes, {"kb_primary": ("preview", "KB")}) is None:
            return unverified_result()
        holdings = [runtime.normalize_holding(record, existing["id"] if existing else "",
                                     "KB증권", existing["name"] if existing else "", "kb_api")
                    for record in records]
        prices, warnings = await client.refresh_prices(holdings)
        with runtime.financial_user_locks(username, 'portfolio.json'):
            data = runtime._load_account_sync(username)

            existing, verified = runtime._resolve_kb_sync_account(data)
            if not verified:
                return unverified_result()

            if existing:
                account_id = existing["id"]
                account_name = existing["name"]  # 사용자가 변경한 이름을 100% 보존!
                existing["source"] = "kb_api"
                existing["account_key"] = "kb_primary"
            else:
                # 삭제되었거나 신규일 때 자동 복구 생성
                account_id = str(runtime.uuid.uuid4())
                account_name = "KB OpenAPI 동기화 계좌"
                data["accounts"].append({
                    "id": account_id,
                    "broker": "KB증권",
                    "name": account_name,
                    "family_group": "All",
                    "source": "kb_api",
                    "account_key": "kb_primary",
                    "owner": "모두",
                })

            for holding in holdings:
                holding["account_id"] = account_id
                holding["account_name"] = account_name
            scopes = runtime.resolve_scopes(records.scopes, {"kb_primary": (account_id, account_name)})
            if scopes is None:
                return unverified_result()
            for holding in holdings:
                price = prices.get(holding["id"])
                if price:
                    holding["current_price"] = price
                    if holding["avg_price"] == 0:
                        holding["avg_price"] = price
            runtime.replace_holdings_in_scopes(data, holdings, source="kb_api", scopes=scopes)
            runtime._mark_sync_success(data, "kb")
            runtime._save_account_sync(data, username)
            status = runtime._holdings_success_status(records)
            message = "KB증권 보유종목이 0개로 확인되었습니다." if not holdings else f"KB증권 보유종목 {len(holdings)}개를 동기화했습니다."
            return {"broker": "KB증권", "status": status, "message": message, "count": len(holdings), "holdings_valid": True, "holdings_state": records.state.value, "cash_valid": False, "cash_updated": False, "data_preserved": False, "warnings": warnings[:10], **retry_info}

    async def sync_toss_for_user(username: str, *, retry_transient: bool = False) -> dict:
        client = runtime.TossOpenAPI(username=username)
        if not client.configured:
            return {"broker": "토스증권", "status": "CONFIG_REQUIRED", "message": "토스증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
        try:
            records, retry_info = await runtime.fetch_account_holdings(client, "TOSS", retry_transient=retry_transient)
            toss_accounts = client.last_accounts
        except runtime.TossOpenAPIError as exc:
            raise runtime.HTTPException(400, str(exc)) from exc
        if not isinstance(records, runtime.BrokerHoldingsResult) or not records.authoritative:
            return runtime._unverified_holdings_response("토스증권", records)
        def resolve_toss_account(data_accounts, seq, acct_no, default_name):
            seq_str = str(seq) if seq is not None else ""
            suffix = str(acct_no)[-4:] if acct_no else ""
            broker_accounts = [
                a for a in data_accounts
                if runtime.canonical_broker_account_identity(a.get("broker"))
                == runtime.canonical_broker_account_identity("토스증권")
            ]
            exact = [a for a in broker_accounts if seq_str and a.get("account_key") == seq_str]
            if len(exact) == 1:
                return exact[0], True
            if len(exact) > 1:
                return None, False
            # Toss deliberately stores only the last four digits for API-created
            # accounts.  A manually entered full number can still be reconciled
            # safely when exactly one account shares that suffix; ambiguity is
            # deliberately left unverified rather than guessing an account.
            suffix_matches = [
                a for a in broker_accounts
                if suffix and runtime.normalize_broker_account_no(a.get("account_no")).endswith(suffix)
            ]
            if len(suffix_matches) == 1:
                return suffix_matches[0], True
            if len(suffix_matches) > 1:
                return None, False
            name_matches = [
                a for a in broker_accounts
                if (suffix and suffix in a.get("name", "")) or a.get("name") == default_name
            ]
            if len(name_matches) == 1:
                return name_matches[0], True
            return None, True

        preview = runtime._load_account_sync(username)
        for account in toss_accounts:
            seq = account.get("accountSeq")
            account_no = str(account.get("accountNo", ""))
            suffix = account_no[-4:] if account_no else ""
            default_name = f"토스증권 계좌 {suffix}" if suffix else (f"토스증권 계좌 {seq}" if seq is not None else "토스증권")
            _, verified = resolve_toss_account(preview["accounts"], seq, account_no, default_name)
            if not verified:
                return runtime._unverified_holdings_response("토스증권", records)
        buying_power = {}
        cash_failures = 0
        for account in toss_accounts:
            seq = account.get("accountSeq")
            if seq is not None:
                try:
                    bp, cash_retry = await runtime.read_account_with_retry(
                        lambda: client.get_buying_power(int(seq)), "TOSS", retry_transient=retry_transient,
                    )
                    if cash_retry:
                        retry_info.update(cash_retry)
                    buying_power[str(seq)] = bp
                except runtime.TossOpenAPIError as exc:
                    diagnostic = runtime.get_failure_diagnostic(exc)
                    retry_info.update({key: diagnostic[key] for key in ("failure_reason", "retryable")
                                       if key in diagnostic})
                    if diagnostic.get("retry_attempted"):
                        retry_info.update({key: diagnostic[key] for key in
                                           ("retry_attempted", "retry_recovered", "initial_failure_reason")})
                    cash_failures += 1
        with runtime.financial_user_locks(username, 'portfolio.json'):
            data = runtime._load_account_sync(username)
            cash = data["settings"].setdefault("toss_cash", {})
            cash_balances = data["settings"].setdefault("cash_balances", {})

            toss_map = {}
            cash_successes = 0
            for account in toss_accounts:
                seq = account.get("accountSeq")
                seq_str = str(seq) if seq is not None else ""
                account_no = str(account.get("accountNo", ""))
                suffix = account_no[-4:] if account_no else ""
                account_name_default = f"토스증권 계좌 {suffix}" if suffix else (f"토스증권 계좌 {seq}" if seq is not None else "토스증권")

                existing, account_scope_verified = resolve_toss_account(data["accounts"], seq, account_no, account_name_default)
                if not account_scope_verified:
                    return runtime._unverified_holdings_response("토스증권", records)
                if existing:
                    account_id = existing["id"]
                    account_name = existing["name"]  # 사용자가 변경한 이름을 100% 보존!
                    existing["source"] = "toss_api"
                    if seq_str:
                        existing["account_key"] = seq_str
                    if suffix:
                        existing["account_no"] = suffix
                else:
                    # 삭제되었거나 신규일 때 자동 복구 생성
                    account_id = str(runtime.uuid.uuid4())
                    account_name = account_name_default
                    data["accounts"].append({
                        "id": account_id,
                        "broker": "토스증권",
                        "name": account_name,
                        "family_group": "All",
                        "source": "toss_api",
                        "account_key": seq_str,
                        "account_no": suffix,
                        "owner": "모두",
                    })

                toss_map[seq_str] = (account_id, account_name)
                if seq_str in buying_power:
                    bp = buying_power[seq_str]
                    cash[str(seq)] = bp
                    cash_balances[account_id] = bp
                    cash_successes += 1

            data["settings"]["toss_cash"] = cash
            data["settings"]["cash_balances"] = cash_balances
            holdings = []
            for record in records:
                acct_key = str(record.get("account_key", ""))
                if acct_key in toss_map:
                    account_id, account_name = toss_map[acct_key]
                else:
                    return runtime._unverified_holdings_response("토스증권", records)
                holdings.append(runtime.normalize_holding(record, account_id, "토스증권", account_name, "toss_api"))

            scopes = runtime.resolve_scopes(records.scopes, toss_map)
            if scopes is None:
                return runtime._unverified_holdings_response("토스증권", records)
            runtime.replace_holdings_in_scopes(data, holdings, source="toss_api", scopes=scopes)
            runtime._mark_sync_success(data, "toss")
            runtime._save_account_sync(data, username)
            status = "PARTIAL_SUCCESS" if cash_failures else runtime._holdings_success_status(records)
            message = "토스증권 보유종목이 0개로 확인되었습니다." if not holdings else f"토스증권 보유종목 {len(holdings)}개를 동기화했습니다."
            message += " 예수금 조회 실패 계좌의 기존 데이터는 유지했습니다." if cash_failures else " 예수금도 동기화했습니다."
            return {"broker": "토스증권", "status": status, "message": message, "count": len(holdings), "holdings_valid": True, "holdings_state": records.state.value, "cash_valid": not cash_failures, "cash_updated": bool(cash_successes), "data_preserved": bool(cash_failures), **retry_info}

    async def sync_namoo_for_user(username: str, *, retry_transient: bool = False) -> dict:
        client = runtime.NhPlugOpenAPI(username=username)
        if not client.configured:
            return {"broker": "NH투자증권(나무)", "status": "CONFIG_REQUIRED", "message": "나무증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
        try:
            records, retry_info = await runtime.fetch_account_holdings(client, "NH", retry_transient=retry_transient)
        except runtime.NhPlugOpenAPIError as exc:
            detail = str(exc)
            if isinstance(exc, runtime.NhPlugRateLimitError) or "IGW42903" in detail or "거래건수를 초과" in detail:
                detail = "나무증권 API 호출 한도를 초과했습니다(IGW42903). 잠시 후 다시 시도해 주세요. 기존 데이터는 유지했습니다."
            raise runtime.HTTPException(429 if isinstance(exc, runtime.NhPlugRateLimitError) or "IGW42903" in str(exc) else 400, detail) from exc
        if not isinstance(records, runtime.BrokerHoldingsResult) or not records.authoritative:
            return runtime._unverified_holdings_response("NH투자증권(나무)", records)
        with runtime.financial_user_locks(username, 'portfolio.json'):
            data = runtime._load_account_sync(username)
            cash_balances = data["settings"].setdefault("cash_balances", {})

            def resolve_namoo_account(data_accounts, acct_no, default_name):
                suffix = str(acct_no)[-4:] if acct_no else ""
                broker_accounts = [
                    a for a in data_accounts
                    if runtime.canonical_broker_account_identity(a.get("broker"))
                    == runtime.canonical_broker_account_identity("NH투자증권(나무)")
                ]
                exact = [a for a in broker_accounts if runtime.normalize_broker_account_no(a.get("account_no")) == runtime.normalize_broker_account_no(acct_no)]
                if len(exact) == 1:
                    return exact[0], True
                if len(exact) > 1:
                    return None, False
                suffix_matches = [a for a in broker_accounts if suffix and a.get("account_key") == suffix]
                if len(suffix_matches) == 1:
                    return suffix_matches[0], True
                if len(suffix_matches) > 1:
                    return None, False
                name_matches = [
                    a for a in broker_accounts
                    if (suffix and suffix in a.get("name", "")) or a.get("name") == default_name
                ]
                if len(name_matches) == 1:
                    return name_matches[0], True
                return None, True

            account_map = {}  # acct_no -> (account_id, account_name)
            for account in client.last_accounts:
                account_no = str(account.get("acct_no", ""))
                default_name = client._account_name(account)
                suffix = account_no[-4:] if account_no else ""
                if account_no:
                    existing, account_scope_verified = resolve_namoo_account(data["accounts"], account_no, default_name)
                    if not account_scope_verified:
                        return runtime._unverified_holdings_response("NH투자증권(나무)", records)
                    if existing:
                        account_id = existing["id"]
                        account_name = existing["name"]  # 사용자가 변경한 이름을 100% 보존!
                        existing["source"] = "nhplug_api"
                        existing["account_key"] = suffix
                        existing["account_no"] = account_no
                    else:
                        # 삭제되었거나 신규일 때 자동 복구 생성
                        account_id = str(runtime.uuid.uuid4())
                        account_name = default_name
                        data["accounts"].append({
                            "id": account_id,
                            "broker": "NH투자증권(나무)",
                            "name": account_name,
                            "family_group": "All",
                            "source": "nhplug_api",
                            "account_key": suffix,
                            "account_no": account_no,
                            "owner": "모두",
                        })
                    account_map[account_no] = (account_id, account_name)
                    if account_no in client.account_cash:
                        cash_balances[account_id] = client.account_cash[account_no]

            holdings = []
            for record in records:
                acct_key = str(record.get("account_key", ""))
                if acct_key in account_map:
                    account_id, account_name = account_map[acct_key]
                else:
                    return runtime._unverified_holdings_response("NH투자증권(나무)", records)
                holdings.append(runtime.normalize_holding(record, account_id, "NH투자증권(나무)", account_name, "nhplug_api"))

            scopes = runtime.resolve_scopes(records.scopes, account_map)
            if scopes is None:
                return runtime._unverified_holdings_response("NH투자증권(나무)", records)
            runtime.replace_holdings_in_scopes(data, holdings, source="nhplug_api", scopes=scopes)
            data["settings"]["cash_balances"] = cash_balances
            runtime._mark_sync_success(data, "nh")
            runtime._save_account_sync(data, username)
            status = runtime._holdings_success_status(records)
            message = "나무증권 보유종목이 0개로 확인되어 예수금만 동기화했습니다." if not holdings else f"나무증권 보유종목 {len(holdings)}개 및 예수금을 동기화했습니다."
            return {"broker": "NH투자증권(나무)", "status": status, "message": message, "count": len(holdings), "holdings_valid": True, "holdings_state": records.state.value, "cash_valid": True, "cash_updated": True, "data_preserved": False, **retry_info}

    async def sync_kis_for_user(username: str, *, retry_transient: bool = False) -> dict:
        client = runtime.KISOpenAPI(username=username)
        if not client.configured:
            return {"broker": "한국투자증권", "status": "CONFIG_REQUIRED", "message": "한국투자증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
        if not client._parse_account_no()[0]:
            return {"broker": "한국투자증권", "status": "CONFIG_REQUIRED", "message": "한국투자증권 계좌번호(CANO 8자리 또는 8자리-상품코드 2자리)를 확인해 주세요. 기존 데이터는 유지했습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
        try:
            records, retry_info = await runtime.fetch_account_holdings(client, "KIS", retry_transient=retry_transient)
        except runtime.KISOpenAPIError as exc:
            raise runtime.HTTPException(400, str(exc)) from exc
        if not isinstance(records, runtime.BrokerHoldingsResult) or not records.authoritative:
            return runtime._unverified_holdings_response("한국투자증권", records)
        with runtime.financial_user_locks(username, 'portfolio.json'):
            data = runtime._load_account_sync(username)
            cash_balances = data["settings"].setdefault("cash_balances", {})

            def resolve_kis_account(data_accounts, acct_no, default_name):
                suffix = str(acct_no)[-4:] if acct_no else ""
                broker_accounts = [
                    a for a in data_accounts
                    if runtime.canonical_broker_account_identity(a.get("broker"))
                    == runtime.canonical_broker_account_identity("한국투자증권")
                ]
                exact = [a for a in broker_accounts if runtime.normalize_broker_account_no(a.get("account_no")) == runtime.normalize_broker_account_no(acct_no)]
                if len(exact) == 1:
                    return exact[0], True
                if len(exact) > 1:
                    return None, False
                suffix_matches = [a for a in broker_accounts if suffix and a.get("account_key") == suffix]
                if len(suffix_matches) == 1:
                    return suffix_matches[0], True
                if len(suffix_matches) > 1:
                    return None, False
                name_matches = [
                    a for a in broker_accounts
                    if (suffix and suffix in a.get("name", "")) or a.get("name") == default_name
                ]
                if len(name_matches) == 1:
                    return name_matches[0], True
                return None, True

            account_map = {}
            for account in client.last_accounts:
                account_no = str(account.get("account_number", ""))
                default_name = account.get("account_name", f"한국투자증권 ({account_no[:4]}****)")
                suffix = account_no[-4:] if account_no else ""
                if account_no:
                    existing, account_scope_verified = resolve_kis_account(data["accounts"], account_no, default_name)
                    if not account_scope_verified:
                        return runtime._unverified_holdings_response("한국투자증권", records)
                    if existing:
                        account_id = existing["id"]
                        account_name = existing["name"]  # 사용자 지정 이름 100% 보존
                        existing["source"] = "kis_api"
                        existing["account_key"] = suffix
                        existing["account_no"] = account_no
                    else:
                        account_id = str(runtime.uuid.uuid4())
                        account_name = default_name
                        data["accounts"].append({
                            "id": account_id,
                            "broker": "한국투자증권",
                            "name": account_name,
                            "family_group": "All",
                            "source": "kis_api",
                            "account_key": suffix,
                            "account_no": account_no,
                            "owner": "모두",
                        })
                    account_map[account_no] = (account_id, account_name)
                    if account_no in client.account_cash:
                        cash_balances.setdefault(account_id, {})
                        for ccy, amt in client.account_cash[account_no].items():
                            cash_balances[account_id][ccy] = amt

            holdings = []
            for record in records:
                acct_no = str(record.get("account_number", ""))
                if acct_no in account_map:
                    account_id, account_name = account_map[acct_no]
                else:
                    return runtime._unverified_holdings_response("한국투자증권", records)
                holdings.append(runtime.normalize_holding(record, account_id, "한국투자증권", account_name, "kis_api"))

            scopes = runtime.resolve_scopes(records.scopes, account_map)
            if scopes is None:
                return runtime._unverified_holdings_response("한국투자증권", records)
            runtime.replace_holdings_in_scopes(data, holdings, source="kis_api", scopes=scopes)
            data["settings"]["cash_balances"] = cash_balances
            runtime._mark_sync_success(data, "kis")
            runtime._save_account_sync(data, username)
            status = runtime._holdings_success_status(records)
            message = "한국투자증권 보유종목이 0개로 확인되어 예수금만 동기화했습니다." if not holdings else f"한국투자증권 보유종목 {len(holdings)}개 및 예수금을 동기화했습니다."
            return {"broker": "한국투자증권", "status": status, "message": message, "count": len(holdings), "holdings_valid": True, "holdings_state": records.state.value, "cash_valid": True, "cash_updated": True, "data_preserved": False, **retry_info}

    async def sync_kiwoom_for_user(username: str, *, retry_transient: bool = False) -> dict:
        client = runtime.KiwoomOpenAPI(username=username)
        if not client.configured:
            return {"broker": "키움증권", "status": "CONFIG_REQUIRED", "message": "키움증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
        try:
            records, retry_info = await runtime.fetch_account_holdings(client, "KIWOOM", retry_transient=retry_transient)
        except runtime.KiwoomOpenAPIError as exc:
            raise runtime.HTTPException(400, str(exc)) from exc
        if not isinstance(records, runtime.BrokerHoldingsResult) or not records.authoritative:
            return runtime._unverified_holdings_response("키움증권", records)
        with runtime.financial_user_locks(username, 'portfolio.json'):
            data = runtime._load_account_sync(username)
            cash_balances = data["settings"].setdefault("cash_balances", {})

            def resolve_kiwoom_account(data_accounts, acct_no, default_name):
                suffix = str(acct_no)[-4:] if acct_no else ""
                broker_accounts = [
                    a for a in data_accounts
                    if runtime.canonical_broker_account_identity(a.get("broker"))
                    == runtime.canonical_broker_account_identity("키움증권")
                ]
                exact = [a for a in broker_accounts if runtime.normalize_broker_account_no(a.get("account_no")) == runtime.normalize_broker_account_no(acct_no)]
                if len(exact) == 1:
                    return exact[0], True
                if len(exact) > 1:
                    return None, False
                suffix_matches = [a for a in broker_accounts if suffix and a.get("account_key") == suffix]
                if len(suffix_matches) == 1:
                    return suffix_matches[0], True
                if len(suffix_matches) > 1:
                    return None, False
                name_matches = [
                    a for a in broker_accounts
                    if (suffix and suffix in a.get("name", "")) or a.get("name") == default_name
                ]
                if len(name_matches) == 1:
                    return name_matches[0], True
                return None, True

            account_map = {}
            for account in client.last_accounts:
                account_no = str(account.get("account_number", ""))
                default_name = account.get("account_name", f"키움증권 ({account_no[:4]}****)")
                suffix = account_no[-4:] if account_no else ""
                if account_no:
                    existing, account_scope_verified = resolve_kiwoom_account(data["accounts"], account_no, default_name)
                    if not account_scope_verified:
                        return runtime._unverified_holdings_response("키움증권", records)
                    if existing:
                        account_id = existing["id"]
                        account_name = existing["name"]  # 사용자 지정 이름 100% 보존
                        existing["source"] = "kiwoom_api"
                        existing["account_key"] = suffix
                        existing["account_no"] = account_no
                    else:
                        account_id = str(runtime.uuid.uuid4())
                        account_name = default_name
                        data["accounts"].append({
                            "id": account_id,
                            "broker": "키움증권",
                            "name": account_name,
                            "family_group": "All",
                            "source": "kiwoom_api",
                            "account_key": suffix,
                            "account_no": account_no,
                            "owner": "모두",
                        })
                    account_map[account_no] = (account_id, account_name)
                    if account_no in client.account_cash:
                        cash_balances.setdefault(account_id, {})
                        for ccy, amt in client.account_cash[account_no].items():
                            cash_balances[account_id][ccy] = amt

            holdings = []
            for record in records:
                acct_no = str(record.get("account_number", ""))
                if acct_no in account_map:
                    account_id, account_name = account_map[acct_no]
                else:
                    return runtime._unverified_holdings_response("키움증권", records)
                holdings.append(runtime.normalize_holding(record, account_id, "키움증권", account_name, "kiwoom_api"))

            scopes = runtime.resolve_scopes(records.scopes, account_map)
            if scopes is None:
                return runtime._unverified_holdings_response("키움증권", records)
            runtime.replace_holdings_in_scopes(data, holdings, source="kiwoom_api", scopes=scopes)
            data["settings"]["cash_balances"] = cash_balances
            runtime._mark_sync_success(data, "kiwoom")
            runtime._save_account_sync(data, username)
            status = runtime._holdings_success_status(records)
            message = "키움증권 국내 보유종목이 0개로 확인되어 KRW 예수금만 동기화했습니다." if not holdings else f"키움증권 국내 보유종목 {len(holdings)}개 및 KRW 예수금을 동기화했습니다."
            return {"broker": "키움증권", "status": status, "message": message, "count": len(holdings), "holdings_valid": True, "holdings_state": records.state.value, "cash_valid": True, "cash_updated": True, "data_preserved": False, **retry_info}

    async def sync_all_accounts_for_user(
        username: str, *, retry_kb_transient: bool = False,
        retry_account_transient: bool = False, provider_observer=None, sync_clock=None,
    ) -> dict:
        sync_clock = sync_clock or (lambda: runtime.datetime.now().astimezone())
        if runtime.is_test_mode():
            brokers = [
                {"broker": label, "status": "TEST_MODE", "count": 0,
                 "holdings_valid": False, "cash_valid": False, "data_preserved": True,
                 "message": "테스트 환경에서는 외부 동기화를 실행하지 않습니다. 기존 데이터를 유지했습니다."}
                for label in ("KB증권", "토스증권", "NH투자증권(나무)", "한국투자증권", "키움증권")
            ]
            return {
                "message": "테스트 환경에서는 계좌 동기화를 실행하지 않습니다. 기존 데이터를 유지했습니다.",
                "synced": 0,
                "errors": [],
                "brokers": brokers,
                "status": "TEST_MODE",
                "data_preserved": True,
            }
        if username in runtime._syncing_users:
            raise runtime.HTTPException(409, "이미 계좌 동기화가 진행 중입니다.")
        runtime._syncing_users.add(username)
        broker_results: list[dict] = []
        try:
            jobs = [
                ("KB증권", runtime.KBOpenAPI(username=username), "sync_kb", runtime.sync_kb_for_user),
                ("토스증권", runtime.TossOpenAPI(username=username), "sync_toss", runtime.sync_toss_for_user),
                ("NH투자증권(나무)", runtime.NhPlugOpenAPI(username=username), "sync_namoo", runtime.sync_namoo_for_user),
                ("한국투자증권", runtime.KISOpenAPI(username=username), "sync_kis", runtime.sync_kis_for_user),
                ("키움증권", runtime.KiwoomOpenAPI(username=username), "sync_kiwoom", runtime.sync_kiwoom_for_user),
            ]
            for label, client, route_name, user_fn in jobs:
                started_at = sync_clock() if provider_observer else None
                if not client.configured:
                    broker_results.append({
                        "broker": label, "status": "CONFIG_REQUIRED", "count": 0,
                        "holdings_valid": False, "cash_valid": False, "data_preserved": True,
                        "message": "OpenAPI 연결 정보가 필요합니다. 기존 데이터는 유지했습니다.",
                    })
                    if provider_observer:
                        provider_observer(broker_results[-1], started_at, sync_clock())
                    continue
                try:
                    route_attr = getattr(runtime, route_name, None)
                    if route_attr is not None and type(route_attr).__module__.startswith("unittest.mock"):
                        try:
                            broker_results.append(await route_attr(username=username))
                        except TypeError:
                            broker_results.append(await route_attr())
                    else:
                        if retry_account_transient or (label == "KB증권" and retry_kb_transient):
                            broker_results.append(await user_fn(username=username, retry_transient=True))
                        else:
                            broker_results.append(await user_fn(username=username))
                except Exception as exc:
                    diagnostic = runtime.get_failure_diagnostic(exc) or (getattr(exc, "kb_sync_diagnostic", {}) if label == "KB증권" else {})
                    status = diagnostic.get("status") or runtime._sync_error_status(exc)
                    # KB diagnostics are allowlisted categories, never raw provider bodies/credentials.
                    message = (diagnostic.get("failure_reason", "KB_SYNC_FAILED") if diagnostic or label == "KB증권"
                               else "ACCOUNT_SYNC_PERSISTENCE_FAILED" if isinstance(exc, runtime.AccountSyncPersistenceError)
                               else runtime._mask_sync_error(exc, client))
                    broker_results.append({
                        "broker": label, "status": status, "count": 0,
                        "holdings_valid": False, "cash_valid": False, "data_preserved": True,
                        "message": f"{message} 기존 데이터는 유지했습니다.",
                        **diagnostic,
                    })
                if provider_observer:
                    provider_observer(broker_results[-1], started_at, sync_clock())
        finally:
            runtime._syncing_users.discard(username)

        successful_statuses = {"SUCCESS", "CONFIRMED_EMPTY", "PARTIAL_SUCCESS"}
        succeeded = [r for r in broker_results if r["status"] in successful_statuses]
        errors = [f"{r['broker']}: {r['message']}" for r in broker_results if r["status"] not in successful_statuses | {"CONFIG_REQUIRED"}]
        lines = [f"{r['broker']} [{r['status']}] {r['message']}" for r in broker_results]
        return {"message": " / ".join(lines), "synced": len(succeeded), "errors": errors, "brokers": broker_results}

    return {
        "_syncing_users": _syncing_users,
        "_mask_sync_error": _mask_sync_error,
        "_sync_error_status": _sync_error_status,
        "_unverified_holdings_response": _unverified_holdings_response,
        "_holdings_success_status": _holdings_success_status,
        "_mark_sync_success": _mark_sync_success,
        "_save_account_sync": _save_account_sync,
        "_load_account_sync": _load_account_sync,
        "_resolve_kb_sync_account": _resolve_kb_sync_account,
        "sync_kb_for_user": sync_kb_for_user,
        "sync_toss_for_user": sync_toss_for_user,
        "sync_namoo_for_user": sync_namoo_for_user,
        "sync_kis_for_user": sync_kis_for_user,
        "sync_kiwoom_for_user": sync_kiwoom_for_user,
        "sync_all_accounts_for_user": sync_all_accounts_for_user,
    }
