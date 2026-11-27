from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request


def create_asset_records_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.get("/api/asset-records")
    async def get_asset_records(request: Request, owner: str = "") -> dict:
        username = runtime.get_current_username(request)
        records = runtime.list_asset_records(username=username)
        if owner:
            records = [r for r in records if (r.get("owner") or "모두") == owner]
        return {"records": records}

    @router.post("/api/asset-records")
    async def create_asset_record(payload: dict, request: Request) -> dict:
        username = runtime.get_current_username(request)
        payload["owner"] = payload.get("owner") or "모두"
        record = runtime.upsert_asset_record(payload, by_date=bool(payload.get("date")), username=username)
        return {"message": "자산기록을 저장했습니다.", "record": record}

    @router.put("/api/asset-records/{record_id}")
    async def update_asset_record(record_id: str, payload: dict, request: Request) -> dict:
        username = runtime.get_current_username(request)
        payload["id"] = record_id
        if "owner" not in payload or not payload["owner"]:
            payload["owner"] = "모두"
        record = runtime.upsert_asset_record(payload, username=username)
        return {"message": "자산기록을 수정했습니다.", "record": record}

    @router.delete("/api/asset-records/{record_id}")
    async def remove_asset_record(record_id: str, request: Request) -> dict:
        username = runtime.get_current_username(request)
        if not runtime.delete_asset_record(record_id, username=username):
            raise runtime.HTTPException(404, "자산기록을 찾지 못했습니다.")
        return {"message": "자산기록을 삭제했습니다."}

    @router.post("/api/asset-records/snapshot")
    async def snapshot_asset_record(request: Request) -> dict:
        username = runtime.get_current_username(request)
        data = runtime.get_dashboard(username=username)
        records = runtime.auto_save_all_owner_snapshots(
            data,
            username=username,
            source="snapshot",
            memo="수동 스냅샷",
        )
        record_all = next((record for record in records if (record.get("owner") or "모두") == "모두"), None)
        return {
            "message": f"오늘 주식기록을 모든 가족 범위({len(records)}개)에 저장했습니다.",
            "record": record_all,
            "records": records,
        }

    return router
