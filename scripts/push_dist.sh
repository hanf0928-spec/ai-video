#!/usr/bin/env bash
# ============================================================
# 【本地打包 + 上传】到云服务器 —— 低配服务器首选方案
# 用法:
#   bash scripts/push_dist.sh root@1.2.3.4
#   bash scripts/push_dist.sh root@1.2.3.4 /opt/ai-manga
# ============================================================
set -e

REMOTE="${1:-}"
REMOTE_DIR="${2:-/opt/ai-manga}"

if [ -z "$REMOTE" ]; then
  echo "用法: bash scripts/push_dist.sh user@host [/opt/ai-manga]"
  echo "示例: bash scripts/push_dist.sh root@1.2.3.4"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> 1. 本地构建前端"
bash scripts/build_frontend.sh --fast

echo "==> 2. 上传 dist 到 $REMOTE:$REMOTE_DIR/frontend/dist"
# -a 保留权限 -z 压缩传输 --delete 远端多余文件删掉
rsync -avz --delete \
  frontend/dist/ \
  "$REMOTE:$REMOTE_DIR/frontend/dist/"

echo "==> 3. 远端 reload Nginx 让静态文件生效"
ssh "$REMOTE" "systemctl reload nginx 2>/dev/null || sudo systemctl reload nginx"

echo "✅ 前端已部署，访问 http://${REMOTE#*@}/"
