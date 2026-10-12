
"""FFmpeg helpers wrapping ffmpeg-python."""
from __future__ import annotations

import functools
import subprocess
from pathlib import Path
from typing import Iterable

from ..core.exceptions import AppError
from ..core.logger import logger


# 编码器优先级：libx264 质量最高 → libopenh264 开源替代 → mpeg4 系统自带兜底
# 大多数发行版（含 OpenCloudOS）默认 ffmpeg 不含 libx264（专利/许可问题），
# 需要通过 RPMFusion / 自编译才能启用。无 libx264 时自动降级到 openh264 或 mpeg4。
_H264_CANDIDATES = ["libx264", "libopenh264", "h264_nvenc", "h264_v4l2m2m"]
_FALLBACK_CODEC = "mpeg4"  # 100% 系统自带，但不是 H.264


@functools.lru_cache(maxsize=1)
def _available_encoders() -> set[str]:
    """探测当前 ffmpeg 支持的视频编码器集合（缓存一次）。"""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return set()
        encoders: set[str] = set()
        for line in r.stdout.splitlines():
            # 典型行：" V..... libx264               H.264 / AVC..."
            parts = line.strip().split(maxsplit=2)
            if len(parts) >= 2 and parts[0].startswith("V"):
                encoders.add(parts[1])
        return encoders
    except Exception as e:  # noqa: BLE001
        logger.warning(f"ffmpeg encoders probe failed: {e}")
        return set()


@functools.lru_cache(maxsize=1)
def _pick_video_codec() -> str:
    """按优先级挑一个当前 ffmpeg 可用的视频编码器。"""
    available = _available_encoders()
    if not available:
        logger.warning("ffmpeg 探测失败，默认尝试 libx264（若报错请安装 ffmpeg-full / RPMFusion ffmpeg）")
        return "libx264"
    for c in _H264_CANDIDATES:
        if c in available:
            if c != "libx264":
                logger.info(f"ffmpeg 未检测到 libx264，自动使用 {c}")
            return c
    logger.warning(
        f"ffmpeg 不支持任何 H.264 编码器，降级到 {_FALLBACK_CODEC}（兼容性差，建议安装 RPMFusion ffmpeg）"
    )
    return _FALLBACK_CODEC


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
    vcodec = _pick_video_codec()
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filt,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", vcodec, "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        str(output),
    ]
    # mpeg4 不接受 -preset/-crf，去掉这些参数避免报错
    if vcodec == "mpeg4":
        cmd = [a for a in cmd if a not in ("-preset", "medium", "-crf", "20")]
        # mpeg4 用 -q:v 控制质量
        idx = cmd.index("-c:v")
        cmd[idx + 2 : idx + 2] = ["-q:v", "3"]
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
    vcodec = _pick_video_codec()
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image),
        "-t", str(duration), "-r", str(fps),
        "-c:v", vcodec, "-pix_fmt", "yuv420p",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        str(output),
    ]
    _run(cmd)
    return str(output)
