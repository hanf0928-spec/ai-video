
# 模型适配器开发指南

本项目的所有外部模型都通过 **Adapter 模式**接入，便于扩展。
所有敏感配置（API Key / Endpoint）**统一通过前端控制台"模型配置"页管理**，加密入库，`.env` 不再承载这些字段。

## 0. 配置来源

- UI 保存后 → `system_configs` 表（敏感字段 Fernet 加密）
- Adapter 构造 → 调 `services.config_service.ensure_configured(provider, "api_key")` 自动获取并校验
- 允许传参覆盖：`HailuoAdapter(api_key="...")` 会**绕过** DB 校验（供 ComfyUI 节点面板场景使用）

## 1. 视频生成适配器

实现 [backend/app/adapters/base.py](../backend/app/adapters/base.py) 中的 `VideoAdapter`：

```python
from backend.app.adapters.base import VideoAdapter, VideoGenRequest, VideoGenResult

class MyVideoAdapter(VideoAdapter):
    name = "myvideo"

    async def submit(self, req: VideoGenRequest) -> VideoGenResult: ...
    async def query(self, task_id: str) -> VideoGenResult: ...
    async def download(self, result: VideoGenResult, dest: str) -> str: ...
```

然后在 [backend/app/adapters/__init__.py](../backend/app/adapters/__init__.py) 的 `get_video_adapter()` 中注册即可。

**同时记得在 `config_service.PROVIDER_SCHEMA` 中声明你的字段**，这样 UI 会自动渲染配置卡片。

## 2. 新增 Provider 到 UI 配置

打开 [backend/app/services/config_service.py](../backend/app/services/config_service.py)，往 `PROVIDER_SCHEMA` 加一个条目：

```python
PROVIDER_SCHEMA["myvideo"] = {
    "api_key":  {"type": "string", "secret": True,  "default": "", "desc": "My Video API Key"},
    "base_url": {"type": "string", "secret": False, "default": "https://api.example.com"},
    "model":    {"type": "string", "secret": False, "default": "v1-pro"},
}
```

- `secret=True` 的字段会被 Fernet 加密、UI 显示为 `****1234`、保存时留空代表"保持原值"
- 还需在 `test_connection()` 中加一个分支，用于"测试连接"按钮

然后前端自动显示新卡片，无需改前端代码。

## 3. 已内置适配器

### Hailuo 03

- 文件：`backend/app/adapters/hailuo/adapter.py`
- 文档：https://platform.minimaxi.com/document/video_generation
- UI 配置：**模型配置 → 海螺 03**（`api_key`, `group_id`, `base_url`, `model`）

关键字段映射：
| VideoGenRequest | Hailuo payload |
|-----------------|----------------|
| prompt          | prompt         |
| image_path      | first_frame_image (base64) |
| duration        | duration       |
| resolution      | resolution     |

### Seedance 2

- 文件：`backend/app/adapters/seedance/adapter.py`
- 文档：https://www.volcengine.com/docs/82379/
- UI 配置：**模型配置 → Seedance 2**（`api_key`, `endpoint_id`, `base_url`, `model`）
- 走 Volcano Ark OpenAPI：`contents/generations/tasks`

Seedance 的 prompt 中可以包含 CLI 风格参数：
```
--ratio 16:9 --duration 5 --resolution 1080P
```

## 4. 新增一个 LLM / TTS 适配器

类比参照 `backend/app/adapters/llm/adapter.py` 和 `backend/app/adapters/tts/adapter.py`。

LLM 使用 OpenAI 兼容协议，只要上游提供 `/chat/completions` 即可无缝接入（Doubao / Qwen / DeepSeek / Moonshot...）。

## 4. ComfyUI 节点里使用 Adapter

见 `comfyui_fork/custom_nodes/ai_manga_suite/nodes/hailuo_node.py`，
核心就是从后端包导入：

```python
from backend.app.adapters import HailuoAdapter, VideoGenRequest
```

需保证 ComfyUI 启动时 `PYTHONPATH` 包含项目根目录（`scripts/start_comfy.sh` 已处理）。

## 5. 失败/重试策略

- 所有适配器方法使用 `tenacity` 装饰器自动重试 3 次（指数退避）
- 适配器层只抛出 `AdapterError`，由上层决定是否降级
- `Pipeline` 层对关键阶段提供回退（见 pipeline 文档）
