#!/usr/bin/env bash
# 启动 ComfyUI（带自定义节点）
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMFY_DIR="$ROOT/comfyui_fork/ComfyUI"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

if [ ! -f "$COMFY_DIR/main.py" ]; then
  echo "❌ 未找到 ComfyUI 本体 ($COMFY_DIR/main.py)"
  echo "👉 请先执行: bash scripts/setup_comfy.sh"
  exit 1
fi

cd "$COMFY_DIR"
[ -d "$ROOT/.venv" ] && source "$ROOT/.venv/bin/activate"
export PYTHONPATH="$ROOT:$PYTHONPATH"

HOST="${COMFY_HOST:-127.0.0.1}"
PORT="${COMFY_PORT:-8188}"

nohup python main.py --listen "$HOST" --port "$PORT" \
  > "$LOG_DIR/comfyui.log" 2>&1 &
echo $! > "$LOG_DIR/comfyui.pid"
echo "✅ ComfyUI started on ${HOST}:${PORT} (pid=$(cat $LOG_DIR/comfyui.pid))"
echo "   日志: tail -f $LOG_DIR/comfyui.log"
