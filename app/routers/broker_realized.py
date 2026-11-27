from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse


def create_broker_realized_routers(
    runtime: ModuleType,
) -> tuple[APIRouter, APIRouter, APIRouter, APIRouter]:
    # Bound to the app's live broker clients, locks, and persistence callbacks.
    kis_router = APIRouter()
    nh_router = APIRouter()
    kb_router = APIRouter()
    kiwoom_router = APIRouter()

    @kis_router.get("/api/kis/status")
    async def kis_status(request: Request) -> JSONResponse:
        """Read-only KIS OpenAPI readiness status and account scope."""
        username = runtime.get_current_username(request)
        client = runtime.KISOpenAPI(username=username)
        cano, prdt_cd = client._parse_account_no()
        source_account_key = client.get_source_account_key() if cano else ""
        masked_account = client.get_masked_account()

        mapped_account_id = runtime._read_kis_mapping(username).get(source_account_key) if source_account_key else None
        resolution = runtime._realized_destination_resolution(
            username, "kis", provider_account_identity=f"{cano}{prdt_cd}" if cano else None,
            mapped_destination_account_id=mapped_account_id,
        )

        return JSONResponse(
            status_code=200,
            content={
                "configured": client.configured,
                "has_account": bool(cano),
                "masked_account": masked_account,
                "source_account_key": source_account_key,
                "source_account_label": masked_account,
                "source_scope_verified": bool(cano),
                "mapped_destination_account_id": resolution.auto_selected_account_id if resolution.mapping_status == "valid" else None,
                **runtime._realized_destination_payload(resolution),
                "is_virtual": client.is_virtual,
                "broker": "한국투자증권",
            },
            headers={"Cache-Control": "no-store"},
        )

    @kis_router.post("/api/kis/realized-feed/fetch")
    async def kis_realized_feed_fetch(request: Request) -> JSONResponse:
        """Fetch read-only, non-persisted realized P/L feed from KIS OpenAPI."""
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None) or username

        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Request body must be a JSON object")
        except Exception:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "Invalid JSON body"},
                headers={"Cache-Control": "no-store"},
            )

        try:
            market, from_date, to_date = runtime.validate_kis_feed_request(
                body.get("market"),
                body.get("from_date"),
                body.get("to_date"),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": str(exc)},
                headers={"Cache-Control": "no-store"},
            )

        client = runtime.KISOpenAPI(username=username)
        if not client.configured:
            raise HTTPException(
                status_code=400,
                detail={"code": "CONFIG_REQUIRED", "message": "한국투자증권 OpenAPI AppKey/AppSecret이 설정되지 않았습니다."},
                headers={"Cache-Control": "no-store"},
            )
        source_account_key = client.get_source_account_key()
        masked_account = client.get_masked_account()
        if not source_account_key:
            raise HTTPException(
                status_code=400,
                detail={"code": "ACCOUNT_REQUIRED", "message": "한국투자증권 계좌번호가 설정되지 않았습니다."},
                headers={"Cache-Control": "no-store"},
            )

        try:
            rows, fetched_key, fetched_label = await client.fetch_realized_profit(
                market=market,
                from_date=from_date,
                to_date=to_date,
            )
            feed_response = runtime.build_kis_realized_feed_response(
                market=market,
                from_date=from_date,
                to_date=to_date,
                rows_raw=rows,
                source_account_key=source_account_key,
                source_account_label=masked_account,
                user_id=str(user_id),
            )
            return JSONResponse(
                status_code=200,
                content=feed_response,
                headers={"Cache-Control": "no-store"},
            )
        except runtime.KISOpenAPIError as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "KIS_API_ERROR", "message": str(exc)},
                headers={"Cache-Control": "no-store"},
            )
        except Exception as exc:
            runtime.logger.exception("KIS feed fetch failed: %s", exc)
            raise HTTPException(
                status_code=500,
                detail={"code": "FEED_FETCH_FAILED", "message": "KIS 실현손익 조회 중 오류가 발생했습니다."},
                headers={"Cache-Control": "no-store"},
            )

    @kis_router.post("/api/kis/realized-feed/import-preview")
    async def kis_realized_feed_import_preview(request: Request) -> JSONResponse:
        """Preview duplicate classification for selected KIS rows without persisting."""
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None) or username

        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Request body must be a JSON object")
        except Exception:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "Invalid JSON body"},
                headers={"Cache-Control": "no-store"},
            )

        selected_items = body.get("selected_items")
        if not isinstance(selected_items, list) or len(selected_items) == 0:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "selected_items must be a non-empty list"},
                headers={"Cache-Control": "no-store"},
            )

        account_id = body.get("account_id")
        if not isinstance(account_id, str) or not account_id.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "account_id is required"},
                headers={"Cache-Control": "no-store"},
            )

        client = runtime.KISOpenAPI(username=username)
        source_account_key = client.get_source_account_key()
        masked_account = client.get_masked_account()
        if not source_account_key:
            raise HTTPException(
                status_code=400,
                detail={"code": "ACCOUNT_REQUIRED", "message": "한국투자증권 계좌 설정이 필요합니다."},
                headers={"Cache-Control": "no-store"},
            )
        cano, prdt_cd = client._parse_account_no()
        destination_account = runtime._require_realized_destination(
            username, "kis", account_id,
            provider_account_identity=f"{cano}{prdt_cd}" if cano else None,
            mapped_destination_account_id=runtime._read_kis_mapping(username).get(source_account_key),
        )

        existing_records = runtime.read_pnl_records(username=username)
        market = str(body.get("market") or "kr").strip().lower()

        preview_result = runtime.preview_kis_realized_selection(
            selected_items=selected_items,
            destination_account=destination_account,
            existing_records=existing_records,
            user_id=str(user_id),
            source_account_key=source_account_key,
            source_account_label=masked_account,
            market=market,
        )
        preview_result = runtime._apply_broker_import_preferences(preview_result, selected_items)

        items_hash = runtime._broker_import_items_hash(runtime.compute_kis_items_hash(selected_items), selected_items)
        preview_ticket = runtime.sign_kis_import_preview_ticket(
            account_id=str(destination_account["id"]),
            items_hash=items_hash,
            user_id=str(user_id),
            source_account_key=source_account_key,
        )
        preview_result["preview_ticket"] = preview_ticket

        return JSONResponse(
            status_code=200,
            content=preview_result,
            headers={"Cache-Control": "no-store"},
        )

    @kis_router.post("/api/kis/realized-feed/import")
    async def kis_realized_feed_import(request: Request) -> JSONResponse:
        """Commit eligible selected KIS rows into user normal realized P/L records.

        Rechecks duplicates at commit time to prevent race conditions.
        """
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None) or username

        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Request body must be a JSON object")
        except Exception:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "Invalid JSON body"},
                headers={"Cache-Control": "no-store"},
            )

        selected_items = body.get("selected_items")
        if not isinstance(selected_items, list) or len(selected_items) == 0:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "selected_items must be a non-empty list"},
                headers={"Cache-Control": "no-store"},
            )

        account_id = body.get("account_id")
        if not isinstance(account_id, str) or not account_id.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "account_id is required"},
                headers={"Cache-Control": "no-store"},
            )

        client = runtime.KISOpenAPI(username=username)
        source_account_key = client.get_source_account_key()
        masked_account = client.get_masked_account()
        if not source_account_key:
            raise HTTPException(
                status_code=400,
                detail={"code": "ACCOUNT_REQUIRED", "message": "한국투자증권 계좌 설정이 필요합니다."},
                headers={"Cache-Control": "no-store"},
            )
        cano, prdt_cd = client._parse_account_no()
        destination_account = runtime._require_realized_destination(
            username, "kis", account_id,
            provider_account_identity=f"{cano}{prdt_cd}" if cano else None,
            mapped_destination_account_id=runtime._read_kis_mapping(username).get(source_account_key),
        )

        items_hash = runtime._broker_import_items_hash(runtime.compute_kis_items_hash(selected_items), selected_items)

        preview_ticket = body.get("preview_ticket")
        if runtime.has_wealth_import_preferences(selected_items) and not preview_ticket:
            raise HTTPException(
                status_code=400,
                detail={"code": "PREVIEW_TICKET_MISSING", "message": "Fresh import preview is required"},
                headers={"Cache-Control": "no-store"},
            )
        if preview_ticket:
            valid_ticket, ticket_err = runtime.verify_kis_import_preview_ticket(
                preview_ticket,
                account_id=str(destination_account["id"]),
                items_hash=items_hash,
                user_id=str(user_id),
                expected_account_key=source_account_key,
            )
            if not valid_ticket:
                raise HTTPException(
                    status_code=400,
                    detail={"code": ticket_err or "PREVIEW_TICKET_INVALID", "message": f"Preview verification failed: {ticket_err}"},
                    headers={"Cache-Control": "no-store"},
                )

        include_possible_duplicates = bool(body.get("include_possible_duplicates", False))
        market = str(body.get("market") or "kr").strip().lower()

        # Validate an existing binding before any financial record is created.  KIS
        # imports used to overwrite this mapping after the import completed.
        with runtime._KIS_IMPORT_LOCK:
            runtime._assert_kis_mapping_compatible(
                username,
                source_account_key,
                str(destination_account["id"]),
            )

        with runtime._KIS_IMPORT_LOCK, runtime.financial_user_locks(username, 'realized_pnl_records.json'):
            fresh_existing = runtime.read_pnl_records(username=username)
            classification = runtime.preview_kis_realized_selection(
                selected_items=selected_items,
                destination_account=destination_account,
                existing_records=fresh_existing,
                user_id=str(user_id),
                source_account_key=source_account_key,
                source_account_label=masked_account,
                market=market,
            )
            classification = runtime._apply_broker_import_preferences(classification, selected_items)

            imported_count = 0
            already_imported_count = 0
            possible_duplicate_skipped = 0
            invalid_count = 0
            imported_ids: list[str] = []
            now_iso = runtime.datetime.now().astimezone().isoformat()

            for item in classification["items"]:
                status = item["status"]
                if status == "ALREADY_IMPORTED":
                    already_imported_count += 1
                    continue
                if status == "INVALID":
                    invalid_count += 1
                    continue
                if status == "POSSIBLE_DUPLICATE":
                    if not include_possible_duplicates:
                        possible_duplicate_skipped += 1
                        continue

                candidate = item.get("candidate")
                if not candidate:
                    invalid_count += 1
                    continue

                candidate_payload = dict(candidate)
                candidate_payload["source"] = "kis"
                candidate_payload["source_fingerprint"] = item["fingerprint"]
                candidate_payload["source_account_key"] = source_account_key
                candidate_payload["source_account_label"] = masked_account
                candidate_payload["source_account_scope"] = f"kis:{source_account_key}"
                candidate_payload["source_scope_verified"] = True
                candidate_payload["account_id"] = str(destination_account["id"])
                candidate_payload["destination_account_id"] = str(destination_account["id"])
                candidate_payload["imported_by_user_action"] = True
                candidate_payload["imported_at"] = now_iso

                created = runtime.create_pnl_record(candidate_payload, username=username)
                imported_ids.append(created["id"])
                imported_count += 1

            # Do not silently remap a verified KIS source to another Wealth account.
            if source_account_key and destination_account.get("id"):
                with runtime._KIS_IMPORT_LOCK:
                    runtime._write_kis_mapping(username, source_account_key, str(destination_account["id"]))

            return JSONResponse(
                status_code=200,
                content={
                    "selected": len(selected_items),
                    "imported": imported_count,
                    "already_imported": already_imported_count,
                    "possible_duplicate_skipped": possible_duplicate_skipped,
                    "invalid": invalid_count,
                    "imported_ids": imported_ids,
                    "scope_kind": "verified",
                    "scope_verified": True,
                    "source_account_key": source_account_key,
                    "source_account_label": masked_account,
                    "destination_account": {
                        "id": destination_account.get("id"),
                        "broker": destination_account.get("broker") or "한국투자증권",
                        "account_name": destination_account.get("account_name") or destination_account.get("name"),
                        "owner": destination_account.get("owner"),
                    },
                },
                headers={"Cache-Control": "no-store"},
            )

    @nh_router.get("/api/nh/status")
    async def nh_status(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request); client = runtime.NhPlugOpenAPI(username=username)
        if not client.configured:
            return JSONResponse({"configured": False, "accounts": [], "broker": "NH투자증권"}, headers={"Cache-Control":"no-store"})
        try:
            mapping = runtime._read_nh_mapping(username)
            accounts=[]
            for account in await client._accounts():
                act_no=str(account.get("acct_no") or account.get("act_no") or "").strip()
                if not act_no: continue
                key=runtime.compute_nh_account_key(act_no)
                resolution=runtime._realized_destination_resolution(
                    username, "nh", provider_account_identity=act_no,
                    mapped_destination_account_id=mapping.get(key),
                )
                accounts.append({
                    "source_account_key":key,"source_account_label":runtime.mask_nh_account(act_no),
                    "mapped_destination_account_id":resolution.auto_selected_account_id if resolution.mapping_status == "valid" else None,
                    **runtime._realized_destination_payload(resolution),
                })
            return JSONResponse({"configured":True,"accounts":accounts,"broker":"NH투자증권"},headers={"Cache-Control":"no-store"})
        except runtime.NhPlugOpenAPIError:
            raise HTTPException(status_code=502, detail={"code":"NH_API_ERROR","message":"NH status unavailable"})

    @nh_router.post("/api/nh/realized-feed/fetch")
    async def nh_realized_feed_fetch(request: Request) -> JSONResponse:
        username=runtime.get_current_username(request); user_id=getattr(request.state,"user_id",None)
        if not user_id: raise HTTPException(status_code=401,detail={"code":"USER_ID_REQUIRED","message":"Stable user identity required"})
        body=await request.json(); market=str(body.get("market") or "").lower(); source_key=str(body.get("source_account_key") or "")
        if market not in {"kr","us"}: raise HTTPException(status_code=400,detail={"code":"INVALID_REQUEST","message":"market must be kr or us"})
        client=runtime.NhPlugOpenAPI(username=username); act_no,label=await runtime._resolve_nh_source_account(client,source_key)
        try:
            rows,fetched_key,_=await client.fetch_realized_profit(act_no=act_no,market=market,from_date=str(body.get("from_date") or ""),to_date=str(body.get("to_date") or ""))
            if fetched_key != source_key: raise HTTPException(status_code=400,detail={"code":"SCOPE_MISMATCH","message":"NH source account changed"})
            return JSONResponse(runtime.build_nh_realized_feed(rows,market=market,source_account_key=source_key,source_account_label=label,user_id=str(user_id)),headers={"Cache-Control":"no-store"})
        except runtime.NhPlugOpenAPIError:
            raise HTTPException(status_code=502,detail={"code":"NH_API_ERROR","message":"NH realized feed unavailable"})

    @nh_router.post("/api/nh/realized-feed/import-preview")
    async def nh_realized_feed_import_preview(request: Request) -> JSONResponse:
        username=runtime.get_current_username(request); user_id=getattr(request.state,"user_id",None)
        if not user_id: raise HTTPException(status_code=401,detail={"code":"USER_ID_REQUIRED","message":"Stable user identity required"})
        body=await request.json(); selected=body.get("selected_items"); market=str(body.get("market") or "").lower(); key=str(body.get("source_account_key") or "")
        if not isinstance(selected,list) or not selected or market not in {"kr","us"}: raise HTTPException(status_code=400,detail={"code":"INVALID_REQUEST","message":"Invalid NH preview request"})
        client=runtime.NhPlugOpenAPI(username=username); act_no,label=await runtime._resolve_nh_source_account(client,key)
        destination=runtime._nh_destination(username,body.get("account_id"),key,act_no)
        result=runtime.preview_nh_realized_selection(selected,destination,runtime._read_nh_pnl_records_strict(username),user_id=str(user_id),source_account_key=key,source_account_label=label,market=market)
        result=runtime._apply_broker_import_preferences(result,selected)
        result["preview_ticket"]=runtime.sign_nh_import_preview_ticket(account_id=str(destination["id"]),items_hash=runtime._broker_import_items_hash(runtime.compute_nh_items_hash(selected),selected),user_id=str(user_id),source_account_key=key,market=market)
        return JSONResponse(result,headers={"Cache-Control":"no-store"})

    @nh_router.post("/api/nh/realized-feed/import")
    async def nh_realized_feed_import(request: Request) -> JSONResponse:
        username=runtime.get_current_username(request); user_id=getattr(request.state,"user_id",None)
        if not user_id: raise HTTPException(status_code=401,detail={"code":"USER_ID_REQUIRED","message":"Stable user identity required"})
        body=await request.json(); selected=body.get("selected_items"); market=str(body.get("market") or "").lower(); key=str(body.get("source_account_key") or "")
        if not isinstance(selected,list) or not selected: raise HTTPException(status_code=400,detail={"code":"INVALID_REQUEST","message":"selected_items required"})
        client=runtime.NhPlugOpenAPI(username=username); act_no,label=await runtime._resolve_nh_source_account(client,key)
        destination=runtime._nh_destination(username,body.get("account_id"),key,act_no)
        valid,error=runtime.verify_nh_import_preview_ticket(str(body.get("preview_ticket") or ""),account_id=str(destination["id"]),items_hash=runtime._broker_import_items_hash(runtime.compute_nh_items_hash(selected),selected),user_id=str(user_id),source_account_key=key,market=market)
        if not valid: raise HTTPException(status_code=400,detail={"code":error or "PREVIEW_TICKET_INVALID","message":"NH preview verification failed"})
        with runtime._NH_IMPORT_LOCK, runtime.financial_user_locks(username, 'realized_pnl_records.json'):
            destination_id=str(destination["id"])
            mapping_exists=runtime._assert_nh_mapping_compatible(username,key,destination_id)
            current=runtime._read_nh_pnl_records_strict(username)
            runtime._assert_nh_source_records_destination(current,key,destination_id)
            result=runtime.preview_nh_realized_selection(selected,destination,current,user_id=str(user_id),source_account_key=key,source_account_label=label,market=market)
            result=runtime._apply_broker_import_preferences(result,selected)
            already_items=[item for item in result["items"] if item.get("status")=="ALREADY_IMPORTED"]
            if already_items:
                already_result={"items":already_items}
                if not runtime._nh_imported_items_match_destination(already_result,current,key,destination_id):
                    raise HTTPException(status_code=409,detail={"code":"DESTINATION_MAPPING_CONFLICT","message":"Imported NH records belong to a different destination"})
            now=runtime.datetime.now().astimezone().isoformat(); imported=0; ids=[]
            include_possible=bool(body.get("include_possible_duplicates",False))
            for item in result["items"]:
                if item["status"]!="NEW" and not (include_possible and item["status"]=="POSSIBLE_DUPLICATE"): continue
                candidate=dict(item["candidate"]); candidate.update({"source":"nh","source_fingerprint":item["fingerprint"],"source_account_key":key,"source_account_label":label,"source_account_scope":f"nh:{key}","source_scope_verified":True,"account_id":destination_id,"destination_account_id":destination_id,"imported_by_user_action":True,"imported_at":now,"source_meta":{"market":market,"country":candidate.get("country"),"classification":candidate.get("classification")}})
                created=runtime.create_pnl_record(candidate,username=username); ids.append(created["id"]); imported+=1
            repairable=(not mapping_exists and imported==0 and runtime._nh_imported_items_match_destination(result,current,key,destination_id))
            mapping_status="already_present" if mapping_exists else "not_written"
            mapping_warning=None
            mapping_repaired=False
            if imported or repairable:
                try:
                    changed=runtime._write_nh_mapping(username,key,destination_id)
                    mapping_status="repaired" if repairable and changed else "persisted" if changed else "already_present"
                    mapping_repaired=bool(repairable and changed)
                except OSError:
                    mapping_status="warning"
                    mapping_warning="MAPPING_PERSISTENCE_FAILED"
        return JSONResponse({"selected":len(selected),"imported":imported,"already_imported":result["counts"]["already_imported"],"possible_duplicate_skipped":result["counts"]["possible_duplicate"],"invalid":result["counts"]["invalid"],"imported_ids":ids,"destination_account":{"id":destination.get("id")},"mapping_status":mapping_status,"mapping_warning":mapping_warning,"mapping_repaired":mapping_repaired,"partial_success":bool(imported and mapping_warning)},headers={"Cache-Control":"no-store"})

    @kb_router.get("/api/kb/status")
    async def kb_status(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request)
        client = runtime.KBOpenAPI(username=username)
        if not client.realized_configured:
            return JSONResponse(
                {
                    "configured": False, "accounts": [], "broker": "KB증권",
                    "available_markets": ["kr"], "source_scope_verified": False,
                },
                headers={"Cache-Control": "no-store"},
            )
        source_key, label = client.get_realized_source_account_state()
        mapping = runtime._read_kb_mapping(username)
        resolution = runtime._realized_destination_resolution(
            username, "kb", mapped_destination_account_id=mapping.get(source_key),
        )
        account = {
            "source_account_key": source_key,
            "source_account_label": label,
            "mapped_destination_account_id": resolution.auto_selected_account_id if resolution.mapping_status == "valid" else None,
            **runtime._realized_destination_payload(resolution),
            "source_scope_verified": False,
        }
        return JSONResponse(
            {
                "configured": True, "accounts": [account], "broker": "KB증권",
                "available_markets": ["kr"], "source_scope_verified": False,
            },
            headers={"Cache-Control": "no-store"},
        )

    @kb_router.post("/api/kb/realized-feed/fetch")
    async def kb_realized_feed_fetch(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail={"code": "USER_ID_REQUIRED", "message": "Stable user identity required"})
        body = await request.json()
        market = str(body.get("market") or "").lower()
        if market in {"overseas", "us", "foreign"}:
            raise HTTPException(status_code=400, detail={"code": "UNSUPPORTED_MARKET", "message": "KB overseas realized P/L is not supported"})
        if market not in {"kr", "domestic"}:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": "market must be kr or domestic"})
        client = runtime.KBOpenAPI(username=username)
        if not client.realized_configured:
            raise HTTPException(status_code=400, detail={"code": "KB_NOT_READY", "message": "KB realized account configuration is incomplete"})
        try:
            rows, source_key, label = await client.fetch_domestic_realized_pnl(
                from_date=str(body.get("from_date") or ""),
                to_date=str(body.get("to_date") or ""),
                stock_code=body.get("stock_code"),
            )
            return JSONResponse(
                runtime.build_kb_realized_feed(
                    rows, market="kr", source_account_key=source_key,
                    source_account_label=label, user_id=str(user_id),
                ),
                headers={"Cache-Control": "no-store"},
            )
        except runtime.KBOpenAPIError as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "KB_API_ERROR", "message": "KB realized feed unavailable"},
            ) from exc

    @kb_router.post("/api/kb/realized-feed/import-preview")
    async def kb_realized_feed_import_preview(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail={"code": "USER_ID_REQUIRED", "message": "Stable user identity required"})
        body = await request.json()
        selected = body.get("selected_items")
        market = str(body.get("market") or "").lower()
        source_key = str(body.get("source_account_key") or "")
        if market in {"overseas", "us", "foreign"}:
            raise HTTPException(status_code=400, detail={"code": "UNSUPPORTED_MARKET", "message": "KB overseas realized P/L is not supported"})
        if not isinstance(selected, list) or not selected or market not in {"kr", "domestic"}:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": "Invalid KB preview request"})
        market = "kr"
        _, label = runtime._verify_kb_source_context(runtime.KBOpenAPI(username=username), source_key)
        destination = runtime._kb_destination(username, body.get("account_id"), source_key)
        result = runtime.preview_kb_realized_selection(
            selected, destination, runtime._read_kb_pnl_records_strict(username),
            user_id=str(user_id), source_account_key=source_key,
            source_account_label=label, market=market,
        )
        result = runtime._apply_broker_import_preferences(result, selected)
        result["preview_ticket"] = runtime.sign_kb_import_preview_ticket(
            account_id=str(destination["id"]),
            items_hash=runtime._broker_import_items_hash(runtime.compute_kb_items_hash(selected), selected),
            user_id=str(user_id), source_account_key=source_key, market=market,
        )
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    @kb_router.post("/api/kb/realized-feed/import")
    async def kb_realized_feed_import(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail={"code": "USER_ID_REQUIRED", "message": "Stable user identity required"})
        body = await request.json()
        selected = body.get("selected_items")
        market = str(body.get("market") or "").lower()
        source_key = str(body.get("source_account_key") or "")
        if market in {"overseas", "us", "foreign"}:
            raise HTTPException(status_code=400, detail={"code": "UNSUPPORTED_MARKET", "message": "KB overseas realized P/L is not supported"})
        if not isinstance(selected, list) or not selected or market not in {"kr", "domestic"}:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": "Invalid KB import request"})
        market = "kr"
        _, label = runtime._verify_kb_source_context(runtime.KBOpenAPI(username=username), source_key)
        destination = runtime._kb_destination(username, body.get("account_id"), source_key)
        valid, error = runtime.verify_kb_import_preview_ticket(
            str(body.get("preview_ticket") or ""), account_id=str(destination["id"]),
            items_hash=runtime._broker_import_items_hash(runtime.compute_kb_items_hash(selected), selected),
            user_id=str(user_id), source_account_key=source_key, market=market,
        )
        if not valid:
            raise HTTPException(
                status_code=400,
                detail={"code": error or "PREVIEW_TICKET_INVALID", "message": "KB preview verification failed"},
            )
        with runtime._KB_IMPORT_LOCK, runtime.financial_user_locks(username, 'realized_pnl_records.json'):
            destination_id = str(destination["id"])
            mapping_exists = runtime._assert_kb_mapping_compatible(username, source_key, destination_id)
            current = runtime._read_kb_pnl_records_strict(username)
            runtime._assert_kb_source_records_destination(current, source_key, destination_id)
            result = runtime.preview_kb_realized_selection(
                selected, destination, current, user_id=str(user_id),
                source_account_key=source_key, source_account_label=label, market=market,
            )
            result = runtime._apply_broker_import_preferences(result, selected)
            already_items = [item for item in result["items"] if item.get("status") == "ALREADY_IMPORTED"]
            if already_items and not runtime._kb_imported_items_match_destination(
                {"items": already_items}, current, source_key, destination_id,
            ):
                raise HTTPException(
                    status_code=409,
                    detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "Imported KB records belong to another destination"},
                )
            now = runtime.datetime.now().astimezone().isoformat()
            imported = 0
            imported_ids: list[str] = []
            include_possible = bool(body.get("include_possible_duplicates", False))
            for item in result["items"]:
                if item["status"] != "NEW" and not (include_possible and item["status"] == "POSSIBLE_DUPLICATE"):
                    continue
                candidate = dict(item["candidate"])
                source_meta = candidate.get("source_meta") if isinstance(candidate.get("source_meta"), dict) else {}
                source_meta = {
                    key: source_meta[key]
                    for key in ("api_id", "pnl_netness")
                    if key in source_meta
                }
                candidate.update({
                    "source": "kb",
                    "source_fingerprint": item["fingerprint"],
                    "source_account_key": source_key,
                    "source_account_scope": f"kb:{source_key}",
                    "source_scope_verified": False,
                    "account_id": destination_id,
                    "destination_account_id": destination_id,
                    "imported_by_user_action": True,
                    "imported_at": now,
                    "source_meta": source_meta,
                })
                created = runtime.create_pnl_record(candidate, username=username)
                imported_ids.append(created["id"])
                imported += 1
            repairable = (
                not mapping_exists
                and imported == 0
                and runtime._kb_imported_items_match_destination(result, current, source_key, destination_id)
            )
            mapping_status = "already_present" if mapping_exists else "not_written"
            mapping_warning = None
            mapping_repaired = False
            if imported or repairable:
                try:
                    changed = runtime._write_kb_mapping(username, source_key, destination_id)
                    mapping_status = "repaired" if repairable and changed else "persisted" if changed else "already_present"
                    mapping_repaired = bool(repairable and changed)
                except OSError:
                    mapping_status = "warning"
                    mapping_warning = "MAPPING_PERSISTENCE_FAILED"
        return JSONResponse(
            {
                "selected": len(selected), "imported": imported,
                "already_imported": result["counts"]["already_imported"],
                "possible_duplicate_skipped": result["counts"]["possible_duplicate"],
                "invalid": result["counts"]["invalid"], "imported_ids": imported_ids,
                "destination_account": {"id": destination.get("id")},
                "mapping_status": mapping_status, "mapping_warning": mapping_warning,
                "mapping_repaired": mapping_repaired,
                "partial_success": bool(imported and mapping_warning),
                "source_scope_verified": False,
            },
            headers={"Cache-Control": "no-store"},
        )

    @kiwoom_router.get("/api/kiwoom/status")
    async def kiwoom_status(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request)
        client = runtime.KiwoomOpenAPI(username=username)
        if not client.configured:
            return JSONResponse(
                {"configured": False, "accounts": [], "broker": "키움증권", "source_scope_verified": False},
                headers={"Cache-Control": "no-store"},
            )
        try:
            account_no, source_key, label = await client.get_realized_source_account_context()
            mapping = runtime._read_kiwoom_mapping(username)
            resolution = runtime._realized_destination_resolution(
                username, "kiwoom", provider_account_identity=account_no,
                mapped_destination_account_id=mapping.get(source_key),
            )
            account = {
                "source_account_key": source_key,
                "source_account_label": label,
                "mapped_destination_account_id": resolution.auto_selected_account_id if resolution.mapping_status == "valid" else None,
                **runtime._realized_destination_payload(resolution),
                "source_scope_verified": False,
            }
            return JSONResponse(
                {"configured": True, "accounts": [account], "broker": "키움증권", "source_scope_verified": False},
                headers={"Cache-Control": "no-store"},
            )
        except runtime.KiwoomOpenAPIError as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "KIWOOM_API_ERROR", "message": "Kiwoom status unavailable"},
            ) from exc

    @kiwoom_router.post("/api/kiwoom/realized-feed/fetch")
    async def kiwoom_realized_feed_fetch(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail={"code": "USER_ID_REQUIRED", "message": "Stable user identity required"})
        body = await request.json()
        market = str(body.get("market") or "").lower()
        if market not in {"kr", "us"}:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": "market must be kr or us"})
        try:
            rows, source_key, label = await runtime.KiwoomOpenAPI(username=username).fetch_realized_profit(
                market=market,
                from_date=str(body.get("from_date") or ""),
                to_date=str(body.get("to_date") or ""),
                stock_code=body.get("stock_code"),
            )
            return JSONResponse(
                runtime.build_kiwoom_realized_feed(
                    rows, market=market, source_account_key=source_key,
                    source_account_label=label, user_id=str(user_id),
                ),
                headers={"Cache-Control": "no-store"},
            )
        except runtime.KiwoomOpenAPIError as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "KIWOOM_API_ERROR", "message": "Kiwoom realized feed unavailable"},
            ) from exc

    @kiwoom_router.post("/api/kiwoom/realized-feed/import-preview")
    async def kiwoom_realized_feed_import_preview(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail={"code": "USER_ID_REQUIRED", "message": "Stable user identity required"})
        body = await request.json()
        selected = body.get("selected_items")
        market = str(body.get("market") or "").lower()
        source_key = str(body.get("source_account_key") or "")
        if not isinstance(selected, list) or not selected or market not in {"kr", "us"}:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": "Invalid Kiwoom preview request"})
        account_no, _, label = await runtime._verify_kiwoom_source_context(runtime.KiwoomOpenAPI(username=username), source_key)
        destination = runtime._kiwoom_destination(username, body.get("account_id"), source_key, account_no)
        result = runtime.preview_kiwoom_realized_selection(
            selected, destination, runtime._read_kiwoom_pnl_records_strict(username),
            user_id=str(user_id), source_account_key=source_key,
            source_account_label=label, market=market,
        )
        result = runtime._apply_broker_import_preferences(result, selected)
        result["preview_ticket"] = runtime.sign_kiwoom_import_preview_ticket(
            account_id=str(destination["id"]), items_hash=runtime._broker_import_items_hash(runtime.compute_kiwoom_items_hash(selected), selected),
            user_id=str(user_id), source_account_key=source_key, market=market,
        )
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    @kiwoom_router.post("/api/kiwoom/realized-feed/import")
    async def kiwoom_realized_feed_import(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail={"code": "USER_ID_REQUIRED", "message": "Stable user identity required"})
        body = await request.json()
        selected = body.get("selected_items")
        market = str(body.get("market") or "").lower()
        source_key = str(body.get("source_account_key") or "")
        if not isinstance(selected, list) or not selected or market not in {"kr", "us"}:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": "Invalid Kiwoom import request"})
        account_no, _, label = await runtime._verify_kiwoom_source_context(runtime.KiwoomOpenAPI(username=username), source_key)
        destination = runtime._kiwoom_destination(username, body.get("account_id"), source_key, account_no)
        valid, error = runtime.verify_kiwoom_import_preview_ticket(
            str(body.get("preview_ticket") or ""), account_id=str(destination["id"]),
            items_hash=runtime._broker_import_items_hash(runtime.compute_kiwoom_items_hash(selected), selected), user_id=str(user_id),
            source_account_key=source_key, market=market,
        )
        if not valid:
            raise HTTPException(
                status_code=400,
                detail={"code": error or "PREVIEW_TICKET_INVALID", "message": "Kiwoom preview verification failed"},
            )
        with runtime._KIWOOM_IMPORT_LOCK, runtime.financial_user_locks(username, 'realized_pnl_records.json'):
            destination_id = str(destination["id"])
            mapping_exists = runtime._assert_kiwoom_mapping_compatible(username, source_key, destination_id)
            current = runtime._read_kiwoom_pnl_records_strict(username)
            runtime._assert_kiwoom_source_records_destination(current, source_key, destination_id)
            result = runtime.preview_kiwoom_realized_selection(
                selected, destination, current, user_id=str(user_id),
                source_account_key=source_key, source_account_label=label, market=market,
            )
            result = runtime._apply_broker_import_preferences(result, selected)
            already_items = [item for item in result["items"] if item.get("status") == "ALREADY_IMPORTED"]
            if already_items and not runtime._kiwoom_imported_items_match_destination(
                {"items": already_items}, current, source_key, destination_id,
            ):
                raise HTTPException(
                    status_code=409,
                    detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "Imported Kiwoom records belong to another destination"},
                )
            now = runtime.datetime.now().astimezone().isoformat()
            imported = 0
            imported_ids: list[str] = []
            include_possible = bool(body.get("include_possible_duplicates", False))
            for item in result["items"]:
                if item["status"] != "NEW" and not (include_possible and item["status"] == "POSSIBLE_DUPLICATE"):
                    continue
                candidate = dict(item["candidate"])
                source_meta = candidate.get("source_meta") if isinstance(candidate.get("source_meta"), dict) else {}
                source_meta = {
                    key: source_meta[key]
                    for key in ("api_id", "buy_amount_semantics", "sell_amount_semantics", "currency_basis")
                    if key in source_meta
                }
                candidate.update({
                    "source": "kiwoom",
                    "source_fingerprint": item["fingerprint"],
                    "source_account_key": source_key,
                    "source_account_label": label,
                    "source_account_scope": f"kiwoom:{source_key}",
                    "source_scope_verified": False,
                    "account_id": destination_id,
                    "destination_account_id": destination_id,
                    "imported_by_user_action": True,
                    "imported_at": now,
                    "source_meta": source_meta,
                })
                created = runtime.create_pnl_record(candidate, username=username)
                imported_ids.append(created["id"])
                imported += 1
            repairable = (
                not mapping_exists
                and imported == 0
                and runtime._kiwoom_imported_items_match_destination(result, current, source_key, destination_id)
            )
            mapping_status = "already_present" if mapping_exists else "not_written"
            mapping_warning = None
            mapping_repaired = False
            if imported or repairable:
                try:
                    changed = runtime._write_kiwoom_mapping(username, source_key, destination_id)
                    mapping_status = "repaired" if repairable and changed else "persisted" if changed else "already_present"
                    mapping_repaired = bool(repairable and changed)
                except OSError:
                    mapping_status = "warning"
                    mapping_warning = "MAPPING_PERSISTENCE_FAILED"
        return JSONResponse(
            {
                "selected": len(selected), "imported": imported,
                "already_imported": result["counts"]["already_imported"],
                "possible_duplicate_skipped": result["counts"]["possible_duplicate"],
                "invalid": result["counts"]["invalid"], "imported_ids": imported_ids,
                "destination_account": {"id": destination.get("id")},
                "mapping_status": mapping_status, "mapping_warning": mapping_warning,
                "mapping_repaired": mapping_repaired,
                "partial_success": bool(imported and mapping_warning),
                "source_scope_verified": False,
            },
            headers={"Cache-Control": "no-store"},
        )

    return kis_router, nh_router, kb_router, kiwoom_router
