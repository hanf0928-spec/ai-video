
# 架构设计

## 1. 总体架构

```
┌───────────────────────────────────────────────────────────────┐
│                   React Web UI (5173)                         │
│   项目管理 / 漫画转漫剧 / 分镜工作台 / 角色场景 / 任务队列        │
└───────────────────────────┬───────────────────────────────────┘
                            │ REST + WebSocket
┌───────────────────────────▼───────────────────────────────────┐
│                 FastAPI Backend (8000)                        │
│  ┌────────────────┐ ┌────────────────┐ ┌─────────────────┐    │
│  │ Projects/Shots │ │ Pipelines      │ │ Jobs (WS 推送)   │    │
│  └────────────────┘ └───────┬────────┘ └─────────────────┘    │
│                              │                                │
│                              ▼                                │
│  ┌───────────────────────────────────────────────────────┐    │
│  │       Manga2Anime Pipeline (多阶段编排)                │    │
│  │  Load → Panel → OCR → Character → Script → I2V →      │    │
│  │  TTS → Concat → BGM → Subtitle → Final                │    │
│  └───────────────────────────────────────────────────────┘    │
└───────┬──────────────┬────────────┬────────────┬──────────────┘
        │              │            │            │
        ▼              ▼            ▼            ▼
   ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ComfyUI  │  │ Hailuo03 │  │Seedance2 │  │ LLM/TTS  │
   │本地推理  │  │  云API   │  │  云API   │  │  云API   │
   └─────────┘  └──────────┘  └──────────┘  └──────────┘
```

## 2. 组件职责

| 组件 | 作用 |
|------|------|
| **Frontend (React/Vite)** | 用户界面，与后端 REST/WS 通信 |
| **Backend (FastAPI)** | 业务 API、权限、项目/剧集管理 |
| **Celery Worker** | 执行长时间任务（漫画转漫剧、剧集渲染） |
| **Redis** | Celery broker / result backend |
| **ComfyUI Fork** | 本地 SD/图生图/工作流推理 + 自定义节点 |
| **Hailuo Adapter** | 调用海螺03云端 I2V API |
| **Seedance Adapter** | 调用 Seedance 2 云端 I2V API |
| **LLM Adapter** | OpenAI 兼容协议，用于分镜脚本 |
| **TTS Adapter** | MiniMax T2A，用于角色配音 |

## 3. 数据流（漫画转漫剧）

```
PDF/图片 ──> pdf2image / PIL
            │
            ▼
          页面图像集 ──> YOLO/传统 CV 分格
                        │
                        ▼
                     panel 图像集 ──> PaddleOCR 识别气泡
                                    │
                                    ▼
                                  (panel, bubbles)
                                    │
                       ┌────────────┴─────────────┐
                       ▼                          ▼
             动漫脸检测+聚类                 LLM 生成分镜脚本 JSON
             (建角色参考库)                       │
                                                 ▼
                                 shot[] (image, prompt, dialogue, emotion)
                                                 │
                            ┌────────────────────┼────────────────────┐
                            ▼                    ▼                    ▼
                      Hailuo/Seedance        TTS 配音            SRT 字幕
                       图生视频                 │                    │
                            │                   │                    │
                            └─── FFmpeg mux / concat / BGM mix ──────┘
                                            │
                                            ▼
                                   最终带音视频+字幕+BGM 的 MP4
```

## 4. ORM 关系

```
Project ──1:N── Episode ──1:N── Shot
   │                              │
   ├──1:N── Character             └── (image/video/audio URLs)
   ├──1:N── Scene
   └──1:N── MangaUpload ──1:N── MangaPanel

Job 独立表，记录 Celery 任务状态
Asset 通用资产表
```

## 5. 模型适配器接口

所有视频生成模型实现 `VideoAdapter`：

```python
class VideoAdapter(ABC):
    async def submit(req: VideoGenRequest) -> VideoGenResult: ...
    async def query(task_id: str) -> VideoGenResult: ...
    async def download(result, dest) -> str: ...
    async def generate(req) -> VideoGenResult   # submit + poll
```

便于后续扩展 Kling / Vidu / Runway 等。
