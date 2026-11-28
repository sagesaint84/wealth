"""Load app configuration and coordinate FastAPI startup."""

from __future__ import annotations

from types import ModuleType

from fastapi import FastAPI


def create_app_startup(runtime: ModuleType) -> dict[str, object]:
    # Resolve application bindings at call time, including the lifespan initializer.
    def load_env_file() -> None:
        if runtime.os.getenv("WEALTH_DISABLE_ENV_FILE", "").strip().lower() in {"1", "true", "yes"}:
            return
        env_path = runtime.ROOT_DIR / ".env"
        if not env_path.exists():
            return
        if not env_path.is_file():
            raise RuntimeError("Configuration error: .env must be a regular file, but a directory was found.")
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                runtime.os.environ.setdefault(key.strip(), value.strip())

    async def ensure_data_dir():
        if runtime.TESTING:
            return
        data_dir = runtime.ROOT_DIR / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        # 1. 멀티유저 초기화 및 sagesaint 데이터 자동 마이그레이션 실행
        from app.services.user_manager import init_users_and_migration
        init_users_and_migration()
        # 2. 계좌 가족 그룹 마이그레이션 실행
        runtime.migrate_add_family_group()
        # 3. 5년치 과거 환율 비동기 동기화
        runtime.asyncio.create_task(runtime.sync_historical_fx())
        # 4. 종목 마스터(국내 ETF/상장사/미국주식) 비동기 동기화
        runtime.asyncio.create_task(runtime.sync_stock_master_online())

    @runtime.asynccontextmanager
    async def app_lifespan(_app: FastAPI):
        """Run the existing startup contract once per application lifespan."""
        await runtime.ensure_data_dir()
        yield

    return {
        "load_env_file": load_env_file,
        "ensure_data_dir": ensure_data_dir,
        "app_lifespan": app_lifespan,
    }
