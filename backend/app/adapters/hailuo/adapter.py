
"""Hailuo 03 (MiniMax) video generation adapter.

API ref: https://platform.minimaxi.com/document/video_generation
Base URL: https://api.minimax.chat/v1
Endpoints used:
  POST /video_generation            -> submit task
  GET  /query/video_generation      -> poll status
  GET  /files/retrieve              -> download URL
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


class HailuoAdapter(VideoAdapter):
    name = "hailuo"

    def __init__(
        self,
        api_key: Optional[str] = None,
        group_id: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        # 配置来源：仅从 UI 配置的 DB 读取；.env 中的对应字段被忽略。
        # 如果外部显式传入 api_key（例如 ComfyUI 节点面板），则不走 DB 校验。
        if api_key:
            cfg: dict = {}
        else:
            cfg = ensure_configured("hailuo", "api_key")
        self.api_key = api_key or cfg.get("api_key") or ""
        self.group_id = group_id or cfg.get("group_id") or ""
        self.base_url = (base_url or cfg.get("base_url") or "https://api.minimax.chat/v1").rstrip("/")
        self.model = model or cfg.get("model") or "MiniMax-Hailuo-03"
        self._default_duration = int(cfg.get("default_duration") or 6)
        self._default_resolution = cfg.get("default_resolution") or "1080P"
        self._client = httpx.AsyncClient(timeout=60.0)

    def _headers(self) -> dict:
        if not self.api_key:
            raise AdapterError("海螺03 API Key 未配置，请到「模型配置」页填写")
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
        payload: dict = {
            "model": self.model,
            "prompt": req.prompt,
            "duration": int(req.duration) if req.duration else self._default_duration,
            "resolution": req.resolution or self._default_resolution,
        }

        # 图生视频首帧
        if req.image_url:
            payload["first_frame_image"] = req.image_url
        elif req.image_path:
            payload["first_frame_image"] = self._encode_image(req.image_path)

        if req.seed is not None:
            payload["seed"] = req.seed

        payload.update(req.extra or {})

        logger.info(f"[Hailuo] submit prompt='{req.prompt[:60]}...' duration={payload['duration']}")
        r = await self._client.post(
            f"{self.base_url}/video_generation", headers=self._headers(), json=payload
        )
        if r.status_code != 200:
            raise AdapterError(f"Hailuo submit failed: {r.status_code} {r.text}")
        data = r.json()
        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            raise AdapterError(f"Hailuo API error: {base_resp}")

        task_id = data.get("task_id")
        if not task_id:
            raise AdapterError(f"Hailuo missing task_id: {data}")

        return VideoGenResult(task_id=task_id, status="pending", raw=data)

    async def query(self, task_id: str) -> VideoGenResult:
        params = {"task_id": task_id}
        r = await self._client.get(
            f"{self.base_url}/query/video_generation",
            headers=self._headers(),
            params=params,
        )
        if r.status_code != 200:
            raise AdapterError(f"Hailuo query failed: {r.status_code} {r.text}")
        data = r.json()
        status_map = {
            "Preparing": "pending",
            "Queueing": "pending",
            "Processing": "running",
            "Success": "success",
            "Fail": "failed",
        }
        raw_status = data.get("status", "Preparing")
        status = status_map.get(raw_status, "running")

        res = VideoGenResult(task_id=task_id, status=status, raw=data)
        if status == "success":
            file_id = data.get("file_id")
            if file_id:
                res.video_url = await self._retrieve_file_url(file_id)
        elif status == "failed":
            res.message = data.get("base_resp", {}).get("status_msg", "failed")
        return res

    async def _retrieve_file_url(self, file_id: str) -> Optional[str]:
        params = {"file_id": file_id}
        if self.group_id:
            params["GroupId"] = self.group_id
        r = await self._client.get(
            f"{self.base_url}/files/retrieve", headers=self._headers(), params=params
        )
        if r.status_code != 200:
            logger.warning(f"[Hailuo] retrieve file url failed: {r.text}")
            return None
        return r.json().get("file", {}).get("download_url")

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
