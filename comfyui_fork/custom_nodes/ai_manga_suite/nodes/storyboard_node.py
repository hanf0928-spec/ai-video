
"""LLM storyboard node."""
from __future__ import annotations

import asyncio
import json
import os


CATEGORY = "AIManga/Script"


class StoryboardLLMNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "topic": ("STRING", {"default": "", "multiline": True}),
                "episode_count": ("INT", {"default": 1, "min": 1, "max": 10}),
                "shots_per_episode": ("INT", {"default": 8, "min": 2, "max": 50}),
                "style": ("STRING", {"default": "日系动画"}),
                "api_key": ("STRING", {"default": ""}),
            },
            "optional": {
                "base_url": ("STRING", {"default": "https://api.openai.com/v1"}),
                "model": ("STRING", {"default": "gpt-4o"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("script_json",)
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, topic, episode_count, shots_per_episode, style, api_key,
            base_url="https://api.openai.com/v1", model="gpt-4o"):
        key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        if not key:
            raise RuntimeError("LLM API key required")
        try:
            from backend.app.adapters import LLMAdapter
        except Exception as e:
            raise RuntimeError("backend package not on PYTHONPATH") from e

        llm = LLMAdapter(api_key=key, base_url=base_url, model=model)
        script = asyncio.run(
            llm.generate_script(
                topic,
                episode_count=episode_count,
                shots_per_episode=shots_per_episode,
                style=style,
            )
        )
        return (json.dumps(script, ensure_ascii=False, indent=2),)
