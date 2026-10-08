
"""Stage 2: Panel detection.

Primary: YOLO model fine-tuned for manga panels.
Fallback: classical CV via contour / connected components on page frames.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import cv2
import numpy as np
from PIL import Image

from ...core.logger import logger


@dataclass
class Panel:
    bbox: tuple[int, int, int, int]   # x1,y1,x2,y2
    order: int
    image_path: str


def detect_panels(page_image: str | Path, output_dir: str | Path, *, page_index: int = 0) -> List[Panel]:
    """Detect manga panels on a single page.

    First tries ultralytics YOLO (if a `panel_yolov8.pt` is placed under
    data/models/). Falls back to a classical CV method.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    panels = _try_yolo(page_image, out, page_index)
    if panels:
        return panels
    return _classical_panel_detect(page_image, out, page_index)


def _try_yolo(page_image: str | Path, out: Path, page_index: int) -> List[Panel]:
    try:
        from ultralytics import YOLO
    except Exception:
        return []
    model_path = Path(__file__).resolve().parents[4] / "data" / "models" / "panel_yolov8.pt"
    if not model_path.exists():
        return []
    try:
        model = YOLO(str(model_path))
        res = model(str(page_image), verbose=False)[0]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"YOLO panel detect failed: {e}")
        return []

    img = cv2.imread(str(page_image))
    panels: list[Panel] = []
    boxes = res.boxes.xyxy.cpu().numpy() if res.boxes is not None else []
    # Sort by reading order (top-to-bottom, then right-to-left for Japanese; here L2R by default)
    sorted_boxes = sorted(boxes, key=lambda b: (b[1] // 50, b[0]))
    for i, b in enumerate(sorted_boxes):
        x1, y1, x2, y2 = map(int, b[:4])
        crop = img[y1:y2, x1:x2]
        dst = out / f"page{page_index:04d}_panel{i:03d}.png"
        cv2.imwrite(str(dst), crop)
        panels.append(Panel(bbox=(x1, y1, x2, y2), order=i, image_path=str(dst)))
    logger.info(f"[panel] YOLO found {len(panels)} panels on page {page_index}")
    return panels


def _classical_panel_detect(page_image: str | Path, out: Path, page_index: int) -> List[Panel]:
    """Edge + contour based panel detection. Works best on clean black-bordered manga."""
    img = cv2.imread(str(page_image))
    if img is None:
        return []
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY)
    # Invert so panels (dark content) become white
    inv = cv2.bitwise_not(bw)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(inv, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area = (H * W) * 0.02
    rects: list[tuple[int, int, int, int]] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < min_area:
            continue
        if w < 50 or h < 50:
            continue
        rects.append((x, y, x + w, y + h))

    if not rects:
        # Treat the whole page as a single panel
        dst = out / f"page{page_index:04d}_panel000.png"
        cv2.imwrite(str(dst), img)
        return [Panel(bbox=(0, 0, W, H), order=0, image_path=str(dst))]

    # Reading order: top-to-bottom bands, then left-to-right within a band
    rects.sort(key=lambda r: (r[1] // 100, r[0]))

    panels: list[Panel] = []
    for i, (x1, y1, x2, y2) in enumerate(rects):
        crop = img[y1:y2, x1:x2]
        dst = out / f"page{page_index:04d}_panel{i:03d}.png"
        cv2.imwrite(str(dst), crop)
        panels.append(Panel(bbox=(x1, y1, x2, y2), order=i, image_path=str(dst)))

    logger.info(f"[panel] classical detected {len(panels)} panels on page {page_index}")
    return panels
