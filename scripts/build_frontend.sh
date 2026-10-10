#!/usr/bin/env bash
# ============================================================
# 构建前端产物（frontend/dist）—— 低配机友好
# 用法:
#   bash scripts/build_frontend.sh            # 自动检测内存
#   bash scripts/build_frontend.sh --no-swap  # 不自动加 swap
#   bash scripts/build_frontend.sh --fast     # 跳过 tsc 类型检查
# ============================================================
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"

info() { echo -e "\033[32m[build]\033[0m $*"; }
warn() { echo -e "\033[33m[build]\033[0m $*"; }

AUTO_SWAP=1
FORCE_FAST=0
for arg in "$@"; do
  case "$arg" in
    --no-swap) AUTO_SWAP=0 ;;
    --fast)    FORCE_FAST=1 ;;
  esac
done

# -------- 检测总内存 (MB) --------
TOTAL_MEM_MB=0
if [ "$(uname -s)" = "Linux" ]; then
  TOTAL_MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
elif [ "$(uname -s)" = "Darwin" ]; then
  TOTAL_MEM_MB=$(($(sysctl -n hw.memsize) / 1024 / 1024))
fi
info "检测到内存: ${TOTAL_MEM_MB} MB"

# -------- 低内存自动加 swap (仅 Linux root) --------
if [ "$(uname -s)" = "Linux" ] && [ "$TOTAL_MEM_MB" -lt 3072 ] && [ "$AUTO_SWAP" = "1" ]; then
  CUR_SWAP=$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)
  if [ "$CUR_SWAP" -lt 1024 ] && [ "$(id -u)" = "0" ]; then
    warn "内存 < 3G 且 swap < 1G，自动创建 2G swap 文件 /swapfile"
    if [ ! -f /swapfile ]; then
      fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048
      chmod 600 /swapfile
      mkswap /swapfile >/dev/null
    fi
    swapon /swapfile 2>/dev/null || true
    grep -q "/swapfile" /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
    info "swap 已启用: $(free -m | awk '/Swap:/ {print $2}') MB"
  fi
fi

# -------- 安装依赖 --------
if [ ! -d node_modules ]; then
  info "安装 npm 依赖"
  npm ci --no-audit --no-fund || npm install --no-audit --no-fund
fi

# -------- 选择构建命令 --------
# 内存 < 3G 时自动走 build:low-mem（限制 Node 堆内存 + 跳过 tsc）
if [ "$FORCE_FAST" = "1" ] || [ "$TOTAL_MEM_MB" -lt 3072 ]; then
  warn "低内存模式：使用 vite build --max-old-space-size=1024（跳过 tsc 类型检查）"
  export NODE_OPTIONS="--max-old-space-size=1024"
  npx vite build
else
  info "标准模式：tsc + vite build"
  npm run build
fi

echo ""
info "✅ 前端已构建到 $ROOT/frontend/dist"
ls -lh dist/ 2>/dev/null | head -20 || true
