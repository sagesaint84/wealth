from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.services.ledger import (
    BalanceConflictError,
    LegacyBalanceDeltaError,
    get_ledger_summary,
    add_transaction,
    update_transaction,
    delete_transaction,
    add_recurring,
    edit_recurring,
    delete_recurring,
    process_recurring_deductions,
    get_cards,
    create_card,
    update_card,
    delete_card,
    settle_card_payment,
    import_ledger_from_file_bytes,
)


def create_ledger_router(
    *,
    get_current_username: Callable[[Request], str],
    get_root_dir: Callable[[], Path],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/ledger")
    async def get_ledger(
        request: Request,
        year: int | None = None,
        month: int | None = None,
        owner: str = "모두",
    ) -> dict:
        """Get ledger summary, category analytics, trend, cards, and transactions for the specified month/owner."""
        username = get_current_username(request)
        try:
            return get_ledger_summary(username=username, year=year, month=month, owner=owner)
        except BalanceConflictError as exc:
            raise HTTPException(409, str(exc)) from exc


    @router.get("/api/ledger/preferences")
    async def ledger_preferences(request: Request) -> dict:
        from app.services.transaction_preferences import get_transaction_defaults
        return {"transaction_defaults": get_transaction_defaults(get_current_username(request))}


    @router.put("/api/ledger/preferences/transaction-defaults")
    async def ledger_transaction_defaults(request: Request) -> dict:
        from app.services.transaction_preferences import set_transaction_defaults
        body = await request.json()
        try:
            defaults = set_transaction_defaults(body.get("owner", "모두"), body.get("defaults", {}),
                                                username=get_current_username(request))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"transaction_defaults": defaults}


    @router.get("/api/import-destination-defaults")
    async def import_destination_defaults(request: Request) -> dict:
        from app.services.transaction_preferences import get_import_defaults
        return {"defaults": get_import_defaults(get_current_username(request))}


    @router.put("/api/import-destination-defaults")
    async def update_import_destination_default(request: Request) -> dict:
        from app.services.transaction_preferences import set_import_default
        body = await request.json()
        try:
            defaults = set_import_default(body.get("workflow"), body.get("account_id", ""),
                                          body.get("owner", "모두"), username=get_current_username(request))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"defaults": defaults}


    @router.post("/api/ledger/transactions")
    async def create_ledger_transaction(request: Request) -> dict:
        """Create a new income/expense/transfer transaction."""
        username = get_current_username(request)
        payload = await request.json()
        if not payload.get("amount"):
            raise HTTPException(400, "금액을 입력해 주세요.")
        try:
            tx = add_transaction(payload, username=username)
        except BalanceConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"message": "내역이 등록되었습니다.", "transaction": tx}


    @router.put("/api/ledger/transactions/{tx_id}")
    async def edit_ledger_transaction(tx_id: str, request: Request) -> dict:
        """Update an existing transaction."""
        username = get_current_username(request)
        payload = await request.json()
        try:
            tx = update_transaction(tx_id, payload, username=username)
        except (LegacyBalanceDeltaError, BalanceConflictError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not tx:
            raise HTTPException(404, "수정할 내역을 찾을 수 없습니다.")
        return {"message": "내역이 수정되었습니다.", "transaction": tx}


    @router.delete("/api/ledger/transactions/{tx_id}")
    async def remove_ledger_transaction(tx_id: str, request: Request) -> dict:
        """Delete a transaction."""
        username = get_current_username(request)
        try:
            success = delete_transaction(tx_id, username=username)
        except (LegacyBalanceDeltaError, BalanceConflictError) as exc:
            raise HTTPException(409, str(exc)) from exc
        if not success:
            raise HTTPException(404, "삭제할 내역을 찾을 수 없습니다.")
        return {"message": "내역이 삭제되었습니다."}


    @router.post("/api/ledger/recurring")
    async def create_recurring(request: Request) -> dict:
        """Add a recurring monthly expense/income."""
        username = get_current_username(request)
        payload = await request.json()
        if not payload.get("name") or not payload.get("amount"):
            raise HTTPException(400, "고정지출 이름과 금액을 입력해 주세요.")
        try:
            rec = add_recurring(payload, username=username)
        except BalanceConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"message": "고정지출이 등록되었습니다.", "recurring": rec}


    @router.delete("/api/ledger/recurring/{rec_id}")
    async def remove_recurring(rec_id: str, request: Request) -> dict:
        """Delete a recurring entry."""
        username = get_current_username(request)
        success = delete_recurring(rec_id, username=username)
        if not success:
            raise HTTPException(404, "삭제할 고정지출 항목을 찾을 수 없습니다.")
        return {"message": "고정지출 항목이 삭제되었습니다."}


    @router.put("/api/ledger/recurring/{rec_id}")
    async def update_recurring_entry(rec_id: str, request: Request) -> dict:
        """Update a recurring entry."""
        username = get_current_username(request)
        payload = await request.json()
        try:
            rec = edit_recurring(rec_id, payload, username=username)
        except BalanceConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not rec:
            raise HTTPException(404, "수정할 고정지출 항목을 찾을 수 없습니다.")
        return {"message": "고정지출 항목이 수정되었습니다.", "recurring": rec}


    @router.post("/api/ledger/recurring/process")
    async def trigger_recurring_deductions(request: Request) -> dict:
        """Trigger processing of recurring bank deductions for current month."""
        username = get_current_username(request)
        try:
            processed = process_recurring_deductions(username=username)
        except BalanceConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        count = len(processed)
        msg = f"당월 자동이체 고정지출 {count}건이 통장에서 정상 출금 처리되었습니다." if count > 0 else "당월 추가로 출금 처리할 자동이체 항목이 없습니다."
        return {"message": msg, "count": count, "processed": processed}


    # ---------------------------------------------------------------------------
    # Credit / Debit Card Routes
    # ---------------------------------------------------------------------------

    @router.get("/api/ledger/cards")
    async def get_ledger_cards(request: Request, owner: str = "모두") -> list[dict]:
        """Get all cards with unpaid bill amount."""
        username = get_current_username(request)
        return get_cards(username=username, owner=owner)


    @router.post("/api/ledger/cards")
    async def add_ledger_card(request: Request) -> dict:
        """Register a new credit or debit card."""
        username = get_current_username(request)
        payload = await request.json()
        if not payload.get("card_name"):
            raise HTTPException(400, "카드명을 입력해 주세요.")
        card = create_card(payload, username=username)
        return {"message": "신용카드가 등록되었습니다.", "card": card}


    @router.put("/api/ledger/cards/{card_id}")
    async def edit_ledger_card(card_id: str, request: Request) -> dict:
        """Update card details."""
        username = get_current_username(request)
        payload = await request.json()
        card = update_card(card_id, payload, username=username)
        if not card:
            raise HTTPException(404, "수정할 카드를 찾을 수 없습니다.")
        return {"message": "카드 정보가 수정되었습니다.", "card": card}


    @router.delete("/api/ledger/cards/{card_id}")
    async def remove_ledger_card(card_id: str, request: Request) -> dict:
        """Delete a card."""
        username = get_current_username(request)
        ok = delete_card(card_id, username=username)
        if not ok:
            raise HTTPException(404, "삭제할 카드를 찾을 수 없습니다.")
        return {"message": "카드가 삭제되었습니다."}


    @router.post("/api/ledger/cards/{card_id}/pay")
    async def pay_ledger_card(card_id: str, request: Request) -> dict:
        """Settle unpaid credit card bills via linked bank account."""
        username = get_current_username(request)
        payload = await request.json() if request.headers.get("content-type") == "application/json" else {}
        try:
            res = settle_card_payment(card_id, payload, username=username)
            return res
        except BalanceConflictError as e:
            raise HTTPException(409, str(e)) from e
        except ValueError as e:
            raise HTTPException(400, str(e))


    # ---------------------------------------------------------------------------
    # Ledger Sample Downloads & Excel File Import
    # ---------------------------------------------------------------------------
    @router.get("/api/sample/card-statement")
    async def download_sample_card_statement():
        """Download sample Excel file for card transaction statements."""
        p = get_root_dir() / "data" / "샘플_카드내역.xlsx"
        if not p.exists():
            raise HTTPException(status_code=404, detail="샘플_카드내역.xlsx 파일을 찾을 수 없습니다.")
        return FileResponse(
            path=str(p),
            filename="샘플_카드내역.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


    @router.get("/api/sample/ledger-transactions")
    async def download_sample_ledger_transactions():
        """Download sample Excel file for general household transactions."""
        p = get_root_dir() / "data" / "샘플_거래내역.xlsx"
        if not p.exists():
            raise HTTPException(status_code=404, detail="샘플_거래내역.xlsx 파일을 찾을 수 없습니다.")
        return FileResponse(
            path=str(p),
            filename="샘플_거래내역.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


    @router.post('/api/ledger/document-import/preview')
    async def preview_ledger_document(request: Request, document_type: str = Query('auto')) -> JSONResponse:
        from app.services import ledger_document_import as importer
        from starlette.concurrency import run_in_threadpool
        get_current_username(request)  # Authentication before consuming any file bytes.
        headers = {'Cache-Control': 'no-store'}
        # Read-free same-origin check: do not resolve settings/user data paths for preview.
        origin = request.headers.get('origin') or request.headers.get('referer')
        try:
            parts = urlsplit(origin or '')
            if (parts.scheme, parts.netloc) != (request.url.scheme, request.url.netloc):
                raise HTTPException(403, '동일 사이트에서 파일을 선택해 주세요.', headers=headers)
            if document_type not in {'auto', 'bank_transactions', 'card_transactions'}:
                raise HTTPException(400, '자료 종류를 확인해 주세요.', headers=headers)
            chunks = []; size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > importer.MAX_BYTES:
                    raise HTTPException(413, '파일은 10MiB 이하로 선택해 주세요.', headers=headers)
                chunks.append(chunk)
            result = await run_in_threadpool(importer.preview, b''.join(chunks),
                request.headers.get('content-type', '').split(';')[0], document_type)
            return JSONResponse(result, headers=headers)
        except ValueError as exc:
            raise HTTPException(400, str(exc), headers=headers) from None


    def _ledger_document_owner(request: Request) -> str:
        username = get_current_username(request)
        origin = request.headers.get('origin') or request.headers.get('referer')
        parts = urlsplit(origin or '')
        if (parts.scheme, parts.netloc) != (request.url.scheme, request.url.netloc):
            raise HTTPException(403, '동일 사이트에서 검토해 주세요.', headers={'Cache-Control': 'no-store'})
        return username


    @router.get('/api/ledger/document-import/options')
    async def ledger_document_options(request: Request) -> JSONResponse:
        from app.services.ledger import document_import_options
        from app.services.financial_json import FinancialStorageError
        from starlette.concurrency import run_in_threadpool
        username = _ledger_document_owner(request)
        try:
            result = await run_in_threadpool(document_import_options, username)
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except (FinancialStorageError, OSError):
            raise HTTPException(503, '가계부를 안전하게 읽지 못했습니다. 저장하지 않았습니다.', headers={'Cache-Control': 'no-store'}) from None


    @router.post('/api/ledger/document-import/review')
    @router.post('/api/ledger/document-import/commit')
    async def ledger_document_review_or_commit(request: Request) -> JSONResponse:
        from app.services.ledger import review_document_transactions, commit_document_transactions, DocumentImportConflict
        from app.services.financial_json import FinancialStorageError
        from starlette.concurrency import run_in_threadpool
        username = _ledger_document_owner(request)
        chunks = []; size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 200000:
                raise HTTPException(413, '검토할 거래가 너무 많습니다.', headers={'Cache-Control': 'no-store'})
            chunks.append(chunk)
        try:
            body = json.loads(b''.join(chunks))
            if not isinstance(body, dict):
                raise ValueError()
            if request.url.path.endswith('/commit'):
                result = await run_in_threadpool(commit_document_transactions, body, username)
            else:
                if set(body) != {'rows'}:
                    raise ValueError()
                result = await run_in_threadpool(review_document_transactions, body['rows'], username)
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except DocumentImportConflict as exc:
            raise HTTPException(409, str(exc), headers={'Cache-Control': 'no-store'}) from None
        except (FinancialStorageError, OSError):
            raise HTTPException(503, '가계부 저장소를 확인하지 못했습니다. 결과를 확인한 뒤 재시도해 주세요.', headers={'Cache-Control': 'no-store'}) from None
        except (ValueError, TypeError, UnicodeError):
            raise HTTPException(400, '날짜·금액·종류·소유자·분류와 확인 항목을 검토해 주세요.', headers={'Cache-Control': 'no-store'}) from None


    @router.post("/api/ledger/import-file")
    async def upload_ledger_file(
        request: Request,
        file: UploadFile = File(...),
        owner: str = Form("모두"),
    ) -> dict:
        """Upload Excel (.xlsx, .xls) or CSV file to import transactions."""
        username = get_current_username(request)
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(400, "업로드된 파일이 비어 있습니다.")
        try:
            count = import_ledger_from_file_bytes(
                file_bytes=file_bytes,
                filename=file.filename or "import.xlsx",
                default_owner=owner,
                username=username,
            )
            return {"message": f"총 {count}건의 거래 내역을 성공적으로 등록했습니다.", "count": count}
        except Exception as e:
            raise HTTPException(400, f"파일 처리 중 오류가 발생했습니다: {str(e)}")

    return router
