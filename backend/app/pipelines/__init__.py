
"""Pipelines package.

重型依赖（cv2 / torch / paddleocr / ultralytics）全部放在子模块中。
为了让 FastAPI 启动不被这些依赖拖慢，不在此处做顶层 import。
请显式使用:
    from backend.app.pipelines.manga2anime import Manga2AnimePipeline
    from backend.app.pipelines.episode_render import render_episode
"""

__all__: list[str] = []
