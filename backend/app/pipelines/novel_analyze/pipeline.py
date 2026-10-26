"""Novel Deep Analysis pipeline (NO video generation).

Flow: Read text → clean/normalize → smart chunk → LLM analyze (per chunk, carrying
character bank) → merge → enrich timecode.

Output JSON **与漫画拆解一致**，便于前端复用 AnalysisReport 组件：
  - title / genre / summary / tone / bgm_hint
  - characters (appearance / costume / personality / voice_tone)
  - script.acts (起承转合)
  - storyboard[] (timecode / shot_type / camera_motion / environment /
                  characters_in_shot / dialogue / text_prompt / image_prompt /
                  video_prompt)
  - notes
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Callable, Optional

from ...adapters import get_llm_adapter
from ...core.config import settings
from ...core.exceptions import PipelineError
from ...core.logger import logger


ProgressCallback = Callable[[str, float, str], None]
"""(stage, progress 0-1, message)"""


# 单次送 LLM 的小说文本上限（字符数）。太大会超模型上下文，太小 LLM 看不到
# 完整情节；取 2500 字平衡成本/效果，远离主流模型 32K/128K 上限。
DEFAULT_CHUNK_SIZE = 2500
# 相邻块之间的重叠字符数，防止把一段剧情从中切断
CHUNK_OVERLAP = 200


class NovelAnalyzePipeline:
    """Pure-text novel analysis: read → chunk → LLM analyze → merge."""

    def __init__(
        self,
        novel_text: str,
        project_id: str,
        *,
        title_hint: Optional[str] = None,
        style: Optional[str] = None,
        extra_hint: Optional[str] = None,
        shot_duration: float = 4.0,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        on_progress: Optional[ProgressCallback] = None,
    ):
        self.novel_text = novel_text or ""
        self.project_id = project_id
        self.title_hint = title_hint
        self.style = style
        self.extra_hint = extra_hint
        self.shot_duration = shot_duration
        self.chunk_size = max(500, int(chunk_size))
        self.on_progress = on_progress or (lambda s, p, m: None)

        self.run_id = uuid.uuid4().hex[:12]
        self.workdir = settings.OUTPUT_DIR_PATH / project_id / f"novel_{self.run_id}"
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _p(self, stage: str, progress: float, msg: str = "") -> None:
        logger.info(f"[novel-analyze] {stage} {progress:.0%} {msg}")
        try:
            self.on_progress(stage, progress, msg)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"progress callback error: {e}")

    async def run(self) -> dict:
        """Execute all stages, return a structured analysis report."""
        # ====== 1. 清洗 & 规整 ======
        self._p("clean", 0.03, "读取/清洗小说文本")
        text = self._clean_text(self.novel_text)
        if len(text) < 50:
            raise PipelineError(
                f"小说文本过短（len={len(text)}），无法进行拆解分析（最少 50 字）"
            )

        # 持久化原文（便于回溯）
        (self.workdir / "novel.txt").write_text(text, encoding="utf-8")
        self._p("clean", 0.08, f"文本长度 {len(text)} 字")

        # ====== 2. 智能分块 ======
        self._p("chunk", 0.12, "智能分块（按段落/句号切，保留上下文重叠）")
        chunks = self._smart_chunk(text, self.chunk_size, CHUNK_OVERLAP)
        if not chunks:
            raise PipelineError("切块失败：没有生成任何块")
        self._p("chunk", 0.18, f"共 {len(chunks)} 块")

        # ====== 3. 逐块送 LLM 分析 ======
        llm = get_llm_adapter()
        merged_characters: list[dict] = []
        merged_shots: list[dict] = []
        last_result: dict = {}
        shot_cursor = 0  # 分镜全局索引游标

        base = 0.20
        per_chunk_frac = 0.65 / max(1, len(chunks))

        for ci, chunk_text in enumerate(chunks):
            is_last = ci == len(chunks) - 1
            prog = base + per_chunk_frac * ci
            self._p(
                "analyze",
                prog,
                f"LLM 深度剖析分块 {ci + 1}/{len(chunks)}（含 {len(merged_characters)} 个已识别角色）",
            )

            try:
                part = await llm.novel_to_analysis(
                    chunk_text,
                    style=self.style,
                    extra_hint=self.extra_hint,
                    start_index=shot_cursor,
                    prior_characters=self._compact_characters(merged_characters),
                    is_last_chunk=is_last,
                )
            except Exception as e:  # noqa: BLE001
                logger.exception(f"LLM analysis failed for chunk {ci}")
                if ci == 0:
                    # 第一块就挂：返回最小兜底报告，让用户至少能看到提示
                    return {
                        "title": self.title_hint or "",
                        "summary": "",
                        "characters": [],
                        "script": {"acts": []},
                        "storyboard": [],
                        "notes": "",
                        "_fallback": True,
                        "_fallback_reason": f"{type(e).__name__}: {e}",
                        "_meta": self._build_meta(len(text), 0, 0),
                    }
                # 中/后续块挂了：用已累积的结果继续
                logger.warning(
                    f"[novel-analyze] chunk {ci} failed, 停止后续块，使用已累积结果"
                )
                break

            # 合并角色（按 name 去重，后出现的若有缺失字段则补齐）
            for c in part.get("characters") or []:
                merged_characters = self._merge_character(merged_characters, c)

            # 收 shots（LLM 应该已按 start_index 排好，这里兜底 reindex）
            part_shots = part.get("storyboard") or []
            for s in part_shots:
                s["index"] = shot_cursor
                shot_cursor += 1
                merged_shots.append(s)

            last_result = part

        # ====== 4. 规整 storyboard：补 timecode & 兜底字段 ======
        self._p("enrich", 0.86, "补时间码 / 兜底字段")
        merged_shots = self._enrich_storyboard(merged_shots)

        # ====== 5. 组装最终 report ======
        # title / summary / script.acts / notes 取最后一块（is_last_chunk=True）的产出；
        # 若后续块挂了，退回第一块 last_result
        report: dict = {
            "title": last_result.get("title") or self.title_hint or "",
            "genre": last_result.get("genre") or "",
            "summary": last_result.get("summary") or "",
            "tone": last_result.get("tone") or "",
            "bgm_hint": last_result.get("bgm_hint") or "",
            "characters": merged_characters,
            "script": last_result.get("script") or {"acts": []},
            "storyboard": merged_shots,
            "notes": last_result.get("notes") or "",
        }

        if not merged_shots:
            logger.warning(
                f"[novel-analyze] 空分镜（chunks={len(chunks)}, chars={len(merged_characters)}）"
            )
            report["_fallback"] = True
            report["_fallback_reason"] = "LLM 未产出任何分镜"

        # ====== 6. 持久化 ======
        self._p("persist", 0.95, "保存剖析报告")
        report_path = self.workdir / "analysis.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        report["_meta"] = self._build_meta(len(text), len(chunks), len(merged_shots))
        report["_meta"]["workdir"] = str(self.workdir)
        report["_meta"]["report_path"] = str(report_path)

        # 相对化：便于前端通过 /static/outputs/... 访问
        try:
            abs_output = Path(settings.OUTPUT_DIR).resolve()
            report["_meta"]["report_url"] = (
                f"/static/outputs/{report_path.resolve().relative_to(abs_output).as_posix()}"
            )
        except Exception:  # noqa: BLE001
            pass

        self._p("done", 1.0, "完成")
        return report

    # -------------------- helpers --------------------
    @staticmethod
    def _clean_text(text: str) -> str:
        """去除 BOM / \\r / 多余空白，但保留段落结构（空行）。"""
        if not text:
            return ""
        t = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
        # 连续 3+ 空行压缩为 2 行
        t = re.sub(r"\n{3,}", "\n\n", t)
        # 行首/行尾空白
        t = "\n".join(line.rstrip() for line in t.split("\n"))
        return t.strip()

    @staticmethod
    def _smart_chunk(text: str, chunk_size: int, overlap: int) -> list[str]:
        """按段落/句号智能分块，保证块内 ≤ chunk_size，相邻块有 overlap 重叠。

        策略：
          1) 先按段落（空行）切；
          2) 累积到接近 chunk_size 时切断；
          3) 块与块之间保留 overlap 字符的尾部作为下一块前缀。
        """
        if len(text) <= chunk_size:
            return [text]

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[str] = []
        buf: list[str] = []
        buf_len = 0

        def _flush() -> None:
            nonlocal buf, buf_len
            if buf:
                chunks.append("\n\n".join(buf).strip())
                buf = []
                buf_len = 0

        for para in paragraphs:
            # 如果单个段落就超过 chunk_size，按句号硬切
            if len(para) > chunk_size:
                _flush()
                for sub in NovelAnalyzePipeline._split_long_paragraph(para, chunk_size):
                    chunks.append(sub)
                continue

            if buf_len + len(para) + 2 > chunk_size:
                _flush()
            buf.append(para)
            buf_len += len(para) + 2

        _flush()

        # 加 overlap：从前一块尾部取 overlap 字符贴到下一块开头
        if overlap > 0 and len(chunks) > 1:
            out: list[str] = [chunks[0]]
            for i in range(1, len(chunks)):
                prev_tail = chunks[i - 1][-overlap:]
                out.append(f"（上文片段：{prev_tail}）\n\n{chunks[i]}")
            chunks = out

        return chunks

    @staticmethod
    def _split_long_paragraph(para: str, max_len: int) -> list[str]:
        """超长段落按中文句号/英文句点/问号/感叹号/分号切。"""
        sentences = re.split(r"(?<=[。！？!?；;])\s*", para)
        out: list[str] = []
        buf = ""
        for s in sentences:
            if not s:
                continue
            if len(buf) + len(s) > max_len and buf:
                out.append(buf)
                buf = s
            else:
                buf += s
        if buf:
            out.append(buf)
        return out

    @staticmethod
    def _compact_characters(chars: list[dict]) -> list[dict]:
        """给 LLM 的 prior_characters 只保留核心字段，省 token。"""
        return [
            {
                "name": c.get("name"),
                "role": c.get("role"),
                "appearance": c.get("appearance", "")[:60],
                "costume": c.get("costume", "")[:60],
            }
            for c in chars
            if c.get("name")
        ]

    @staticmethod
    def _merge_character(bank: list[dict], new_c: dict) -> list[dict]:
        """按 name 合并角色：已存在的补齐缺失字段，新的直接追加。"""
        name = (new_c.get("name") or "").strip()
        if not name:
            return bank
        for existing in bank:
            if (existing.get("name") or "").strip() == name:
                for k, v in new_c.items():
                    if v and not existing.get(k):
                        existing[k] = v
                return bank
        bank.append(dict(new_c))
        return bank

    def _enrich_storyboard(self, shots: list[dict]) -> list[dict]:
        """补 timecode / duration / 空字段兜底。"""
        cursor = 0.0
        for i, shot in enumerate(shots):
            shot["index"] = i
            try:
                dur = float(shot.get("duration") or self.shot_duration)
            except (TypeError, ValueError):
                dur = self.shot_duration
            shot["duration"] = dur
            shot["timecode"] = f"{self._fmt_tc(cursor)}~{self._fmt_tc(cursor + dur)}"
            cursor += dur

            # 兜底字段，防止前端渲染空指针
            shot.setdefault("shot_type", "中景")
            shot.setdefault("camera_motion", "固定")
            shot.setdefault("characters_in_shot", [])
            env = shot.setdefault("environment", {})
            env.setdefault("location", "未指明")
            env.setdefault("time_of_day", "白天")
            env.setdefault("weather", "未知")
            env.setdefault("lighting", "自然光")
        return shots

    @staticmethod
    def _fmt_tc(sec: float) -> str:
        total = int(round(sec))
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _build_meta(self, text_len: int, chunk_count: int, shot_count: int) -> dict:
        return {
            "project_id": self.project_id,
            "run_id": self.run_id,
            "text_length": text_len,
            "chunk_count": chunk_count,
            "shot_count": shot_count,
            "source_type": "novel",
        }
