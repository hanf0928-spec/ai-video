
"""Job progress / status routes."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.logger import logger
from ..db import SessionLocal, get_db
from ..models.orm import Job, Episode, Shot, Character, Scene, Project
from ..schemas import JobOut, ResponseModel


router = APIRouter(prefix="/jobs", tags=["jobs"])


_SKIP_LOCATIONS = {"", "未指明", "未知", "unknown"}


def _build_shot_prompt_from_report(shot: dict) -> str:
    """从漫画/小说深度剖析报告的单个 storyboard shot 组装分镜工作台可用的 prompt。

    优先用 LLM 产出的 image_prompt/video_prompt；缺失时退回用环境+角色动作拼一个兜底描述。
    """
    parts: list[str] = []
    img_p = (shot.get("image_prompt") or "").strip()
    vid_p = (shot.get("video_prompt") or "").strip()
    if img_p:
        parts.append(img_p)
    if vid_p and vid_p != img_p:
        parts.append(vid_p)
    if not parts:
        env = shot.get("environment") or {}
        loc = env.get("location") or ""
        tod = env.get("time_of_day") or ""
        scene_desc = ", ".join(x for x in [loc, tod] if x)
        actions = "; ".join(
            f"{c.get('name', '')} {c.get('action', '')}".strip()
            for c in (shot.get("characters_in_shot") or []) if c.get("name")
        )
        parts.append(", ".join(x for x in [scene_desc, actions] if x) or "anime cinematic scene")
    shot_type = shot.get("shot_type") or ""
    camera = shot.get("camera_motion") or ""
    if shot_type or camera:
        parts.append(f"镜头：{shot_type} {camera}".strip())
    return "。".join(p for p in parts if p)


@router.post("/{job_id}/activate", response_model=ResponseModel)
def activate_job(job_id: str, db: Session = Depends(get_db)):
    """一键启用「漫画拆解 / 小说拆解」的剖析结果：

      1. characters[] -> 角色库 Character（按项目维度，name 去重）
      2. storyboard[].environment.location -> 场景库 Scene（按项目维度，name 去重）
      3. storyboard[] -> 新建一集 Episode + 对应 Shot 列表，写入「分镜工作台」（按项目维度）

    导入后即可在「角色与场景」「分镜工作台」页面看到数据，并用已有的
    「生成」按钮（/generate/shot）逐条把分镜转换为视频片段。
    幂等保护：同一个 job 只能启用一次（防止重复点击产生重复数据）。
    """
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.type not in ("novel_analyze", "manga_analyze"):
        raise HTTPException(400, f"job.type={job.type} 不支持启用（仅支持 novel_analyze / manga_analyze）")
    if job.status != "success":
        raise HTTPException(400, f"任务尚未成功完成（status={job.status}），无法启用")
    if not job.project_id:
        raise HTTPException(400, "该任务未关联项目，无法启用")
    if not db.get(Project, job.project_id):
        raise HTTPException(404, "project not found")

    result: dict = job.result or {}
    if result.get("_activated"):
        raise HTTPException(
            409,
            f"该任务已启用过（episode_id={result.get('_activated_episode_id')}），请勿重复操作",
        )

    characters: list[dict] = result.get("characters") or []
    storyboard: list[dict] = result.get("storyboard") or []
    if not characters and not storyboard:
        raise HTTPException(400, "报告为空（无角色/分镜数据），无法启用")

    # ---------- 1. 角色去重导入 ----------
    existing_char_names = {
        c.name.strip().lower()
        for c in db.query(Character).filter(Character.project_id == job.project_id).all()
    }
    chars_created = 0
    for c in characters:
        name = (c.get("name") or "").strip()
        if not name or name.lower() in existing_char_names:
            continue
        desc_parts = [
            f"【{c['role']}】" if c.get("role") else "",
            f"外貌：{c['appearance']}" if c.get("appearance") else "",
            f"服装：{c['costume']}" if c.get("costume") else "",
            f"性格：{c['personality']}" if c.get("personality") else "",
            f"声线：{c['voice_tone']}" if c.get("voice_tone") else "",
        ]
        db.add(Character(
            project_id=job.project_id,
            name=name,
            description="；".join(p for p in desc_parts if p),
        ))
        existing_char_names.add(name.lower())
        chars_created += 1

    # ---------- 2. 场景去重导入（从 storyboard[].environment 提取唯一地点） ----------
    existing_scene_names = {
        s.name.strip().lower()
        for s in db.query(Scene).filter(Scene.project_id == job.project_id).all()
    }
    scenes_created = 0
    seen_locations: set[str] = set()
    for shot in storyboard:
        env = shot.get("environment") or {}
        loc = (env.get("location") or "").strip()
        if loc.lower() in _SKIP_LOCATIONS or loc.lower() in seen_locations:
            continue
        seen_locations.add(loc.lower())
        if loc.lower() in existing_scene_names:
            continue
        desc_parts = [env.get("time_of_day"), env.get("weather"), env.get("lighting"), env.get("details")]
        db.add(Scene(
            project_id=job.project_id,
            name=loc,
            description=" / ".join(p for p in desc_parts if p),
        ))
        existing_scene_names.add(loc.lower())
        scenes_created += 1

    # ---------- 3. 分镜 -> 新建 Episode + Shot 列表 ----------
    shots_created = 0
    episode_id: str | None = None
    if storyboard:
        row = (
            db.query(Episode.index)
            .filter(Episode.project_id == job.project_id)
            .order_by(Episode.index.desc())
            .first()
        )
        next_index = (row[0] + 1) if row else 1
        source_type = (result.get("_meta") or {}).get("source_type")
        default_title = f"{'小说' if source_type == 'novel' else '漫画'}拆解导入-{job.id[:8]}"
        ep = Episode(
            project_id=job.project_id,
            index=next_index,
            title=result.get("title") or default_title,
            status="draft",
            script=json.dumps(result.get("script") or {}, ensure_ascii=False),
            meta={"source_job_id": job.id, "source_type": source_type},
        )
        db.add(ep)
        db.flush()  # 拿到 ep.id，供下面 Shot 的外键使用
        episode_id = ep.id

        for shot in storyboard:
            chars_in_shot = shot.get("characters_in_shot") or []
            db.add(Shot(
                episode_id=ep.id,
                index=int(shot.get("index") or 0),
                prompt=_build_shot_prompt_from_report(shot),
                dialogue=shot.get("dialogue") or None,
                speaker=shot.get("speaker") or None,
                emotion=(chars_in_shot[0].get("emotion") if chars_in_shot else None),
                duration=float(shot.get("duration") or 4.0),
                model_backend="hailuo",
                meta={
                    "timecode": shot.get("timecode"),
                    "shot_type": shot.get("shot_type"),
                    "camera_motion": shot.get("camera_motion"),
                    "environment": shot.get("environment"),
                    "characters_in_shot": chars_in_shot,
                    "sfx": shot.get("sfx"),
                    "image_prompt": shot.get("image_prompt"),
                    "video_prompt": shot.get("video_prompt"),
                },
            ))
            shots_created += 1

    # ---------- 4. 标记任务已启用（避免重复导入） ----------
    new_result = dict(result)
    new_result["_activated"] = True
    new_result["_activated_at"] = datetime.utcnow().isoformat()
    new_result["_activated_episode_id"] = episode_id
    job.result = new_result
    db.add(job)
    db.commit()

    return ResponseModel(data={
        "episode_id": episode_id,
        "characters_created": chars_created,
        "scenes_created": scenes_created,
        "shots_created": shots_created,
    })


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
