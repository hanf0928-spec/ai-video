
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
        poll_interval: float = 5.0,
        timeout: float = 1200.0,
    ) -> VideoGenResult:
        """Submit + poll until finished."""
        import asyncio
        res = await self.submit(req)
        start = asyncio.get_event_loop().time()
        while res.status in ("pending", "running"):
            await asyncio.sleep(poll_interval)
            res = await self.query(res.task_id)
            if asyncio.get_event_loop().time() - start > timeout:
                res.status = "failed"
                res.message = "timeout"
                break
        return res
