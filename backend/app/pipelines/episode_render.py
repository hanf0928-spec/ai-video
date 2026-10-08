
"""Episode rendering pipeline: generates all shots in an episode from its script."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session

from ..adapters import VideoGenRequest, get_video_adapter, get_tts_adapter
from ..core.config import settings
from ..core.exceptions import PipelineError
from ..core.logger import logger
from ..models.orm import Episode, Shot
from ..utils import (
    build_srt, shots_to_srt_entries, concat_videos, mux_audio,
    image_to_video, pick_bgm, dominant_emotion, mix_audio, burn_subtitle,
    probe_duration,
)


ProgressCallback = Callable[[str, float, str], None]


async def render_episode(
    db: Session,
    episode_id: str,
    *,
    backend: str = "hailuo",
    enable_tts: bool = True,
    enable_bgm: bool = True,
    enable_subtitle: bool = True,
    on_progress: Optional[ProgressCallback] = None,
) -> dict:
    """Render all shots in an episode and compose the final video."""
    report = lambda s, p, m="": (on_progress or (lambda *_: None))(s, p, m)  # noqa: E731

    ep: Episode | None = db.get(Episode, episode_id)
    if not ep:
        raise PipelineError(f"episode not found: {episode_id}")
    shots: list[Shot] = sorted(ep.shots, key=lambda s: s.index)
    if not shots:
        raise PipelineError("episode has no shots")

    workdir = settings.OUTPUT_DIR / ep.project_id / f"ep_{ep.id}"
    workdir.mkdir(parents=True, exist_ok=True)

    # Shots -> videos
    report("video", 0.05, "generating shots")
    adapter = get_video_adapter(backend)
    shot_videos: list[str] = []
    for i, shot in enumerate(shots):
        dst = workdir / "shots" / f"shot_{i:03d}.mp4"
        dst.parent.mkdir(parents=True, exist_ok=True)
        if shot.video_url and Path(shot.video_url).exists():
            shot_videos.append(shot.video_url)
            continue
        if not shot.image_url:
            raise PipelineError(f"shot {shot.id} has no image_url")

        req = VideoGenRequest(
            prompt=shot.prompt or "anime scene",
            image_path=shot.image_url,
            duration=shot.duration or 4.0,
        )
        try:
            res = await adapter.generate(req)
            if res.status == "success" and res.video_url:
                await adapter.download(res, str(dst))
            else:
                raise PipelineError(res.message or "generation failed")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"shot {i} fallback to still image: {e}")
            image_to_video(shot.image_url, shot.duration or 4.0, str(dst))
        shot.video_url = str(dst)
        shot.status = "done"
        db.add(shot)
        shot_videos.append(str(dst))
        report("video", 0.05 + 0.6 * (i + 1) / len(shots), f"{i+1}/{len(shots)}")
    db.commit()

    # TTS
    if enable_tts:
        report("tts", 0.68, "synthesizing voice")
        tts = get_tts_adapter()
        for i, shot in enumerate(shots):
            if not shot.dialogue:
                continue
            if shot.audio_url and Path(shot.audio_url).exists():
                continue
            try:
                out = workdir / "tts" / f"shot_{i:03d}.mp3"
                await tts.synthesize(
                    shot.dialogue, emotion=shot.emotion, output_path=str(out),
                )
                shot.audio_url = str(out)
                db.add(shot)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"tts failed shot {i}: {e}")
        db.commit()
        # mux
        muxed: list[str] = []
        for i, (shot, vid) in enumerate(zip(shots, shot_videos)):
            if shot.audio_url and Path(shot.audio_url).exists():
                out = workdir / "shots_av" / f"shot_{i:03d}.mp4"
                out.parent.mkdir(parents=True, exist_ok=True)
                try:
                    mux_audio(vid, shot.audio_url, str(out), replace=True)
                    muxed.append(str(out))
                    continue
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"mux failed shot {i}: {e}")
            muxed.append(vid)
        shot_videos = muxed

    # Concat
    report("concat", 0.80, "concatenating")
    concat_out = workdir / "concat.mp4"
    concat_videos(shot_videos, str(concat_out))

    final = concat_out
    # BGM
    if enable_bgm:
        report("bgm", 0.88, "adding bgm")
        emo = dominant_emotion([{"emotion": s.emotion} for s in shots])
        bgm = pick_bgm(emo)
        if bgm:
            import subprocess
            try:
                tmp = workdir / "concat_audio.m4a"
                subprocess.run(["ffmpeg", "-y", "-i", str(concat_out), "-vn", "-c:a", "aac", str(tmp)],
                               capture_output=True)
                mixed = workdir / "mixed.m4a"
                mix_audio([str(tmp), bgm], str(mixed), volumes=[1.0, 0.25])
                bgm_out = workdir / "with_bgm.mp4"
                mux_audio(str(concat_out), str(mixed), str(bgm_out), replace=True)
                final = bgm_out
            except Exception as e:  # noqa: BLE001
                logger.warning(f"bgm failed: {e}")

    # Subtitle
    if enable_subtitle:
        report("subtitle", 0.95, "burning subtitles")
        entries = shots_to_srt_entries([{
            "duration": s.duration, "dialogue": s.dialogue, "speaker": s.speaker,
        } for s in shots])
        if entries:
            srt = workdir / "subtitle.srt"
            build_srt(entries, str(srt))
            burned = workdir / "final.mp4"
            try:
                burn_subtitle(str(final), str(srt), str(burned))
                final = burned
            except Exception as e:  # noqa: BLE001
                logger.warning(f"burn subtitle failed: {e}")

    ep.video_url = str(final)
    ep.duration = probe_duration(final)
    ep.status = "done"
    db.add(ep)
    db.commit()
    report("done", 1.0, "done")
    return {"video_path": str(final), "duration": ep.duration}
