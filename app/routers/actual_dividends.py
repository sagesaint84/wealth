from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse


def create_actual_dividends_router(
    *,
    get_current_username: Callable[[Request], str],
    get_dashboard: Callable[..., dict],
    get_root_dir: Callable[[], Path],
    log_exception: Callable[[str], None],
    get_actual_dividend_summary: Callable[..., dict],
    _actual_dividend_evidence: Callable[..., Awaitable[dict]],
    create_dividend_record: Callable[..., dict],
    update_dividend_record: Callable[..., dict | None],
    delete_dividend_record: Callable[..., bool],
    import_dividend_file_data: Callable[..., list[dict]],
    clear_dividend_records: Callable[..., None],
    sync_historical_fx: Callable[..., Awaitable[dict[str, float]]],
    recalculate_dividend_historical_fx: Callable[..., int],
    get_historical_fx_rate: Callable[..., float],
    now: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/actual-dividends")
    async def get_actual_dividends(request: Request, owner: str = "모두", year: str | None = None) -> dict:
        """Return actual dividend records and 12-month summary."""
        username = get_current_username(request)
        summary = get_actual_dividend_summary(owner=owner, year=year, username=username)
        from app.services.dividend_records import estimate_record_dividend
        evidence = await _actual_dividend_evidence(summary['records'], username)
        # Enrich response copies only. Never migrate or persist inferred tax values.
        summary['records'] = [{**r, 'tax_estimate': estimate_record_dividend(r, evidence.get(r.get('code')))}
            for r in summary['records']]
        return summary


    @router.post('/api/actual-dividends/estimate')
    async def preview_actual_dividend_estimate(request: Request) -> JSONResponse:
        username = get_current_username(request)
        from app.services.dividend_records import estimate_record_dividend, _record_tax_metadata
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError('invalid record')
            _record_tax_metadata(body)
            evidence = await _actual_dividend_evidence([body], username)
            result = estimate_record_dividend(body, evidence.get(body.get('code')))
        except (ValueError, TypeError):
            raise HTTPException(400, '배당 세금 입력값을 확인해 주세요.') from None
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})


    @router.post("/api/actual-dividends")
    async def add_actual_dividend(request: Request) -> dict:
        """Add a new actual dividend record."""
        username = get_current_username(request)
        body = await request.json()
        try:
            record = create_dividend_record(body, username=username)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"message": "배당금이 등록되었습니다.", "record": record}


    @router.put("/api/actual-dividends/{record_id}")
    async def edit_actual_dividend(record_id: str, request: Request) -> dict:
        """Update an existing actual dividend record."""
        username = get_current_username(request)
        body = await request.json()
        try:
            record = update_dividend_record(record_id, body, username=username)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not record:
            raise HTTPException(status_code=404, detail="배당 기록을 찾을 수 없습니다.")
        return {"message": "배당금이 수정되었습니다.", "record": record}


    @router.delete("/api/actual-dividends/{record_id}")
    async def remove_actual_dividend(record_id: str, request: Request) -> dict:
        """Delete an actual dividend record."""
        username = get_current_username(request)
        try:
            ok = delete_dividend_record(record_id, username=username)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not ok:
            raise HTTPException(status_code=404, detail="배당 기록을 찾을 수 없습니다.")
        return {"message": "배당 기록이 삭제되었습니다."}


    @router.post("/api/import-dividends")
    async def import_dividends_endpoint(request: Request, file: UploadFile = File(...)) -> dict:
        """Import actual dividend records from Excel or CSV."""
        if not file.filename:
            raise HTTPException(status_code=400, detail="업로드할 파일을 선택하세요.")
        username = get_current_username(request)
        contents = await file.read()
        full = get_dashboard(username=username)
        fx_rate = full.get("fx_rates", {}).get("USD", 1385.0)
        try:
            records = import_dividend_file_data(contents, file.filename, fx_rate=fx_rate, username=username)
            return {
                "message": f"총 {len(records)}건의 배당금 내역을 가져왔습니다.",
                "count": len(records),
                "records": records,
            }
        except Exception as e:
            log_exception("배당 파일 가져오기 실패")
            raise HTTPException(status_code=400, detail=f"배당 파일 처리 실패: {e}")


    @router.post("/api/actual-dividends/clear")
    async def clear_actual_dividends_endpoint(request: Request) -> dict:
        """Clear all actual dividend records."""
        username = get_current_username(request)
        clear_dividend_records(username=username)
        return {"message": "모든 실제 배당금 기록이 삭제되었습니다."}


    @router.post("/api/actual-dividends/recalculate-fx")
    async def recalculate_actual_dividends_fx(request: Request) -> dict:
        """Recalculate USD dividend amounts using historical exchange rates for each deposit date."""
        username = get_current_username(request)
        await sync_historical_fx()
        updated = recalculate_dividend_historical_fx(username=username)
        return {"message": f"총 {updated}건의 해외 배당금 환율이 입금일자 기준으로 재계산되었습니다.", "updated_count": updated}


    @router.get("/api/historical-fx")
    async def get_historical_fx_endpoint(date: str = "") -> dict:
        """Get historical USD/KRW exchange rate for a given date."""
        today = now().strftime("%Y-%m-%d")
        target = date.strip() or today
        rate = get_historical_fx_rate(target)
        return {"date": target, "rate": rate, "currency": "USD"}


    @router.get("/api/sample/dividends")
    async def download_sample_dividends():
        """Download sample Excel file for actual dividend tracking."""
        p = get_root_dir() / "data" / "샘플_배당.xlsx"
        if not p.exists():
            p = get_root_dir() / "샘플_배당.xlsx"
        if not p.exists():
            raise HTTPException(status_code=404, detail="샘플_배당.xlsx 파일을 찾을 수 없습니다.")
        return FileResponse(
            path=str(p),
            filename="샘플_배당.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return router
