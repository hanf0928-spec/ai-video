
# 🌐 公网部署指南（云服务器）

本文档说明如何把 AI 漫剧工作流部署到有公网 IP 的 Linux 云服务器（Ubuntu / Debian / CentOS）。

> macOS / 家庭宽带用户请改用「内网穿透」方案（见文末「其他场景」）。

---

## 📐 架构

```
                     ┌─ /          → frontend/dist (静态)
         ┌──────┐    │
用户 ───►│Nginx │────┼─ /api/      → 127.0.0.1:8000  (FastAPI)
         │ :80  │    │
         │ :443 │    ├─ /api/jobs/ws/* → 127.0.0.1:8000  (WebSocket)
         └──────┘    │
                     └─ /static/   → 127.0.0.1:8000  (生成产物)

                        内部不暴露公网：
                        127.0.0.1:6379  Redis
                        127.0.0.1:8188  ComfyUI
                        Celery Worker
```

**对外只开 80 / 443 端口**，一切经 Nginx 反代；后端、ComfyUI、Redis 均绑定 `127.0.0.1`，更安全。

---

## 🚀 一键部署

### 1. 开放云厂商安全组
在你的云厂商控制台（阿里云 / 腾讯云 / AWS / 华为云 ...）为该主机加入站规则：

| 协议 | 端口 | 来源 | 说明 |
|------|------|------|------|
| TCP  | 22   | 你的 IP | SSH |
| TCP  | 80   | 0.0.0.0/0 | HTTP |
| TCP  | 443  | 0.0.0.0/0 | HTTPS（可选） |

> ⚠️ **不要**开放 8000 / 5173 / 8188 到公网，这些是内部端口。

### 2. SSH 登录服务器拉代码

```bash
ssh root@<公网IP>
cd /opt
git clone https://github.com/hanf0928-spec/ai-video.git ai-manga
cd ai-manga
```

### 3. 执行一键部署脚本

```bash
sudo bash scripts/deploy.sh
```

脚本会自动做：
- 安装 Nginx / Redis / ffmpeg / Python / Node.js
- 创建 Python venv，安装 `requirements.txt`
- 构建前端 (`npm run build` → `frontend/dist`)
- 生成 `.env`，随机填充 `APP_SECRET_KEY`
- 注册 systemd 服务：`ai-manga-backend` / `ai-manga-celery` / `ai-manga-comfyui`
- 配置 Nginx 反代（`/etc/nginx/conf.d/ai-manga.conf`）
- 启动所有服务

部署完成后：

```
✅ 部署完成
   访问: http://<公网IP>/
   API : http://<公网IP>/api/docs
```

### 4. 首次登录配置模型

浏览器打开 `http://<公网IP>/` → 侧栏「🔧 模型配置」→ 填入海螺03 / Seedance2 / LLM / TTS 的 API Key → 点「测试连接」。

---

## 🔐 启用 HTTPS（强烈推荐）

### 前提：已把域名 A 记录指向服务器公网 IP

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

Certbot 会自动：
- 生成免费 Let's Encrypt 证书
- 修改 `/etc/nginx/conf.d/ai-manga.conf` 补齐 443 段
- 配置自动续期（`/etc/cron.d/certbot`）

完成后 `https://your-domain.com` 即可访问，HTTP 自动跳转 HTTPS。

---

## 🧰 常用运维命令

```bash
# 查看服务状态
systemctl status ai-manga-backend ai-manga-celery ai-manga-comfyui

# 实时日志
journalctl -u ai-manga-backend -f
journalctl -u ai-manga-celery  -f
tail -f /var/log/ai-manga/*.log

# 重启
sudo systemctl restart ai-manga-backend ai-manga-celery

# 更新代码
cd /opt/ai-manga
git pull
sudo bash scripts/deploy.sh   # 幂等，可重复跑

# 只重新构建前端
sudo bash scripts/build_frontend.sh
```

---

## ❓ 排错清单

### 1. 浏览器打开 http://公网IP 显示 "连接超时"
- 云厂商安全组是否放通 80 端口？
- 服务器防火墙：`sudo ufw status`，必要时 `sudo ufw allow 80/tcp`
- Nginx 是否在跑：`systemctl status nginx`

### 2. 访问后页面空白 / 404
- 前端未构建：`sudo bash scripts/build_frontend.sh`
- Nginx `root` 路径不对：确认 `/opt/ai-manga/frontend/dist/index.html` 存在

### 2.5 前端构建卡死 / `transforming (XXXX)` 不动
典型原因：服务器内存 ≤ 2G，Vite 构建吃光内存被 OOM 挂起。**三选一**解决：

**方案 A（推荐）：本地打包后 rsync 上传**，不占服务器资源
```bash
# 在本地（Mac/PC）执行即可
bash scripts/push_dist.sh root@你的公网IP
```

**方案 B：服务器加 swap，重跑 build**（`build_frontend.sh` 已内置自动加 swap）
```bash
sudo bash scripts/build_frontend.sh
```

**方案 C：手工加 swap + 低内存命令**
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
cd /opt/ai-manga/frontend
NODE_OPTIONS="--max-old-space-size=1024" npx vite build
```

### 3. 页面能打开但接口 502 / 504
- 后端未起：`systemctl status ai-manga-backend` + `journalctl -u ai-manga-backend -n 100`
- `.env` 中 `APP_SECRET_KEY` 为空也会启动失败

### 4. WebSocket 任务进度不更新
- Nginx 的 `/api/jobs/ws/` 段必须保留 `proxy_http_version 1.1` + `Upgrade` 头（已在模板中）
- 浏览器 Network 面板看 WS 请求是否 101

### 5. 上传大文件报 413
- Nginx 的 `client_max_body_size` 默认已设为 1G，更大的话在 `nginx.conf` 中调大

---

## 🔄 其他场景（非云服务器）

### 场景 A：macOS / 家庭宽带 → 临时演示
用内网穿透工具，30 秒出公网链接：

```bash
# ngrok (需注册) 把前端端口暴露
ngrok http 5173

# 或 cloudflared (免费免注册)
cloudflared tunnel --url http://localhost:5173
```

> 注意：这种模式后端 API 同宿主机，前端 dev server 代理 `/api` 到 `localhost:8000`，直接可用。

### 场景 B：家庭宽带长期用
- 路由器开 FRP / NPS 内网穿透到一台有公网 IP 的小机器
- 或申请公网 IPv6 + DDNS

