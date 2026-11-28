from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse


def create_site_file_routers(runtime: ModuleType) -> tuple[APIRouter, APIRouter, APIRouter]:
    root_assets_router = APIRouter()
    site_pages_router = APIRouter()
    site_samples_router = APIRouter()

    @root_assets_router.get("/sw.js")
    async def service_worker_file():
        return runtime.FileResponse(runtime.STATIC_DIR / "sw.js", media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})

    @root_assets_router.get("/manifest.json")
    async def manifest_file_root():
        return runtime.FileResponse(runtime.STATIC_DIR / "manifest.json", media_type="application/manifest+json")

    @site_pages_router.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return runtime.FileResponse(runtime.STATIC_DIR / "index.html")

    @site_pages_router.get("/dashboard", include_in_schema=False)
    async def dashboard_page() -> FileResponse:
        return runtime.FileResponse(runtime.STATIC_DIR / "index.html")

    @site_pages_router.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> HTMLResponse:
        return runtime.HTMLResponse(status_code=204)

    @site_samples_router.get("/api/sample/holdings")
    async def download_sample_holdings():
        """Download sample Excel file for portfolio holdings."""
        p = runtime.ROOT_DIR / "data" / "샘플_타증권사_보유종목.xlsx"
        if not p.exists():
            p = runtime.ROOT_DIR / "샘플_타증권사_보유종목.xlsx"
        if not p.exists():
            raise runtime.HTTPException(status_code=404, detail="샘플_타증권사_보유종목.xlsx 파일을 찾을 수 없습니다.")
        return runtime.FileResponse(
            path=str(p),
            filename="샘플_타증권사_보유종목.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @site_samples_router.get("/api/sample/accounts")
    async def download_sample_accounts():
        p = runtime.ROOT_DIR / "data" / "샘플_증권계좌.xlsx"
        if not p.exists():
            p = runtime.ROOT_DIR / "샘플_증권계좌.xlsx"
        if not p.exists():
            raise runtime.HTTPException(status_code=404, detail="샘플_증권계좌.xlsx 파일을 찾을 수 없습니다.")
        return runtime.FileResponse(path=str(p), filename="샘플_증권계좌.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return root_assets_router, site_pages_router, site_samples_router
