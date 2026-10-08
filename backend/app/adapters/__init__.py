
"""Adapter factory + registry."""
from __future__ import annotations

from typing import Literal

from ..core.exceptions import AdapterError
from .base import VideoAdapter, VideoGenRequest, VideoGenResult
from .hailuo import HailuoAdapter
from .seedance import SeedanceAdapter
from .tts import TTSAdapter
from .llm import LLMAdapter


VideoBackend = Literal["hailuo", "seedance"]


def get_video_adapter(backend: VideoBackend) -> VideoAdapter:
    if backend == "hailuo":
        return HailuoAdapter()
    if backend == "seedance":
        return SeedanceAdapter()
    raise AdapterError(f"unknown video backend: {backend}")


def get_tts_adapter() -> TTSAdapter:
    return TTSAdapter()


def get_llm_adapter() -> LLMAdapter:
    return LLMAdapter()


__all__ = [
    "VideoAdapter",
    "VideoGenRequest",
    "VideoGenResult",
    "HailuoAdapter",
    "SeedanceAdapter",
    "TTSAdapter",
    "LLMAdapter",
    "get_video_adapter",
    "get_tts_adapter",
    "get_llm_adapter",
]
