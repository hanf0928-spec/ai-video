
"""OCR node for manga panels."""
from __future__ import annotations

from ..utils import tensor_to_pil


CATEGORY = "AIManga/Analyze"


class MangaOCRNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "lang": (["ch", "en", "ja"], {"default": "ch"}),
                "engine": (["paddleocr", "easyocr"], {"default": "paddleocr"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "run"
    CATEGORY = CATEGORY

    _cache: dict = {}

    def _get_reader(self, engine: str, lang: str):
        key = f"{engine}:{lang}"
        if key in self._cache:
            return self._cache[key]
        if engine == "paddleocr":
            from paddleocr import PaddleOCR
            reader = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        else:
            import easyocr
            langs = ["ch_sim", "en"] if lang == "ch" else [lang]
            reader = easyocr.Reader(langs, gpu=False)
        self._cache[key] = reader
        return reader

    def run(self, image, lang: str, engine: str):
        pil = tensor_to_pil(image)
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            pil.save(path)
            reader = self._get_reader(engine, lang)
            if engine == "paddleocr":
                res = reader.ocr(path, cls=True)
                if not res or not res[0]:
                    return ("",)
                text = " ".join(line[1][0] for line in res[0] if line and line[1])
            else:
                items = reader.readtext(path)
                text = " ".join(t for _, t, _ in items)
            return (text,)
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass
