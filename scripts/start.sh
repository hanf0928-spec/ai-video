
#!/usr/bin/env bash
# 一键启动所有服务（在后台）
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p logs

[ -d .venv ] && source .venv/bin/activate

export PYTHONPATH="$ROOT:$PYTHONPATH"

echo "==> 启动 Redis（如未运行）"
if ! pgrep -x redis-server >/dev/null; then
  if command -v redis-server >/dev/null 2>&1; then
    redis-server --daemonize yes --logfile "$ROOT/logs/redis.log" || true
  else
    echo "⚠️  未检测到 redis-server，请手动启动 Redis"
  fi
fi

echo "==> 启动后端 FastAPI (8000)"
nohup uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload \
  > logs/backend.log 2>&1 &
echo $! > logs/backend.pid

echo "==> 启动 Celery Worker"
nohup celery -A backend.app.celery_app.celery_app worker -l info --concurrency=2 \
  > logs/celery.log 2>&1 &
echo $! > logs/celery.pid

echo "==> 启动 ComfyUI (8188)"
bash "$ROOT/scripts/start_comfy.sh" &

echo "==> 启动前端 (5173)"
cd frontend
nohup npm run dev > "$ROOT/logs/frontend.log" 2>&1 &
echo $! > "$ROOT/logs/frontend.pid"
cd "$ROOT"

echo "✅ 启动完成"
echo "  后端:    http://localhost:8000/docs"
echo "  前端:    http://localhost:5173"
echo "  ComfyUI: http://localhost:8188"
echo ""
echo "查看日志: tail -f logs/*.log"
echo "停止服务: bash scripts/stop.sh"
