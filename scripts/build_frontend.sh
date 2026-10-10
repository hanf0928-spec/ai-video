
#!/usr/bin/env bash
# 单独构建前端产物（dist/）
set -e
cd "$(dirname "$0")/.."/frontend
npm ci || npm install
npm run build
echo "✅ 前端已构建到 frontend/dist"
