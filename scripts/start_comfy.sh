
#!/usr/bin/env bash
# 启动 ComfyUI（带自定义节点）
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/comfyui_fork/ComfyUI"

[ -d "$ROOT/.venv" ] && source "$ROOT/.venv/bin/activate"
export PYTHONPATH="$ROOT:$PYTHONPATH"

nohup python main.py --listen 0.0.0.0 --port 8188 \
  > "$ROOT/logs/comfyui.log" 2>&1 &
echo $! > "$ROOT/logs/comfyui.pid"
echo "ComfyUI started on port 8188 (pid=$(cat $ROOT/logs/comfyui.pid))"
