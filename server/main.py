"""
FastAPI 앱 — 조립만 한다.

실행:
    python -m server.main                 # 개발 서버 (http://127.0.0.1:8000)
    uvicorn server.main:app --reload
    python -m server.seed                 # 대시보드 계정 생성/갱신
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from collector.config import ROOT  # noqa: E402
from server.routers import auth, data, system  # noqa: E402

WEB_DIR = ROOT / "web"


def create_app() -> FastAPI:
    app = FastAPI(
        title="소담촌 마곡점 매출 대시보드 API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.include_router(auth.router)
    app.include_router(data.router)
    app.include_router(system.router)

    _install_error_handlers(app)
    _install_scheduler(app)
    _mount_frontend(app)
    return app


def _install_scheduler(app: FastAPI) -> None:
    """
    SCHEDULER_ENABLED=true 일 때만 앱 안에서 수집을 돌린다 (FN-601).

    웹 서버와 한 프로세스에 두면 배포 대상이 하나로 줄지만,
    워커를 2개 이상 띄우면 수집이 중복된다. 워커를 늘릴 계획이면
    `python -m collector.scheduler`를 별도 프로세스로 돌릴 것.
    """
    from collector.config import Settings

    settings = Settings.load()
    if not settings.scheduler_enabled:
        return

    # ⚠ 이 import 는 반드시 early return **뒤**에 온다.
    #   collector.scheduler 는 auth·pos_client·service 를 끌어오므로,
    #   앞에 두면 스케줄러를 껐어도 대시보드가 POS 클라이언트 전체를 적재한다.
    #   Vercel 배포판에는 POS 계정도 POS 코드도 있을 이유가 없다
    #   (CLAUDE.md 「POS 접근은 오직 collector/ 안에서만」).
    from collector.scheduler import build_scheduler, describe

    scheduler = build_scheduler(settings)

    @app.on_event("startup")
    def _start() -> None:
        scheduler.start()
        print(f"[scheduler] {describe(settings)}", flush=True)

    @app.on_event("shutdown")
    def _stop() -> None:
        scheduler.shutdown(wait=False)


def _install_error_handlers(app: FastAPI) -> None:
    """
    docs/02 5.3 공통 오류 형식으로 통일한다.
    사용자에게 보이는 메시지는 한글이어야 한다 (FR-SYS-02).
    """

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(_: Request, error: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content={"success": False,
                     "error": {"code": "INVALID_PARAM", "message": "요청 값이 올바르지 않습니다."}},
        )

    @app.exception_handler(Exception)
    async def on_unexpected_error(_: Request, error: Exception):
        return JSONResponse(
            status_code=500,
            content={"success": False,
                     "error": {"code": "INTERNAL_ERROR", "message": "일시적인 오류가 발생했습니다."}},
        )

    from fastapi import HTTPException

    @app.exception_handler(HTTPException)
    async def on_http_error(_: Request, error: HTTPException):
        detail = error.detail
        payload = detail if isinstance(detail, dict) else {"code": "ERROR", "message": str(detail)}
        return JSONResponse(status_code=error.status_code,
                            content={"success": False, "error": payload},
                            headers=getattr(error, "headers", None))


def _mount_frontend(app: FastAPI) -> None:
    """정적 프론트엔드를 같은 서버에서 서빙한다 — 배포 대상을 하나로 줄인다."""
    if not WEB_DIR.exists():
        return

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/dashboard")
    def dashboard():
        return FileResponse(WEB_DIR / "dashboard.html")

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.main:app", host="127.0.0.1", port=8000, reload=False)
