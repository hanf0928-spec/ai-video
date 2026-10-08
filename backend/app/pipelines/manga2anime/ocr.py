
"""Stage 3: OCR - extract dialogue bubbles' text from each panel."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ...core.config import settings
from ...core.logger import logger


@dataclass
class Bubble:
    bbox: tuple[int, int, int, int]
    text: str
    confidence: float = 0.0


_ocr_singleton = None


def _get_ocr():
    global _ocr_singleton
    if _ocr_singleton is not None:
        return _ocr_singleton
    provider = settings.OCR_PROVIDER
    try:
        if provider == "paddleocr":
            from paddleocr import PaddleOCR
            _ocr_singleton = PaddleOCR(use_angle_cls=True, lang=settings.OCR_LANG, show_log=False)
        elif provider == "easyocr":
            import easyocr
            lang = ["ch_sim", "en"] if settings.OCR_LANG.startswith("ch") else ["en"]
            _ocr_singleton = easyocr.Reader(lang, gpu=False)
        else:
            _ocr_singleton = None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"OCR init failed ({provider}): {e}")
        _ocr_singleton = None
    return _ocr_singleton


def ocr_panel(image_path: str | Path) -> List[Bubble]:
    """Run OCR on a single panel image. Returns list of Bubbles."""
    if not settings.ENABLE_OCR:
        return []
    ocr = _get_ocr()
    if ocr is None:
        return []

    bubbles: list[Bubble] = []
    try:
        if settings.OCR_PROVIDER == "paddleocr":
            result = ocr.ocr(str(image_path), cls=True)
            if not result or not result[0]:
                return []
            for line in result[0]:
                box, (text, conf) = line
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                bbox = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
                if text and text.strip():
                    bubbles.append(Bubble(bbox=bbox, text=text.strip(), confidence=float(conf)))
        elif settings.OCR_PROVIDER == "easyocr":
            for item in ocr.readtext(str(image_path)):
                box, text, conf = item
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                bbox = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
                if text and text.strip():
                    bubbles.append(Bubble(bbox=bbox, text=text.strip(), confidence=float(conf)))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"OCR failed on {image_path}: {e}")
        return []

    return bubbles


def group_bubbles(bubbles: List[Bubble]) -> List[Bubble]:
    """Merge horizontally/vertically adjacent OCR fragments into bubbles."""
    if not bubbles:
        return []
    # Simple merge by proximity (y gap < 15px and x overlap)
    sorted_b = sorted(bubbles, key=lambda b: (b.bbox[1], b.bbox[0]))
    merged: list[Bubble] = []
    for b in sorted_b:
        if not merged:
            merged.append(b)
            continue
        last = merged[-1]
        lx1, ly1, lx2, ly2 = last.bbox
        x1, y1, x2, y2 = b.bbox
        y_gap = y1 - ly2
        x_overlap = min(lx2, x2) - max(lx1, x1)
        if y_gap < 15 and x_overlap > 0:
            merged[-1] = Bubble(
                bbox=(min(lx1, x1), min(ly1, y1), max(lx2, x2), max(ly2, y2)),
                text=(last.text + " " + b.text).strip(),
                confidence=min(last.confidence, b.confidence),
            )
        else:
            merged.append(b)
    return merged
