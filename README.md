
# AI 漫剧工作流 (AI Manga-to-Anime Studio)

> 基于 ComfyUI Fork 二次开发的 AI 漫剧生成工作流系统，支持将静态漫画（PDF / 长条漫 / 多图）一键自动转换为带有配音、字幕、BGM 的 AI 动画短剧。

## ✨ 核心特性

### 基础漫剧工作流
- 🎨 **文生图分镜** — 基于剧本自动生成分镜图
- 🎬 **图生视频** — 分镜图自动转视频片段
- 👤 **角色一致性** — 角色 LoRA / IP-Adapter 绑定管理
- 🏞️ **场景一致性** — 场景风格参考库
- 📁 **项目/剧集管理** — 多剧集、多集数、版本回溯

### 漫画自动转漫剧（Manga-to-Anime Pipeline）
1. **输入解析** — PDF / 长条漫 / 多图上传
2. **分格检测** — Panel Detection（基于视觉模型）
3. **OCR 对白识别** — 气泡识别 + 角色归属
4. **角色一致性识别** — 自动聚类并绑定角色
5. **分镜脚本生成** — LLM 自动拆分故事板
6. **图像增强 / 风格迁移** — 漫画 → 动画风格
7. **图生视频 (I2V)** — Hailuo 03 / Seedance 2
8. **TTS 配音** — 多角色音色绑定
9. **BGM 自动配乐** — 情绪驱动的 BGM 选择
10. **字幕 + 视频合成** — FFmpeg 一键输出

## 🏗️ 技术栈

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (React + TypeScript + Vite + Ant Design)      │
└────────────────────────────┬────────────────────────────┘
                             │ REST / WebSocket
┌────────────────────────────▼────────────────────────────┐
│  Backend (FastAPI + Celery + Redis + SQLite)            │
│  ├─ API Layer                                           │
│  ├─ Pipeline Orchestrator                               │
│  ├─ ComfyUI Client (WebSocket)                          │
│  └─ Model Adapters (Hailuo / Seedance / TTS / LLM)      │
└────────────────────────────┬────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
   ┌─────────────┐   ┌──────────────┐   ┌─────────────┐
   │ ComfyUI Fork│   │ Hailuo 03 API│   │ Seedance 2  │
   │ (本地推理)   │   │  (云端视频)  │   │  API (云端) │
   └─────────────┘   └──────────────┘   └─────────────┘
```

## 📂 项目结构

```
AI漫剧工作流/
├─ backend/                  # FastAPI 后端
│  └─ app/
│     ├─ api/                # REST / WS 路由
│     ├─ core/               # 配置、日志、安全
│     ├─ services/           # 业务服务层
│     ├─ pipelines/          # 流水线编排
│     │  └─ manga2anime/     # 漫画→漫剧流水线
│     ├─ comfy_client/       # ComfyUI API 客户端
│     ├─ adapters/           # 外部模型适配器
│     │  ├─ hailuo/          # 海螺 03
│     │  ├─ seedance/        # Seedance 2
│     │  ├─ tts/             # TTS 适配
│     │  └─ llm/             # LLM 适配（分镜脚本）
│     ├─ models/             # ORM 模型
│     ├─ schemas/            # Pydantic 模型
│     ├─ db/                 # 数据库
│     └─ utils/              # 工具库
├─ frontend/                 # React 前端
├─ comfyui_fork/             # ComfyUI Fork 二次开发
│  └─ custom_nodes/
│     └─ ai_manga_suite/     # 自定义节点
├─ workflows/                # 工作流 JSON 模板
│  ├─ base/                  # 基础工作流
│  ├─ manga2anime/           # 漫画转漫剧工作流
│  └─ templates/             # 模板
├─ data/                     # 用户数据
│  ├─ projects/              # 项目数据
│  ├─ uploads/               # 上传文件
│  ├─ outputs/               # 输出产物
│  └─ cache/                 # 缓存
├─ docs/                     # 文档
├─ scripts/                  # 构建/部署脚本
└─ tests/                    # 测试
```

## 🚀 快速开始

### 环境要求
- Python 3.10+
- Node.js 18+
- Redis 6+
- FFmpeg 5+
- CUDA 11.8+（本地推理可选）

### 一键启动
```bash
# 1. 克隆并进入项目
cd AI漫剧工作流

# 2. 初始化（安装依赖、拉取 ComfyUI、下载基础模型）
bash scripts/setup.sh

# 3. 复制应用级环境变量（可选，默认值即可运行）
cp .env.example .env
# ⚠️ 注意：模型 API Key 不再写入 .env，启动后在控制台配置

# 4. 启动所有服务
bash scripts/start.sh

# 5. 浏览器打开 http://localhost:5173，进入 「模型配置」 页面
#    填写海螺03 / Seedance2 / LLM / TTS 的 API Key，点"测试连接"验证
```

启动后访问：
- 前端界面：http://localhost:5173
- 后端 API：http://localhost:8000/docs
- ComfyUI：http://localhost:8188

## 🔑 配置管理

模型接入信息（API Key / Endpoint）**全部通过 Web 控制台配置**，加密保存在数据库中：

👉 启动后进入前端 **「模型配置」** 页面：

| 提供商 | 必填字段 |
|--------|---------|
| 🎥 海螺 03 (MiniMax) | api_key, group_id |
| 🎬 Seedance 2 (字节) | api_key, endpoint_id |
| 🧠 LLM (OpenAI 兼容) | api_key, base_url, model |
| 🔊 TTS (MiniMax) | api_key |
| 🎨 ComfyUI | api_url, ws_url |

应用级配置（Redis / 存储路径 / CORS / OCR 等）仍在 `.env` 文件，详见 [.env.example](./.env.example)。

> `APP_SECRET_KEY` 用于加密模型配置中的敏感字段，**生产环境务必修改为长随机串**。

## 📖 文档

- [🌐 公网部署指南 (云服务器)](./deploy/README.md)
- [架构设计](./docs/architecture.md)
- [漫画转漫剧流水线详解](./docs/manga2anime-pipeline.md)
- [模型适配器开发指南](./docs/adapter-dev.md)
- [ComfyUI 自定义节点](./docs/comfyui-nodes.md)

## 🚢 公网部署速览

云服务器一键部署（Ubuntu/Debian）：
```bash
ssh root@<公网IP>
git clone https://github.com/hanf0928-spec/ai-video.git /opt/ai-manga
cd /opt/ai-manga
sudo bash scripts/deploy.sh
```
完整说明见 [deploy/README.md](./deploy/README.md)。

## 📝 License

MIT
