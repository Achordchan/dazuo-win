import asyncio
import logging
from typing import Optional

import aiohttp

from ..achord_engine import AchordEngineManager
from ..fanyi import FanYiJieKou
from ...version import APP_VERSION

logger = logging.getLogger(__name__)


class AchordBuiltinAPI(FanYiJieKou):
    LANG_CODES = {
        "简体中文": "ZH",
        "中文": "ZH",
        "繁体中文": "ZH-HANT",
        "英语": "EN",
        "日语": "JA",
        "韩语": "KO",
        "法语": "FR",
        "德语": "DE",
        "西班牙语": "ES",
        "俄语": "RU",
        "意大利语": "IT",
        "葡萄牙语": "PT",
        "越南语": "VI",
        "泰语": None,
        "阿拉伯语": "AR",
        "自动检测": "auto",
    }

    TARGET_LANG_CODES = {
        **LANG_CODES,
        "简体中文": "ZH",
        "中文": "ZH",
        "繁体中文": "ZH-HANT",
        "英语": "EN-US",
        "葡萄牙语": "PT-BR",
        "自动检测": None,
        "泰语": None,
    }

    SOURCE_LANG_CODES = {
        **LANG_CODES,
        "自动检测": "auto",
    }

    def __init__(self, manager: Optional[AchordEngineManager] = None):
        self.manager = manager or AchordEngineManager()
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_key = ""
        self._timeout = aiohttp.ClientTimeout(total=25, connect=8, sock_read=20)
        self._semaphore = asyncio.Semaphore(3)

    async def _ensure_ready(self) -> aiohttp.ClientSession:
        await self.manager.ensure_started()
        if self.session is not None and not self.session.closed and self.api_key != self.manager.token:
            await self.session.close()
            self.session = None
        if self.session is None or self.session.closed:
            self.api_key = self.manager.token
            self.session = aiohttp.ClientSession(
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.manager.token}",
                    "User-Agent": f"DaZuoFanYiGuan/{APP_VERSION}",
                },
                timeout=self._timeout,
                trust_env=True,
            )
        return self.session

    def _translate_url(self) -> str:
        return f"{self.manager.base_url}/translate"

    async def _read_json(self, response: aiohttp.ClientResponse) -> dict:
        try:
            data = await response.json(content_type=None)
            return data if isinstance(data, dict) else {"data": data}
        except Exception:
            body = await response.text()
            return {"message": body.strip()[:500]}

    def _extract_translation(self, data: dict) -> str:
        value = data.get("data")
        if isinstance(value, str):
            return value
        for key in ("text", "translation", "result", "translated_text", "dst", "Dst"):
            value = data.get(key)
            if isinstance(value, str):
                return value
        return ""

    async def fanyi(self, text: str, source_lang: str, target_lang: str) -> tuple[str, Optional[str]]:
        if not text:
            return "", None

        target_code = self.TARGET_LANG_CODES.get(target_lang)
        if not target_code:
            raise ValueError(f"Achord 内置引擎暂不支持目标语言：{target_lang}")

        source_code = self.SOURCE_LANG_CODES.get(source_lang, "auto")
        if source_code is None:
            raise ValueError(f"Achord 内置引擎暂不支持源语言：{source_lang}")

        payload = {
            "text": text,
            "source_lang": source_code or "auto",
            "target_lang": target_code,
        }

        async with self._semaphore:
            session = await self._ensure_ready()
            try:
                async with session.post(self._translate_url(), json=payload) as response:
                    data = await self._read_json(response)
                    if response.status != 200:
                        message = data.get("message") or data.get("msg") or data.get("error") or ""
                        raise ValueError(f"Achord 内置引擎翻译失败: HTTP {response.status} {message}".strip())

                    code = data.get("code")
                    if code not in (None, 0, 200):
                        message = data.get("message") or data.get("msg") or data.get("error") or ""
                        raise ValueError(f"Achord 内置引擎翻译失败: {code} {message}".strip())

                    translated = self._extract_translation(data)
                    if not translated:
                        raise ValueError("Achord 内置引擎未返回翻译结果")

                    detected = data.get("source_lang") or data.get("detected_source_language")
                    logger.info("Achord 内置引擎检测到的语言: %s", detected)
                    return translated.strip(), detected
            except aiohttp.ClientConnectorError as error:
                raise ValueError("无法连接到 Achord 内置引擎，请重新选择翻译服务或更新内置引擎") from error
            except aiohttp.ClientError as error:
                raise ValueError(f"Achord 内置引擎网络错误: {error}") from error

    async def health_check(self) -> None:
        await self.fanyi("test", "自动检测", "简体中文")

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None
        self.manager.stop()
