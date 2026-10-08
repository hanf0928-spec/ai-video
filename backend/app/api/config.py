
"""Model provider config endpoints (UI-managed in mode B).

GET  /api/config/providers              list all providers (masked)
GET  /api/config/providers/{provider}   get single (masked)
PUT  /api/config/providers/{provider}   upsert
POST /api/config/providers/{provider}/test   live connectivity test
DELETE /api/config/providers/{provider}      clear
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import ResponseModel
from ..services import config_service


router = APIRouter(prefix="/config", tags=["config"])


@router.get("/providers", response_model=ResponseModel)
def list_providers():
    return ResponseModel(data=config_service.list_all_public())


@router.get("/providers/{provider}", response_model=ResponseModel)
def get_provider(provider: str):
    if provider not in config_service.PROVIDER_SCHEMA:
        raise HTTPException(404, "unknown provider")
    return ResponseModel(data=config_service.get_config_public(provider))


@router.put("/providers/{provider}", response_model=ResponseModel)
def set_provider(provider: str, payload: dict):
    """payload = {"enabled": bool?, "config": {...}}"""
    if provider not in config_service.PROVIDER_SCHEMA:
        raise HTTPException(404, "unknown provider")
    cfg = payload.get("config") or {}
    enabled = payload.get("enabled")
    data = config_service.set_config(provider, cfg, enabled=enabled)
    return ResponseModel(data=data, message="saved")


@router.post("/providers/{provider}/test", response_model=ResponseModel)
async def test_provider(provider: str):
    if provider not in config_service.PROVIDER_SCHEMA:
        raise HTTPException(404, "unknown provider")
    ok, msg = await config_service.test_connection(provider)
    return ResponseModel(success=ok, message=msg, data={"ok": ok, "message": msg})


@router.delete("/providers/{provider}", response_model=ResponseModel)
def delete_provider(provider: str):
    if provider not in config_service.PROVIDER_SCHEMA:
        raise HTTPException(404, "unknown provider")
    config_service.clear_config(provider)
    return ResponseModel(message="cleared")
