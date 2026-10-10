"""ComfyUI node that calls Minimax H3 (海螺03) via EdgeOne Makers Model Pro.

⚠️ 新接口（V1.2）要求首帧图片使用公网可访问 URL（不支持 base64 / 本地路径）。
   本节点保留 image 输入仅为兼容既有 workflow；实际会要求用户额外填写
   first_frame_url。如果不填且用户确实需要图生视频，请改用上游节点将图片
   上传到对象存储后再传 URL。
"""
from __future__ import annotations

import asyncio
import os


CATEGORY = "AIManga/VideoGen"


class HailuoI2VNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "duration": ("INT", {"default": 5, "min": 4, "max": 15}),
                "resolution": (["480P", "720P", "768P"], {"default": "768P"}),
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "base_url": ("STRING", {"default": "", "multiline": False,
                                        "placeholder": "EdgeOne 网关域名 (AI_GATEWAY_BASE_URL)"}),
            },
            "optional": {
                "first_frame_url": ("STRING", {"default": "", "multiline": False,
                                               "placeholder": "首帧图片的公网 URL（I2VA 必填）"}),
                "last_frame_url":  ("STRING", {"default": "", "multiline": False}),
                "ratio": (["adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
                          {"default": "16:9"}),
                "remove_audio": ("BOOLEAN", {"default": False}),
                "model": ("STRING", {"default": "MiniMax-H3"}),
                "seed": ("INT", {"default": 0}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video_url",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY

    def run(
        self,
        prompt: str,
        duration: int,
        resolution: str,
        api_key: str,
        base_url: str,
        first_frame_url: str = "",
        last_frame_url: str = "",
        ratio: str = "16:9",
        remove_audio: bool = False,
        model: str = "MiniMax-H3",
        seed: int = 0,
    ):
        key = api_key or os.environ.get("HAILUO_API_KEY", "")
        if not key:
            raise RuntimeError("Hailuo API key is required (node input or HAILUO_API_KEY env)")
        gw = base_url or os.environ.get("AI_GATEWAY_BASE_URL", "")
        if not gw:
            raise RuntimeError(
                "EdgeOne 网关 base_url 未填写 (node input 或 AI_GATEWAY_BASE_URL env)"
            )

        # Lazy import adapter from backend package (if present on PYTHONPATH)
        try:
            from backend.app.adapters import HailuoAdapter, VideoGenRequest
        except Exception as e:
            raise RuntimeError(
                "Backend package not on PYTHONPATH. "
                "Add `/path/to/project/backend` to PYTHONPATH, or install as package."
            ) from e

        adapter = HailuoAdapter(api_key=key, base_url=gw, model=model)
        req = VideoGenRequest(
            prompt=prompt,
            image_url=first_frame_url or None,
            last_frame_url=last_frame_url or None,
            duration=duration,
            resolution=resolution,
            aspect_ratio=ratio,
            seed=seed or None,
            extra={"remove_audio": bool(remove_audio)} if remove_audio else {},
        )
        res = asyncio.run(adapter.generate(req))
        if res.status != "success":
            raise RuntimeError(res.message or "Hailuo generation failed")
        return (res.video_url or "",)
