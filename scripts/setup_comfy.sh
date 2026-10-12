#!/usr/bin/env bash
# ============================================================
# 单独初始化 ComfyUI：克隆源码 + 装依赖 + 软链自定义节点
# 适用于：后端/前端已部署好，只是还没装 ComfyUI 的场景
# 用法：  bash scripts/setup_comfy.sh
# ============================================================
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMFY_DIR="$ROOT/comfyui_fork/ComfyUI"
VENV_DIR="$ROOT/.venv"

echo "==> 1. 检查 Python 虚拟环境"
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip >/dev/null

echo "==> 2. 拉取 ComfyUI 源码"
mkdir -p "$ROOT/comfyui_fork"
if [ ! -d "$COMFY_DIR" ]; then
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
else
  echo "   已存在，跳过克隆（如需升级：cd $COMFY_DIR && git pull）"
fi

echo "==> 3. 安装 ComfyUI 依赖（可能耗时 3-10 分钟）"
pip install -r "$COMFY_DIR/requirements.txt"

echo "==> 4. 软链自定义节点 ai_manga_suite"
mkdir -p "$COMFY_DIR/custom_nodes"
ln -sfn "$ROOT/comfyui_fork/custom_nodes/ai_manga_suite" \
         "$COMFY_DIR/custom_nodes/ai_manga_suite"
ls -l "$COMFY_DIR/custom_nodes/ai_manga_suite"

echo "==> 5. 创建模型目录占位"
for d in checkpoints vae loras controlnet upscale_models clip_vision; do
  mkdir -p "$COMFY_DIR/models/$d"
done

cat <<'TIP'

==> ✅ ComfyUI 初始化完成！

接下来可选操作：
  1) 放入模型文件（任选一种）
     - 直接拷贝到 comfyui_fork/ComfyUI/models/checkpoints/ 下
     - 推荐先放一个 SD1.5/SDXL 底模用于冒烟测试
  2) 启动 ComfyUI
     - 前台调试：   cd comfyui_fork/ComfyUI && source ../../.venv/bin/activate && python main.py --listen 127.0.0.1 --port 8188
     - 后台脚本：   bash scripts/start_comfy.sh
     - systemd：    sudo systemctl restart ai-manga-comfyui
  3) 在前端 "🔧 模型配置 → ComfyUI" 点 "测试连接"
     - 应返回 HTTP 200 (ComfyUI online)

TIP
