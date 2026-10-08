
"""MangaPanelLoader node: load panels from a manga file."""
from __future__ import annotations

from pathlib import Path

import torch
from PIL import Image

from ..utils import pil_to_tensor


CATEGORY = "AIManga/Load"


class MangaPanelLoader:
    """Load manga pages/panels. Supports PDF / image / directory."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_path": ("STRING", {"default": "", "multiline": False}),
                "page_index": ("INT", {"default": 0, "min": 0, "max": 1000}),
            },
            "optional": {
                "panel_index": ("INT", {"default": -1, "min": -1, "max": 100,
                                        "tooltip": "-1 means return full page"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info")
    FUNCTION = "load"
    CATEGORY = CATEGORY

    def load(self, file_path: str, page_index: int, panel_index: int = -1):
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(file_path)

        if p.suffix.lower() == ".pdf":
            from pdf2image import convert_from_path
            pages = convert_from_path(str(p), dpi=200, first_page=page_index + 1, last_page=page_index + 1)
            img = pages[0] if pages else None
        else:
            img = Image.open(p)
        if img is None:
            raise RuntimeError("failed to load image")

        info = f"{p.name} page={page_index} size={img.size}"
        tensor = pil_to_tensor(img)
        return (tensor, info)
