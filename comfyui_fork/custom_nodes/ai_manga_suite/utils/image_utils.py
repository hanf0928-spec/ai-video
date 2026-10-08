
"""Shared helpers for custom nodes."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import torch
from PIL import Image


def pil_to_tensor(img: Image.Image) -> torch.Tensor:
    """Convert PIL image -> ComfyUI image tensor (1,H,W,3) float32 0..1."""
    img = img.convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def tensor_to_pil(t: torch.Tensor) -> Image.Image:
    """Convert ComfyUI tensor (1,H,W,3) back to PIL."""
    if t.ndim == 4:
        t = t[0]
    arr = (t.detach().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def tensor_to_png_bytes(t: torch.Tensor) -> bytes:
    buf = io.BytesIO()
    tensor_to_pil(t).save(buf, format="PNG")
    return buf.getvalue()


def save_tensor_to_file(t: torch.Tensor, path: str | Path) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tensor_to_pil(t).save(p)
    return str(p)
