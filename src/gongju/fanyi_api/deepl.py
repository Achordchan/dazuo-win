import asyncio
import logging
from typing import Optional

import aiohttp

from ..fanyi import FanYiJieKou
from ...version import APP_VERSION

logger = logging.getLogger(__name__)


def infer_deepl_plan(api_key: str) -> str:
    return "free" if (api_key or "").strip().endswith(":fx") else "pro"


def deepl_base_url_for_plan(plan: str) -> str:
    return "https://api-free.deepl.com" if plan == "free" else "https://api.deepl.com"


async def read_deepl_json(response: aiohttp.ClientResponse) -> dict:
    try:
        data = await response.json(content_type=None)
        return data if isinstance(data, dict) else {}
    except Exception:
        body = await response.text()
        return {"message": body.strip()[:500]}


async def verify_deepl_auth(api_key: str) -> dict:
    api_key = (api_key or "").strip()
    if not api_key:
        raise ValueError("未设置DeepL API密钥")

    plan = infer_deepl_plan(api_key)
    base_url = deepl_base_url_for_plan(plan)
    timeout = aiohttp.ClientTimeout(total=12, connect=6, sock_read=8)
    headers = {
        "Authorization": f"DeepL-Auth-Key {api_key}",
        "Accept": "application/json",
        "User-Agent": f"DaZuoFanYiGuan/{APP_VERSION}",
    }
    async with aiohttp.ClientSession(headers=headers, timeout=timeout, trust_env=True) as session:
        async with session.get(f"{base_url}/v2/usage") as response:
            data = await read_deepl_json(response)
            if response.status != 200:
                message = data.get("message", "")
                raise ValueError(f"DeepL认证失败: HTTP {response.status} {message}".strip())
            return {"plan": plan, "base_url": base_url, "usage": data}


class DeepLAPI(FanYiJieKou):
    DETECTED_LANG_CODES = {
        "ZH": "简体中文",
        "EN": "英语",
        "JA": "日语",
        "KO": "韩语",
        "FR": "法语",
        "DE": "德语",
        "ES": "西班牙语",
        "RU": "俄语",
        "IT": "意大利语",
        "PT": "葡萄牙语",
        "VI": "越南语",
        "TH": "泰语",
        "AR": "阿拉伯语",
    }

    TARGET_LANG_CODES = {
        "简体中文": "ZH-HANS",
        "繁体中文": "ZH-HANT",
        "英语": "EN-US",
        "日语": "JA",
        "韩语": "KO",
        "法语": "FR",
        "德语": "DE",
        "西班牙语": "ES",
        "俄语": "RU",
        "意大利语": "IT",
        "葡萄牙语": "PT-PT",
        "越南语": "VI",
        "泰语": "TH",
        "阿拉伯语": "AR",
        "自动检测": None,
    }

    SOURCE_LANG_CODES = {
        "简体中文": "ZH",
        "繁体中文": "ZH",
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
        "自动检测": None,
    }

    def __init__(self, api_key: str):
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise ValueError("未设置DeepL API密钥")

        self.plan = infer_deepl_plan(self.api_key)
        self.base_url = deepl_base_url_for_plan(self.plan)
        self.session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=15)
        self._semaphore = asyncio.Semaphore(3)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"DeepL-Auth-Key {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": f"DaZuoFanYiGuan/{APP_VERSION}",
                },
                timeout=self._timeout,
                trust_env=True,
            )
        return self.session

    async def fanyi(self, text: str, source_lang: str, target_lang: str) -> tuple[str, Optional[str]]:
        if not text:
            return "", None

        target_code = self.TARGET_LANG_CODES.get(target_lang)
        if not target_code:
            raise ValueError(f"DeepL暂不支持目标语言：{target_lang}")

        source_code = self.SOURCE_LANG_CODES.get(source_lang)
        payload = {
            "text": [text],
            "target_lang": target_code,
            "preserve_formatting": True,
        }
        if source_code:
            payload["source_lang"] = source_code

        async with self._semaphore:
            session = await self._ensure_session()
            try:
                async with session.post(f"{self.base_url}/v2/translate", json=payload) as response:
                    data = await read_deepl_json(response)
                    if response.status != 200:
                        message = data.get("message", "")
                        raise ValueError(f"DeepL翻译失败: HTTP {response.status} {message}".strip())

                    translations = data.get("translations", [])
                    if not translations:
                        raise ValueError("DeepL未返回翻译结果")

                    translated = translations[0].get("text", "")
                    detected = translations[0].get("detected_source_language")
                    logger.info("DeepL检测到的语言: %s", detected)
                    return translated.strip(), detected
            except aiohttp.ClientConnectorError as error:
                raise ValueError("无法连接到 DeepL 服务，请检查网络连接或代理设置") from error
            except aiohttp.ClientError as error:
                raise ValueError(f"DeepL网络错误: {error}") from error

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def health_check(self) -> None:
        await verify_deepl_auth(self.api_key)
