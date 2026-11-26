from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Query, Request


def create_savings_pension_router(
    *,
    get_current_username: Callable[[Request], str],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/savings")
    async def get_savings_endpoint(request: Request) -> dict:
        from app.services.savings import get_savings_data
        username = get_current_username(request)
        return get_savings_data(username=username)

    @router.post("/api/bank-accounts")
    async def save_bank_account_endpoint(request: Request) -> dict:
        from app.services.savings import OverdraftValidationError, save_bank_account
        username = get_current_username(request)
        body = await request.json()
        try:
            record = save_bank_account(body, username=username)
        except OverdraftValidationError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"message": "은행 계좌가 저장되었습니다.", "account": record}

    @router.delete("/api/bank-accounts/{acc_id}")
    async def delete_bank_account_endpoint(acc_id: str, request: Request) -> dict:
        from app.services.savings import OverdraftValidationError, delete_bank_account
        username = get_current_username(request)
        try:
            success = delete_bank_account(acc_id, username=username)
        except OverdraftValidationError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not success:
            raise HTTPException(404, "계좌를 찾을 수 없습니다.")
        return {"message": "은행 계좌가 삭제되었습니다."}

    @router.post("/api/savings-accounts")
    async def save_saving_account_endpoint(request: Request) -> dict:
        from app.services.savings import save_saving_account
        username = get_current_username(request)
        body = await request.json()
        try:
            record = save_saving_account(body, username=username)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"message": "예·적금 상품이 저장되었습니다.", "saving": record}

    @router.delete("/api/savings-accounts/{saving_id}")
    async def delete_saving_account_endpoint(saving_id: str, request: Request) -> dict:
        from app.services.savings import delete_saving_account
        username = get_current_username(request)
        success = delete_saving_account(saving_id, username=username)
        if not success:
            raise HTTPException(404, "예·적금 상품을 찾을 수 없습니다.")
        return {"message": "예·적금 상품이 삭제되었습니다."}


    async def _saving_contribution_action(request: Request, saving_id: str, action, contribution_id: str | None = None) -> dict:
        from app.services.savings_contributions import ContributionConflict
        username = get_current_username(request)
        try:
            if request.method == "DELETE":
                action(saving_id, contribution_id, username=username)
                return {"message": "납입 이력이 삭제되었습니다."}
            body = await request.json()
            if contribution_id is None:
                record = action(saving_id, body, username=username)
            else:
                record = action(saving_id, contribution_id, body, username=username)
        except ContributionConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"message": "납입 이력이 저장되었습니다.", "contribution": record}


    @router.post("/api/savings-accounts/{saving_id}/contributions")
    async def add_saving_contribution(saving_id: str, request: Request) -> dict:
        from app.services.savings_contributions import create_contribution
        return await _saving_contribution_action(request, saving_id, create_contribution)


    @router.put("/api/savings-accounts/{saving_id}/contributions/{contribution_id}")
    async def edit_saving_contribution(saving_id: str, contribution_id: str, request: Request) -> dict:
        from app.services.savings_contributions import update_contribution
        return await _saving_contribution_action(request, saving_id, update_contribution, contribution_id)


    @router.delete("/api/savings-accounts/{saving_id}/contributions/{contribution_id}")
    async def remove_saving_contribution(saving_id: str, contribution_id: str, request: Request) -> dict:
        from app.services.savings_contributions import delete_contribution
        return await _saving_contribution_action(request, saving_id, delete_contribution, contribution_id)

    @router.post("/api/savings/calculate")
    async def calculate_saving_endpoint(request: Request) -> dict:
        from app.services.savings import calculate_interest
        body = await request.json()
        calc = calculate_interest(
            saving_type=body.get("saving_type", "deposit"),
            principal_or_monthly=float(body.get("principal_or_monthly") or 0.0),
            interest_rate=float(body.get("interest_rate") or 0.0),
            duration_months=int(body.get("duration_months") or 12),
            tax_type=body.get("tax_type", "normal"),
        )
        return {"calc": calc}

    @router.post("/api/insurance-accounts")
    async def save_insurance_account_endpoint(request: Request) -> dict:
        from app.services.savings import save_insurance_account
        username = get_current_username(request)
        body = await request.json()
        try:
            record = save_insurance_account(body, username=username)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"message": "보험/연금 상품이 저장되었습니다.", "insurance": record}


    @router.put("/api/insurance-accounts/{ins_id}/yearly-contributions")
    async def save_national_pension_history_endpoint(ins_id: str, request: Request) -> dict:
        from app.services.savings import save_national_pension_history, NationalPensionHistoryConflict
        username = get_current_username(request)
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("expected_history"), list):
            raise HTTPException(400, "기존 납부 이력을 확인한 뒤 저장하세요.")
        try:
            item = save_national_pension_history(ins_id, body.get("yearly_contributions"), username,
                                                expected_history=body.get("expected_history"))
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except NationalPensionHistoryConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"insurance": item, "message": "국민연금 납부 이력이 저장되었습니다."}

    @router.delete("/api/insurance-accounts/{ins_id}")
    async def delete_insurance_account_endpoint(ins_id: str, request: Request) -> dict:
        from app.services.savings import delete_insurance_account
        username = get_current_username(request)
        success = delete_insurance_account(ins_id, username=username)
        if not success:
            raise HTTPException(404, "보험/연금 상품을 찾을 수 없습니다.")
        return {"message": "보험/연금 상품이 삭제되었습니다."}


    @router.get("/api/insurance-accounts/{ins_id}/national-pension-analysis")
    async def get_national_pension_analysis_endpoint(ins_id: str, request: Request) -> dict:
        from app.services.national_pension import view
        try:
            return view(ins_id, get_current_username(request))
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


    async def _national_pension_analysis_action(ins_id: str, request: Request, *, reset: bool = False, calculate_only: bool = False) -> dict:
        from app.services import national_pension
        username = get_current_username(request)
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "분석 입력은 객체여야 합니다.")
        try:
            if calculate_only:
                if not isinstance(body.get("expected_history"), list):
                    raise ValueError("현재 납부 이력을 확인한 뒤 계산하세요.")
                revision = national_pension.integer(body.get("revision"), 0, 2**53 - 1)
                return national_pension.calculate(ins_id, body.get("analysis"), username, revision=revision,
                                                 expected_history=body["expected_history"])
            if not isinstance(body.get("expected_history"), list):
                raise ValueError("현재 납부 이력을 확인한 뒤 저장하세요.")
            return national_pension.save(ins_id, {} if reset else body.get("analysis"), body.get("revision"), username,
                                         expected_history=body["expected_history"])
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except national_pension.PensionConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


    @router.put("/api/insurance-accounts/{ins_id}/national-pension-analysis")
    async def save_national_pension_analysis_endpoint(ins_id: str, request: Request) -> dict:
        return await _national_pension_analysis_action(ins_id, request)


    @router.delete("/api/insurance-accounts/{ins_id}/national-pension-analysis")
    async def reset_national_pension_analysis_endpoint(ins_id: str, request: Request) -> dict:
        return await _national_pension_analysis_action(ins_id, request, reset=True)


    @router.post("/api/insurance-accounts/{ins_id}/national-pension-analysis/calculate")
    async def calculate_national_pension_analysis_endpoint(ins_id: str, request: Request) -> dict:
        return await _national_pension_analysis_action(ins_id, request, calculate_only=True)

    @router.post("/api/insurance-accounts/{ins_id}/national-pension-import/preview")
    async def preview_national_pension_document(ins_id: str, request: Request, document_type: str = Query('auto')) -> dict:
        from app.services import national_pension as np, national_pension_import as importer
        from starlette.concurrency import run_in_threadpool
        username=get_current_username(request)
        try:
            # Check ownership before decoding any uploaded content. Raw body, no unbounded multipart spooling.
            _,data=np.read_state(username);np.find_item(data,ins_id)
            chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>importer.MAX_BYTES: raise HTTPException(413,'파일은 10MB 이하로 선택해 주세요.')
                chunks.append(chunk)
            return await run_in_threadpool(importer.preview,ins_id,username,b''.join(chunks),
                                          request.headers.get('content-type','').split(';')[0],document_type)
        except LookupError as exc: raise HTTPException(404,'국민연금 상품을 찾을 수 없습니다.') from exc
        except ValueError as exc: raise HTTPException(400,str(exc)) from exc


    @router.post("/api/insurance-accounts/{ins_id}/national-pension-import/apply")
    async def apply_national_pension_document(ins_id: str, request: Request) -> dict:
        from app.services import national_pension as np, national_pension_import as importer
        try:
            return importer.apply(ins_id,get_current_username(request),await request.json())
        except LookupError as exc: raise HTTPException(404,'국민연금 상품을 찾을 수 없습니다.') from exc
        except np.PensionConflict as exc: raise HTTPException(409,str(exc)) from exc
        except ValueError as exc: raise HTTPException(400,str(exc)) from exc


    @router.post("/api/loan-accounts")
    async def save_loan_account_endpoint(request: Request) -> dict:
        from app.services.savings import OverdraftValidationError, save_loan_account
        username = get_current_username(request)
        body = await request.json()
        try:
            record = save_loan_account(body, username=username)
        except OverdraftValidationError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"message": "대출·마이너스통장이 저장되었습니다.", "loan": record}

    @router.delete("/api/loan-accounts/{loan_id}")
    async def delete_loan_account_endpoint(loan_id: str, request: Request) -> dict:
        from app.services.savings import OverdraftValidationError, delete_loan_account
        username = get_current_username(request)
        try:
            success = delete_loan_account(loan_id, username=username)
        except OverdraftValidationError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not success:
            raise HTTPException(404, "대출·마이너스통장을 찾을 수 없습니다.")
        return {"message": "대출·마이너스통장이 삭제되었습니다."}

    @router.post("/api/loans/calculate")
    async def calculate_loan_endpoint(request: Request) -> dict:
        from app.services.savings import calculate_loan_interest
        body = await request.json()
        calc = calculate_loan_interest(
            current_balance=float(body.get("current_balance") or 0.0),
            interest_rate=float(body.get("interest_rate") or 0.0),
            repayment_type=body.get("repayment_type", "bullet"),
            remaining_months=int(body.get("remaining_months") or 12),
        )
        return {"calc": calc}

    return router
