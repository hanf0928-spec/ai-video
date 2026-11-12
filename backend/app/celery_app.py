
"""Celery application + background tasks."""
from __future__ import annotations

import asyncio

from celery import Celery

from .core.config import settings
from .core.logger import logger
from .db import SessionLocal
from .models.orm import Job, Episode, MangaUpload, Shot, Character
from .utils import clamp_shot_duration


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


def should_cancel(job_id: str) -> bool:
    """检查任务是否被用户取消（读取 Job.cancelled 标志）。"""
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            return bool(job and job.cancelled)
    except Exception:  # noqa: BLE001
        return False


class CancelledError(RuntimeError):
    """任务被用户取消时抛出，由 task 包装器捕获。"""


def _check_cancel(job_id: str) -> None:
    """在进度检查点调用：若已取消则抛出 CancelledError。"""
    if should_cancel(job_id):
        raise CancelledError(f"job {job_id} cancelled by user")


@celery_app.task(bind=True, name="task.manga2anime")
def task_manga2anime(self, job_id: str, upload_id: str, project_id: str, params: dict):
    """Full manga -> anime job."""
    from .pipelines.manga2anime import Manga2AnimePipeline

    _update_job(job_id, status="running", stage="start", progress=0.0)

    def on_progress(stage: str, progress: float, msg: str) -> None:
        _check_cancel(job_id)
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
            strict_video=params.get("strict_video", False),
            on_progress=on_progress,
        )

        result = asyncio.run(pipeline.run())
        _update_job(job_id, status="success", progress=1.0, stage="done", result=result)
        return result
    except CancelledError:
        logger.info(f"manga2anime job {job_id} cancelled by user")
        _update_job(job_id, status="cancelled", stage="cancelled", message="用户已取消")
    except Exception as e:
        logger.exception(f"manga2anime job {job_id} failed")
        _update_job(job_id, status="failed", message=str(e))
        raise


@celery_app.task(bind=True, name="task.generate_shot")
def task_generate_shot(self, job_id: str, shot_id: str, backend: str, extra: dict):
    """单个分镜生成视频（I2V 有首帧图 / T2V 无首帧图均走此任务）。

    之前 /generate/shot 是同步 HTTP 接口内直接 submit+轮询（最长30分钟），
    超出前端 axios / Nginx 默认 60s 超时后连接被掐断，看起来像"任务没启动"。
    现在统一走 Celery，由 Job.progress/stage/message 承载真实状态。
    """
    from .adapters import VideoGenRequest, get_video_adapter

    _update_job(job_id, status="running", stage="submit", progress=0.05, message="提交生成任务")

    try:
        # 先在一个打开的 session 内把本任务需要的字段读出到局部变量，
        # 避免 session 关闭（commit 默认 expire_on_commit）后再访问导致
        # DetachedInstanceError。
        with SessionLocal() as db:
            shot = db.get(Shot, shot_id)
            if not shot:
                raise RuntimeError(f"shot not found: {shot_id}")
            shot.status = "running"
            db.add(shot); db.commit()
            shot_prompt = shot.prompt
            shot_image_url = shot.image_url
            shot_duration = shot.duration
            shot_episode_id = shot.episode_id
            shot_meta = dict(shot.meta or {})

            # 角色一致性：按 meta.characters_in_shot[].character_id 查出该分镜涉及
            # 的角色参考图，自动作为 R2VA 参考图附加给海螺03，约束角色外观跨镜头一致。
            char_ids = {
                c.get("character_id")
                for c in (shot_meta.get("characters_in_shot") or [])
                if c.get("character_id")
            }
            reference_images: list[str] = []
            if char_ids:
                for ch in db.query(Character).filter(Character.id.in_(char_ids)).all():
                    if ch.reference_images:
                        reference_images.append(ch.reference_images[0])
                reference_images = list(dict.fromkeys(reference_images))  # 去重保序

        extra = dict(extra or {})
        if not shot_image_url and "aspect_ratio" not in extra:
            extra["aspect_ratio"] = "16:9"
        if backend == "hailuo" and reference_images and "reference_images" not in extra:
            extra["reference_images"] = reference_images
            logger.info(f"[generate_shot] shot={shot_id} 自动附加 {len(reference_images)} 张角色参考图")

        # VideoGenRequest 顶层字段(resolution/aspect_ratio/fps/seed)可按需覆盖；
        # 其余 backend 专属参数(reference_images/remove_audio等)必须放进嵌套的
        # extra dict 字段，才能被各 adapter 的 _build_content/_build_payload 读到
        # ——这里之前曾经把整个 extra 字典 **展开 当作顶层 kwargs，导致
        # reference_images/remove_audio 等参数实际从未生效，现在统一修正。
        _known_top_level = {"resolution", "aspect_ratio", "fps", "seed"}
        top_level_kwargs = {k: v for k, v in extra.items() if k in _known_top_level}
        nested_extra = {k: v for k, v in extra.items() if k not in _known_top_level}

        adapter = get_video_adapter(backend)
        req = VideoGenRequest(
            prompt=shot_prompt or "anime scene",
            image_url=shot_image_url,  # may be None -> adapter will run T2V
            duration=clamp_shot_duration(shot_duration),
            extra=nested_extra,
            **top_level_kwargs,
        )

        def on_poll(stage: str, progress: float, msg: str) -> None:
            _check_cancel(job_id)
            _update_job(job_id, stage=stage, progress=progress, message=msg)

        res = asyncio.run(_poll_shot_generate(adapter, req, on_poll))
        if res.status != "success":
            with SessionLocal() as db:
                shot = db.get(Shot, shot_id)
                if shot:
                    shot.status = "failed"
                    db.add(shot); db.commit()
            err = res.message or "generation failed"
            _update_job(job_id, status="failed", message=err)
            raise RuntimeError(err)

        dst = settings.OUTPUT_DIR_PATH / shot_episode_id / f"shot_{shot_id}.mp4"
        dst.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(adapter.download(res, str(dst)))

        with SessionLocal() as db:
            shot = db.get(Shot, shot_id)
            if shot:
                shot.video_url = str(dst)
                shot.status = "done"
                shot.model_backend = backend
                db.add(shot); db.commit()

        result = {"video_url": str(dst), "shot_id": shot_id}
        _update_job(job_id, status="success", progress=1.0, stage="done", result=result, message="完成")
        return result
    except CancelledError:
        logger.info(f"generate_shot job {job_id} cancelled by user")
        with SessionLocal() as db:
            shot = db.get(Shot, shot_id)
            if shot:
                shot.status = "pending"
                db.add(shot); db.commit()
        _update_job(job_id, status="cancelled", stage="cancelled", message="用户已取消")
    except Exception as e:
        logger.exception(f"generate_shot job {job_id} failed")
        with SessionLocal() as db:
            shot = db.get(Shot, shot_id)
            if shot and shot.status != "failed":
                shot.status = "failed"
                db.add(shot); db.commit()
        _update_job(job_id, status="failed", message=str(e))
        raise


async def _poll_shot_generate(adapter, req, on_progress):
    """submit + 轮询，期间持续回报进度，复用 VideoAdapter 既有的 submit/query 接口。"""
    res = await adapter.submit(req)
    on_progress("submit", 0.1, f"任务已提交 (task_id={res.task_id})")
    start = asyncio.get_event_loop().time()
    poll_count = 0
    timeout = 1800.0
    poll_interval = 15.0
    while res.status in ("pending", "running"):
        await asyncio.sleep(poll_interval)
        poll_count += 1
        res = await adapter.query(res.task_id)
        elapsed = asyncio.get_event_loop().time() - start
        # 进度估算：0.1~0.9 之间，按轮询次数线性递增但不超过 0.9
        progress = min(0.1 + poll_count * 0.05, 0.9)
        on_progress("polling", progress, f"云端生成中 第{poll_count}次轮询 已等待{elapsed:.0f}s")
        if elapsed > timeout:
            res.status = "failed"
            res.message = f"timeout after {timeout:.0f}s ({poll_count} polls)"
            break
    return res


@celery_app.task(bind=True, name="task.render_episode")
def task_render_episode(self, job_id: str, episode_id: str, params: dict):
    from .pipelines.episode_render import render_episode

    _update_job(job_id, status="running", stage="start", progress=0.0)

    def on_progress(stage: str, progress: float, msg: str) -> None:
        _check_cancel(job_id)
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
    except CancelledError:
        logger.info(f"render_episode job {job_id} cancelled by user")
        _update_job(job_id, status="cancelled", stage="cancelled", message="用户已取消")
    except Exception as e:
        logger.exception(f"render_episode job {job_id} failed")
        _update_job(job_id, status="failed", message=str(e))
        raise


@celery_app.task(bind=True, name="task.manga_analyze")
def task_manga_analyze(self, job_id: str, upload_id: str, project_id: str, params: dict):
    """漫画深度剖析任务：角色 / 剧本 / 分镜（时刻/衣着/动作/神态/环境）。"""
    from .pipelines.manga_analyze import MangaAnalyzePipeline

    _update_job(job_id, status="running", stage="start", progress=0.0)

    def on_progress(stage: str, progress: float, msg: str) -> None:
        _check_cancel(job_id)
        _update_job(job_id, stage=stage, progress=progress, message=msg)

    try:
        with SessionLocal() as db:
            upload = db.get(MangaUpload, upload_id)
            if not upload:
                raise RuntimeError(f"upload not found: {upload_id}")
            upload_path = upload.file_path

        pipeline = MangaAnalyzePipeline(
            upload_path=upload_path,
            project_id=project_id,
            style=params.get("style"),
            extra_hint=params.get("extra_hint"),
            shot_duration=params.get("shot_duration", 4.0),
            on_progress=on_progress,
        )

        result = asyncio.run(pipeline.run())
        _update_job(job_id, status="success", progress=1.0, stage="done", result=result)
        return result
    except CancelledError:
        logger.info(f"manga_analyze job {job_id} cancelled by user")
        _update_job(job_id, status="cancelled", stage="cancelled", message="用户已取消")
    except Exception as e:
        logger.exception(f"manga_analyze job {job_id} failed")
        _update_job(job_id, status="failed", message=str(e))
        raise


@celery_app.task(bind=True, name="task.novel_analyze")
def task_novel_analyze(self, job_id: str, project_id: str, params: dict):
    """小说深度剖析：文本 → 角色 / 剧本 / 分镜（时刻/衣着/动作/神态/环境/prompt）。"""
    from .pipelines.novel_analyze import NovelAnalyzePipeline

    _update_job(job_id, status="running", stage="start", progress=0.0)

    def on_progress(stage: str, progress: float, msg: str) -> None:
        _check_cancel(job_id)
        _update_job(job_id, stage=stage, progress=progress, message=msg)

    try:
        pipeline = NovelAnalyzePipeline(
            novel_text=params.get("novel_text", ""),
            project_id=project_id,
            title_hint=params.get("title_hint"),
            style=params.get("style"),
            extra_hint=params.get("extra_hint"),
            shot_duration=params.get("shot_duration", 4.0),
            chunk_size=params.get("chunk_size", 2500),
            on_progress=on_progress,
        )

        result = asyncio.run(pipeline.run())
        _update_job(job_id, status="success", progress=1.0, stage="done", result=result)
        return result
    except CancelledError:
        logger.info(f"novel_analyze job {job_id} cancelled by user")
        _update_job(job_id, status="cancelled", stage="cancelled", message="用户已取消")
    except Exception as e:
        logger.exception(f"novel_analyze job {job_id} failed")
        _update_job(job_id, status="failed", message=str(e))
        raise


@celery_app.task(bind=True, name="task.novel2anime")
def task_novel2anime(self, job_id: str, project_id: str, params: dict):
    """小说 → 深度剖析 → 海螺03(MiniMax H3) 文生视频，音画同出一次性生成。"""
    from .pipelines.novel2anime import Novel2AnimePipeline

    _update_job(job_id, status="running", stage="start", progress=0.0)

    def on_progress(stage: str, progress: float, msg: str) -> None:
        _check_cancel(job_id)
        _update_job(job_id, stage=stage, progress=progress, message=msg)

    try:
        pipeline = Novel2AnimePipeline(
            novel_text=params.get("novel_text", ""),
            project_id=project_id,
            title_hint=params.get("title_hint"),
            style=params.get("style"),
            extra_hint=params.get("extra_hint"),
            chunk_size=params.get("chunk_size", 2500),
            shot_duration=params.get("shot_duration", 5.0),
            video_backend=params.get("video_backend", "hailuo"),
            resolution=params.get("resolution", "768P"),
            aspect_ratio=params.get("aspect_ratio", "16:9"),
            enable_bgm=params.get("enable_bgm", True),
            enable_subtitle=params.get("enable_subtitle", True),
            max_shots=params.get("max_shots"),
            strict_video=params.get("strict_video", False),
            on_progress=on_progress,
        )

        result = asyncio.run(pipeline.run())
        _update_job(job_id, status="success", progress=1.0, stage="done", result=result)
        return result
    except CancelledError:
        logger.info(f"novel2anime job {job_id} cancelled by user")
        _update_job(job_id, status="cancelled", stage="cancelled", message="用户已取消")
    except Exception as e:
        logger.exception(f"novel2anime job {job_id} failed")
        _update_job(job_id, status="failed", message=str(e))
        raise
