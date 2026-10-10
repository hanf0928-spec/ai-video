
"""TTS adapter - MiniMax t2a_v2 interface.

API: POST https://api.minimax.chat/v1/t2a_v2  (hex audio in response)
"""
from __future__ import annotations

import binascii
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ...core.config import settings
from ...core.exceptions import AdapterError
from ...core.logger import logger
from ...services.config_service import ensure_configured, get_config


class TTSAdapter:
    """Simple TTS adapter. MiniMax is default; can be extended."""

    name = "minimax"

    def __init__(
        self,
        api_key: Optional[str] = None,
        group_id: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        # TTS 从 UI 配置读取；显式传参时绕过 DB 校验
        if api_key:
            cfg: dict = {}
        else:
            cfg = ensure_configured("tts", "api_key")
        self.api_key = api_key or cfg.get("api_key") or ""
        self.group_id = group_id or cfg.get("group_id") or ""
        self.base_url = (base_url or cfg.get("base_url") or "https://api.minimax.chat/v1").rstrip("/")
        self._default_voice = cfg.get("default_voice") or "female-shaonv"
        self._default_speed = float(cfg.get("default_speed") or 1.0)
        self._client = httpx.AsyncClient(timeout=60.0)

    def _headers(self) -> dict:
        if not self.api_key:
            raise AdapterError("TTS API Key 未配置，请到「模型配置」页填写")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def synthesize(
        self,
        text: str,
        *,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        volume: float = 1.0,
        pitch: int = 0,
        emotion: Optional[str] = None,
        output_path: str | Path = "",
        sample_rate: int = 32000,
        audio_format: str = "mp3",
    ) -> str:
        """Synthesize `text` and write to `output_path`. Returns path."""
        voice = voice_id or self._default_voice
        payload = {
            "model": "speech-02-hd",
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice,
                "speed": speed,
                "vol": volume,
                "pitch": pitch,
            },
            "audio_setting": {
                "sample_rate": sample_rate,
                "bitrate": 128000,
                "format": audio_format,
                "channel": 1,
            },
        }
        if emotion:
            payload["voice_setting"]["emotion"] = emotion

        url = f"{self.base_url}/t2a_v2"
        if self.group_id:
            url += f"?GroupId={self.group_id}"
        logger.info(f"[TTS] synth voice={voice} text='{text[:40]}...'")
        r = await self._client.post(url, headers=self._headers(), json=payload)
        if r.status_code != 200:
            raise AdapterError(f"TTS failed: {r.status_code} {r.text}")
        data = r.json()
        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            raise AdapterError(f"TTS API error: {base_resp}")

        audio_hex = data.get("data", {}).get("audio", "")
        if not audio_hex:
            raise AdapterError("TTS returned empty audio")
        audio_bytes = binascii.unhexlify(audio_hex)

        out = Path(output_path) if output_path else settings.OUTPUT_DIR_PATH / "tts" / f"tts_{abs(hash(text)) % 10_000_000}.{audio_format}"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(audio_bytes)
        return str(out)
