from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, File, Request, UploadFile


def create_data_transfer_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.post("/api/import")
    async def import_portfolio(request: Request, file: UploadFile = File(...), broker: str = "기타 증권사") -> dict:
        if runtime.Path(file.filename or "").suffix.lower() not in {".csv", ".xlsx", ".xlsm"}:
            raise runtime.HTTPException(400, "CSV 또는 XLSX 파일만 가져올 수 있습니다.")
        username = runtime.get_current_username(request)
        try:
            count, warnings = runtime.import_rows(file.filename or "portfolio.csv", await file.read(), broker, username=username)
        except ValueError as exc:
            raise runtime.HTTPException(400, str(exc)) from exc
        return {"message": f"{count}개 보유종목을 반영했습니다.", "count": count, "warnings": warnings}

    @router.post("/api/import-accounts")
    async def import_accounts(request: Request, file: UploadFile = File(...)) -> dict:
        if runtime.Path(file.filename or "").suffix.lower() not in {".csv", ".xlsx", ".xlsm"}:
            raise runtime.HTTPException(400, "CSV 또는 XLSX 파일만 가져올 수 있습니다.")
        username = runtime.get_current_username(request)
        data = runtime.read_portfolio(username=username)
        result = runtime.import_account_rows(file.filename or "accounts.csv", await file.read(), username=username, allowed_owners=set(runtime.get_family_members(data)))
        result["message"] = f"증권계좌 {result['created']}개를 추가했습니다."
        return result

    @router.get("/api/export")
    async def export_data(request: Request):
        """포트폴리오, 가계부 등 전체 데이터를 JSON 파일로 다운로드"""
        import json
        from app.services.portfolio import read_portfolio
        from app.services.asset_records import read_asset_records
        from app.services.dividend_records import read_dividend_records
        from app.services.pnl_records import read_pnl_records
        from app.services.ledger import read_ledger

        username = runtime._require_authenticated_username(request)
        bundle = runtime._sanitize_export_data({
            "version": "2.2",
            "exported_at": runtime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "user": username,
            "backup_policy": "general_data_only",
            "portfolio": read_portfolio(username=username),
            "asset_records": read_asset_records(username=username),
            "dividend_records": read_dividend_records(username=username),
            "realized_pnl_records": read_pnl_records(username=username),
            "ledger": read_ledger(username=username),
        })
        content = json.dumps(bundle, ensure_ascii=False, indent=2)
        from starlette.responses import Response
        today_str = runtime.datetime.now().strftime("%Y-%m-%d")
        filename = f"wealth_{username}_{today_str}.json"
        return Response(
            content=content.encode("utf-8"),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/api/import-backup")
    async def import_backup(request: Request, file: UploadFile = File(...)) -> dict:
        """백업 JSON 파일에서 데이터 복원 (포트폴리오, 자산기록, 배당, 손익, 가계부, OpenAPI)"""
        import json
        from app.services.backup_restore import MAX_BACKUP_UPLOAD_BYTES, restore_general_data
        from app.services.user_openapi import save_user_openapi_config

        username = runtime.get_current_username(request)
        try:
            raw = await file.read(MAX_BACKUP_UPLOAD_BYTES + 1)
            if len(raw) > MAX_BACKUP_UPLOAD_BYTES:
                raise runtime.HTTPException(413, "백업 파일 크기 제한을 초과했습니다.")
            bundle = json.loads(raw.decode("utf-8"))
        except runtime.HTTPException:
            raise
        except Exception as exc:
            raise runtime.HTTPException(400, f"JSON 파싱 실패: {exc}") from exc

        if not isinstance(bundle, dict):
            raise runtime.HTTPException(400, "유효한 백업 파일이 아닙니다.")
        if "portfolio" not in bundle and "asset_records" not in bundle and "ledger" not in bundle:
            raise runtime.HTTPException(400, "유효한 백업 파일이 아닙니다.")

        expected_sections = {
            "portfolio": dict,
            "asset_records": dict,
            "dividend_records": list,
            "realized_pnl_records": list,
            "ledger": dict,
        }
        for section, expected_type in expected_sections.items():
            value = bundle.get(section)
            if value and (not isinstance(value, expected_type) or (expected_type is list and not all(isinstance(item, dict) for item in value))):
                raise runtime.HTTPException(400, "유효한 백업 파일이 아닙니다.")

        msgs = restore_general_data(username, bundle)
        # Current general_data_only exports never carry credentials. Preserve the
        # legacy config restore path only for older backups without that policy.
        if bundle.get("backup_policy") != "general_data_only" and "openapi_config" in bundle and isinstance(bundle["openapi_config"], dict):
            try:
                save_user_openapi_config(username=username, update_data=bundle["openapi_config"])
                msgs.append("OpenAPI설정")
            except Exception as e:
                runtime.logger.warning("OpenAPI config restore warning: %s", e)

        return {"message": f"{', '.join(msgs)} 데이터를 복원했습니다."}

    return router
