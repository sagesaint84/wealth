from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse


def create_ipo_market_router(
    *,
    get_current_username: Callable[[Request], str],
    log_exception: Callable[[str], None],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/ipo/market")
    async def get_ipo_market(request: Request) -> dict:
        """Return canonical IPO market records and schedule."""
        username = get_current_username(request)
        from app.services.ipo.store import read_market_store_read_only
        from app.services.ipo.presentation import present_market_store
        return present_market_store(username, read_market_store_read_only())


    @router.post("/api/ipo/market/refresh")
    async def refresh_ipo_market(request: Request) -> JSONResponse:
        """Refresh shared market schedules without notification or user application effects."""
        username = get_current_username(request)
        from app.services.ipo.refresh_adapter import refresh_ipo_market as sync_ipo_market
        from app.services.ipo.store import read_market_store
        try:
            result = await asyncio.to_thread(sync_ipo_market, username=username)
        except Exception as exc:
            from app.services.ipo.orchestrator import IpoRefreshAlreadyRunning
            if isinstance(exc, IpoRefreshAlreadyRunning):
                raise HTTPException(
                    status_code=409,
                    detail={"code": "IPO_REFRESH_ALREADY_RUNNING"},
                    headers={"Cache-Control": "no-store"},
                ) from exc
            log_exception("IPO market refresh failed")
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "IPO_MARKET_REFRESH_FAILED",
                    "message": "공모주 일정 동기화에 실패했습니다. 기존 데이터를 유지합니다.",
                },
                headers={"Cache-Control": "no-store"},
            ) from exc
        if result.get("status") == "preserved":
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "IPO_MARKET_REFRESH_FAILED",
                    "message": "공모주 일정 동기화에 실패했습니다. 기존 데이터를 유지합니다.",
                },
                headers={"Cache-Control": "no-store"},
            )
        from app.services.ipo.presentation import present_market_store
        return JSONResponse({"market": present_market_store(username, read_market_store()), "refresh": result}, headers={"Cache-Control": "no-store"})


    @router.post("/api/ipo/historical-sync/preview")
    async def preview_online_historical_ipo_sync(request: Request) -> JSONResponse:
        """Legacy non-Npay online history collection is disabled; saved history remains readable."""
        username = get_current_username(request)
        del username
        return JSONResponse(
            {"detail": {
                "code": "IPO_NPAY_ONLY_HISTORICAL_SYNC_DISABLED",
                "message": "온라인 과거자료 재수집은 비활성화되었습니다. 저장된 과거자료 조회 또는 공식 파일 가져오기를 이용해 주세요.",
            }},
            status_code=410,
            headers={"Cache-Control": "no-store"},
        )


    @router.post("/api/ipo/historical-sync/commit")
    async def commit_online_historical_ipo_sync(request: Request) -> JSONResponse:
        """Reject legacy online KRX previews without changing stored market history."""
        username = get_current_username(request)
        del username
        return JSONResponse(
            {"detail": {
                "code": "IPO_NPAY_ONLY_HISTORICAL_SYNC_DISABLED",
                "message": "온라인 과거자료 재수집은 비활성화되었습니다. 기존 기록은 변경되지 않았습니다.",
            }},
            status_code=410,
            headers={"Cache-Control": "no-store"},
        )


    @router.post("/api/ipo/historical-import/preview")
    async def preview_official_historical_ipo_import(request: Request, file: UploadFile = File(...)) -> JSONResponse:
        """Preview an operator-downloaded official KRX/KIND export; never fetches web data."""
        username = get_current_username(request)
        from app.services.ipo.historical_import import (
            MAX_UPLOAD_BYTES,
            HistoricalImportError,
            create_preview,
        )
        from app.services.ipo.store import read_market_store_read_only

        # Read at most one byte past the accepted limit so a malicious/accidental
        # oversized upload is rejected without buffering the entire file in memory.
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail={"code": "FILE_TOO_LARGE", "message": "파일 크기가 16MB 제한을 초과했습니다."},
            )

        try:
            result = create_preview(
                file.filename or "",
                content,
                username,
                read_market_store_read_only(),
            )
        except HistoricalImportError as exc:
            status = 413 if exc.code == "FILE_TOO_LARGE" else 400
            raise HTTPException(
                status_code=status,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc

        return JSONResponse(result, headers={"Cache-Control": "no-store"})


    @router.post("/api/ipo/historical-import/commit")
    async def commit_official_historical_ipo_import(request: Request) -> JSONResponse:
        """Commit only the server-held, user-bound preview payload atomically."""
        username = get_current_username(request)
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "PREVIEW_TICKET_INVALID", "message": "유효한 미리보기가 필요합니다."},
            ) from exc

        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "PREVIEW_TICKET_INVALID", "message": "유효한 미리보기가 필요합니다."},
            )

        from app.services.ipo.historical_import import HistoricalImportError, commit_preview

        try:
            result = commit_preview(str(body.get("preview_ticket") or ""), username)
        except HistoricalImportError as exc:
            status = (
                409
                if exc.code in {"PREVIEW_STALE", "PREVIEW_TICKET_EXPIRED", "PREVIEW_TICKET_IN_USE"}
                else 400
            )
            raise HTTPException(
                status_code=status,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc

        from app.services.ipo.presentation import present_market_store

        result["market"] = present_market_store(username, result["market"])
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    return router
