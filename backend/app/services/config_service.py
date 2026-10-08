
"""Provider config service.

Supplies the authoritative API-key / endpoint config for all model adapters.
In mode B this service is the ONLY source — .env values for sensitive fields
are intentionally ignored.

Design:
    * `PROVIDER_SCHEMA` declares each provider's fields and which are secret.
    * `get_config(provider)` returns a fully-decrypted dict (for internal use).
    * `get_config_public(provider)` returns a UI-safe dict (secrets masked).
    * `set_config(provider, payload)` encrypts secrets and persists.
    * `test_connection(provider)` does a lightweight live check.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from sqlalchemy.orm import Session

from ..core.exceptions import AdapterError, NotFoundError
from ..core.logger import logger
from ..db import SessionLocal
from ..models.orm import SystemConfig
from ..utils.crypto import decrypt, encrypt, mask


# ---------- Provider schema ----------
# field: (type, is_secret, default, description)
PROVIDER_SCHEMA: dict[str, dict[str, dict]] = {
    "hailuo": {
        "api_key":   {"type": "string", "secret": True,  "default": "", "desc": "海螺03 API Key"},
        "group_id":  {"type": "string", "secret": True,  "default": "", "desc": "MiniMax Group ID"},
        "base_url":  {"type": "string", "secret": False, "default": "https://api.minimax.chat/v1", "desc": "API 地址"},
        "model":     {"type": "string", "secret": False, "default": "MiniMax-Hailuo-03", "desc": "模型名"},
        "default_duration":   {"type": "int", "secret": False, "default": 6},
        "default_resolution": {"type": "string", "secret": False, "default": "1080P"},
    },
    "seedance": {
        "api_key":    {"type": "string", "secret": True,  "default": "", "desc": "火山引擎 API Key"},
        "endpoint_id":{"type": "string", "secret": True,  "default": "", "desc": "Endpoint ID"},
        "base_url":   {"type": "string", "secret": False, "default": "https://ark.cn-beijing.volces.com/api/v3"},
        "model":      {"type": "string", "secret": False, "default": "doubao-seedance-2-0-pro"},
        "default_duration": {"type": "int", "secret": False, "default": 5},
        "default_ratio":    {"type": "string", "secret": False, "default": "16:9"},
    },
    "llm": {
        "provider":  {"type": "string", "secret": False, "default": "openai"},
        "api_key":   {"type": "string", "secret": True,  "default": ""},
        "base_url":  {"type": "string", "secret": False, "default": "https://api.openai.com/v1"},
        "model":     {"type": "string", "secret": False, "default": "gpt-4o"},
    },
    "tts": {
        "provider":      {"type": "string", "secret": False, "default": "minimax"},
        "api_key":       {"type": "string", "secret": True,  "default": ""},
        "group_id":      {"type": "string", "secret": True,  "default": ""},
        "base_url":      {"type": "string", "secret": False, "default": "https://api.minimax.chat/v1"},
        "default_voice": {"type": "string", "secret": False, "default": "female-shaonv"},
        "default_speed": {"type": "float",  "secret": False, "default": 1.0},
    },
    "comfyui": {
        "api_url": {"type": "string", "secret": False, "default": "http://127.0.0.1:8188"},
        "ws_url":  {"type": "string", "secret": False, "default": "ws://127.0.0.1:8188/ws"},
    },
}


def list_providers() -> list[str]:
    return list(PROVIDER_SCHEMA.keys())


def _schema_defaults(provider: str) -> dict:
    schema = PROVIDER_SCHEMA.get(provider, {})
    return {k: v.get("default", "") for k, v in schema.items()}


def _is_secret(provider: str, field: str) -> bool:
    return bool(PROVIDER_SCHEMA.get(provider, {}).get(field, {}).get("secret"))


# ---------- Low-level DB access ----------
def _get_row(db: Session, provider: str) -> SystemConfig | None:
    return db.get(SystemConfig, provider)


def _raw_config(db: Session, provider: str) -> dict:
    row = _get_row(db, provider)
    if row and isinstance(row.config, dict):
        return row.config
    return {}


# ---------- Decrypted read (for internal adapters) ----------
def get_config(provider: str) -> dict:
    """Return a fully decrypted config dict for internal use.

    Missing values fall back to schema defaults (non-secret only).
    """
    if provider not in PROVIDER_SCHEMA:
        raise NotFoundError(f"unknown provider: {provider}")
    with SessionLocal() as db:
        raw = _raw_config(db, provider)
    merged = _schema_defaults(provider)
    for field, meta in PROVIDER_SCHEMA[provider].items():
        if field not in raw:
            continue
        val = raw[field]
        if meta.get("secret") and isinstance(val, str) and val:
            val = decrypt(val)
        merged[field] = val
    return merged


def get_config_public(provider: str) -> dict:
    """Return a UI-safe view: secrets are masked, never returned in clear."""
    cfg = get_config(provider)
    with SessionLocal() as db:
        row = _get_row(db, provider)
    out: dict[str, Any] = {}
    for field, meta in PROVIDER_SCHEMA[provider].items():
        v = cfg.get(field, meta.get("default", ""))
        if meta.get("secret") and isinstance(v, str) and v:
            out[field] = {"masked": mask(v), "has_value": True}
        else:
            out[field] = v
    return {
        "provider": provider,
        "enabled": bool(row.enabled) if row else True,
        "config": out,
        "schema": PROVIDER_SCHEMA[provider],
        "last_tested_at": row.last_tested_at.isoformat() if row and row.last_tested_at else None,
        "last_test_ok": row.last_test_ok if row else None,
        "last_test_message": row.last_test_message if row else None,
    }


def list_all_public() -> list[dict]:
    return [get_config_public(p) for p in list_providers()]


# ---------- Write ----------
def set_config(provider: str, payload: dict, *, enabled: bool | None = None) -> dict:
    """Persist provider config. Secret fields are encrypted.

    Any secret field whose incoming value is "" or None is treated as "keep
    existing value" (so UI can submit without re-typing the key).
    """
    if provider not in PROVIDER_SCHEMA:
        raise NotFoundError(f"unknown provider: {provider}")
    schema = PROVIDER_SCHEMA[provider]

    with SessionLocal() as db:
        row = _get_row(db, provider)
        existing_raw = dict(row.config) if row and isinstance(row.config, dict) else {}

        new_raw: dict[str, Any] = {}
        for field, meta in schema.items():
            if field not in payload:
                if field in existing_raw:
                    new_raw[field] = existing_raw[field]
                continue
            val = payload[field]
            if meta.get("secret"):
                if val in (None, ""):
                    # keep old value
                    if field in existing_raw:
                        new_raw[field] = existing_raw[field]
                    continue
                new_raw[field] = encrypt(str(val))
            else:
                new_raw[field] = val

        if row is None:
            row = SystemConfig(provider=provider, config=new_raw,
                               enabled=True if enabled is None else enabled)
            db.add(row)
        else:
            row.config = new_raw
            if enabled is not None:
                row.enabled = enabled
        db.commit()
        logger.info(f"[config] provider={provider} updated fields={list(payload.keys())}")
    return get_config_public(provider)


def clear_config(provider: str) -> None:
    with SessionLocal() as db:
        row = _get_row(db, provider)
        if row:
            db.delete(row)
            db.commit()


# ---------- Validation ----------
def ensure_configured(provider: str, *required_fields: str) -> dict:
    """Raise AdapterError if any required field is missing.

    Returns the decrypted config dict.
    """
    cfg = get_config(provider)
    missing = [f for f in required_fields if not cfg.get(f)]
    if missing:
        raise AdapterError(
            f"[{provider}] 以下字段未配置，请到「模型配置」页填写：{', '.join(missing)}"
        )
    return cfg


# ---------- Connection test ----------
async def test_connection(provider: str) -> tuple[bool, str]:
    """Lightweight live check. Does not consume generation quota where possible."""
    import httpx

    try:
        if provider == "hailuo":
            cfg = ensure_configured("hailuo", "api_key")
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(
                    f"{cfg['base_url'].rstrip('/')}/query/video_generation",
                    headers={"Authorization": f"Bearer {cfg['api_key']}"},
                    params={"task_id": "test"},
                )
                # 任何非 401/403 即视为凭证可用（哪怕 task 不存在）
                ok = r.status_code not in (401, 403)
                msg = f"HTTP {r.status_code}"
        elif provider == "seedance":
            cfg = ensure_configured("seedance", "api_key")
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(
                    f"{cfg['base_url'].rstrip('/')}/contents/generations/tasks/_probe",
                    headers={"Authorization": f"Bearer {cfg['api_key']}"},
                )
                ok = r.status_code not in (401, 403)
                msg = f"HTTP {r.status_code}"
        elif provider == "llm":
            cfg = ensure_configured("llm", "api_key")
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.post(
                    f"{cfg['base_url'].rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {cfg['api_key']}",
                             "Content-Type": "application/json"},
                    json={"model": cfg.get("model") or "gpt-4o",
                          "messages": [{"role": "user", "content": "ping"}],
                          "max_tokens": 1},
                )
                ok = r.status_code == 200
                msg = f"HTTP {r.status_code}" if ok else r.text[:200]
        elif provider == "tts":
            cfg = ensure_configured("tts", "api_key")
            ok = True
            msg = "TTS 配置已填写（未发实际请求）"
        elif provider == "comfyui":
            cfg = get_config("comfyui")
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(f"{cfg['api_url'].rstrip('/')}/system_stats")
                ok = r.status_code == 200
                msg = "ComfyUI online" if ok else f"HTTP {r.status_code}"
        else:
            return False, f"unknown provider: {provider}"
    except AdapterError as e:
        ok, msg = False, str(e)
    except Exception as e:  # noqa: BLE001
        ok, msg = False, f"连接失败: {e}"

    # 更新最后测试状态
    with SessionLocal() as db:
        row = _get_row(db, provider)
        if row:
            row.last_tested_at = datetime.utcnow()
            row.last_test_ok = ok
            row.last_test_message = msg
            db.commit()
    return ok, msg
