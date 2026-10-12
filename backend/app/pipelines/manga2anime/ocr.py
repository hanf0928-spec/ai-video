
"""Stage 3: OCR - extract dialogue bubbles' text from each panel."""
from __future__ import annotations

import base64
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
        elif provider == "vlm":
            # 云端 VLM：无需本地模型。用 sentinel 标记已初始化即可。
            _ocr_singleton = "__vlm__"
        else:
            _ocr_singleton = None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"OCR init failed ({provider}): {e}")
        _ocr_singleton = None
    return _ocr_singleton


# ---------- VLM OCR ----------
def _detect_mime(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "webp": "image/webp",
        "bmp": "image/bmp", "gif": "image/gif",
    }.get(ext, "image/png")


def _image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size  # (w, h)
    except Exception:
        return (0, 0)


def _vlm_ocr(image_path: Path) -> List[Bubble]:
    """Run OCR via OpenAI-compatible Vision chat/completions (e.g. OpenRouter).

    Config is pulled from the `vlm_ocr` provider at call time so the user can
    update API key / model without restarting workers.
    """
    import httpx
    from ...services.config_service import get_config

    cfg = get_config("vlm_ocr")
    api_key = cfg.get("api_key") or ""
    base_url = (cfg.get("base_url") or "").rstrip("/")
    model = cfg.get("model") or "google/gemma-4-31b-it:free"
    prompt = cfg.get("prompt") or "Extract all text from this image. Output only the raw text."
    try:
        max_tokens = int(cfg.get("max_tokens") or 1024)
    except (TypeError, ValueError):
        max_tokens = 1024
    try:
        timeout = float(cfg.get("timeout") or 60)
    except (TypeError, ValueError):
        timeout = 60.0

    if not api_key or not base_url:
        logger.warning("[vlm_ocr] api_key / base_url 未配置，返回空结果")
        return []

    data = image_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    mime = _detect_mime(image_path)
    data_url = f"data:{mime};base64,{b64}"

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # OpenRouter 推荐带以下两个 header（可选但有益统计/优先级）
        "HTTP-Referer": "https://ai-manga.local",
        "X-Title": "AI Manga Studio",
    }

    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        if r.status_code != 200:
            logger.warning(f"[vlm_ocr] HTTP {r.status_code}: {r.text[:200]}")
            return []
        resp = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[vlm_ocr] request failed on {image_path.name}: {e}")
        return []

    try:
        text = (resp["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        logger.warning(f"[vlm_ocr] malformed response: {resp}")
        return []

    if not text:
        return []

    # VLM 不返回每行坐标。用整张图尺寸作为 bbox 占位，交给下游 group_bubbles 原样返回。
    w, h = _image_size(image_path)
    bbox = (0, 0, int(w), int(h))

    bubbles: list[Bubble] = []
    for line in text.splitlines():
        s = line.strip().strip("•- ").strip()
        if not s:
            continue
        # 过滤典型的 "无文字 / no text" 短句
        low = s.lower()
        if low in ("无", "无文字", "no text", "none", "n/a", "(无)", "(none)"):
            continue
        bubbles.append(Bubble(bbox=bbox, text=s, confidence=1.0))

    return bubbles


def ocr_panel(image_path: str | Path) -> List[Bubble]:
    """Run OCR on a single panel image. Returns list of Bubbles."""
    if not settings.ENABLE_OCR:
        return []
    ocr = _get_ocr()
    if ocr is None:
        return []

    p = Path(image_path)
    bubbles: list[Bubble] = []
    try:
        if settings.OCR_PROVIDER == "paddleocr":
            result = ocr.ocr(str(p), cls=True)
            if not result or not result[0]:
                return []
            for line in result[0]:
                box, (text, conf) = line
                xs = [pt[0] for pt in box]
                ys = [pt[1] for pt in box]
                bbox = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
                if text and text.strip():
                    bubbles.append(Bubble(bbox=bbox, text=text.strip(), confidence=float(conf)))
        elif settings.OCR_PROVIDER == "easyocr":
            for item in ocr.readtext(str(p)):
                box, text, conf = item
                xs = [pt[0] for pt in box]
                ys = [pt[1] for pt in box]
                bbox = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
                if text and text.strip():
                    bubbles.append(Bubble(bbox=bbox, text=text.strip(), confidence=float(conf)))
        elif settings.OCR_PROVIDER == "vlm":
            bubbles = _vlm_ocr(p)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"OCR failed on {p}: {e}")
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
