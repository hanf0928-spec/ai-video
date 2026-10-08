
"""FFmpeg helpers wrapping ffmpeg-python."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from ..core.exceptions import AppError
from ..core.logger import logger


def _run(cmd: list[str]) -> None:
    logger.debug("ffmpeg: " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AppError(f"ffmpeg failed: {r.stderr[-500:]}")


def probe_duration(path: str | Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return 0.0
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def mux_audio(video: str, audio: str, output: str, *, replace: bool = True) -> str:
    """Mux an audio track onto a video. If replace=True, drop the original audio."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video),
        "-i", str(audio),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
    ]
    if replace:
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    cmd.append(str(output))
    _run(cmd)
    return str(output)


def mix_audio(audio_list: Iterable[str], output: str, *, volumes: list[float] | None = None) -> str:
    """Mix multiple audios to one. volumes list parallel to audio_list, default 1.0."""
    audios = list(audio_list)
    if not audios:
        raise AppError("mix_audio: empty audio list")
    if volumes is None:
        volumes = [1.0] * len(audios)
    inputs: list[str] = []
    for a in audios:
        inputs += ["-i", str(a)]
    filters = []
    for i, v in enumerate(volumes):
        filters.append(f"[{i}:a]volume={v}[a{i}]")
    mixin = "".join(f"[a{i}]" for i in range(len(audios)))
    filters.append(f"{mixin}amix=inputs={len(audios)}:duration=longest:dropout_transition=0[aout]")
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
           "-map", "[aout]", str(output)]
    _run(cmd)
    return str(output)


def concat_videos(videos: list[str], output: str) -> str:
    """Concat multiple videos with re-encoding (safe for differing codecs)."""
    if not videos:
        raise AppError("concat_videos: empty list")
    inputs: list[str] = []
    for v in videos:
        inputs += ["-i", str(v)]
    n = len(videos)
    filter_parts = []
    for i in range(n):
        filter_parts.append(f"[{i}:v:0][{i}:a:0?]")
    filt = "".join(filter_parts) + f"concat=n={n}:v=1:a=1[outv][outa]"
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filt,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        str(output),
    ]
    _run(cmd)
    return str(output)


def burn_subtitle(video: str, srt_path: str, output: str) -> str:
    """Burn an SRT subtitle onto a video."""
    cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-vf", f"subtitles={srt_path}:force_style='Fontsize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2'",
        "-c:a", "copy",
        str(output),
    ]
    _run(cmd)
    return str(output)


def image_to_video(image: str, duration: float, output: str, *, fps: int = 24) -> str:
    """Create a still-image video (for fallback when I2V fails)."""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image),
        "-t", str(duration), "-r", str(fps),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        str(output),
    ]
    _run(cmd)
    return str(output)
