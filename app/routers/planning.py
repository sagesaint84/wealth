from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request


def create_planning_routers(runtime: ModuleType) -> tuple[APIRouter, APIRouter]:
    read_router = APIRouter()
    write_router = APIRouter()

    @read_router.get("/api/planning")
    async def get_planning(request: Request) -> dict:
        from app.services.planning import read_planning
        return read_planning(runtime._require_authenticated_username(request))

    @write_router.post("/api/planning/{operation}")
    async def save_planning(operation: str, request: Request) -> dict:
        from app.services.planning import mutate, PlanningConflict
        username = runtime._require_authenticated_username(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise runtime.HTTPException(400, "입력 형식이 올바르지 않습니다.")
        try:
            if operation == "snapshot-all":
                source = str(payload.get("source") or "user_confirmed")
                if source not in {"auto", "user_confirmed"}:
                    raise ValueError("기록 출처를 확인하세요.")
                data = runtime.get_full_dashboard_for_user(username=username, record_snapshots=False)
                state, _snapshots = runtime.save_all_owner_net_worth_snapshots(data, username, source=source)
                return state
            return mutate(username, operation, payload)
        except PlanningConflict as exc:
            raise runtime.HTTPException(409, str(exc)) from exc
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise runtime.HTTPException(400, "입력값을 확인하세요. " + str(exc)) from exc

    return read_router, write_router
