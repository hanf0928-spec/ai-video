
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

    @staticmethod
    def _safe_parse_json(text: str) -> dict:
        """Parse LLM output into dict, tolerating markdown fences / prefixes / suffixes."""
        import re

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

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned non-JSON: {text[:300]}")
            raise AdapterError(f"LLM returned invalid JSON: {e}") from e
