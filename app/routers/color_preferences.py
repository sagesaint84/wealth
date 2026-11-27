from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request


def create_color_preferences_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.get("/api/color-preferences")
    async def get_color_preferences(request: Request) -> dict:
        from app.services.color_preferences import read_colors
        username = runtime._require_authenticated_username(request)
        try:
            return read_colors(username)
        except ValueError as exc:
            raise runtime.HTTPException(400, str(exc)) from exc

    @router.patch("/api/color-preferences")
    async def patch_color_preferences(request: Request) -> dict:
        from app.services.color_preferences import patch_color
        username = runtime._require_authenticated_username(request)
        try:
            return patch_color(username, await request.json())
        except (ValueError, TypeError) as exc:
            raise runtime.HTTPException(400, str(exc)) from exc

    return router
