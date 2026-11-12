
"""Utility helpers."""
from .ffmpeg_util import (
    probe_duration, mux_audio, mix_audio, concat_videos,
    burn_subtitle, image_to_video,
)
from .subtitle import build_srt, shots_to_srt_entries
from .bgm import pick_bgm, dominant_emotion
from .crypto import encrypt, decrypt, mask

# 全局分镜时长约束：海螺03(MiniMax H3) API 最短支持 4 秒单镜头；
# 产品层要求单镜头不超过 6 秒，避免镜头过长拖沓、保持漫剧剪辑节奏紧凑。
# 注意：这是"自动生成分镜时长"的产品级约束，hailuo adapter 内部仍保留
# 4~15 秒的真实 API 硬限（供手动/ComfyUI 等高级场景使用更长时长）。
SHOT_DURATION_MIN = 4
SHOT_DURATION_MAX = 6


def clamp_shot_duration(d, default: int = 5) -> int:
    """把任意来源（LLM 产出 / 用户输入 / 历史数据）的时长统一夹到 4~6 秒整数。"""
    try:
        v = int(round(float(d))) if d is not None else default
    except (TypeError, ValueError):
        v = default
    return max(SHOT_DURATION_MIN, min(SHOT_DURATION_MAX, v))


__all__ = [
    "probe_duration", "mux_audio", "mix_audio", "concat_videos",
    "burn_subtitle", "image_to_video",
    "build_srt", "shots_to_srt_entries",
    "pick_bgm", "dominant_emotion",
    "encrypt", "decrypt", "mask",
    "SHOT_DURATION_MIN", "SHOT_DURATION_MAX", "clamp_shot_duration",
]
