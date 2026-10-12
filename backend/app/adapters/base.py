
"""Abstract base class for video-generation model adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VideoGenRequest:
    prompt: str
    image_url: Optional[str] = None            # 图生视频的首帧
    image_path: Optional[str] = None           # 本地文件（将被上传或编码为base64）
    last_frame_url: Optional[str] = None       # 结尾帧（支持的后端可用）
    duration: float = 5.0                      # 秒
    resolution: str = "1080P"                  # 1080P / 720P / 540P 或者 WxH
    aspect_ratio: str = "16:9"
    fps: int = 24
    seed: Optional[int] = None
    extra: dict = field(default_factory=dict)  # 后端特定参数


@dataclass
class VideoGenResult:
    task_id: str
    status: str                     # pending / running / success / failed
    video_url: Optional[str] = None
    local_path: Optional[str] = None
    duration: Optional[float] = None
    message: Optional[str] = None
    raw: dict = field(default_factory=dict)


class VideoAdapter(ABC):
    """Common interface for cloud video-gen models (Hailuo / Seedance / ...)."""

    name: str = "base"

    @abstractmethod
    async def submit(self, req: VideoGenRequest) -> VideoGenResult: ...

    @abstractmethod
    async def query(self, task_id: str) -> VideoGenResult: ...

    @abstractmethod
    async def download(self, result: VideoGenResult, dest: str) -> str: ...

    async def generate(
        self,
        req: VideoGenRequest,
        *,
        poll_interval: float = 15.0,
        timeout: float = 1800.0,
    ) -> VideoGenResult:
        """Submit + poll until finished.

        默认轮询间隔 15s（海螺 PDF 建议 15~30s），默认超时 30 分钟。
        每次 query 都打日志，便于诊断是否真的在等待云端生成。
        """
        import asyncio
        from ..core.logger import logger

        res = await self.submit(req)
        logger.info(f"[{self.name}] task submitted: id={res.task_id} initial_status={res.status}")
        start = asyncio.get_event_loop().time()
        poll_count = 0
        while res.status in ("pending", "running"):
            await asyncio.sleep(poll_interval)
            poll_count += 1
            res = await self.query(res.task_id)
            elapsed = asyncio.get_event_loop().time() - start
            logger.info(
                f"[{self.name}] poll#{poll_count} task={res.task_id} "
                f"status={res.status} elapsed={elapsed:.0f}s"
            )
            if elapsed > timeout:
                res.status = "failed"
                res.message = f"timeout after {timeout:.0f}s ({poll_count} polls)"
                logger.error(f"[{self.name}] {res.message}")
                break
        if res.status == "success":
            logger.info(
                f"[{self.name}] task {res.task_id} succeeded in "
                f"{asyncio.get_event_loop().time() - start:.0f}s, video_url={res.video_url[:80] if res.video_url else ''}..."
            )
        elif res.status == "failed":
            logger.error(f"[{self.name}] task {res.task_id} FAILED: {res.message}")
        return res
