
#!/usr/bin/env bash
# ============================================================
# 云服务器一键部署脚本（Ubuntu / Debian）
# 用法：curl 代码到服务器后，sudo bash scripts/deploy.sh
# ============================================================
set -euo pipefail

APP_DIR="/opt/ai-manga"
LOG_DIR="/var/log/ai-manga"
RUN_USER="www-data"

info() { echo -e "\033[32m[deploy]\033[0m $*"; }
warn() { echo -e "\033[33m[deploy]\033[0m $*"; }
err()  { echo -e "\033[31m[deploy]\033[0m $*" >&2; }

[ "$(id -u)" = "0" ] || { err "请用 sudo 运行"; exit 1; }

info "==> 1. 系统依赖"
apt-get update -y
apt-get install -y nginx redis-server ffmpeg python3 python3-venv python3-pip \
                   build-essential git curl ca-certificates

# Node.js 20
if ! command -v node >/dev/null; then
  info "安装 Node.js 20"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

info "==> 2. 应用目录"
mkdir -p "$APP_DIR" "$LOG_DIR"
# 如果脚本在仓库中，自动把当前仓库拷贝过去
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [ "$REPO_DIR" != "$APP_DIR" ]; then
  info "同步代码到 $APP_DIR"
  rsync -a --delete \
    --exclude='.git' --exclude='node_modules' --exclude='.venv' \
    --exclude='data/outputs' --exclude='data/uploads' --exclude='logs' \
    "$REPO_DIR/" "$APP_DIR/"
fi

info "==> 3. Python venv + 依赖"
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

info "==> 4. 前端构建"
cd "$APP_DIR/frontend"
npm ci || npm install
npm run build
cd "$APP_DIR"

info "==> 5. 环境变量"
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  SECRET=$(openssl rand -hex 32)
  sed -i "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=${SECRET}|" "$APP_DIR/.env"
  warn "已生成 .env，APP_SECRET_KEY 已随机填充"
fi

info "==> 6. 权限"
chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR" "$LOG_DIR"

info "==> 7. 安装 systemd 服务"
cp "$APP_DIR/deploy/systemd/"*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now redis-server
systemctl enable --now ai-manga-backend
systemctl enable --now ai-manga-celery
# ComfyUI 可选（若未下载模型则先不启）
if [ -f "$APP_DIR/comfyui_fork/main.py" ]; then
  systemctl enable --now ai-manga-comfyui || warn "ComfyUI 启动失败，可稍后手动排查"
else
  warn "未检测到 comfyui_fork/main.py，跳过 ComfyUI 服务"
fi

info "==> 8. 配置 Nginx"
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/conf.d/ai-manga.conf
# 禁用默认站点，避免 80 端口冲突
if [ -f /etc/nginx/sites-enabled/default ]; then
  rm -f /etc/nginx/sites-enabled/default
fi
nginx -t
systemctl reload nginx || systemctl restart nginx

PUB_IP=$(curl -s https://ipinfo.io/ip || echo "<your-ip>")
echo ""
info "✅ 部署完成"
echo "    访问: http://${PUB_IP}/"
echo "    API : http://${PUB_IP}/api/docs"
echo ""
warn "下一步："
echo "  1. 云厂商控制台开放安全组：TCP 80 (必) / 443 (HTTPS)"
echo "  2. 浏览器访问后 → 「模型配置」页填 API Key"
echo "  3. 可选: sudo certbot --nginx -d your-domain.com 启用 HTTPS"
echo ""
echo "常用命令："
echo "  查看后端:   journalctl -u ai-manga-backend -f"
echo "  查看任务:   journalctl -u ai-manga-celery  -f"
echo "  重启全部:   systemctl restart ai-manga-backend ai-manga-celery ai-manga-comfyui"
