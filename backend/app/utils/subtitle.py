
"""SRT subtitle generation utils."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _format_timestamp(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(entries: Iterable[dict], output_path: str | Path) -> str:
    """entries: [{"start":float, "end":float, "text":str}, ...]"""
    lines: list[str] = []
    for i, e in enumerate(entries, start=1):
        lines.append(str(i))
        lines.append(f"{_format_timestamp(e['start'])} --> {_format_timestamp(e['end'])}")
        lines.append(e.get("text", "").strip())
        lines.append("")
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


def shots_to_srt_entries(shots: list[dict]) -> list[dict]:
    """Convert shot list (with duration + dialogue) to srt entries.
    Each shot dict should have: duration, dialogue (optional), speaker (optional).
    """
    entries: list[dict] = []
    t = 0.0
    for s in shots:
        dur = float(s.get("duration") or 4.0)
        text = (s.get("dialogue") or "").strip()
        if text:
            speaker = s.get("speaker")
            display = f"{speaker}：{text}" if speaker else text
            entries.append({"start": t, "end": t + dur, "text": display})
        t += dur
    return entries
