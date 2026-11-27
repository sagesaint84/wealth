from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse


def create_toss_wts_feed_router(runtime: ModuleType) -> APIRouter:
    # Resolve app dependencies per request to preserve existing Python callers and patches.
    router = APIRouter()

    # Session readiness and confirmation
    @router.get("/api/toss-wts/status")
    async def toss_wts_local_status(request: Request, response: Response = None) -> dict:
        """Local-only WTS readiness state; protected by static allowed-user authorization."""
        username = runtime.get_current_username(request)
        auth_decision = runtime.check_wts_feed_static_authorization(getattr(request.state, "user_id", None))
        if not auth_decision.authorized:
            raise runtime.HTTPException(
                status_code=403,
                detail={"code": "STATIC_AUTHORIZATION_FAILED"},
                headers={"Cache-Control": "no-store"},
            )
        if response is not None:
            response.headers["Cache-Control"] = "no-store"
        return runtime.TossWtsAdapter(username=username).get_local_status()


    @router.post("/api/toss-wts/feed/confirm")
    async def toss_wts_feed_confirm(request: Request) -> JSONResponse:
        """Explicitly confirm current local WTS session generation for the allowed Wealth user."""
        username = runtime.get_current_username(request)
        try:
            decision = runtime.confirm_wts_feed_runtime_session_for_username(
                getattr(request.state, "user_id", None), username
            )
        except Exception:
            raise runtime.HTTPException(
                status_code=500,
                detail={"code": "CONFIRMATION_FAILED"},
                headers={"Cache-Control": "no-store"},
            )
        if decision.confirmed and decision.code == "CONFIRMED":
            return runtime.JSONResponse(
                status_code=200,
                content={"confirmed": True, "code": "CONFIRMED"},
                headers={"Cache-Control": "no-store"},
            )
        if decision.code == "STATIC_AUTHORIZATION_FAILED":
            raise runtime.HTTPException(
                status_code=403,
                detail={"code": "STATIC_AUTHORIZATION_FAILED"},
                headers={"Cache-Control": "no-store"},
            )
        if decision.code == "RUNTIME_MATERIAL_UNAVAILABLE":
            raise runtime.HTTPException(
                status_code=503,
                detail={"code": "RUNTIME_MATERIAL_UNAVAILABLE"},
                headers={"Cache-Control": "no-store"},
            )
        raise runtime.HTTPException(
            status_code=409,
            detail={"code": decision.code if decision.code else "CONFIRMATION_FAILED"},
            headers={"Cache-Control": "no-store"},
        )


    # Realized profit and loss
    @router.post("/api/toss-wts/realized-feed/fetch")
    async def toss_wts_realized_feed_fetch(request: Request) -> JSONResponse:
        """Fetch read-only, non-persisted realized P/L feed for the confirmed WTS session."""
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None)
        runtime_decision = runtime.check_wts_feed_runtime_confirmation_for_username(user_id, username)
        if not runtime_decision.confirmed:
            if runtime_decision.code == "STATIC_AUTHORIZATION_FAILED":
                raise runtime.HTTPException(
                    status_code=403,
                    detail={"code": "STATIC_AUTHORIZATION_FAILED"},
                    headers={"Cache-Control": "no-store"},
                )
            if runtime_decision.code == "RUNTIME_MATERIAL_UNAVAILABLE":
                raise runtime.HTTPException(
                    status_code=503,
                    detail={"code": "RUNTIME_MATERIAL_UNAVAILABLE"},
                    headers={"Cache-Control": "no-store"},
                )
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": runtime_decision.code},
                headers={"Cache-Control": "no-store"},
            )

        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Request body must be a JSON object")
        except Exception:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "Invalid JSON body"},
                headers={"Cache-Control": "no-store"},
            )

        try:
            from_date, to_date, basis = runtime.validate_realized_feed_request(
                body.get("from_date"),
                body.get("to_date"),
                body.get("profit_rate_basis"),
            )
        except ValueError as exc:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": str(exc)},
                headers={"Cache-Control": "no-store"},
            )

        try:
            adapter = runtime.TossWtsAdapter(username=username)
            raw_result = adapter.get_profit_daily(from_date=from_date, to_date=to_date, currency=basis)
            gen_id = runtime.get_current_runtime_generation_id_for_username(user_id, username)
            feed_response = runtime.build_realized_feed_response(
                from_date,
                to_date,
                basis,
                raw_result,
                user_id=str(user_id) if user_id else None,
                generation_id=gen_id,
            )
            effective_from = str(raw_result.get("effective_from_date") or raw_result.get("from") or from_date)
            effective_to = str(raw_result.get("effective_to_date") or raw_result.get("to") or to_date)
            adjusted = bool(raw_result.get("date_range_adjusted"))
            feed_response["provider_effective"] = {
                "from_date": effective_from,
                "to_date": effective_to,
            }
            feed_response["date_compatibility"] = {
                "adjusted": adjusted,
                "code": raw_result.get("compatibility_code") if adjusted else None,
            }
            return runtime.JSONResponse(
                status_code=200,
                content=feed_response,
                headers={"Cache-Control": "no-store"},
            )
        except runtime.TossWtsAdapterError as exc:
            status_code = 502 if exc.code in {"INVALID_JSON", "INVALID_SCHEMA", "UNSUPPORTED_COMMAND"} else 503
            raise runtime.HTTPException(
                status_code=status_code,
                detail={"code": exc.code},
                headers={"Cache-Control": "no-store"},
            )
        except Exception:
            raise runtime.HTTPException(
                status_code=500,
                detail={"code": "FEED_FETCH_FAILED"},
                headers={"Cache-Control": "no-store"},
            )


    @router.post("/api/toss-wts/realized-feed/import-preview")
    async def toss_wts_realized_feed_import_preview(request: Request) -> JSONResponse:
        """Preview duplicate classification for selected WTS rows without persisting."""
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None)
        auth_decision = runtime.check_wts_feed_static_authorization(user_id)
        if not auth_decision.authorized:
            raise runtime.HTTPException(
                status_code=403,
                detail={"code": "STATIC_AUTHORIZATION_FAILED"},
                headers={"Cache-Control": "no-store"},
            )
        runtime_decision = runtime.check_wts_feed_runtime_confirmation_for_username(user_id, username)
        if not runtime_decision.confirmed:
            if runtime_decision.code == "RUNTIME_MATERIAL_UNAVAILABLE":
                raise runtime.HTTPException(
                    status_code=503,
                    detail={"code": "RUNTIME_MATERIAL_UNAVAILABLE"},
                    headers={"Cache-Control": "no-store"},
                )
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": runtime_decision.code},
                headers={"Cache-Control": "no-store"},
            )

        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Request body must be a JSON object")
        except Exception:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "Invalid JSON body"},
                headers={"Cache-Control": "no-store"},
            )

        selected_items = body.get("selected_items")
        if not isinstance(selected_items, list) or len(selected_items) == 0:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "selected_items must be a non-empty list"},
                headers={"Cache-Control": "no-store"},
            )

        account_id = body.get("account_id")
        if not isinstance(account_id, str) or not account_id.strip():
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "account_id is required"},
                headers={"Cache-Control": "no-store"},
            )

        portfolio = runtime.read_portfolio(username=username)
        accounts = portfolio.get("accounts", [])
        destination_account = next((a for a in accounts if str(a.get("id")) == account_id.strip()), None)
        if not destination_account:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "INVALID_ACCOUNT", "message": "Destination account not found in user portfolio"},
                headers={"Cache-Control": "no-store"},
            )

        gen_id = runtime.get_current_runtime_generation_id_for_username(user_id, username)
        existing_records = runtime.read_pnl_records(username=username)
        profit_rate_basis = str(body.get("profit_rate_basis") or "KRW").upper()
        if profit_rate_basis not in ("KRW", "USD"):
            profit_rate_basis = "KRW"

        preview_result = runtime.preview_toss_wts_realized_selection(
            selected_items=selected_items,
            destination_account=destination_account,
            existing_records=existing_records,
            user_id=str(user_id),
            current_generation_id=gen_id,
            profit_rate_basis=profit_rate_basis,
        )
        preview_result = runtime._apply_broker_import_preferences(preview_result, selected_items)

        items_hash = runtime._broker_import_items_hash(runtime.compute_items_hash(selected_items), selected_items)
        preview_ticket = runtime.sign_import_preview_ticket(
            account_id=str(destination_account["id"]),
            items_hash=items_hash,
            user_id=str(user_id),
            generation_id=gen_id,
        )
        preview_result["preview_ticket"] = preview_ticket

        return runtime.JSONResponse(
            status_code=200,
            content=preview_result,
            headers={"Cache-Control": "no-store"},
        )


    @router.post("/api/toss-wts/realized-feed/import")
    async def toss_wts_realized_feed_import(request: Request) -> JSONResponse:
        """Commit eligible selected WTS rows into user's normal realized P/L records.

    Rechecks duplicates at commit time to prevent race conditions.
    """
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None)
        auth_decision = runtime.check_wts_feed_static_authorization(user_id)
        if not auth_decision.authorized:
            raise runtime.HTTPException(
                status_code=403,
                detail={"code": "STATIC_AUTHORIZATION_FAILED"},
                headers={"Cache-Control": "no-store"},
            )
        runtime_decision = runtime.check_wts_feed_runtime_confirmation_for_username(user_id, username)
        if not runtime_decision.confirmed:
            if runtime_decision.code == "RUNTIME_MATERIAL_UNAVAILABLE":
                raise runtime.HTTPException(
                    status_code=503,
                    detail={"code": "RUNTIME_MATERIAL_UNAVAILABLE"},
                    headers={"Cache-Control": "no-store"},
                )
            raise runtime.HTTPException(
                status_code=409,
                detail={"code": runtime_decision.code},
                headers={"Cache-Control": "no-store"},
            )

        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Request body must be a JSON object")
        except Exception:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "Invalid JSON body"},
                headers={"Cache-Control": "no-store"},
            )

        selected_items = body.get("selected_items")
        if not isinstance(selected_items, list) or len(selected_items) == 0:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "selected_items must be a non-empty list"},
                headers={"Cache-Control": "no-store"},
            )

        account_id = body.get("account_id")
        if not isinstance(account_id, str) or not account_id.strip():
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "account_id is required"},
                headers={"Cache-Control": "no-store"},
            )

        portfolio = runtime.read_portfolio(username=username)
        accounts = portfolio.get("accounts", [])
        destination_account = next((a for a in accounts if str(a.get("id")) == account_id.strip()), None)
        if not destination_account:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "INVALID_ACCOUNT", "message": "Destination account not found in user portfolio"},
                headers={"Cache-Control": "no-store"},
            )

        gen_id = runtime.get_current_runtime_generation_id_for_username(user_id, username)
        items_hash = runtime._broker_import_items_hash(runtime.compute_items_hash(selected_items), selected_items)

        preview_ticket = body.get("preview_ticket")
        if runtime.has_wealth_import_preferences(selected_items) and not preview_ticket:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "PREVIEW_TICKET_MISSING", "message": "Fresh import preview is required"},
                headers={"Cache-Control": "no-store"},
            )
        if preview_ticket:
            valid_ticket, ticket_err = runtime.verify_import_preview_ticket(
                preview_ticket,
                account_id=str(destination_account["id"]),
                items_hash=items_hash,
                user_id=str(user_id),
                current_generation_id=gen_id,
            )
            if not valid_ticket:
                raise runtime.HTTPException(
                    status_code=400,
                    detail={"code": ticket_err or "PREVIEW_TICKET_INVALID", "message": f"Preview verification failed: {ticket_err}"},
                    headers={"Cache-Control": "no-store"},
                )

        include_possible_duplicates = bool(body.get("include_possible_duplicates", False))
        profit_rate_basis = str(body.get("profit_rate_basis") or "KRW").upper()
        if profit_rate_basis not in ("KRW", "USD"):
            profit_rate_basis = "KRW"

        with runtime.financial_user_locks(username, 'realized_pnl_records.json'):
            fresh_existing = runtime.read_pnl_records(username=username)
            classification = runtime.preview_toss_wts_realized_selection(
                selected_items=selected_items,
                destination_account=destination_account,
                existing_records=fresh_existing,
                user_id=str(user_id),
                current_generation_id=gen_id,
                profit_rate_basis=profit_rate_basis,
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
                candidate_payload["source"] = "toss_wts"
                candidate_payload["source_fingerprint"] = item["fingerprint"]
                candidate_payload["source_scope_verified"] = False
                candidate_payload["imported_by_user_action"] = True
                candidate_payload["imported_at"] = now_iso

                created = runtime.create_pnl_record(candidate_payload, username=username)
                imported_ids.append(created["id"])
                imported_count += 1

            return runtime.JSONResponse(
                status_code=200,
                content={
                    "selected": len(selected_items),
                    "imported": imported_count,
                    "already_imported": already_imported_count,
                    "possible_duplicate_skipped": possible_duplicate_skipped,
                    "invalid": invalid_count,
                    "imported_ids": imported_ids,
                    "scope_kind": "unverified",
                    "scope_verified": False,
                    "destination_account": {
                        "id": destination_account.get("id"),
                        "broker": destination_account.get("broker"),
                        "account_name": destination_account.get("account_name") or destination_account.get("name"),
                        "owner": destination_account.get("owner"),
                    },
                },
                headers={"Cache-Control": "no-store"},
            )



    # Dividend and interest
    @router.post("/api/toss-wts/income-feed/fetch")
    async def toss_wts_income_feed_fetch(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None)
        runtime_decision = runtime.check_wts_feed_runtime_confirmation_for_username(user_id, username)
        if not runtime_decision.confirmed:
            status = 503 if runtime_decision.code == "RUNTIME_MATERIAL_UNAVAILABLE" else (403 if runtime_decision.code == "STATIC_AUTHORIZATION_FAILED" else 409)
            raise runtime.HTTPException(status_code=status, detail={"code": runtime_decision.code}, headers={"Cache-Control": "no-store"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("invalid body")
            from app.services.toss_wts_income_feed import validate_income_feed_request, sign_income_feed_row
            from app.services.toss_wts_income import map_toss_wts_income_rows
            from_date, to_date = validate_income_feed_request(body.get("from_date"), body.get("to_date"))
            adapter = runtime.TossWtsAdapter(username=username)
            ledger = adapter.get_income_transactions(from_date, to_date)
            mapped = map_toss_wts_income_rows(ledger["rows"])
            generation_id = runtime.get_current_runtime_generation_id_for_username(user_id, username)
            eligible_rows = []
            tokens = []
            for row in ledger["rows"]:
                from app.services.toss_wts_income import map_toss_wts_income_row
                candidate = map_toss_wts_income_row(row)
                if candidate is None:
                    continue
                projected = dict(row)
                projected["income_type"] = candidate["income_type"]
                projected["display_code"] = candidate["code"]
                projected["display_name"] = candidate["name"]
                projected["net_amount"] = candidate["amount"]
                if "gross_amount" in candidate:
                    projected["gross_amount"] = candidate["gross_amount"]
                if "tax" in candidate:
                    projected["tax"] = candidate["tax"]
                projected["source_fingerprint"] = candidate["source_fingerprint"]
                eligible_rows.append(projected)
                tokens.append(sign_income_feed_row(projected, user_id=str(user_id), generation_id=generation_id))
            content = {
                "source": "toss_wts",
                "kind": "income_feed",
                "scope_kind": "unverified",
                "scope_verified": False,
                "persisted": False,
                "requested": {"from_date": from_date, "to_date": to_date},
                "windows": ledger["windows"],
                "fetched": mapped["fetched"],
                "eligible": len(eligible_rows),
                "ignored": mapped["ignored"],
                "invalid": mapped["invalid"],
                "rows": eligible_rows,
                "selection_tokens": tokens,
            }
            return runtime.JSONResponse(content, headers={"Cache-Control": "no-store"})
        except runtime.TossWtsAdapterError as exc:
            status = 502 if exc.code in {"INVALID_JSON", "INVALID_SCHEMA", "UNSUPPORTED_COMMAND"} else 503
            raise runtime.HTTPException(status_code=status, detail={"code": exc.code}, headers={"Cache-Control": "no-store"}) from exc
        except ValueError as exc:
            raise runtime.HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)}, headers={"Cache-Control": "no-store"}) from exc
        except Exception as exc:
            runtime.logger.exception("Toss WTS income feed fetch failed")
            raise runtime.HTTPException(status_code=500, detail={"code": "INCOME_FEED_FETCH_FAILED"}, headers={"Cache-Control": "no-store"}) from exc


    @router.post("/api/toss-wts/income-feed/import-preview")
    async def toss_wts_income_feed_import_preview(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None)
        runtime_decision = runtime.check_wts_feed_runtime_confirmation_for_username(user_id, username)
        if not runtime_decision.confirmed:
            status = 503 if runtime_decision.code == "RUNTIME_MATERIAL_UNAVAILABLE" else (403 if runtime_decision.code == "STATIC_AUTHORIZATION_FAILED" else 409)
            raise runtime.HTTPException(status_code=status, detail={"code": runtime_decision.code}, headers={"Cache-Control": "no-store"})
        try:
            body = await request.json()
        except Exception as exc:
            raise runtime.HTTPException(status_code=400, detail={"code": "INVALID_REQUEST"}, headers={"Cache-Control": "no-store"}) from exc
        if not isinstance(body, dict) or not isinstance(body.get("selected_items"), list) or not body["selected_items"]:
            raise runtime.HTTPException(status_code=400, detail={"code": "INVALID_REQUEST"}, headers={"Cache-Control": "no-store"})
        account_id = body.get("account_id")
        if not isinstance(account_id, str) or not account_id.strip():
            raise runtime.HTTPException(status_code=400, detail={"code": "INVALID_REQUEST"}, headers={"Cache-Control": "no-store"})
        destination = runtime._require_realized_destination(username, "toss", account_id)
        try:
            existing = runtime.read_dividend_records_for_import(username=username)
        except runtime.DividendRecordsStorageError as exc:
            raise runtime.HTTPException(status_code=409, detail={"code": "DIVIDEND_STORAGE_UNREADABLE"}, headers={"Cache-Control": "no-store"}) from exc
        from app.services.toss_wts_income_import import preview_toss_wts_income_selection
        from app.services.toss_wts_income_feed import compute_income_items_hash, sign_income_preview_ticket
        generation_id = runtime.get_current_runtime_generation_id_for_username(user_id, username)
        result = preview_toss_wts_income_selection(
            body["selected_items"], destination, existing,
            user_id=str(user_id), current_generation_id=generation_id,
        )
        items_hash = compute_income_items_hash(body["selected_items"])
        result["preview_ticket"] = sign_income_preview_ticket(
            account_id=str(destination["id"]), items_hash=items_hash,
            user_id=str(user_id), generation_id=generation_id,
        )
        result["destination_account"] = {
            "id": destination.get("id"), "broker": destination.get("broker"),
            "account_name": destination.get("account_name") or destination.get("name"),
            "owner": destination.get("owner"),
        }
        return runtime.JSONResponse(result, headers={"Cache-Control": "no-store"})


    @router.post("/api/toss-wts/income-feed/import")
    async def toss_wts_income_feed_import(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request)
        user_id = getattr(request.state, "user_id", None)
        runtime_decision = runtime.check_wts_feed_runtime_confirmation_for_username(user_id, username)
        if not runtime_decision.confirmed:
            status = 503 if runtime_decision.code == "RUNTIME_MATERIAL_UNAVAILABLE" else (403 if runtime_decision.code == "STATIC_AUTHORIZATION_FAILED" else 409)
            raise runtime.HTTPException(status_code=status, detail={"code": runtime_decision.code}, headers={"Cache-Control": "no-store"})
        try:
            body = await request.json()
        except Exception as exc:
            raise runtime.HTTPException(status_code=400, detail={"code": "INVALID_REQUEST"}, headers={"Cache-Control": "no-store"}) from exc
        selected_items = body.get("selected_items") if isinstance(body, dict) else None
        account_id = body.get("account_id") if isinstance(body, dict) else None
        if not isinstance(selected_items, list) or not selected_items or not isinstance(account_id, str) or not account_id.strip():
            raise runtime.HTTPException(status_code=400, detail={"code": "INVALID_REQUEST"}, headers={"Cache-Control": "no-store"})
        destination = runtime._require_realized_destination(username, "toss", account_id)
        from app.services.toss_wts_income_feed import compute_income_items_hash, verify_income_preview_ticket
        from app.services.toss_wts_income_import import preview_toss_wts_income_selection
        generation_id = runtime.get_current_runtime_generation_id_for_username(user_id, username)
        items_hash = compute_income_items_hash(selected_items)
        valid, error = verify_income_preview_ticket(
            str(body.get("preview_ticket") or ""), account_id=str(destination["id"]),
            items_hash=items_hash, user_id=str(user_id), current_generation_id=generation_id,
        )
        if not valid:
            raise runtime.HTTPException(status_code=400, detail={"code": error or "PREVIEW_TICKET_INVALID"}, headers={"Cache-Control": "no-store"})
        include_possible = bool(body.get("include_possible_duplicates", False))
        with runtime._TOSS_WTS_INCOME_IMPORT_LOCK, runtime.financial_user_locks(username, 'dividend_records.json'):
            try:
                fresh_existing = runtime.read_dividend_records_for_import(username=username)
            except runtime.DividendRecordsStorageError as exc:
                raise runtime.HTTPException(status_code=409, detail={"code": "DIVIDEND_STORAGE_UNREADABLE"}, headers={"Cache-Control": "no-store"}) from exc
            classification = preview_toss_wts_income_selection(
                selected_items, destination, fresh_existing,
                user_id=str(user_id), current_generation_id=generation_id,
            )
            imported_ids: list[str] = []
            counts = {"imported": 0, "already_imported": 0, "possible_duplicate_skipped": 0, "invalid": 0}
            now_iso = runtime.datetime.now().astimezone().isoformat()
            for item in classification["items"]:
                status = item["status"]
                if status == "ALREADY_IMPORTED":
                    counts["already_imported"] += 1
                    continue
                if status == "INVALID":
                    counts["invalid"] += 1
                    continue
                if status == "POSSIBLE_DUPLICATE" and not include_possible:
                    counts["possible_duplicate_skipped"] += 1
                    continue
                candidate = item.get("candidate")
                if not isinstance(candidate, dict):
                    counts["invalid"] += 1
                    continue
                payload = dict(candidate)
                payload["source_scope_verified"] = False
                payload["imported_by_user_action"] = True
                payload["imported_at"] = now_iso
                created = runtime.create_dividend_record(payload, username=username)
                imported_ids.append(created["id"])
                counts["imported"] += 1
        return runtime.JSONResponse({
            "selected": len(selected_items), **counts, "imported_ids": imported_ids,
            "scope_kind": "unverified", "scope_verified": False,
            "destination_account": {
                "id": destination.get("id"), "broker": destination.get("broker"),
                "account_name": destination.get("account_name") or destination.get("name"),
                "owner": destination.get("owner"),
            },
        }, headers={"Cache-Control": "no-store"})

    return router
