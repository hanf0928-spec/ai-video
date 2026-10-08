
# ComfyUI 自定义节点开发指南

本项目在 `comfyui_fork/custom_nodes/ai_manga_suite/` 下提供了 5 个 AI 漫剧专用节点。

## 📦 内置节点

| 分类 | 节点 | 作用 |
|------|------|------|
| AIManga/Load | `MangaPanelLoader` | 加载漫画 PDF / 图像 / 分格 |
| AIManga/Analyze | `MangaOCRNode` | PaddleOCR / EasyOCR 文字识别 |
| AIManga/Script | `StoryboardLLMNode` | LLM 生成分镜脚本 |
| AIManga/VideoGen | `HailuoI2VNode` | 海螺 03 图生视频 |
| AIManga/VideoGen | `SeedanceI2VNode` | Seedance 2 图生视频 |

## 🧩 新增节点模板

```python
# comfyui_fork/custom_nodes/ai_manga_suite/nodes/my_node.py

class MyNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {"default": "", "multiline": True}),
            },
            "optional": {
                "strength": ("FLOAT", {"default": 1.0, "min": 0, "max": 2, "step": 0.1}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info")
    FUNCTION = "run"
    CATEGORY = "AIManga/MySubcategory"

    def run(self, image, prompt, strength=1.0):
        # ... do things ...
        return (image, "ok")
```

然后在 `comfyui_fork/custom_nodes/ai_manga_suite/__init__.py` 的 `NODE_CLASS_MAPPINGS` 中注册：

```python
from .nodes.my_node import MyNode

NODE_CLASS_MAPPINGS["MyNode"] = MyNode
NODE_DISPLAY_NAME_MAPPINGS["MyNode"] = "✨ My Custom Node"
```

重启 ComfyUI 即可在节点菜单中看到。

## 🔗 跨项目依赖

节点可以直接 import 后端 adapters：

```python
from backend.app.adapters import HailuoAdapter, VideoGenRequest
```

前提：启动 ComfyUI 时设置 `PYTHONPATH` 包含项目根目录（`scripts/start_comfy.sh` 自动处理）。

## 📋 工作流 JSON

项目根目录 `workflows/` 下存放已经导出的工作流 JSON，供后端通过 `/api/comfy/run` 调用：

- `workflows/base/text2image.json`
- `workflows/base/image2video_hailuo.json`
- `workflows/base/image2video_seedance.json`
- `workflows/manga2anime/full_pipeline.json`

支持 `${var}` 模板变量，由 `workflow_loader.substitute()` 动态替换。
