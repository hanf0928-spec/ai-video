
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


def _run_with_codec_fallback(build_cmd, label: str) -> None:
    """Run an ffmpeg command built by build_cmd(codec); on encoder-related error,
    retry with the next available codec. Last fallback is always 'mpeg4'.
    """
    tried: list[str] = []
    available = _available_encoders()
    # 按优先级构造实际可试序列：当前优选 + 所有其他候选 + mpeg4
    seq: list[str] = []
    primary = _pick_video_codec()
    seq.append(primary)
    for c in _H264_CANDIDATES:
        if c not in seq and c in available:
            seq.append(c)
    if _FALLBACK_CODEC not in seq:
        seq.append(_FALLBACK_CODEC)

    for codec in seq:
        cmd = build_cmd(codec)
        logger.debug(f"ffmpeg[{label}] codec={codec}: {' '.join(cmd)}")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            if codec != primary:
                logger.warning(f"ffmpeg[{label}] codec {primary} 失败，已成功降级到 {codec}")
            return
        err = r.stderr[-500:]
        tried.append(f"{codec}: {err[-200:]}")
        err_lower = err.lower()

        # 识别真正的"编码器相关错误"——仅这些错误才值得换编码器重试
        is_encoder_error = any(k in err_lower for k in (
            "unknown encoder",
            "encoder not found",
            "could not open encoder",
            "error selecting an encoder",
        ))

        # 其他错误（filter 图谱、输入文件、权限、磁盘等）与编码器无关，直接抛出
        if not is_encoder_error:
            raise AppError(f"ffmpeg[{label}] failed (非编码器问题): {err}")

        logger.warning(f"ffmpeg[{label}] codec {codec} 失败，尝试下一个编码器")

    raise AppError(f"ffmpeg[{label}] 所有编码器都失败：\n" + "\n".join(tried))


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


def _has_audio_stream(path: str | Path) -> bool:
    """Return True if the given media file has at least one audio stream."""
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and bool(r.stdout.strip())


def concat_videos(videos: list[str], output: str) -> str:
    """Concat multiple videos with re-encoding (safe for differing codecs).

    FFmpeg concat filter 要求所有输入流配置一致。如果某些 shot 没有音频流
    （常见于 image_to_video 的 fallback 视频），我们用 anullsrc 为它们生成
    静音音轨，保证 concat 稳定。
    """
    if not videos:
        raise AppError("concat_videos: empty list")

    n = len(videos)
    # 1) 探测每个输入是否有音频
    audio_flags = [_has_audio_stream(v) for v in videos]
    has_any_audio = any(audio_flags)
    all_have_audio = all(audio_flags)

    logger.debug(
        f"concat_videos: n={n}, audio_flags={audio_flags}, "
        f"has_any_audio={has_any_audio}, all_have_audio={all_have_audio}"
    )

    inputs: list[str] = []
    for v in videos:
        inputs += ["-i", str(v)]

    # 2) 根据有没有音频决定 filtergraph
    if all_have_audio:
        # 所有输入都有音频：最简单的 concat
        filter_parts = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
        filt = f"{filter_parts}concat=n={n}:v=1:a=1[outv][outa]"
        maps = ["-map", "[outv]", "-map", "[outa]"]
        audio_codec_args = ["-c:a", "aac", "-b:a", "192k"]
    elif has_any_audio:
        # 混合情况：给没音频的 shot 用 anullsrc 补静音
        # 先为每个无音频输入生成一个 anullsrc 音轨 [slience_i]
        silent_parts = []
        for i in range(n):
            if not audio_flags[i]:
                # 用 anullsrc 生成和原视频等长的静音
                # 注意：这里我们生成一个任意长度（concat filter 会按视频长度匹配），
                # 不加 trim，让 concat 自己处理
                silent_parts.append(
                    f"anullsrc=channel_layout=stereo:sample_rate=44100[silent{i}]"
                )
        # 构造 concat 的每对输入
        pairs = []
        for i in range(n):
            if audio_flags[i]:
                pairs.append(f"[{i}:v:0][{i}:a:0]")
            else:
                pairs.append(f"[{i}:v:0][silent{i}]")
        concat_part = "".join(pairs) + f"concat=n={n}:v=1:a=1[outv][outa]"
        if silent_parts:
            filt = ";".join(silent_parts) + ";" + concat_part
        else:
            filt = concat_part
        maps = ["-map", "[outv]", "-map", "[outa]"]
        audio_codec_args = ["-c:a", "aac", "-b:a", "192k"]
    else:
        # 完全没有音频：只合并视频，不输出音频流
        filter_parts = "".join(f"[{i}:v:0]" for i in range(n))
        filt = f"{filter_parts}concat=n={n}:v=1:a=0[outv]"
        maps = ["-map", "[outv]"]
        audio_codec_args = []  # 没音频，不加 -c:a

    def _build(codec: str) -> list[str]:
        cmd = [
            "ffmpeg", "-y", *inputs,
            "-filter_complex", filt,
            *maps,
            "-c:v", codec,
            *audio_codec_args,
            str(output),
        ]
        if codec == "mpeg4":
            # mpeg4 不支持 preset/crf，用 q:v
            idx = cmd.index("-c:v")
            cmd[idx + 2 : idx + 2] = ["-q:v", "3"]
        else:
            idx = cmd.index("-c:v")
            cmd[idx + 2 : idx + 2] = ["-preset", "medium", "-crf", "20"]
        return cmd

    _run_with_codec_fallback(_build, "concat_videos")
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
    def _build(codec: str) -> list[str]:
        return [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(image),
            "-t", str(duration), "-r", str(fps),
            "-c:v", codec, "-pix_fmt", "yuv420p",
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
            str(output),
        ]

    _run_with_codec_fallback(_build, "image_to_video")
    return str(output)
