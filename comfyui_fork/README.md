
# ComfyUI Fork - AI 漫剧版本

本目录是 **ComfyUI 的二次开发 Fork**，在原生 ComfyUI 基础上集成了 AI 漫剧相关的自定义节点。

## 📦 目录结构

```
comfyui_fork/
├─ ComfyUI/                      # 原生 ComfyUI（通过 scripts/setup.sh 拉取，被 .gitignore）
└─ custom_nodes/
   └─ ai_manga_suite/            # 本项目的自定义节点
      ├─ nodes/
      │  ├─ manga_loader.py      # 🎞 漫画分格加载
      │  ├─ ocr_node.py          # 📝 OCR 文字识别
      │  ├─ hailuo_node.py       # 🎥 海螺 03 图生视频
      │  ├─ seedance_node.py     # 🎬 Seedance 2 图生视频
      │  └─ storyboard_node.py   # 🧠 LLM 分镜脚本
      └─ utils/
```

## 🚀 启动方式

### 方式 A：自动初始化（推荐）

```bash
# 从项目根目录
bash scripts/setup.sh         # 拉取 ComfyUI 并软链 custom_nodes
bash scripts/start_comfy.sh   # 启动 ComfyUI (端口 8188)
```

### 方式 B：手动初始化

```bash
cd comfyui_fork
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install -r requirements.txt
# 把本项目的 custom_nodes 软链到 ComfyUI 下
ln -s "$(pwd)/../custom_nodes/ai_manga_suite" custom_nodes/ai_manga_suite
python main.py --listen 0.0.0.0 --port 8188
```

## 🔑 自定义节点依赖后端包

`hailuo_node`、`seedance_node`、`storyboard_node` 复用 `backend/app/adapters/` 下的适配器。
启动 ComfyUI 时需要让 Python 能找到 `backend` 包：

```bash
export PYTHONPATH="/path/to/AI漫剧工作流:$PYTHONPATH"
python main.py --listen 0.0.0.0 --port 8188
```

`scripts/start_comfy.sh` 会自动完成这个 export。

## 🎨 使用

启动后在 ComfyUI 面板左侧搜索 `AIManga/*` 分类即可找到所有节点。
典型连法：

```
MangaPanelLoader → MangaOCRNode
                 ↘  
                   StoryboardLLMNode → (prompt) → HailuoI2VNode / SeedanceI2VNode
```

## ✅ 版本

本 Fork 跟随 ComfyUI master 分支，建议定期：

```bash
cd comfyui_fork/ComfyUI && git pull
```
