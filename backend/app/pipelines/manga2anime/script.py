
"""Stage 5: Storyboard script generation via LLM from panels data."""
from __future__ import annotations

from typing import List

from ...adapters import LLMAdapter, get_llm_adapter
from ...core.logger import logger


async def panels_to_storyboard(panels: list[dict], *, style: str | None = None) -> dict:
    """Call LLM to turn panel OCR + bbox data into a structured storyboard.

    Each panel dict should include:
      - order
      - ocr_text / bubbles
      - character_ids (optional)
    """
    llm: LLMAdapter = get_llm_adapter()
    simplified = [
        {
            "order": p.get("order", 0),
            "page": p.get("page", 0),
            "text": p.get("ocr_text") or " ".join(b.get("text", "") for b in p.get("bubbles", [])),
            "characters": p.get("character_ids", []),
        }
        for p in panels
    ]
    logger.info(f"[script] generating storyboard from {len(simplified)} panels")
    result = await llm.panels_to_script(simplified, style=style)
    return result
