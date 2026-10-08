
"""Generation endpoints: script, shot, episode render."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..adapters import VideoGenRequest, get_video_adapter, get_llm_adapter
from ..celery_app import task_render_episode
from ..core.config import settings
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


@router.post("/shot", response_model=ResponseModel)
async def generate_shot(body: GenerateShotRequest, db: Session = Depends(get_db)):
    """Generate a single shot's video synchronously."""
    shot = db.get(Shot, body.shot_id)
    if not shot:
        raise HTTPException(404, "shot not found")
    if not shot.image_url:
        raise HTTPException(400, "shot has no image_url (first frame)")

    adapter = get_video_adapter(body.backend)
    req = VideoGenRequest(
        prompt=shot.prompt or "anime scene",
        image_path=shot.image_url,
        duration=shot.duration or 4.0,
        **body.extra,
    )
    shot.status = "running"
    db.add(shot); db.commit()
    try:
        res = await adapter.generate(req)
        if res.status != "success":
            shot.status = "failed"
            db.add(shot); db.commit()
            raise HTTPException(502, res.message or "generation failed")
        dst = settings.OUTPUT_DIR / shot.episode_id / f"shot_{shot.id}.mp4"
        dst.parent.mkdir(parents=True, exist_ok=True)
        await adapter.download(res, str(dst))
        shot.video_url = str(dst)
        shot.status = "done"
        shot.model_backend = body.backend
        db.add(shot); db.commit()
        return ResponseModel(data={"video_url": shot.video_url})
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        shot.status = "failed"
        db.add(shot); db.commit()
        raise HTTPException(500, str(e))


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
