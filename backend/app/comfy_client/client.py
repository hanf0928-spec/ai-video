
"""Async ComfyUI client: REST + WebSocket.

Reference: https://github.com/comfyanonymous/ComfyUI
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

import httpx
import websockets

from ..core.config import settings
from ..core.exceptions import ComfyUIError
from ..core.logger import logger
from ..services.config_service import get_config as _get_cfg


class ComfyUIClient:
    """Async client for a running ComfyUI server."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        ws_url: Optional[str] = None,
        client_id: Optional[str] = None,
    ):
        cfg = _get_cfg("comfyui")
        self.api_url = (api_url or cfg.get("api_url") or "http://127.0.0.1:8188").rstrip("/")
        self.ws_url = ws_url or cfg.get("ws_url") or "ws://127.0.0.1:8188/ws"
        self.client_id = client_id or uuid.uuid4().hex
        self._http = httpx.AsyncClient(timeout=60.0)

    async def close(self) -> None:
        await self._http.aclose()

    # ---------------- REST ----------------
    async def health(self) -> bool:
        try:
            r = await self._http.get(f"{self.api_url}/system_stats")
            return r.status_code == 200
        except Exception as e:
            logger.warning(f"ComfyUI health check failed: {e}")
            return False

    async def queue_prompt(self, workflow: dict) -> str:
        """Submit a workflow JSON. Returns prompt_id."""
        payload = {"prompt": workflow, "client_id": self.client_id}
        r = await self._http.post(f"{self.api_url}/prompt", json=payload)
        if r.status_code != 200:
            raise ComfyUIError(f"queue_prompt failed: {r.status_code} {r.text}")
        data = r.json()
        pid = data.get("prompt_id")
        if not pid:
            raise ComfyUIError(f"missing prompt_id in response: {data}")
        logger.info(f"[ComfyUI] queued prompt_id={pid}")
        return pid

    async def get_history(self, prompt_id: str) -> dict:
        r = await self._http.get(f"{self.api_url}/history/{prompt_id}")
        if r.status_code != 200:
            raise ComfyUIError(f"get_history failed: {r.status_code}")
        return r.json()

    async def get_image(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        params = {"filename": filename, "subfolder": subfolder, "type": type_}
        r = await self._http.get(f"{self.api_url}/view", params=params)
        if r.status_code != 200:
            raise ComfyUIError(f"get_image failed: {r.status_code}")
        return r.content

    async def upload_image(self, file_path: str | Path, name: Optional[str] = None) -> str:
        """Upload an image to the ComfyUI input folder. Returns the server filename."""
        p = Path(file_path)
        files = {"image": (name or p.name, p.read_bytes(), "image/png")}
        data = {"overwrite": "true"}
        r = await self._http.post(f"{self.api_url}/upload/image", files=files, data=data)
        if r.status_code != 200:
            raise ComfyUIError(f"upload_image failed: {r.status_code} {r.text}")
        return r.json().get("name", p.name)

    async def interrupt(self) -> None:
        await self._http.post(f"{self.api_url}/interrupt")

    # ---------------- WebSocket ----------------
    async def listen(self, prompt_id: str) -> AsyncIterator[dict]:
        """Yield progress events for a given prompt_id. Stops when execution completes."""
        url = f"{self.ws_url}?clientId={self.client_id}"
        async with websockets.connect(url, max_size=16 * 1024 * 1024) as ws:
            while True:
                raw = await ws.recv()
                if isinstance(raw, bytes):
                    continue  # binary preview frame
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                mtype = msg.get("type")
                data = msg.get("data", {})
                if data.get("prompt_id") and data.get("prompt_id") != prompt_id:
                    continue
                yield msg
                if mtype == "executing" and data.get("node") is None and data.get("prompt_id") == prompt_id:
                    # execution finished for this prompt
                    return

    async def run_workflow(
        self,
        workflow: dict,
        *,
        timeout: float = 600.0,
        on_progress=None,
    ) -> dict:
        """Submit and wait until a workflow completes. Returns history result dict."""
        prompt_id = await self.queue_prompt(workflow)

        async def _wait():
            async for msg in self.listen(prompt_id):
                if on_progress:
                    try:
                        on_progress(msg)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"on_progress callback error: {e}")

        try:
            await asyncio.wait_for(_wait(), timeout=timeout)
        except asyncio.TimeoutError as e:
            await self.interrupt()
            raise ComfyUIError(f"workflow timed out after {timeout}s") from e

        history = await self.get_history(prompt_id)
        return history.get(prompt_id, {})


async def get_client() -> ComfyUIClient:
    """FastAPI dependency."""
    return ComfyUIClient()
