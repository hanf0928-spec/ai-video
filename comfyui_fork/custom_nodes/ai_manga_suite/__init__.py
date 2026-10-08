
"""AI Manga Suite - ComfyUI custom nodes for the manga-to-anime workflow.

Nodes:
- MangaPanelLoader   : Load manga file, output panel images.
- MangaOCRNode       : Run OCR on an image, output recognized text.
- HailuoI2VNode      : Image-to-video via Hailuo 03 cloud API.
- SeedanceI2VNode    : Image-to-video via Seedance 2 cloud API.
- StoryboardLLMNode  : LLM-based storyboard generation.

Place this folder under ComfyUI/custom_nodes/ to enable.
"""

from .nodes.manga_loader import MangaPanelLoader
from .nodes.ocr_node import MangaOCRNode
from .nodes.hailuo_node import HailuoI2VNode
from .nodes.seedance_node import SeedanceI2VNode
from .nodes.storyboard_node import StoryboardLLMNode


NODE_CLASS_MAPPINGS = {
    "MangaPanelLoader": MangaPanelLoader,
    "MangaOCRNode": MangaOCRNode,
    "HailuoI2VNode": HailuoI2VNode,
    "SeedanceI2VNode": SeedanceI2VNode,
    "StoryboardLLMNode": StoryboardLLMNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MangaPanelLoader": "🎞 Manga Panel Loader",
    "MangaOCRNode": "📝 Manga OCR",
    "HailuoI2VNode": "🎥 Hailuo 03 (I2V)",
    "SeedanceI2VNode": "🎬 Seedance 2 (I2V)",
    "StoryboardLLMNode": "🧠 Storyboard LLM",
}


__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
