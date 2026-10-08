
#!/usr/bin/env bash
# 一次性初始化整个项目：拉取 ComfyUI、安装 Python / 前端依赖
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> 1. 创建 Python 虚拟环境"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

echo "==> 2. 安装后端依赖"
pip install --upgrade pip
pip install -r backend/requirements.txt

echo "==> 2.1 可选：PaddleOCR（Linux / Windows 推荐）"
OS_NAME="$(uname -s)"
ARCH_NAME="$(uname -m)"
if [ "$OS_NAME" = "Darwin" ] && [ "$ARCH_NAME" = "arm64" ]; then
  echo "   检测到 macOS Apple Silicon (arm64)，PaddlePaddle 官方 wheel 支持有限，已跳过。"
  echo "   默认使用 easyocr（已在主依赖中）。如仍想使用 paddleocr，请参考 backend/requirements-paddle.txt。"
else
  pip install -r backend/requirements-paddle.txt || \
    echo "   ⚠️  PaddleOCR 安装失败，可忽略；系统将使用 easyocr。"
fi

echo "==> 3. 拉取 ComfyUI"
mkdir -p comfyui_fork
if [ ! -d comfyui_fork/ComfyUI ]; then
  git clone https://github.com/comfyanonymous/ComfyUI.git comfyui_fork/ComfyUI
fi

echo "==> 4. 安装 ComfyUI 依赖"
pip install -r comfyui_fork/ComfyUI/requirements.txt || true

echo "==> 5. 软链自定义节点"
ln -sfn "$ROOT/comfyui_fork/custom_nodes/ai_manga_suite" \
         "$ROOT/comfyui_fork/ComfyUI/custom_nodes/ai_manga_suite"

echo "==> 6. 前端依赖"
cd frontend
if command -v pnpm >/dev/null 2>&1; then
  pnpm install
elif command -v yarn >/dev/null 2>&1; then
  yarn install
else
  npm install
fi
cd "$ROOT"

echo "==> 7. 创建 .env 文件（如不存在）"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "   已生成 .env，请打开编辑 API Key！"
fi

echo "==> ✅ 初始化完成！"
echo "下一步： bash scripts/start.sh"
