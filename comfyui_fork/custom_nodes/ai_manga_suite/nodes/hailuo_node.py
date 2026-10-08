
"""ComfyUI node that calls Hailuo 03 cloud API for image-to-video."""
from __future__ import annotations

import asyncio
import os
import tempfile

from ..utils import tensor_to_pil


CATEGORY = "AIManga/VideoGen"


class HailuoI2VNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "duration": ("INT", {"default": 6, "min": 3, "max": 10}),
                "resolution": (["540P", "720P", "1080P"], {"default": "1080P"}),
                "api_key": ("STRING", {"default": "", "multiline": False}),
            },
            "optional": {
                "model": ("STRING", {"default": "MiniMax-Hailuo-03"}),
                "seed": ("INT", {"default": 0}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video_url",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY

    def run(self, image, prompt: str, duration: int, resolution: str, api_key: str,
            model: str = "MiniMax-Hailuo-03", seed: int = 0):
        # Save first-frame image to a temp file
        pil = tensor_to_pil(image)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img_path = f.name
        try:
            pil.save(img_path)
            key = api_key or os.environ.get("HAILUO_API_KEY", "")
            if not key:
                raise RuntimeError("Hailuo API key is required (node input or HAILUO_API_KEY env)")

            # Lazy import adapter from backend package (if present on PYTHONPATH)
            try:
                from backend.app.adapters import HailuoAdapter, VideoGenRequest
            except Exception as e:
                raise RuntimeError(
                    "Backend package not on PYTHONPATH. "
                    "Add `/path/to/project/backend` to PYTHONPATH, or install as package."
                ) from e

            adapter = HailuoAdapter(api_key=key, model=model)
            req = VideoGenRequest(
                prompt=prompt,
                image_path=img_path,
                duration=duration,
                resolution=resolution,
                seed=seed or None,
            )
            res = asyncio.run(adapter.generate(req))
            if res.status != "success":
                raise RuntimeError(res.message or "Hailuo generation failed")
            return (res.video_url or "",)
        finally:
            try:
                os.unlink(img_path)
            except Exception:
                pass
