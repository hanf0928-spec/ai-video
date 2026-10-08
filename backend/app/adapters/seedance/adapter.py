
"""Seedance 2 (ByteDance Volcano Engine Doubao) video generation adapter.

API ref: https://www.volcengine.com/docs/82379/
使用 Ark 推理服务 OpenAPI:
  POST /contents/generations/tasks   -> submit (type=video)
  GET  /contents/generations/tasks/{task_id} -> poll
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ...core.config import settings
from ...core.exceptions import AdapterError
from ...core.logger import logger
from ...services.config_service import ensure_configured
from ..base import VideoAdapter, VideoGenRequest, VideoGenResult


class SeedanceAdapter(VideoAdapter):
    name = "seedance"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        endpoint_id: Optional[str] = None,
    ):
        # 配置来源：仅从 UI 配置的 DB 读取；.env 中的对应字段被忽略。
        # 显式传入 api_key 时则绕过 DB 校验（ComfyUI 节点面板场景）。
        if api_key:
            cfg: dict = {}
        else:
            cfg = ensure_configured("seedance", "api_key")
        self.api_key = api_key or cfg.get("api_key") or ""
        self.base_url = (base_url or cfg.get("base_url") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
        self.model = model or cfg.get("model") or "doubao-seedance-2-0-pro"
        self.endpoint_id = endpoint_id or cfg.get("endpoint_id") or ""
        self._default_duration = int(cfg.get("default_duration") or 5)
        self._default_ratio = cfg.get("default_ratio") or "16:9"
        self._client = httpx.AsyncClient(timeout=60.0)

    def _headers(self) -> dict:
        if not self.api_key:
            raise AdapterError("Seedance 2 API Key 未配置，请到「模型配置」页填写")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _encode_image(path: str) -> str:
        p = Path(path)
        mime = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def submit(self, req: VideoGenRequest) -> VideoGenResult:
        # 组装 content 列表（text + 可选 image_url）
        content: list[dict] = [
            {
                "type": "text",
                "text": self._build_prompt_text(req),
            }
        ]

        img = req.image_url
        if not img and req.image_path:
            img = self._encode_image(req.image_path)
        if img:
            content.append({"type": "image_url", "image_url": {"url": img}})

        if req.last_frame_url:
            content.append({"type": "image_url", "image_url": {"url": req.last_frame_url}, "role": "last_frame"})

        payload: dict = {
            "model": self.endpoint_id or self.model,
            "content": content,
        }
        payload.update(req.extra or {})

        logger.info(f"[Seedance] submit prompt='{req.prompt[:60]}...'")
        r = await self._client.post(
            f"{self.base_url}/contents/generations/tasks",
            headers=self._headers(),
            json=payload,
        )
        if r.status_code != 200:
            raise AdapterError(f"Seedance submit failed: {r.status_code} {r.text}")
        data = r.json()
        task_id = data.get("id") or data.get("task_id")
        if not task_id:
            raise AdapterError(f"Seedance missing task_id: {data}")
        return VideoGenResult(task_id=task_id, status="pending", raw=data)

    def _build_prompt_text(self, req: VideoGenRequest) -> str:
        parts = [req.prompt]
        # Seedance 通过 prompt 文本中的参数指令控制输出
        parts.append(f"--ratio {req.aspect_ratio}")
        parts.append(f"--duration {int(req.duration)}")
        if req.resolution:
            parts.append(f"--resolution {req.resolution}")
        if req.seed is not None:
            parts.append(f"--seed {req.seed}")
        return " ".join(parts)

    async def query(self, task_id: str) -> VideoGenResult:
        r = await self._client.get(
            f"{self.base_url}/contents/generations/tasks/{task_id}",
            headers=self._headers(),
        )
        if r.status_code != 200:
            raise AdapterError(f"Seedance query failed: {r.status_code} {r.text}")
        data = r.json()
        status_map = {
            "queued": "pending",
            "running": "running",
            "succeeded": "success",
            "cancelled": "failed",
            "failed": "failed",
        }
        raw_status = (data.get("status") or "queued").lower()
        status = status_map.get(raw_status, "running")
        res = VideoGenResult(task_id=task_id, status=status, raw=data)

        if status == "success":
            # 结果结构: {"content":{"video_url": "..."}}
            content = data.get("content") or {}
            res.video_url = content.get("video_url") or data.get("video_url")
        elif status == "failed":
            res.message = data.get("error", {}).get("message", "failed")
        return res

    async def download(self, result: VideoGenResult, dest: str) -> str:
        if not result.video_url:
            raise AdapterError("no video_url to download")
        p = Path(dest)
        p.parent.mkdir(parents=True, exist_ok=True)
        async with self._client.stream("GET", result.video_url) as r:
            r.raise_for_status()
            with p.open("wb") as f:
                async for chunk in r.aiter_bytes(1024 * 64):
                    f.write(chunk)
        result.local_path = str(p)
        return str(p)
