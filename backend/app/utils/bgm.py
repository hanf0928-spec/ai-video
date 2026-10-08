
"""BGM selector: emotion-driven, picks a bgm asset by tag."""
from __future__ import annotations

import random
from pathlib import Path

from ..core.config import settings


# Emotion -> list of tags (fallback random)
EMOTION_TAG = {
    "happy": ["bright", "cheerful", "pop"],
    "sad": ["sad", "piano", "slow"],
    "angry": ["tense", "rock", "intense"],
    "surprised": ["dramatic", "orchestral"],
    "neutral": ["ambient", "calm"],
    "romantic": ["romantic", "soft"],
    "epic": ["epic", "orchestral", "battle"],
}


def _bgm_dir() -> Path:
    d = settings.ROOT / "data" / "bgm"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pick_bgm(emotion: str | None = None) -> str | None:
    """Pick a BGM file from data/bgm/. Returns absolute path or None."""
    files = list(_bgm_dir().glob("*.mp3")) + list(_bgm_dir().glob("*.wav"))
    if not files:
        return None

    emotion = (emotion or "neutral").lower()
    tags = EMOTION_TAG.get(emotion, [])
    matched = [f for f in files if any(t in f.stem.lower() for t in tags)]
    pool = matched or files
    return str(random.choice(pool))


def dominant_emotion(shots: list[dict]) -> str:
    counts: dict[str, int] = {}
    for s in shots:
        e = (s.get("emotion") or "neutral").lower()
        counts[e] = counts.get(e, 0) + 1
    if not counts:
        return "neutral"
    return max(counts.items(), key=lambda x: x[1])[0]
