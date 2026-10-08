
"""End-to-end Manga -> Anime pipeline orchestrator."""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from ...adapters import (
    VideoGenRequest, get_video_adapter, get_tts_adapter, get_llm_adapter,
)
from ...core.config import settings
from ...core.exceptions import PipelineError
from ...core.logger import logger
from ...utils import (
    build_srt, shots_to_srt_entries, concat_videos, mux_audio,
    image_to_video, pick_bgm, dominant_emotion, mix_audio, burn_subtitle,
    probe_duration,
)
from .loader import load_pages
from .panel_detect import detect_panels
from .ocr import ocr_panel, group_bubbles
from .character import build_character_bank
from .script import panels_to_storyboard


ProgressCallback = Callable[[str, float, str], None]
"""(stage, progress 0-1, message)"""


class Manga2AnimePipeline:
    """Executes the full manga-to-anime generation workflow."""

    def __init__(
        self,
        upload_path: str | Path,
        project_id: str,
        *,
        video_backend: str = "hailuo",
        style: Optional[str] = None,
        tts_voice: Optional[str] = None,
        enable_bgm: bool = True,
        enable_subtitle: bool = True,
        shot_duration: float = 4.0,
        resolution: str = "1080P",
        on_progress: Optional[ProgressCallback] = None,
    ):
        self.upload_path = Path(upload_path)
        self.project_id = project_id
        self.video_backend = video_backend
        self.style = style
        self.tts_voice = tts_voice
        self.enable_bgm = enable_bgm
        self.enable_subtitle = enable_subtitle
        self.shot_duration = shot_duration
        self.resolution = resolution
        self.on_progress = on_progress or (lambda s, p, m: None)

        self.run_id = uuid.uuid4().hex[:12]
        self.workdir = settings.OUTPUT_DIR / project_id / f"m2a_{self.run_id}"
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _p(self, stage: str, progress: float, msg: str = "") -> None:
        logger.info(f"[m2a] {stage} {progress:.0%} {msg}")
        try:
            self.on_progress(stage, progress, msg)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"progress callback error: {e}")

    async def run(self) -> dict:
        """Execute all stages, return a result dict with video path."""
        # ====== 1. Load pages ======
        self._p("load", 0.02, "读取漫画文件")
        page_dir = self.workdir / "pages"
        pages = load_pages(self.upload_path, page_dir)
        if not pages:
            raise PipelineError("no pages loaded")
        self._p("load", 0.08, f"加载 {len(pages)} 页")

        # ====== 2. Panel detection ======
        self._p("panel", 0.1, "分格检测")
        panels_data: list[dict] = []
        panel_dir = self.workdir / "panels"
        for i, page in enumerate(pages):
            panels = detect_panels(page, panel_dir, page_index=i)
            for pan in panels:
                panels_data.append({
                    "page": i,
                    "order": len(panels_data),
                    "bbox": list(pan.bbox),
                    "image_path": pan.image_path,
                })
            self._p("panel", 0.1 + 0.1 * (i + 1) / len(pages), f"第 {i+1}/{len(pages)} 页")
        if not panels_data:
            raise PipelineError("no panels detected")
        self._p("panel", 0.2, f"共检测到 {len(panels_data)} 格")

        # ====== 3. OCR ======
        self._p("ocr", 0.22, "OCR 对白识别")
        for i, p in enumerate(panels_data):
            bubbles = group_bubbles(ocr_panel(p["image_path"]))
            p["bubbles"] = [{"bbox": list(b.bbox), "text": b.text} for b in bubbles]
            p["ocr_text"] = " ".join(b.text for b in bubbles)
            if (i + 1) % 5 == 0:
                self._p("ocr", 0.22 + 0.08 * (i + 1) / len(panels_data), f"{i+1}/{len(panels_data)}")
        self._p("ocr", 0.30, "OCR 完成")

        # ====== 4. Character consistency ======
        self._p("character", 0.32, "角色一致性识别")
        char_dir = self.workdir / "characters"
        characters = build_character_bank(panels_data, char_dir)
        # Assign cluster ids to panels (nearest in panel index order)
        self._p("character", 0.4, f"识别出 {len(characters)} 个角色")

        # ====== 5. Script via LLM ======
        self._p("script", 0.42, "LLM 生成分镜脚本")
        try:
            script = await panels_to_storyboard(panels_data, style=self.style)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"LLM script failed, falling back to simple script: {e}")
            script = self._fallback_script(panels_data)
        # Persist
        (self.workdir / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
        shots = script.get("shots") or []
        if not shots:
            raise PipelineError("empty storyboard")
        self._p("script", 0.5, f"分镜 {len(shots)} 个")

        # ====== 6. Image preparation (reuse panel images as first frames) ======
        self._p("image", 0.52, "准备首帧图")
        for i, shot in enumerate(shots):
            if i < len(panels_data):
                shot["first_frame"] = panels_data[i]["image_path"]
            shot["duration"] = shot.get("duration") or self.shot_duration
        self._p("image", 0.55, "首帧就绪")

        # ====== 7. I2V generation ======
        self._p("video", 0.56, f"图生视频 ({self.video_backend})")
        adapter = get_video_adapter(self.video_backend)
        shot_videos: list[str] = []
        for i, shot in enumerate(shots):
            prompt = self._build_shot_prompt(shot)
            req = VideoGenRequest(
                prompt=prompt,
                image_path=shot.get("first_frame"),
                duration=float(shot.get("duration") or self.shot_duration),
                resolution=self.resolution,
            )
            try:
                res = await adapter.generate(req)
                if res.status != "success" or not res.video_url:
                    raise PipelineError(f"shot {i} failed: {res.message}")
                dst = self.workdir / "shots" / f"shot_{i:03d}.mp4"
                await adapter.download(res, str(dst))
                shot_videos.append(str(dst))
            except Exception as e:  # noqa: BLE001
                logger.error(f"shot {i} generation failed, fallback to still-image video: {e}")
                dst = self.workdir / "shots" / f"shot_{i:03d}.mp4"
                dst.parent.mkdir(parents=True, exist_ok=True)
                image_to_video(shot["first_frame"], shot["duration"], str(dst))
                shot_videos.append(str(dst))
            self._p("video", 0.56 + 0.24 * (i + 1) / len(shots), f"{i+1}/{len(shots)}")

        # ====== 8. TTS ======
        tts_tracks: list[str] = []
        if any(s.get("dialogue") for s in shots):
            self._p("tts", 0.80, "TTS 配音")
            tts = get_tts_adapter()
            tts_dir = self.workdir / "tts"
            tts_dir.mkdir(parents=True, exist_ok=True)
            for i, shot in enumerate(shots):
                text = (shot.get("dialogue") or "").strip()
                if not text:
                    tts_tracks.append("")
                    continue
                try:
                    out = tts_dir / f"shot_{i:03d}.mp3"
                    await tts.synthesize(
                        text,
                        voice_id=self.tts_voice,
                        emotion=shot.get("emotion"),
                        output_path=str(out),
                    )
                    tts_tracks.append(str(out))
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"tts failed for shot {i}: {e}")
                    tts_tracks.append("")
            # Mux per-shot TTS onto per-shot video
            muxed: list[str] = []
            for i, (vid, aud) in enumerate(zip(shot_videos, tts_tracks)):
                if aud and Path(aud).exists():
                    out = self.workdir / "shots_av" / f"shot_{i:03d}.mp4"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        mux_audio(vid, aud, str(out), replace=True)
                        muxed.append(str(out))
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"mux failed shot {i}: {e}")
                        muxed.append(vid)
                else:
                    muxed.append(vid)
            shot_videos = muxed

        # ====== 9. Concat ======
        self._p("concat", 0.86, "合并分镜")
        concat_out = self.workdir / "concat.mp4"
        concat_videos(shot_videos, str(concat_out))

        # ====== 10. BGM ======
        final_av = concat_out
        if self.enable_bgm:
            self._p("bgm", 0.90, "添加 BGM")
            emo = dominant_emotion(shots)
            bgm = pick_bgm(emo)
            if bgm:
                try:
                    # extract current audio from concat_out
                    import subprocess
                    tmp_audio = self.workdir / "concat_audio.m4a"
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", str(concat_out), "-vn", "-c:a", "aac", str(tmp_audio)],
                        capture_output=True,
                    )
                    mixed = self.workdir / "mixed.m4a"
                    mix_audio([str(tmp_audio), bgm], str(mixed), volumes=[1.0, 0.25])
                    final_av = self.workdir / "with_bgm.mp4"
                    mux_audio(str(concat_out), str(mixed), str(final_av), replace=True)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"bgm mix failed: {e}")
                    final_av = concat_out
            else:
                logger.info("no bgm asset found, skipping")

        # ====== 11. Subtitle ======
        final_video = final_av
        if self.enable_subtitle:
            self._p("subtitle", 0.95, "烧录字幕")
            srt_path = self.workdir / "subtitle.srt"
            entries = shots_to_srt_entries(shots)
            if entries:
                build_srt(entries, str(srt_path))
                burned = self.workdir / "final.mp4"
                try:
                    burn_subtitle(str(final_av), str(srt_path), str(burned))
                    final_video = burned
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"burn subtitle failed: {e}")

        self._p("done", 1.0, "完成")
        return {
            "video_path": str(final_video),
            "duration": probe_duration(final_video),
            "shots": len(shots),
            "characters": len(characters),
            "panels": len(panels_data),
            "workdir": str(self.workdir),
            "script": script,
        }

    @staticmethod
    def _build_shot_prompt(shot: dict) -> str:
        parts = []
        if shot.get("scene"):
            parts.append(shot["scene"])
        if shot.get("action"):
            parts.append(shot["action"])
        if shot.get("camera"):
            parts.append(f"镜头: {shot['camera']}")
        if shot.get("emotion"):
            parts.append(f"情绪: {shot['emotion']}")
        return "，".join(parts) or "anime scene, cinematic lighting"

    @staticmethod
    def _fallback_script(panels: list[dict]) -> dict:
        """When LLM is unavailable, build a trivial shot list from OCR text."""
        shots = []
        for p in panels:
            text = p.get("ocr_text", "")
            shots.append({
                "index": p["order"],
                "scene": "anime style, cinematic",
                "camera": "medium shot",
                "action": "scene unfolds",
                "dialogue": text,
                "speaker": "",
                "emotion": "neutral",
                "duration": 4.0,
            })
        return {"title": "Auto Episode", "summary": "", "characters": [], "shots": shots}
