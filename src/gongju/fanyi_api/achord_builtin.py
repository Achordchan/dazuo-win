import asyncio
import logging
import math
import time
from typing import ClassVar, Optional

import aiohttp

from ..achord_engine import AchordEngineManager
from ..fanyi import FanYiJieKou
from ...version import APP_VERSION

logger = logging.getLogger(__name__)


class AchordBuiltinAPI(FanYiJieKou):
    DETECTED_LANG_CODES = {
        "ZH": "简体中文",
        "ZH-HANS": "简体中文",
        "ZH-HANT": "繁体中文",
        "EN": "英语",
        "EN-US": "英语",
        "JA": "日语",
        "KO": "韩语",
        "FR": "法语",
        "DE": "德语",
        "ES": "西班牙语",
        "RU": "俄语",
        "IT": "意大利语",
        "PT": "葡萄牙语",
        "PT-BR": "葡萄牙语",
        "VI": "越南语",
        "TH": "泰语",
        "AR": "阿拉伯语",
    }

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
        "泰语": "TH",
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
        "泰语": "TH",
    }

    SOURCE_LANG_CODES = {
        **LANG_CODES,
        "自动检测": "auto",
    }

    # Shared across instances so mini window / main window / reconnect all honor
    # the same DeepLX/IP ban cooldown window.
    _shared_rate_limit_until: ClassVar[float] = 0.0
    # Free upstream often bans the IP for longer than a few seconds.
    _rate_limit_cooldown_s: ClassVar[float] = 60.0

    def __init__(self, manager: Optional[AchordEngineManager] = None):
        self.manager = manager or AchordEngineManager()
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_key = ""
        self._timeout = aiohttp.ClientTimeout(total=25, connect=8, sock_read=20)
        # Single in-flight translate reduces 429 storms while typing / double-copying.
        self._semaphore = asyncio.Semaphore(1)

    @classmethod
    def rate_limit_remaining_s(cls) -> float:
        return max(0.0, float(cls._shared_rate_limit_until) - time.monotonic())

    @classmethod
    def note_rate_limited(cls, cooldown_s: Optional[float] = None) -> float:
        wait_s = float(cls._rate_limit_cooldown_s if cooldown_s is None else cooldown_s)
        wait_s = max(1.0, wait_s)
        cls._shared_rate_limit_until = max(cls._shared_rate_limit_until, time.monotonic() + wait_s)
        return wait_s

    def _raise_if_rate_limited(self) -> None:
        remaining = self.rate_limit_remaining_s()
        if remaining <= 0:
            return
        seconds = max(1, int(math.ceil(remaining)))
        raise ValueError(f"Achord 内置引擎请求过于频繁，请 {seconds} 秒后再试")

    @staticmethod
    def _looks_like_rate_limit(status: Optional[int], message: str) -> bool:
        if status == 429:
            return True
        text = str(message or "").lower()
        return (
            "429" in text
            or "too many requests" in text
            or "rate limit" in text
            or "ratelimit" in text
            or "请求过于频繁" in str(message or "")
        )

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
                trust_env=False,
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

        # Enforce cooldown for every entry path (main window, mini, double-copy).
        self._raise_if_rate_limited()

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
            # Re-check after waiting for the semaphore; another call may have been banned.
            self._raise_if_rate_limited()
            session = await self._ensure_ready()
            try:
                async with session.post(self._translate_url(), json=payload) as response:
                    data = await self._read_json(response)
                    message = data.get("message") or data.get("msg") or data.get("error") or ""
                    if response.status != 200:
                        if self._looks_like_rate_limit(response.status, str(message)):
                            wait_s = self.note_rate_limited()
                            seconds = max(1, int(math.ceil(wait_s)))
                            raise ValueError(
                                f"Achord 内置引擎请求过于频繁（HTTP {response.status}），"
                                f"已暂停 {seconds} 秒，请稍后再试"
                            )
                        raise ValueError(
                            f"Achord 内置引擎翻译失败: HTTP {response.status} {message}".strip()
                        )

                    code = data.get("code")
                    if code not in (None, 0, 200):
                        if self._looks_like_rate_limit(None, f"{code} {message}"):
                            wait_s = self.note_rate_limited()
                            seconds = max(1, int(math.ceil(wait_s)))
                            raise ValueError(
                                f"Achord 内置引擎请求过于频繁，已暂停 {seconds} 秒，请稍后再试"
                            )
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
        """Prove the local engine is up without spending a real translate quota.

        ensure_started already waits until the process accepts loopback TCP.
        We then open an authorized HTTP session and confirm the process is still
        alive. A full /translate call is reserved for actual user translations.
        """
        await self._ensure_ready()
        process = getattr(self.manager, "process", None)
        if process is None or process.poll() is not None:
            raise ValueError("Achord 内置引擎未运行")
        port = getattr(self.manager, "port", None)
        if not port:
            raise ValueError("Achord 内置引擎端口不可用")
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", int(port))
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        except Exception as error:
            raise ValueError(f"无法连接到 Achord 内置引擎: {error}") from error

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None
        self.manager.stop()
