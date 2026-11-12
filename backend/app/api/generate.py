
"""Generation endpoints: script, shot, episode render."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..adapters import get_llm_adapter
from ..celery_app import task_render_episode, task_generate_shot
from ..db import get_db
from ..models.orm import Episode, Job, Shot
from ..schemas import (
    GenerateShotRequest, GenerateEpisodeRequest, ScriptGenerateRequest,
    JobOut, ResponseModel,
)


router = APIRouter(prefix="/generate", tags=["generate"])


@router.post("/script", response_model=ResponseModel)
async def generate_script(body: ScriptGenerateRequest):
    """LLM-only: generate a storyboard script from a topic."""
    llm = get_llm_adapter()
    script = await llm.generate_script(
        body.topic,
        episode_count=body.episode_count,
        shots_per_episode=body.shots_per_episode,
        style=body.style,
    )
    return ResponseModel(data=script)


@router.post("/shot", response_model=JobOut)
def generate_shot(body: GenerateShotRequest, db: Session = Depends(get_db)):
    """Generate a single shot's video asynchronously (celery job).

    - When ``shot.image_url`` is provided, the adapter runs I2V (image-to-video).
    - Otherwise falls back to T2V (text-to-video). Prompt is required in that case.

    之前这里是同步 HTTP 请求内直接 submit+轮询（最长可达 30 分钟），
    但前端 axios 超时 60s、Nginx 默认 proxy_read_timeout 也是 60s，
    云端视频生成稍慢就会导致连接被掐断——前端看起来"任务没有启动"，
    实际上后端仍在阻塞轮询。现在改为投递 Celery 任务 + 返回 Job，
    前端通过 /jobs/ws/{job_id} 或轮询 GET /jobs/{job_id} 跟踪真实进度。
    """
    shot = db.get(Shot, body.shot_id)
    if not shot:
        raise HTTPException(404, "shot not found")

    # T2V requires a non-empty prompt
    if not shot.image_url and not (shot.prompt and shot.prompt.strip()):
        raise HTTPException(
            400,
            "shot has neither first-frame image nor prompt; please fill in a prompt first",
        )

    episode = db.get(Episode, shot.episode_id)
    shot.status = "pending"
    db.add(shot); db.commit()

    payload = body.model_dump()
    job = Job(
        type="generate_shot",
        project_id=episode.project_id if episode else None,
        episode_id=shot.episode_id,
        status="pending",
        payload=payload,
    )
    db.add(job); db.commit(); db.refresh(job)

    async_result = task_generate_shot.delay(job.id, body.shot_id, body.backend, body.extra or {})
    job.celery_task_id = async_result.id
    db.add(job); db.commit(); db.refresh(job)
    return job


@router.post("/episode", response_model=JobOut)
def generate_episode(body: GenerateEpisodeRequest, db: Session = Depends(get_db)):
    """Kick off a full episode render job."""
    ep = db.get(Episode, body.episode_id)
    if not ep:
        raise HTTPException(404, "episode not found")

    job = Job(
        type="episode_render",
        project_id=ep.project_id,
        episode_id=ep.id,
        status="pending",
        payload=body.model_dump(),
    )
    db.add(job); db.commit(); db.refresh(job)
    async_result = task_render_episode.delay(job.id, ep.id, body.model_dump())
    job.celery_task_id = async_result.id
    ep.status = "generating"
    db.add(job); db.add(ep); db.commit(); db.refresh(job)
    return job
