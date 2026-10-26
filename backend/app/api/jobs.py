
"""Job progress / status routes."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.logger import logger
from ..db import SessionLocal, get_db
from ..models.orm import Job, Episode
from ..schemas import JobOut


router = APIRouter(prefix="/jobs", tags=["jobs"])


def _ensure_video_url(job: Job) -> None:
    """为老任务动态补上 result.video_url（不改库，只影响序列化输出）。

    pipeline 新版本会直接写入 video_url；此函数作为向后兼容兜底。
    """
    if not isinstance(job.result, dict):
        return
    if job.result.get("video_url"):
        return
    vp = job.result.get("video_path")
    if not vp:
        return
    try:
        abs_video = Path(vp).resolve()
        abs_output = Path(settings.OUTPUT_DIR).resolve()
        rel = abs_video.relative_to(abs_output).as_posix()
        # 用 dict 复制避免 SQLAlchemy 把它当"字段已改"写回 DB
        new_result = dict(job.result)
        new_result["video_url"] = f"/static/outputs/{rel}"
        job.result = new_result
    except Exception:  # noqa: BLE001
        # 相对化失败（例如 video_path 不在 OUTPUT_DIR 下）：跳过
        pass


@router.get("", response_model=list[JobOut])
def list_jobs(project_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Job).order_by(Job.created_at.desc())
    if project_id:
        q = q.filter(Job.project_id == project_id)
    jobs = q.limit(100).all()
    for j in jobs:
        _ensure_video_url(j)
    return jobs


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    _ensure_video_url(j)
    return j


@router.post("/{job_id}/stop", response_model=JobOut)
def stop_job(job_id: str, db: Session = Depends(get_db)):
    """停止（取消）一个正在运行/等待中的任务。

    - 标记 Job.cancelled = True（pipeline 在下个进度检查点检测到后干净退出）
    - 同时向 Celery 发送 revoke(terminate=True) 立即终止 worker 进程
    - 若是剧集渲染任务，回滚 Episode.status 为 pending
    """
    from ..celery_app import celery_app

    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    if j.status in ("success", "failed", "cancelled"):
        raise HTTPException(409, f"任务已结束（{j.status}），无法停止")

    # 1. 标记取消标志（pipeline 轮询检测）
    j.cancelled = True
    j.message = "正在停止…"
    db.add(j)

    # 2. 回滚关联剧集状态（如有）
    if j.episode_id:
        ep = db.get(Episode, j.episode_id)
        if ep and ep.status == "generating":
            ep.status = "pending"
            db.add(ep)

    db.commit()
    db.refresh(j)

    # 3. 终止 celery worker 上的实际进程（best-effort）
    if j.celery_task_id:
        try:
            celery_app.control.revoke(j.celery_task_id, terminate=True, signal="SIGTERM")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"revoke celery task {j.celery_task_id} failed: {e}")

    _ensure_video_url(j)
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
                _ensure_video_url(j)
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
            if snap["status"] in ("success", "failed", "cancelled"):
                await ws.close()
                return
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
