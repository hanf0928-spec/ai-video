
"""Stage 1: Load manga files (PDF / long-strip / multi-image) into page images."""
from __future__ import annotations

from pathlib import Path
from typing import List

from PIL import Image

from ...core.config import settings
from ...core.exceptions import PipelineError
from ...core.logger import logger


SUPPORTED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def load_pages(file_path: str | Path, work_dir: str | Path) -> List[Path]:
    """Convert the uploaded file into a list of page image paths.

    - PDF -> pdf2image renders each page
    - Image -> optional long-strip auto-split
    - Directory / ZIP -> list images in order
    """
    p = Path(file_path)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    if not p.exists():
        raise PipelineError(f"file not found: {p}")

    suffix = p.suffix.lower()

    if suffix == ".pdf":
        return _pdf_to_images(p, work)
    if suffix in SUPPORTED_IMAGE:
        return _maybe_split_longstrip(p, work)
    if p.is_dir():
        return sorted([f for f in p.iterdir() if f.suffix.lower() in SUPPORTED_IMAGE])
    raise PipelineError(f"unsupported file type: {suffix}")


def _pdf_to_images(pdf: Path, work: Path, *, dpi: int = 200) -> List[Path]:
    try:
        from pdf2image import convert_from_path
    except Exception as e:  # noqa: BLE001
        raise PipelineError(f"pdf2image not available: {e}") from e

    logger.info(f"[pipeline] rendering PDF {pdf.name} dpi={dpi}")
    images = convert_from_path(str(pdf), dpi=dpi)
    out: list[Path] = []
    for i, im in enumerate(images):
        dst = work / f"page_{i:04d}.png"
        im.save(dst, "PNG")
        out.append(dst)
    return out


def _maybe_split_longstrip(img_path: Path, work: Path, *, max_h: int = 2400) -> List[Path]:
    """If the image is unusually tall (e.g. a webtoon strip), split it into chunks."""
    im = Image.open(img_path).convert("RGB")
    w, h = im.size
    if h <= max_h * 1.3:
        dst = work / f"page_0000{img_path.suffix}"
        im.save(dst)
        return [dst]
    out: list[Path] = []
    i = 0
    y = 0
    while y < h:
        y2 = min(y + max_h, h)
        chunk = im.crop((0, y, w, y2))
        dst = work / f"page_{i:04d}.png"
        chunk.save(dst, "PNG")
        out.append(dst)
        y = y2
        i += 1
    logger.info(f"[pipeline] split long-strip {img_path.name} -> {len(out)} chunks")
    return out
