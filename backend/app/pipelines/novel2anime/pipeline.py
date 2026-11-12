
"""Novel -> AI 漫剧视频流水线（文生视频 + 原生音频，"音画同出"）。

和 `novel_analyze`（纯文本剖析，不生成视频）/ `episode_render`、`manga2anime`
（先生成哑剧视频，再用独立 TTS 配音轨道事后 mux）都不同：

本流水线在拿到小说深度剖析（角色 / 剧本 / 分镜）之后，把每个分镜的场景、动作、
对白、音效一起写进 prompt，交给海螺03（MiniMax H3）做纯文本生视频（T2VA），
显式关闭 `remove_audio`，让模型原生产出 **画面 + 对白/音效同步生成** 的结果，
不再需要"先出哑剧视频、再拼接 TTS"的二次合成步骤。
"""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Callable, Optional

from ...adapters import VideoGenRequest, get_video_adapter, get_tts_adapter
from ...core.config import settings
from ...core.exceptions import PipelineError
from ...core.logger import logger
from ...utils import (
    build_srt, shots_to_srt_entries, concat_videos, mux_audio,
    pick_bgm, mix_audio, burn_subtitle, probe_duration, clamp_shot_duration,
)
from ...utils.ffmpeg_util import _ffmpeg_bin
from ..novel_analyze import NovelAnalyzePipeline


ProgressCallback = Callable[[str, float, str], None]
"""(stage, progress 0-1, message)"""


class Novel2AnimePipeline:
    """小说文本 → 深度剖析 → 海螺03 T2VA（音画同出）→ 合并/BGM/字幕 → 成片。"""

    def __init__(
        self,
        novel_text: str,
        project_id: str,
        *,
        title_hint: Optional[str] = None,
        style: Optional[str] = None,
        extra_hint: Optional[str] = None,
        chunk_size: int = 2500,
        shot_duration: float = 5.0,
        video_backend: str = "hailuo",
        resolution: str = "768P",
        aspect_ratio: str = "16:9",
        enable_bgm: bool = True,
        enable_subtitle: bool = True,
        max_shots: Optional[int] = None,
        strict_video: bool = False,
        on_progress: Optional[ProgressCallback] = None,
    ):
        self.novel_text = novel_text or ""
        self.project_id = project_id
        self.title_hint = title_hint
        self.style = style
        self.extra_hint = extra_hint
        self.chunk_size = chunk_size
        self.shot_duration = shot_duration
        self.video_backend = video_backend
        self.resolution = resolution
        self.aspect_ratio = aspect_ratio
        self.enable_bgm = enable_bgm
        self.enable_subtitle = enable_subtitle
        self.max_shots = max_shots
        # strict_video=True 时任一分镜 T2VA 失败直接整个任务失败；
        # False 时降级为纯色占位片段（+ 若有台词则用 TTS 兜底配音）
        self.strict_video = strict_video
        self.on_progress = on_progress or (lambda s, p, m: None)

        self.run_id = uuid.uuid4().hex[:12]
        self.workdir = settings.OUTPUT_DIR_PATH / project_id / f"novel2video_{self.run_id}"
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _p(self, stage: str, progress: float, msg: str = "") -> None:
        logger.info(f"[novel2anime] {stage} {progress:.0%} {msg}")
        try:
            self.on_progress(stage, progress, msg)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"progress callback error: {e}")

    async def run(self) -> dict:
        """Execute all stages, return a result dict with video path/url."""
        # ====== 1. 深度剖析（复用 novel_analyze，本身不生成视频） ======
        self._p("analyze", 0.02, "LLM 深度剖析小说文本")

        def _analyze_progress(stage: str, progress: float, msg: str) -> None:
            # 剖析阶段折算到总进度的 2%~35%
            self._p(f"analyze:{stage}", 0.02 + 0.33 * progress, msg)

        analyzer = NovelAnalyzePipeline(
            novel_text=self.novel_text,
            project_id=self.project_id,
            title_hint=self.title_hint,
            style=self.style,
            extra_hint=self.extra_hint,
            shot_duration=self.shot_duration,
            chunk_size=self.chunk_size,
            on_progress=_analyze_progress,
        )
        report = await analyzer.run()

        storyboard: list[dict] = report.get("storyboard") or []
        if not storyboard:
            raise PipelineError(
                "小说深度剖析未产出任何分镜，无法继续生成视频"
                f"（_fallback_reason={report.get('_fallback_reason')}）"
            )
        if self.max_shots and len(storyboard) > self.max_shots:
            logger.warning(
                f"[novel2anime] 分镜数 {len(storyboard)} 超过 max_shots={self.max_shots}，已截断"
            )
            storyboard = storyboard[: self.max_shots]
        self._p("analyze", 0.35, f"剖析完成，共 {len(storyboard)} 个分镜")

        # ====== 2. 逐分镜 T2VA 生成（音画同出：对白/音效随视频原生生成） ======
        self._p("video", 0.36, f"生成分镜视频（{self.video_backend}，文生视频 + 原生音频）")
        adapter = get_video_adapter(self.video_backend)
        shot_videos: list[str] = []
        shots_dir = self.workdir / "shots"
        shots_dir.mkdir(parents=True, exist_ok=True)

        for i, shot in enumerate(storyboard):
            prompt = self._build_shot_prompt(shot)
            duration = self._clamp_duration(shot.get("duration"))
            req = VideoGenRequest(
                prompt=prompt,
                duration=duration,
                resolution=self.resolution,
                aspect_ratio=self.aspect_ratio,
                # 显式保留模型原生生成的音频（对白/音效）——这正是"音画同出"的关键，
                # 区别于 episode_render / manga2anime 的"先哑剧视频 + 事后 TTS 合成"。
                extra={"remove_audio": False},
            )
            dst = shots_dir / f"shot_{i:03d}.mp4"
            try:
                res = await adapter.generate(req)
                if res.status != "success" or not res.video_url:
                    raise PipelineError(f"shot {i} failed: {res.message}")
                await adapter.download(res, str(dst))
                shot_videos.append(str(dst))
            except Exception as e:  # noqa: BLE001
                err_msg = self._format_exc(e)
                if self.strict_video:
                    raise PipelineError(
                        f"shot {i} 云端 T2VA 失败且 strict_video=True：{err_msg}"
                    )
                logger.error(f"[novel2anime] shot {i} 生成失败，降级为占位片段: {err_msg}")
                await self._fallback_clip(shot, duration, dst)
                shot_videos.append(str(dst))

            self._p(
                "video", 0.36 + 0.46 * (i + 1) / len(storyboard),
                f"{i + 1}/{len(storyboard)}",
            )

        # ====== 3. 合并分镜（每段已自带原生音频，不再叠加整段 TTS） ======
        self._p("concat", 0.84, "合并分镜")
        concat_out = self.workdir / "concat.mp4"
        concat_videos(shot_videos, str(concat_out))

        final_av = concat_out
        # ====== 4. BGM（叠加在原生音轨之上，低音量不盖过台词） ======
        if self.enable_bgm:
            self._p("bgm", 0.90, "叠加 BGM")
            emo = self._dominant_emotion(storyboard)
            bgm = pick_bgm(emo)
            if bgm:
                try:
                    tmp_audio = self.workdir / "concat_audio.m4a"
                    subprocess.run(
                        [_ffmpeg_bin(), "-y", "-i", str(concat_out), "-vn", "-c:a", "aac", str(tmp_audio)],
                        capture_output=True,
                    )
                    mixed = self.workdir / "mixed.m4a"
                    mix_audio([str(tmp_audio), bgm], str(mixed), volumes=[1.0, 0.2])
                    bgm_out = self.workdir / "with_bgm.mp4"
                    mux_audio(str(concat_out), str(mixed), str(bgm_out), replace=True)
                    final_av = bgm_out
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[novel2anime] bgm mix failed: {e}")
            else:
                logger.info("[novel2anime] 未找到 bgm 素材 (data/bgm/)，跳过")

        # ====== 5. 字幕 ======
        final_video = final_av
        if self.enable_subtitle:
            self._p("subtitle", 0.96, "烧录字幕")
            entries = shots_to_srt_entries(storyboard)
            if entries:
                srt_path = self.workdir / "subtitle.srt"
                build_srt(entries, str(srt_path))
                burned = self.workdir / "final.mp4"
                try:
                    burn_subtitle(str(final_av), str(srt_path), str(burned))
                    final_video = burned
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[novel2anime] burn subtitle failed: {e}")

        self._p("done", 1.0, "完成")

        return {
            "title": report.get("title") or self.title_hint or "",
            "genre": report.get("genre") or "",
            "summary": report.get("summary") or "",
            "characters": report.get("characters") or [],
            "storyboard": storyboard,
            "video_path": str(final_video),
            "video_url": self._to_static_url(final_video),
            "duration": probe_duration(final_video),
            "shots": len(storyboard),
            "workdir": str(self.workdir),
            "analysis_meta": report.get("_meta") or {},
        }

    # -------------------- helpers --------------------
    @staticmethod
    def _clamp_duration(d) -> float:
        return float(clamp_shot_duration(d, default=5))

    @staticmethod
    def _build_shot_prompt(shot: dict) -> str:
        """把分镜信息组装成英文 prompt，显式包含对白/音效指令以引导模型原生生成音频。"""
        parts: list[str] = []
        img_p = (shot.get("image_prompt") or "").strip()
        vid_p = (shot.get("video_prompt") or "").strip()
        if img_p:
            parts.append(img_p)
        if vid_p and vid_p != img_p:
            parts.append(vid_p)
        if not parts:
            env = shot.get("environment") or {}
            loc = env.get("location") or ""
            tod = env.get("time_of_day") or ""
            scene_desc = ", ".join(x for x in [loc, tod] if x)
            actions = "; ".join(
                f"{c.get('name', '')} {c.get('action', '')} ({c.get('expression', '')})".strip()
                for c in (shot.get("characters_in_shot") or []) if c.get("name")
            )
            parts.append(", ".join(x for x in [scene_desc, actions] if x) or "anime cinematic scene")

        shot_type = shot.get("shot_type") or ""
        camera = shot.get("camera_motion") or ""
        if shot_type or camera:
            parts.append(f"Shot type: {shot_type}, camera movement: {camera}")

        # "音画同出"关键：显式告诉模型要生成对白人声/音效，而非默认哑剧
        dialogue = (shot.get("dialogue") or "").strip()
        if dialogue:
            speaker = (shot.get("speaker") or "the character").strip()
            parts.append(
                f'{speaker} speaks clearly with synchronized lip movement and audible voice: "{dialogue}"'
            )
        sfx = (shot.get("sfx") or "").strip()
        if sfx:
            parts.append(f"Ambient sound effect: {sfx}")

        return ". ".join(p for p in parts if p)

    @staticmethod
    def _dominant_emotion(storyboard: list[dict]) -> str:
        counts: dict[str, int] = {}
        for shot in storyboard:
            for c in (shot.get("characters_in_shot") or []):
                e = (c.get("emotion") or "neutral").lower()
                counts[e] = counts.get(e, 0) + 1
        if not counts:
            return "neutral"
        return max(counts.items(), key=lambda x: x[1])[0]

    async def _fallback_clip(self, shot: dict, duration: float, dst: Path) -> None:
        """T2VA 失败时的兜底：纯色占位视频 +（若有台词）TTS 配音。"""
        dst.parent.mkdir(parents=True, exist_ok=True)
        silent = dst.with_suffix(".silent.mp4")
        subprocess.run(
            [
                _ffmpeg_bin(), "-y",
                "-f", "lavfi", "-i", f"color=c=black:s=1280x720:d={duration}",
                "-vf", "format=yuv420p",
                str(silent),
            ],
            capture_output=True,
        )
        dialogue = (shot.get("dialogue") or "").strip()
        if dialogue:
            try:
                tts = get_tts_adapter()
                audio_path = dst.with_suffix(".tts.mp3")
                await tts.synthesize(dialogue, emotion=None, output_path=str(audio_path))
                mux_audio(str(silent), str(audio_path), str(dst), replace=True)
                silent.unlink(missing_ok=True)
                return
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[novel2anime] fallback TTS failed: {e}")
        silent.rename(dst)

    @staticmethod
    def _format_exc(e: Exception) -> str:
        err_type = type(e).__name__
        err_msg = str(e)
        inner = getattr(e, "last_attempt", None)
        if inner is not None:
            try:
                inner_exc = inner.exception()
                return f"{err_type}: {err_msg} <- {type(inner_exc).__name__}: {inner_exc}"
            except Exception:  # noqa: BLE001
                pass
        return f"{err_type}: {err_msg}"

    def _to_static_url(self, path: Path) -> str:
        try:
            abs_video = Path(path).resolve()
            abs_output = Path(settings.OUTPUT_DIR).resolve()
            rel = abs_video.relative_to(abs_output).as_posix()
            return f"/static/outputs/{rel}"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[novel2anime] compute video_url failed: {e}")
            return ""
