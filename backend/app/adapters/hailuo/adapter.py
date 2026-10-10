"""Minimax H3 (海螺03) video generation adapter.

对接 EdgeOne Makers Model Pro 网关的 Minimax H3 接口（V1.2）。

Endpoints:
  POST ${AI_GATEWAY_BASE_URL}/minimax/v2/video_generation   -> submit task
  GET  ${AI_GATEWAY_BASE_URL}/minimax/query/{task_id}       -> poll status

鉴权:
  Authorization: Bearer $AI_GATEWAY_API_KEY

请求体采用多模态 content[] 数组:
  - T2VA 文生视频     : 仅 text（必须显式指定 ratio）
  - I2VA 图生视频     : text + image_url(role=first_frame[/last_frame])
  - R2VA 全能参考生成 : text + 任意组合参考 image / video / audio
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ...core.exceptions import AdapterError
from ...core.logger import logger
from ...services.config_service import ensure_configured
from ..base import VideoAdapter, VideoGenRequest, VideoGenResult


# PDF V1.2: duration 范围 4~15 秒；ratio 枚举；resolution 三挡
_ALLOWED_RATIOS = {"adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}
_ALLOWED_RESOLUTIONS = {"480P", "720P", "768P"}
_DURATION_MIN, _DURATION_MAX = 4, 15


class HailuoAdapter(VideoAdapter):
    name = "hailuo"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        **_: Any,  # 向后兼容：旧的 group_id 等参数被忽略
    ):
        # 配置来源：仅从 UI 配置的 DB 读取；.env 中的对应字段被忽略。
        # 如果外部显式传入 api_key（例如 ComfyUI 节点面板），则不走 DB 校验。
        if api_key:
            cfg: dict = {}
        else:
            cfg = ensure_configured("hailuo", "api_key", "base_url")
        self.api_key = api_key or cfg.get("api_key") or ""
        # base_url 对应 PDF 中的 ${AI_GATEWAY_BASE_URL}
        self.base_url = (base_url or cfg.get("base_url") or "").rstrip("/")
        self.model = model or cfg.get("model") or "MiniMax-H3"
        self._default_duration = int(cfg.get("default_duration") or 5)
        self._default_resolution = str(cfg.get("default_resolution") or "768P")
        self._default_ratio = str(cfg.get("default_ratio") or "16:9")
        self._default_remove_audio = self._to_bool(cfg.get("default_remove_audio"))
        self._client = httpx.AsyncClient(timeout=60.0)

    @staticmethod
    def _to_bool(v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        return str(v).strip().lower() in ("1", "true", "yes", "y", "on")

    # ---------- helpers ----------
    def _headers(self) -> dict:
        if not self.api_key:
            raise AdapterError("海螺03 API Key 未配置，请到「模型配置」页填写")
        if not self.base_url:
            raise AdapterError(
                "海螺03 base_url (AI_GATEWAY_BASE_URL) 未配置，请到「模型配置」页填写 EdgeOne 网关域名"
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _clamp_duration(d: Any, default: int) -> int:
        try:
            v = int(d) if d is not None else default
        except (TypeError, ValueError):
            v = default
        return max(_DURATION_MIN, min(_DURATION_MAX, v))

    def _normalize_ratio(self, ratio: Optional[str]) -> str:
        r = (ratio or self._default_ratio or "16:9").strip()
        return r if r in _ALLOWED_RATIOS else "16:9"

    def _normalize_resolution(self, resolution: Optional[str]) -> str:
        r = (resolution or self._default_resolution or "768P").strip().upper()
        return r if r in _ALLOWED_RESOLUTIONS else "768P"

    @staticmethod
    def _build_content(req: VideoGenRequest) -> list[dict]:
        """根据请求组装多模态 content 数组。

        - 必须包含一个非空 text 元素
        - image_url 使用公网可访问 URL（PDF 明确要求：不支持 Cookie/登录态/内网）
        - 本地文件 (image_path) 当前不支持，直接抛错指引
        """
        content: list[dict] = [{"type": "text", "text": req.prompt or ""}]

        extra = req.extra or {}

        # 首帧
        first_frame_url = req.image_url or extra.get("first_frame_url")
        if not first_frame_url and req.image_path:
            raise AdapterError(
                "海螺03 新接口要求首帧图片使用公网可访问 URL。"
                "请先将本地图片上传至对象存储（如 COS/OSS/S3）后，"
                "通过 req.image_url 传入；暂不支持 base64 内联。"
            )
        if first_frame_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": first_frame_url},
                "role": "first_frame",
            })

        # 尾帧
        last_frame_url = req.last_frame_url or extra.get("last_frame_url")
        if last_frame_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": last_frame_url},
                "role": "last_frame",
            })

        # R2VA 参考资源（extra 透传）：最多 9 张参考图
        for ref_img in (extra.get("reference_images") or [])[:9]:
            if ref_img:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": ref_img},
                    "role": "reference_image",
                })
        if extra.get("reference_video"):
            content.append({
                "type": "video_url",
                "video_url": {"url": extra["reference_video"]},
                "role": "reference_video",
            })
        if extra.get("reference_audio"):
            content.append({
                "type": "audio_url",
                "audio_url": {"url": extra["reference_audio"]},
                "role": "reference_audio",
            })

        return content

    def _build_payload(self, req: VideoGenRequest) -> dict:
        content = self._build_content(req)
        has_first_frame = any(c.get("role") == "first_frame" for c in content)

        payload: dict[str, Any] = {
            "content": content,
            "duration": self._clamp_duration(req.duration, self._default_duration),
            "resolution": self._normalize_resolution(req.resolution),
        }

        # I2VA（含 first_frame）由图片决定比例，无需 ratio
        if not has_first_frame:
            payload["ratio"] = self._normalize_ratio(req.aspect_ratio)

        # 可选：去除原生音轨
        extra = req.extra or {}
        remove_audio = self._to_bool(extra.get("remove_audio", self._default_remove_audio))
        if remove_audio:
            payload["remove_audio"] = True

        # 允许 extra 内其他字段透传（排除内部用的 key）
        reserved = {
            "first_frame_url", "last_frame_url",
            "reference_images", "reference_video", "reference_audio",
            "remove_audio",
        }
        for k, v in extra.items():
            if k not in reserved and k not in payload:
                payload[k] = v

        return payload

    # ---------- submit ----------
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def submit(self, req: VideoGenRequest) -> VideoGenResult:
        payload = self._build_payload(req)
        logger.info(
            "[Hailuo] submit prompt='%s...' duration=%s resolution=%s roles=%s",
            (req.prompt or "")[:60],
            payload["duration"],
            payload["resolution"],
            [c.get("role") or c.get("type") for c in payload["content"]],
        )

        url = f"{self.base_url}/minimax/v2/video_generation"
        r = await self._client.post(url, headers=self._headers(), json=payload)
        if r.status_code != 200:
            raise AdapterError(f"Hailuo submit failed: {r.status_code} {r.text}")
        data = r.json()
        # PDF: 响应 { "TaskId": "<task_id>" } —— 注意区分大小写
        task_id = data.get("TaskId") or data.get("task_id")
        if not task_id:
            raise AdapterError(f"Hailuo missing TaskId in response: {data}")
        return VideoGenResult(task_id=str(task_id), status="pending", raw=data)

    # ---------- query ----------
    async def query(self, task_id: str) -> VideoGenResult:
        url = f"{self.base_url}/minimax/query/{task_id}"
        r = await self._client.get(url, headers=self._headers())
        if r.status_code != 200:
            raise AdapterError(f"Hailuo query failed: {r.status_code} {r.text}")
        data = r.json()
        task = data.get("task") or {}
        raw_status = (task.get("status") or "running").lower()

        # PDF: running / succeeded / failed
        status_map = {
            "pending": "pending",
            "queued": "pending",
            "queueing": "pending",
            "running": "running",
            "processing": "running",
            "succeeded": "success",
            "success": "success",
            "failed": "failed",
            "fail": "failed",
        }
        status = status_map.get(raw_status, "running")

        res = VideoGenResult(task_id=task_id, status=status, raw=data)
        if status == "success":
            # 视频 URL 带临时签名，直接可下载
            res.video_url = (task.get("content") or {}).get("url")
            dur = task.get("duration")
            if dur is not None:
                try:
                    res.duration = float(dur)
                except (TypeError, ValueError):
                    pass
        elif status == "failed":
            err = task.get("error") or {}
            res.message = (
                task.get("fail_reason")
                or err.get("message")
                or f"failed (request_id={data.get('request_id')})"
            )
        return res

    # ---------- download ----------
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
