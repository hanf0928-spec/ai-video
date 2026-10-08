
#!/usr/bin/env bash
# 停止所有服务
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for svc in backend celery frontend comfyui; do
  pidfile="$ROOT/logs/$svc.pid"
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid"
      echo "stopped $svc (pid=$pid)"
    fi
    rm -f "$pidfile"
  fi
done

echo "✅ 全部停止"
