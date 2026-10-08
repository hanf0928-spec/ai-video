
"""Celery application + background tasks."""
from __future__ import annotations

import asyncio

from celery import Celery

from .core.config import settings
from .core.logger import logger
from .db import SessionLocal
from .models.orm import Job, Episode, MangaUpload


celery_app = Celery(
    "ai_manga_studio",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=1,
)


def _update_job(job_id: str, **kwargs) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            return
        for k, v in kwargs.items():
            setattr(job, k, v)
        db.add(job)
        db.commit()


@celery_app.task(bind=True, name="task.manga2anime")
def task_manga2anime(self, job_id: str, upload_id: str, project_id: str, params: dict):
    """Full manga -> anime job."""
    from .pipelines import Manga2AnimePipeline

    _update_job(job_id, status="running", stage="start", progress=0.0)

    def on_progress(stage: str, progress: float, msg: str) -> None:
        _update_job(job_id, stage=stage, progress=progress, message=msg)

    try:
        with SessionLocal() as db:
            upload = db.get(MangaUpload, upload_id)
            if not upload:
                raise RuntimeError(f"upload not found: {upload_id}")
            upload_path = upload.file_path

        pipeline = Manga2AnimePipeline(
            upload_path=upload_path,
            project_id=project_id,
            video_backend=params.get("video_backend", "hailuo"),
            style=params.get("style"),
            tts_voice=params.get("tts_voice"),
            enable_bgm=params.get("enable_bgm", True),
            enable_subtitle=params.get("enable_subtitle", True),
            shot_duration=params.get("shot_duration", 4.0),
            resolution=params.get("resolution", "1080P"),
            on_progress=on_progress,
        )

        result = asyncio.run(pipeline.run())
        _update_job(job_id, status="success", progress=1.0, stage="done", result=result)
        return result
    except Exception as e:
        logger.exception(f"manga2anime job {job_id} failed")
        _update_job(job_id, status="failed", message=str(e))
        raise


@celery_app.task(bind=True, name="task.render_episode")
def task_render_episode(self, job_id: str, episode_id: str, params: dict):
    from .pipelines import render_episode

    _update_job(job_id, status="running", stage="start", progress=0.0)

    def on_progress(stage: str, progress: float, msg: str) -> None:
        _update_job(job_id, stage=stage, progress=progress, message=msg)

    try:
        with SessionLocal() as db:
            result = asyncio.run(
                render_episode(
                    db, episode_id,
                    backend=params.get("backend", "hailuo"),
                    enable_tts=params.get("enable_tts", True),
                    enable_bgm=params.get("enable_bgm", True),
                    enable_subtitle=params.get("enable_subtitle", True),
                    on_progress=on_progress,
                )
            )
        _update_job(job_id, status="success", progress=1.0, stage="done", result=result)
        return result
    except Exception as e:
        logger.exception(f"render_episode job {job_id} failed")
        _update_job(job_id, status="failed", message=str(e))
        raise
