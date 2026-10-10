
#!/usr/bin/env bash
# ============================================================
# 云服务器一键部署脚本
# 支持：Ubuntu / Debian / CentOS / RHEL / Rocky / Alibaba Cloud Linux
# 用法：sudo bash scripts/deploy.sh
# ============================================================
set -euo pipefail

APP_DIR="/opt/ai-manga"
LOG_DIR="/var/log/ai-manga"

info() { echo -e "\033[32m[deploy]\033[0m $*"; }
warn() { echo -e "\033[33m[deploy]\033[0m $*"; }
err()  { echo -e "\033[31m[deploy]\033[0m $*" >&2; }

# ---------- 0. 平台检测 ----------
OS_NAME="$(uname -s)"
if [ "$OS_NAME" = "Darwin" ]; then
  err "检测到 macOS，当前脚本仅支持 Linux 云服务器。"
  err "本机开发/测试请改用：  bash scripts/start.sh"
  err "部署到云服务器：先 SSH 到 Linux 服务器，然后在那边执行本脚本。"
  exit 1
fi

if [ ! -f /etc/os-release ]; then
  err "未找到 /etc/os-release，无法识别系统类型"
  exit 1
fi
# shellcheck disable=SC1091
. /etc/os-release
DISTRO_ID="${ID:-unknown}"
DISTRO_LIKE="${ID_LIKE:-}"

# 选择包管理器与各平台包名
PKG=""
case "$DISTRO_ID" in
  ubuntu|debian) PKG="apt" ;;
  centos|rhel|rocky|almalinux|alinux|anolis|openEuler) PKG="yum" ;;
  fedora) PKG="dnf" ;;
  *)
    if echo "$DISTRO_LIKE" | grep -qi "debian"; then PKG="apt"
    elif echo "$DISTRO_LIKE" | grep -qi -E "rhel|fedora|centos"; then PKG="yum"
    fi
    ;;
esac
if [ -z "$PKG" ]; then
  err "不支持的发行版: $DISTRO_ID（ID_LIKE=$DISTRO_LIKE）"
  err "请手动安装: nginx redis ffmpeg python3 python3-pip nodejs rsync curl"
  exit 1
fi
info "检测到发行版: $PRETTY_NAME  (包管理器: $PKG)"

[ "$(id -u)" = "0" ] || { err "请用 sudo 运行"; exit 1; }

# ---------- 用户：Debian 系用 www-data，RHEL 系用 nginx ----------
if id -u www-data >/dev/null 2>&1; then
  RUN_USER="www-data"
elif id -u nginx >/dev/null 2>&1; then
  RUN_USER="nginx"
else
  RUN_USER="root"
fi
info "服务运行用户: $RUN_USER"

# ---------- 1. 系统依赖 ----------
info "==> 1. 系统依赖"
case "$PKG" in
  apt)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y nginx redis-server ffmpeg python3 python3-venv python3-pip \
                       build-essential git curl ca-certificates rsync openssl
    REDIS_SERVICE="redis-server"
    ;;
  yum|dnf)
    $PKG install -y epel-release || true
    $PKG install -y nginx redis ffmpeg python3 python3-pip gcc gcc-c++ make \
                    git curl ca-certificates rsync openssl || \
    $PKG install -y nginx redis python3 python3-pip gcc gcc-c++ make \
                    git curl ca-certificates rsync openssl   # ffmpeg 可能不在源内
    if ! command -v ffmpeg >/dev/null; then
      warn "ffmpeg 未在源中，可参考 https://rpmfusion.org 或静态二进制自行安装"
    fi
    REDIS_SERVICE="redis"
    ;;
esac

# Node.js 20
if ! command -v node >/dev/null; then
  info "安装 Node.js 20"
  case "$PKG" in
    apt)
      curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
      apt-get install -y nodejs
      ;;
    yum|dnf)
      curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
      $PKG install -y nodejs
      ;;
  esac
fi

# ---------- 2. 应用目录 ----------
info "==> 2. 应用目录"
mkdir -p "$APP_DIR" "$LOG_DIR"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [ "$REPO_DIR" != "$APP_DIR" ]; then
  info "同步代码到 $APP_DIR"
  rsync -a --delete \
    --exclude='.git' --exclude='node_modules' --exclude='.venv' \
    --exclude='data/outputs' --exclude='data/uploads' --exclude='logs' \
    "$REPO_DIR/" "$APP_DIR/"
fi

# ---------- 3. Python venv + 依赖 ----------
info "==> 3. Python venv + 依赖"
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

# ---------- 4. 前端构建 ----------
info "==> 4. 前端构建"
cd "$APP_DIR/frontend"
npm ci || npm install
npm run build
cd "$APP_DIR"

# ---------- 5. 环境变量 ----------
info "==> 5. 环境变量"
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  SECRET=$(openssl rand -hex 32)
  sed -i "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=${SECRET}|" "$APP_DIR/.env"
  warn "已生成 .env，APP_SECRET_KEY 已随机填充"
fi

# ---------- 6. 权限 ----------
info "==> 6. 权限"
chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR" "$LOG_DIR"

# ---------- 7. 安装 systemd 服务 ----------
info "==> 7. 安装 systemd 服务"
# 根据运行用户动态改写 service 中的 User/Group
TMP_UNIT=$(mktemp -d)
for f in "$APP_DIR"/deploy/systemd/*.service; do
  sed -e "s|^User=.*|User=${RUN_USER}|" \
      -e "s|^Group=.*|Group=${RUN_USER}|" \
      "$f" > "$TMP_UNIT/$(basename "$f")"
done
cp "$TMP_UNIT"/*.service /etc/systemd/system/
rm -rf "$TMP_UNIT"

systemctl daemon-reload
systemctl enable --now "$REDIS_SERVICE"
systemctl enable --now ai-manga-backend
systemctl enable --now ai-manga-celery
if [ -f "$APP_DIR/comfyui_fork/main.py" ]; then
  systemctl enable --now ai-manga-comfyui || warn "ComfyUI 启动失败，可稍后手动排查"
else
  warn "未检测到 comfyui_fork/main.py，跳过 ComfyUI 服务"
fi

# ---------- 8. Nginx ----------
info "==> 8. 配置 Nginx"
NGINX_CONF_DIR="/etc/nginx/conf.d"
mkdir -p "$NGINX_CONF_DIR"
cp "$APP_DIR/deploy/nginx.conf" "$NGINX_CONF_DIR/ai-manga.conf"
# 禁用 Debian 默认站点
if [ -f /etc/nginx/sites-enabled/default ]; then
  rm -f /etc/nginx/sites-enabled/default
fi
nginx -t
systemctl enable nginx || true
systemctl reload nginx || systemctl restart nginx

# SELinux (CentOS/RHEL) 允许 Nginx 反代本机端口
if command -v getenforce >/dev/null && [ "$(getenforce)" = "Enforcing" ]; then
  info "SELinux 开启中，允许 httpd 网络连接"
  setsebool -P httpd_can_network_connect 1 || true
fi

# firewalld (CentOS/RHEL) 放通 80
if systemctl is-active --quiet firewalld; then
  firewall-cmd --permanent --add-service=http  || true
  firewall-cmd --permanent --add-service=https || true
  firewall-cmd --reload || true
fi

PUB_IP=$(curl -s https://ipinfo.io/ip 2>/dev/null || curl -s https://ifconfig.me 2>/dev/null || echo "<your-ip>")
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
