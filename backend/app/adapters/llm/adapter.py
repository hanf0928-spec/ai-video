
"""LLM adapter for storyboard/script generation.

Supports OpenAI-compatible endpoints (OpenAI / Doubao / Qwen / DeepSeek /...).
"""
from __future__ import annotations

import json
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ...core.config import settings
from ...core.exceptions import AdapterError
from ...core.logger import logger
from ...services.config_service import ensure_configured


SYSTEM_SCRIPT_PROMPT = """\
你是一名专业动画编剧，擅长将漫画分格或故事大纲转换成 AI 动画分镜脚本。
请根据输入内容，输出一个严格的 JSON，结构如下：
{
  "title": "剧集标题",
  "summary": "一句话简介",
  "characters": [{"name":"角色名","description":"外貌/性格"}],
  "shots": [
    {
      "index": 0,
      "scene": "场景描述（用于文生图/图生视频 prompt）",
      "camera": "镜头语言（远景/中景/近景/特写/推拉摇移等）",
      "action": "角色动作/事件",
      "dialogue": "对白台词（可空）",
      "speaker": "说话人名字（可空）",
      "emotion": "情绪(neutral/happy/sad/angry/surprised)",
      "duration": 4
    }
  ]
}
只输出 JSON，不要任何其他内容。
"""


SYSTEM_PANEL2SHOT_PROMPT = """\
你是一名专业动画分镜师。接下来会给你一批漫画分格的 OCR 文字和描述，
请把它们转换成适合 AI 图生视频的分镜脚本 JSON，结构同上。
请根据漫画阅读顺序推进剧情，保持角色一致性。
只输出 JSON。
"""


SYSTEM_PANEL_ANALYZE_PROMPT = """\
你是一名资深漫剧改编制片人与分镜师，擅长将漫画拆解为可执行的影视化方案。
下面会给你一批漫画分格（panel）的 OCR 文字和阅读顺序，请深度剖析并输出一个严格的 JSON，结构如下：

{
  "title": "作品标题（根据内容猜测，可留空）",
  "genre": "类型：热血/恋爱/悬疑/日常/科幻/奇幻/恐怖/喜剧/...",
  "summary": "一句话故事概要（≤80 字）",
  "tone": "整体氛围/色调风格建议",
  "bgm_hint": "推荐 BGM 风格",
  "characters": [
    {
      "name": "角色名（没有就用 '少年A'/'少女B'）",
      "role": "主角/配角/路人",
      "appearance": "外貌（性别、年龄、身高、发色、瞳色、体型）",
      "costume": "典型服装（上下装、配饰）",
      "personality": "性格",
      "voice_tone": "声线建议（如：少年感、清冷御姐、低沉大叔）",
      "first_appear_panel": 0
    }
  ],
  "script": {
    "acts": [
      {
        "name": "起/承/转/合 或 自定义段落名",
        "panels_range": [起始panel索引, 结束panel索引],
        "summary": "本段剧情概要"
      }
    ]
  },
  "storyboard": [
    {
      "index": 0,
      "page": 0,
      "panel_order": 0,
      "timecode": "00:00:00~00:00:04",
      "duration": 4,
      "shot_type": "大特写/特写/近景/中景/全景/远景/大远景",
      "camera_motion": "固定/推/拉/摇/移/跟/升降/旋转",
      "environment": {
        "location": "地点",
        "time_of_day": "清晨/白天/黄昏/夜晚",
        "weather": "晴/阴/雨/雪/未知",
        "lighting": "自然光/逆光/侧光/舞台光/...",
        "details": "环境细节（道具、背景、氛围线索）"
      },
      "characters_in_shot": [
        {
          "name": "角色名",
          "costume": "本镜头服装（如有变化）",
          "action": "正在做什么动作",
          "expression": "面部神态",
          "emotion": "情绪：neutral/happy/sad/angry/surprised/afraid/determined"
        }
      ],
      "dialogue": "台词（可空）",
      "speaker": "说话人（可空）",
      "sfx": "音效建议（可空）",
      "image_prompt": "文生图/图生视频 prompt（英文、尽量具体，可直接喂给 Flux/SDXL/海螺）",
      "video_prompt": "镜头/动作补充 prompt（描述镜头移动和角色动作）"
    }
  ],
  "notes": "其他给制作团队的提醒（如：主角 A 服装前后一致、第 5 镜用慢动作强调情感）"
}

严格要求：
1. storyboard 长度必须等于输入 panels 数量，index 从 0 开始，和 panel_order 一一对应。
2. 所有字符串用中文（image_prompt / video_prompt 用英文，便于喂给扩散模型）。
3. environment.time_of_day、expression、emotion、shot_type、camera_motion 必须从枚举中选。
4. 不要输出任何 Markdown 代码围栏或注释，只输出纯 JSON。
"""


class LLMAdapter:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        # 配置来源：UI 控制台（忽略 .env 对应字段）；显式传参时绕过 DB 校验
        if api_key:
            cfg: dict = {}
        else:
            cfg = ensure_configured("llm", "api_key")
        self.api_key = api_key or cfg.get("api_key") or ""
        self.base_url = (base_url or cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or cfg.get("model") or "gpt-4o"
        self._client = httpx.AsyncClient(timeout=120.0)

    def _headers(self) -> dict:
        if not self.api_key:
            raise AdapterError("LLM API Key 未配置，请到「模型配置」页填写")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def chat(self, messages: list[dict], *, response_format_json: bool = False) -> str:
        """Call OpenAI-compatible chat API.

        Note: `response_format: {type: 'json_object'}` is a OpenAI feature; many
        providers (Nemotron, Gemma, DeepSeek-free, etc.) will 400 on it. We
        auto-retry WITHOUT that field so callers do not need to care.

        For OpenRouter "reasoning" models (nemotron, deepseek-r1, …), content
        may be empty because the real answer lives in `reasoning_content`.
        We explicitly disable reasoning for those models and fallback to
        reading reasoning_content if content is empty.
        """
        base_payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.8,
            # 保证输出足够长的 JSON；不同网关对 max_tokens 命名略有差异，OpenRouter 用 max_tokens
            "max_tokens": 4096,
        }

        # 对 OpenRouter 的 reasoning 模型显式关闭思考模式，否则 content 常为空
        model_lower = (self.model or "").lower()
        if any(k in model_lower for k in ("nemotron", "deepseek-r1", "reasoning", "o1", "o3", "qwq")):
            # OpenRouter 规范：reasoning={"exclude": true} 不返回 reasoning tokens
            # 并把 effort 调到 low，让模型少想多输出
            base_payload["reasoning"] = {"exclude": True, "effort": "low"}

        async def _do_post(payload: dict) -> httpx.Response:
            logger.info(
                f"[LLM] chat model={self.model} messages={len(messages)} "
                f"json_mode={bool(payload.get('response_format'))} "
                f"reasoning={bool(payload.get('reasoning'))}"
            )
            return await self._client.post(
                f"{self.base_url}/chat/completions", headers=self._headers(), json=payload
            )

        payload = dict(base_payload)
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        r = await _do_post(payload)
        # 如果模型不支持 response_format，大多数网关返回 400 + 关键字 response_format / unsupported
        if r.status_code == 400 and response_format_json:
            txt = (r.text or "").lower()
            if any(k in txt for k in ("response_format", "unsupported", "invalid parameter", "not support")):
                logger.warning(f"[LLM] {self.model} 不支持 response_format=json_object, 自动去掉重试")
                r = await _do_post(base_payload)

        if r.status_code != 200:
            raise AdapterError(f"LLM chat failed: {r.status_code} {r.text}")
        data = r.json()
        try:
            msg = data["choices"][0]["message"]
            content = msg.get("content") or ""
            # Reasoning 模型兜底：content 为空时去 reasoning_content / reasoning 字段取
            if not content.strip():
                for alt_key in ("reasoning_content", "reasoning"):
                    alt = msg.get(alt_key)
                    if isinstance(alt, str) and alt.strip():
                        logger.warning(
                            f"[LLM] {self.model} content 为空，使用 {alt_key} 字段兜底"
                        )
                        content = alt
                        break
            return content
        except (KeyError, IndexError) as e:
            raise AdapterError(f"LLM invalid response: {data}") from e

    async def generate_script(
        self,
        topic: str,
        *,
        episode_count: int = 1,
        shots_per_episode: int = 8,
        style: Optional[str] = None,
    ) -> dict:
        user = (
            f"主题：{topic}\n"
            f"要求：生成 {episode_count} 集，每集约 {shots_per_episode} 个分镜。\n"
            f"风格：{style or '日系动画'}\n"
            f"若 episode_count>1，请在最外层返回 {{\"episodes\":[...]}}，每集结构同上。"
        )
        content = await self.chat(
            [
                {"role": "system", "content": SYSTEM_SCRIPT_PROMPT},
                {"role": "user", "content": user},
            ],
            response_format_json=True,
        )
        return self._safe_parse_json(content)

    async def panels_to_script(self, panels: list[dict], style: Optional[str] = None) -> dict:
        """Convert panel OCR+bbox data into a storyboard script."""
        user = {
            "style": style or "日系动画",
            "panels": panels,
        }
        content = await self.chat(
            [
                {"role": "system", "content": SYSTEM_PANEL2SHOT_PROMPT},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            response_format_json=True,
        )
        result = self._safe_parse_json(content)
        shots = result.get("shots") or []
        logger.info(
            f"[LLM] panels_to_script done: input_panels={len(panels)}, "
            f"output_shots={len(shots)}, keys={list(result.keys())}"
        )
        if not shots:
            # 记录完整返回，便于诊断 "empty storyboard"
            logger.warning(f"[LLM] empty shots. raw content (first 500 chars): {content[:500]}")
        return result

    async def panels_to_analysis(
        self,
        panels: list[dict],
        *,
        style: Optional[str] = None,
        extra_hint: Optional[str] = None,
    ) -> dict:
        """Deep manga analysis: 角色 + 剧本 + 分镜（时刻/衣着/动作/神态/环境）.

        输入格式与 panels_to_script 相同（panel order + OCR 文字）。
        输出一个大 JSON，key 包括 characters / script / storyboard / notes 等。
        """
        user_payload = {
            "style": style or "日系动画",
            "extra_hint": extra_hint or "",
            "panel_count": len(panels),
            "panels": panels,
        }
        content = await self.chat(
            [
                {"role": "system", "content": SYSTEM_PANEL_ANALYZE_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            response_format_json=True,
        )
        result = self._safe_parse_json(content)
        storyboard = result.get("storyboard") or []
        characters = result.get("characters") or []
        logger.info(
            f"[LLM] panels_to_analysis done: input_panels={len(panels)}, "
            f"storyboard={len(storyboard)}, characters={len(characters)}, "
            f"keys={list(result.keys())}"
        )
        if not storyboard:
            logger.warning(
                f"[LLM] empty storyboard in analysis. raw (first 500): {content[:500]}"
            )
        return result

    @staticmethod
    def _safe_parse_json(text: str) -> dict:
        """Parse LLM output into dict, tolerating markdown fences / prefixes / suffixes
        / unescaped control characters inside string values.

        健壮性策略（按顺序尝试）：
          1) 去 markdown 代码围栏
          2) 截取首个 `{` 到末尾 `}` 之间的内容
          3) 严格 json.loads
          4) strict=False 容忍字符串里的 \\n \\t 等真实控制字符
          5) 用正则定位字符串字面量，把其中的真实控制字符替换成转义形式后再 parse
          6) 全部失败才抛 AdapterError
        """
        import re

        raw_input = text
        text = (text or "").strip()
        if not text:
            logger.warning("[LLM] _safe_parse_json received empty text")
            return {}

        # 1) 去 markdown 代码围栏 ```json ... ``` 或 ``` ... ```
        fence = re.match(r"^```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()

        # 2) 常见 LLM 在 JSON 前后加前言/说明，截取第一个 { 到最后一个 }
        if not text.startswith("{"):
            lb = text.find("{")
            rb = text.rfind("}")
            if lb != -1 and rb != -1 and rb > lb:
                text = text[lb : rb + 1]

        # 3) 严格 parse
        try:
            return json.loads(text)
        except json.JSONDecodeError as e_strict:
            first_err = e_strict

        # 4) 容忍字符串里的真实控制字符（\n \t \r 等）
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            pass

        # 5) 深度清洗：把 "..."  字符串字面量内的裸控制字符替换成合法转义
        try:
            cleaned = _escape_ctrl_inside_strings(text)
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 6) 再退一步：把全文的 \r\n \t 全替换掉再 strict=False 尝试一次
        try:
            fallback = (
                text.replace("\r\n", "\\n")
                    .replace("\r", "\\n")
                    .replace("\n", "\\n")
                    .replace("\t", "\\t")
            )
            return json.loads(fallback, strict=False)
        except json.JSONDecodeError:
            pass

        logger.error(f"LLM returned non-JSON (first 500): {text[:500]}")
        logger.error(f"LLM raw (first 300): {raw_input[:300] if raw_input else ''}")
        raise AdapterError(f"LLM returned invalid JSON: {first_err}") from first_err


def _escape_ctrl_inside_strings(s: str) -> str:
    """Walk through the JSON text and inside every "..." literal, escape raw
    control chars (<= 0x1F) to their JSON escaped form.

    这是针对 "LLM 在字符串值里直接写了真实换行" 场景的硬核修复。
    外部结构字符保持不变，只处理双引号包裹的字符串字面量内部。
    """
    out: list[str] = []
    in_str = False
    escape = False
    for ch in s:
        if in_str:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                out.append(ch)
                in_str = False
                continue
            code = ord(ch)
            if code <= 0x1F:
                # 常见控制字符走标准转义，其它用 \uXXXX
                if ch == "\n":
                    out.append("\\n")
                elif ch == "\r":
                    out.append("\\r")
                elif ch == "\t":
                    out.append("\\t")
                elif ch == "\b":
                    out.append("\\b")
                elif ch == "\f":
                    out.append("\\f")
                else:
                    out.append(f"\\u{code:04x}")
                continue
            out.append(ch)
        else:
            if ch == '"':
                in_str = True
            out.append(ch)
    return "".join(out)
