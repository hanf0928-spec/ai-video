
"""ComfyUI node that calls Seedance 2 cloud API for image-to-video."""
from __future__ import annotations

import asyncio
import os
import tempfile

from ..utils import tensor_to_pil


CATEGORY = "AIManga/VideoGen"


class SeedanceI2VNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "duration": ("INT", {"default": 5, "min": 3, "max": 10}),
                "ratio": (["16:9", "9:16", "1:1", "4:3"], {"default": "16:9"}),
                "resolution": (["540P", "720P", "1080P"], {"default": "1080P"}),
                "api_key": ("STRING", {"default": "", "multiline": False}),
            },
            "optional": {
                "endpoint_id": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": "doubao-seedance-2-0-pro"}),
                "seed": ("INT", {"default": 0}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video_url",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY

    def run(self, image, prompt: str, duration: int, ratio: str, resolution: str,
            api_key: str, endpoint_id: str = "",
            model: str = "doubao-seedance-2-0-pro", seed: int = 0):
        pil = tensor_to_pil(image)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img_path = f.name
        try:
            pil.save(img_path)
            key = api_key or os.environ.get("SEEDANCE_API_KEY", "")
            if not key:
                raise RuntimeError("Seedance API key required")
            try:
                from backend.app.adapters import SeedanceAdapter, VideoGenRequest
            except Exception as e:
                raise RuntimeError(
                    "Backend package not importable. Ensure `backend` is on PYTHONPATH."
                ) from e
            adapter = SeedanceAdapter(api_key=key, model=model,
                                      endpoint_id=endpoint_id or None)
            req = VideoGenRequest(
                prompt=prompt,
                image_path=img_path,
                duration=duration,
                aspect_ratio=ratio,
                resolution=resolution,
                seed=seed or None,
            )
            res = asyncio.run(adapter.generate(req))
            if res.status != "success":
                raise RuntimeError(res.message or "Seedance generation failed")
            return (res.video_url or "",)
        finally:
            try:
                os.unlink(img_path)
            except Exception:
                pass
