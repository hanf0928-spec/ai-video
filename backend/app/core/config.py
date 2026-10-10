
"""Application configuration via pydantic-settings.

All environment variables are declared here with sensible defaults
so the app can boot in development without a .env file.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- App ----------
    APP_ENV: Literal["development", "production", "test"] = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_SECRET_KEY: str = "change-me"
    LOG_LEVEL: str = "INFO"

    # ---------- DB ----------
    DATABASE_URL: str = f"sqlite:///{ROOT_DIR / 'data' / 'app.db'}"

    # ---------- Redis / Celery ----------
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ---------- 模型接入配置 ----------
    # ⚠️ 模式 B：以下模型相关的 API Key / endpoint 不再从 .env 读取，
    #    请通过前端 Web 控制台 → "模型配置" 页面统一管理（加密入库）。
    #    详见 backend/app/services/config_service.py 中的 PROVIDER_SCHEMA

    # ---------- OCR ----------
    # 默认 easyocr：跨平台（含 macOS arm64）开箱可用。
    # 如需切换 paddleocr：先 `pip install -r backend/requirements-paddle.txt`，
    # 然后在 .env 中设置 OCR_PROVIDER=paddleocr。
    OCR_PROVIDER: Literal["paddleocr", "easyocr", "cloud"] = "easyocr"
    OCR_LANG: str = "ch"

    # ---------- Storage ----------
    UPLOAD_DIR: Path = ROOT_DIR / "data" / "uploads"
    OUTPUT_DIR: Path = ROOT_DIR / "data" / "outputs"
    PROJECT_DIR: Path = ROOT_DIR / "data" / "projects"
    CACHE_DIR: Path = ROOT_DIR / "data" / "cache"
    MAX_UPLOAD_SIZE_MB: int = 500

    # ---------- Feature Flags ----------
    ENABLE_LOCAL_COMFYUI: bool = True
    ENABLE_PANEL_DETECTION: bool = True
    ENABLE_OCR: bool = True

    # ---------- CORS ----------
    # 公网部署场景：建议直接放通（反代由 Nginx 做）
    # 多个来源用英文逗号分隔，例如：
    #   CORS_ORIGINS=https://your-domain.com,http://1.2.3.4
    # 使用 "*" 表示不限制来源（配合 allow_credentials=False 更安全，当前为 True 需谨慎）
    # ⚠️ 必须用 str 类型 + 属性拆分，不能用 List[str]。
    #    因为 pydantic-settings 对 List[str] 会强制尝试 json.loads()，
    #    使得 `CORS_ORIGINS=*` / `CORS_ORIGINS=a,b` 这种人类友好写法直接报错。
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    @property
    def CORS_ORIGINS_LIST(self) -> List[str]:
        """把逗号分隔的字符串拆成列表，支持 '*' 直通。"""
        raw = (self.CORS_ORIGINS or "").strip()
        if not raw:
            return []
        if raw == "*":
            return ["*"]
        return [i.strip() for i in raw.split(",") if i.strip()]

    @property
    def ROOT(self) -> Path:
        return ROOT_DIR

    def ensure_dirs(self) -> None:
        for d in (self.UPLOAD_DIR, self.OUTPUT_DIR, self.PROJECT_DIR, self.CACHE_DIR):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
