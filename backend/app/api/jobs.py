
"""Job progress / status routes."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..models.orm import Job
from ..schemas import JobOut


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(project_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Job).order_by(Job.created_at.desc())
    if project_id:
        q = q.filter(Job.project_id == project_id)
    return q.limit(100).all()


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j


@router.websocket("/ws/{job_id}")
async def job_progress_ws(ws: WebSocket, job_id: str):
    """Push real-time progress for a job."""
    await ws.accept()
    try:
        last = None
        while True:
            with SessionLocal() as db:
                j = db.get(Job, job_id)
                if not j:
                    await ws.send_text(json.dumps({"error": "job not found"}))
                    await ws.close()
                    return
                snap = {
                    "status": j.status,
                    "progress": j.progress,
                    "stage": j.stage,
                    "message": j.message,
                    "result": j.result,
                }
            if snap != last:
                await ws.send_text(json.dumps(snap, ensure_ascii=False))
                last = snap
            if snap["status"] in ("success", "failed"):
                await ws.close()
                return
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
