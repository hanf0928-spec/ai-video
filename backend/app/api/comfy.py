
"""ComfyUI pass-through endpoints: workflow list, run, upload."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..comfy_client import ComfyUIClient, list_workflows, load_workflow, substitute
from ..schemas import ResponseModel


router = APIRouter(prefix="/comfy", tags=["comfy"])


@router.get("/health", response_model=ResponseModel)
async def comfy_health():
    client = ComfyUIClient()
    ok = await client.health()
    await client.close()
    return ResponseModel(success=ok, data={"online": ok})


@router.get("/workflows", response_model=ResponseModel)
def list_wfs():
    return ResponseModel(data=list_workflows())


@router.post("/run", response_model=ResponseModel)
async def run_workflow(payload: dict):
    """payload = {"workflow": "base/t2i.json", "vars": {...}}"""
    wf_name = payload.get("workflow")
    variables = payload.get("vars", {})
    if not wf_name:
        raise HTTPException(400, "workflow is required")
    wf = substitute(load_workflow(wf_name), variables)
    client = ComfyUIClient()
    try:
        result = await client.run_workflow(wf)
        return ResponseModel(data=result)
    finally:
        await client.close()
