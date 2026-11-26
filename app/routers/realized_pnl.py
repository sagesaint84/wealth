from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.services.pnl_records import PnlRecordLinkedToIpoError, PnlRecordsLinkedToIpoError


def create_realized_pnl_routers(
    *,
    get_current_username: Callable[[Request], str],
    get_dashboard: Callable[..., dict],
    get_root_dir: Callable[[], Path],
    log_exception: Callable[[str], None],
    get_pnl_summary: Callable[..., dict],
    create_pnl_record: Callable[..., dict],
    update_pnl_record: Callable[..., dict | None],
    delete_pnl_record: Callable[..., bool],
    clear_pnl_records: Callable[..., None],
    clear_pnl_records_for_broker: Callable[..., int],
    import_pnl_file_data: Callable[..., list[dict]],
    recalculate_pnl_historical_fx: Callable[..., int],
) -> tuple[APIRouter, APIRouter]:
    records = APIRouter()
    imports_and_fx = APIRouter()

    @records.get("/api/realized-pnl")
    async def get_realized_pnl(request: Request, owner: str = "모두", year: str | None = None, trade_type: str = "all") -> dict:
        """Return realized profit and loss records and summary."""
        username = get_current_username(request)
        return get_pnl_summary(owner=owner, year=year, trade_type=trade_type, username=username)


    @records.post("/api/realized-pnl")
    async def add_realized_pnl(request: Request) -> dict:
        """Add a new realized PnL record."""
        username = get_current_username(request)
        body = await request.json()
        record = create_pnl_record(body, username=username)
        return {"message": "매도 실현손익이 등록되었습니다.", "record": record}


    @records.put("/api/realized-pnl/{record_id}")
    async def edit_realized_pnl(record_id: str, request: Request) -> dict:
        """Update an existing realized PnL record."""
        username = get_current_username(request)
        body = await request.json()
        record = update_pnl_record(record_id, body, username=username)
        if not record:
            raise HTTPException(status_code=404, detail="실현손익 기록을 찾을 수 없습니다.")
        return {"message": "매도 실현손익이 수정되었습니다.", "record": record}


    @records.delete("/api/realized-pnl/{record_id}")
    async def remove_realized_pnl(record_id: str, request: Request) -> dict:
        """Delete a realized PnL record."""
        username = get_current_username(request)
        try:
            ok = delete_pnl_record(record_id, username=username)
        except PnlRecordLinkedToIpoError as exc:
            raise HTTPException(status_code=409, detail={"code": "PNL_RECORD_LINKED_TO_IPO", "message": "Unlink the IPO sale before deleting this P&L record"}) from exc
        if not ok:
            raise HTTPException(status_code=404, detail="실현손익 기록을 찾을 수 없습니다.")
        return {"message": "실현손익 기록이 삭제되었습니다."}


    @records.post("/api/realized-pnl/clear")
    async def clear_realized_pnl_endpoint(
        request: Request,
        broker: str | None = None,
    ) -> dict:
        """Clear all realized PnL records, or only one broker scope when requested."""
        username = get_current_username(request)

        broker_scope = None if broker is None else str(broker).strip()
        if broker is not None and not broker_scope:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "BROKER_SCOPE_INVALID",
                    "message": "Broker scope is required",
                },
            )

        try:
            if broker_scope is None:
                clear_pnl_records(username=username)
                return {
                    "message": "모든 매도 실현손익 기록이 삭제되었습니다."
                }

            deleted = clear_pnl_records_for_broker(
                broker_scope,
                username=username,
            )
        except PnlRecordsLinkedToIpoError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PNL_RECORDS_LINKED_TO_IPO",
                    "message": "Unlink IPO sales before clearing realized P&L",
                },
            ) from exc

        broker_label = (
            "증권사 미지정"
            if broker_scope == "__unassigned__"
            else broker_scope
        )
        return {
            "message": f"{broker_label} 실현손익 {deleted}건이 삭제되었습니다.",
            "deleted": deleted,
            "broker": broker_scope,
        }


    @imports_and_fx.post("/api/import-realized-pnl")
    async def import_realized_pnl_endpoint(request: Request, file: UploadFile = File(...)) -> dict:
        """Import realized PnL records from Excel or CSV."""
        if not file.filename:
            raise HTTPException(status_code=400, detail="업로드할 파일을 선택하세요.")
        username = get_current_username(request)
        contents = await file.read()
        full = get_dashboard(username=username)
        fx_rate = full.get("fx_rates", {}).get("USD", 1385.0)
        try:
            records = import_pnl_file_data(contents, file.filename, fx_rate=fx_rate, username=username)
            return {
                "message": f"총 {len(records)}건의 실현손익 내역을 가져왔습니다.",
                "count": len(records),
                "records": records,
            }
        except Exception as e:
            log_exception("실현손익 파일 가져오기 실패")
            raise HTTPException(status_code=400, detail=f"실현손익 파일 처리 실패: {e}")


    @imports_and_fx.post("/api/realized-pnl/recalculate-fx")
    async def recalculate_realized_pnl_fx_endpoint(request: Request) -> dict:
        """Recalculate historical FX rates and KRW amounts for all USD realized PnL records."""
        username = get_current_username(request)
        count = recalculate_pnl_historical_fx(username=username)
        return {
            "message": f"총 {count}건의 달러 실현손익 내역을 매도일자 기준 환율 및 환차손익으로 재계산했습니다.",
            "count": count,
        }


    @imports_and_fx.get("/api/sample/realized-pnl")
    async def download_sample_pnl():
        """Download sample Excel file for realized profit/loss tracking."""
        p = get_root_dir() / "data" / "샘플_매도실현손익.xlsx"
        if not p.exists():
            p = get_root_dir() / "샘플_매도실현손익.xlsx"
        if not p.exists():
            raise HTTPException(status_code=404, detail="샘플_매도실현손익.xlsx 파일을 찾을 수 없습니다.")
        return FileResponse(
            path=str(p),
            filename="샘플_매도실현손익.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return records, imports_and_fx
