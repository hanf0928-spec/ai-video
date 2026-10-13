"""Manga Deep Analysis pipeline (NO video generation).

Flow: Load pages → Detect panels → OCR → Build character bank → LLM deep analysis.
Produces a structured JSON report with:
  - characters (appearance / costume / personality / voice_tone)
  - script (起承转合段落)
  - storyboard (timecode / shot_type / camera / environment / characters_in_shot / dialogue / image_prompt)
  - notes
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Callable, Optional

from ...adapters import get_llm_adapter
from ...core.config import settings
from ...core.exceptions import PipelineError
from ...core.logger import logger

# 复用 manga2anime 的 preprocessing 组件（避免重复实现）
from ..manga2anime.loader import load_pages
from ..manga2anime.panel_detect import detect_panels
from ..manga2anime.ocr import ocr_panel, group_bubbles
from ..manga2anime.character import build_character_bank


ProgressCallback = Callable[[str, float, str], None]
"""(stage, progress 0-1, message)"""


class MangaAnalyzePipeline:
    """Pure-text manga analysis: load → panel → ocr → character → LLM analysis."""

    def __init__(
        self,
        upload_path: str | Path,
        project_id: str,
        *,
        style: Optional[str] = None,
        extra_hint: Optional[str] = None,
        shot_duration: float = 4.0,
        on_progress: Optional[ProgressCallback] = None,
    ):
        self.upload_path = Path(upload_path)
        self.project_id = project_id
        self.style = style
        self.extra_hint = extra_hint
        self.shot_duration = shot_duration
        self.on_progress = on_progress or (lambda s, p, m: None)

        self.run_id = uuid.uuid4().hex[:12]
        self.workdir = settings.OUTPUT_DIR_PATH / project_id / f"analyze_{self.run_id}"
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _p(self, stage: str, progress: float, msg: str = "") -> None:
        logger.info(f"[analyze] {stage} {progress:.0%} {msg}")
        try:
            self.on_progress(stage, progress, msg)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"progress callback error: {e}")

    async def run(self) -> dict:
        """Execute all stages, return a structured analysis report."""
        # ====== 1. Load pages ======
        self._p("load", 0.05, "读取漫画文件")
        page_dir = self.workdir / "pages"
        pages = load_pages(self.upload_path, page_dir)
        if not pages:
            raise PipelineError("no pages loaded")
        self._p("load", 0.15, f"加载 {len(pages)} 页")

        # ====== 2. Panel detection ======
        self._p("panel", 0.18, "分格检测")
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
            self._p("panel", 0.18 + 0.12 * (i + 1) / len(pages), f"第 {i+1}/{len(pages)} 页")
        if not panels_data:
            raise PipelineError("no panels detected")
        self._p("panel", 0.3, f"共检测到 {len(panels_data)} 格")

        # ====== 3. OCR ======
        self._p("ocr", 0.33, "OCR 对白识别")
        for i, p in enumerate(panels_data):
            bubbles = group_bubbles(ocr_panel(p["image_path"]))
            p["bubbles"] = [{"bbox": list(b.bbox), "text": b.text} for b in bubbles]
            p["ocr_text"] = " ".join(b.text for b in bubbles)
            if (i + 1) % 5 == 0:
                self._p("ocr", 0.33 + 0.12 * (i + 1) / len(panels_data), f"{i+1}/{len(panels_data)}")
        self._p("ocr", 0.45, "OCR 完成")

        # ====== 4. Character consistency ======
        self._p("character", 0.48, "角色一致性识别")
        char_dir = self.workdir / "characters"
        characters_raw = build_character_bank(panels_data, char_dir)
        self._p("character", 0.55, f"识别出 {len(characters_raw)} 个角色聚类")

        # ====== 5. LLM 深度剖析 ======
        self._p("analyze", 0.6, "LLM 深度剖析（角色/剧本/分镜）")
        llm = get_llm_adapter()

        # 为 LLM 构造轻量 input（避免把 bbox 太多字段塞进去）
        panels_payload = [
            {
                "index": p["order"],
                "page": p["page"],
                "ocr_text": p.get("ocr_text") or "",
                "has_dialogue": bool((p.get("ocr_text") or "").strip()),
            }
            for p in panels_data
        ]

        try:
            report = await llm.panels_to_analysis(
                panels_payload,
                style=self.style,
                extra_hint=self.extra_hint,
            )
        except Exception as e:  # noqa: BLE001
            # 深度剖析失败不直接 fail 整个任务，而是降级为简版 storyboard，
            # 让用户至少能拿到基础分镜列表，并在报告里明确标注原因。
            logger.exception("LLM analysis failed, fallback to minimal storyboard")
            report = {
                "title": "",
                "summary": "",
                "characters": [],
                "script": {"acts": []},
                "storyboard": [],
                "notes": "",
                "_fallback": True,
                "_fallback_reason": f"{type(e).__name__}: {e}",
            }

        storyboard = report.get("storyboard") or []
        if not storyboard:
            logger.warning(
                f"[analyze] LLM 返回空 storyboard（keys={list(report.keys())}），"
                f"降级为按 panels 自动生成简版 storyboard"
            )
            report["storyboard"] = self._fallback_storyboard(panels_data)
            report.setdefault("_fallback", True)

        # 规整 storyboard：补时间码、关联 panel 图片 URL
        report["storyboard"] = self._enrich_storyboard(report["storyboard"], panels_data)

        self._p("analyze", 0.9, f"生成 {len(report['storyboard'])} 条分镜说明")

        # ====== 6. 持久化报告 ======
        self._p("persist", 0.95, "保存剖析报告")
        report_path = self.workdir / "analysis.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 为报告补一个概要段
        report["_meta"] = {
            "project_id": self.project_id,
            "run_id": self.run_id,
            "page_count": len(pages),
            "panel_count": len(panels_data),
            "character_cluster_count": len(characters_raw),
            "workdir": str(self.workdir),
            "report_path": str(report_path),
        }

        # 相对化：便于前端通过 /static/outputs/... 访问 panel 图片
        try:
            abs_output = Path(settings.OUTPUT_DIR).resolve()
            report["_meta"]["report_url"] = (
                f"/static/outputs/{report_path.resolve().relative_to(abs_output).as_posix()}"
            )
        except Exception:  # noqa: BLE001
            pass

        self._p("done", 1.0, "完成")
        return report

    def _enrich_storyboard(self, storyboard: list[dict], panels_data: list[dict]) -> list[dict]:
        """为每个 shot 补时间码 + panel image URL（便于前端展示）."""
        abs_output = Path(settings.OUTPUT_DIR).resolve()
        cursor = 0.0
        for i, shot in enumerate(storyboard):
            # 兼容 LLM 没给 duration 的情况
            try:
                dur = float(shot.get("duration") or self.shot_duration)
            except (TypeError, ValueError):
                dur = self.shot_duration
            shot["duration"] = dur
            # 补时间码（LLM 自己给的格式可能五花八门，这里统一覆盖）
            shot["timecode"] = f"{self._fmt_tc(cursor)}~{self._fmt_tc(cursor + dur)}"
            cursor += dur

            # 关联 panel 图片 URL（通过 panel_order / index 对齐）
            po = shot.get("panel_order")
            if po is None:
                po = shot.get("index", i)
            try:
                po_i = int(po)
            except (TypeError, ValueError):
                po_i = i
            if 0 <= po_i < len(panels_data):
                img_path = panels_data[po_i].get("image_path")
                if img_path:
                    try:
                        rel = Path(img_path).resolve().relative_to(abs_output).as_posix()
                        shot["panel_image_url"] = f"/static/outputs/{rel}"
                    except Exception:  # noqa: BLE001
                        shot["panel_image_url"] = ""
        return storyboard

    @staticmethod
    def _fmt_tc(sec: float) -> str:
        total = int(round(sec))
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _fallback_storyboard(self, panels_data: list[dict]) -> list[dict]:
        """LLM 挂掉时的最小兜底，保证前端有东西看。"""
        return [
            {
                "index": i,
                "page": p["page"],
                "panel_order": p["order"],
                "duration": self.shot_duration,
                "shot_type": "中景",
                "camera_motion": "固定",
                "environment": {
                    "location": "未知",
                    "time_of_day": "白天",
                    "weather": "未知",
                    "lighting": "自然光",
                    "details": "（LLM 未响应，无法剖析环境细节）",
                },
                "characters_in_shot": [],
                "dialogue": p.get("ocr_text") or "",
                "speaker": "",
                "sfx": "",
                "image_prompt": "anime manga panel, cinematic composition",
                "video_prompt": "subtle motion, cinematic",
            }
            for i, p in enumerate(panels_data)
        ]
