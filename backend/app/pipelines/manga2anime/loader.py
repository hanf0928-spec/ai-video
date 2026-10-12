
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
    """Render each page of a PDF to PNG.

    Prefer PyMuPDF (pure-Python wheel, no system dependency).
    Fallback to pdf2image (requires poppler-utils in PATH) for compatibility.
    """
    # ---------- Preferred: PyMuPDF (fitz) ----------
    try:
        import fitz  # PyMuPDF
    except Exception:  # noqa: BLE001
        fitz = None

    if fitz is not None:
        try:
            logger.info(f"[pipeline] rendering PDF {pdf.name} via PyMuPDF dpi={dpi}")
            doc = fitz.open(str(pdf))
            zoom = dpi / 72.0  # fitz default is 72 dpi
            mat = fitz.Matrix(zoom, zoom)
            out: list[Path] = []
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=mat, alpha=False)
                dst = work / f"page_{i:04d}.png"
                pix.save(str(dst))
                out.append(dst)
            doc.close()
            return out
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[pipeline] PyMuPDF failed, fallback to pdf2image: {e}")

    # ---------- Fallback: pdf2image (needs poppler) ----------
    try:
        from pdf2image import convert_from_path
    except Exception as e:  # noqa: BLE001
        raise PipelineError(
            "PDF rendering unavailable: PyMuPDF import failed and pdf2image not installed. "
            "Install either `pip install PyMuPDF` or `apt/yum install poppler-utils`."
        ) from e

    logger.info(f"[pipeline] rendering PDF {pdf.name} via pdf2image dpi={dpi}")
    try:
        images = convert_from_path(str(pdf), dpi=dpi)
    except Exception as e:  # noqa: BLE001
        raise PipelineError(
            f"pdf2image failed (missing poppler? run `yum install -y poppler-utils` on CentOS/OpenCloudOS, "
            f"or `apt install -y poppler-utils` on Debian/Ubuntu). Original error: {e}"
        ) from e
    out = []
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
