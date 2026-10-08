
"""FastAPI application entrypoint."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .core.config import settings
from .core.exceptions import AppError
from .core.logger import logger
from .db import init_db


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI 漫剧工作流",
        description="基于 ComfyUI Fork 的 AI 漫剧生成工作流系统",
        version="0.1.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _on_start():
        logger.info(f"Starting app env={settings.APP_ENV}")
        init_db()
        settings.ensure_dirs()

    @app.exception_handler(AppError)
    async def app_err_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status,
            content={
                "success": False,
                "code": exc.code,
                "message": exc.message,
                "detail": exc.detail,
            },
        )

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    # Business routes
    app.include_router(api_router)

    # Serve generated outputs as static (/static/outputs/...)
    for name, path in (
        ("outputs", settings.OUTPUT_DIR),
        ("uploads", settings.UPLOAD_DIR),
    ):
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        app.mount(f"/static/{name}", StaticFiles(directory=str(p)), name=name)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_ENV == "development",
    )
