import asyncio
import json
import logging
import re
from typing import Dict, Optional

import aiohttp

from ..fanyi import FanYiJieKou

logger = logging.getLogger(__name__)


class AchordAPI(FanYiJieKou):
    BASE_URL = "https://api.translate.zvo.cn"
    LANGUAGE_ENDPOINT = "/language.json"
    HEALTH_ENDPOINT = "/index.do"
    TRANSLATE_ENDPOINT = "/translate.json"
    _NL_MARKER = "[[DAZUO_NL]]"
    _NL_SPLIT_RE = re.compile(r"\s*\[\[DAZUO_NL\]\]\s*")

    LANG_CODE_CANDIDATES = {
        "简体中文": ["zh-cn", "zh", "zh-hans", "chs"],
        "繁体中文": ["zh-tw", "zh-hant", "cht", "zh-hk"],
        "英语": ["english", "en"],
        "日语": ["japanese", "ja"],
        "韩语": ["korean", "ko"],
        "法语": ["french", "fr"],
        "德语": ["german", "de"],
        "西班牙语": ["spanish", "es"],
        "俄语": ["russian", "ru"],
        "意大利语": ["italian", "it"],
        "葡萄牙语": ["portuguese", "pt"],
        "越南语": ["vietnamese", "vi"],
        "泰语": ["thai", "th"],
        "阿拉伯语": ["arabic", "ar"],
        "自动检测": ["auto"],
    }

    LANG_CODES = {
        "简体中文": "zh-cn",
        "繁体中文": "zh-tw",
        "英语": "english",
        "日语": "japanese",
        "韩语": "korean",
        "法语": "french",
        "德语": "german",
        "西班牙语": "spanish",
        "俄语": "russian",
        "意大利语": "italian",
        "葡萄牙语": "portuguese",
        "越南语": "vietnamese",
        "泰语": "thai",
        "阿拉伯语": "arabic",
        "自动检测": "auto",
    }

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=12, connect=6, sock_read=6)
        self._lang_id_map: Optional[Dict[str, str]] = None
        self._id_to_service: Optional[Dict[str, str]] = None
        self._lang_lock = asyncio.Lock()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout, trust_env=True)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    def _norm(self, value: Optional[str]) -> str:
        return (value or "").strip().lower().replace(" ", "")

    async def _load_languages(self) -> None:
        if self._lang_id_map is not None:
            return

        async with self._lang_lock:
            if self._lang_id_map is not None:
                return

            session = await self._ensure_session()
            url = f"{self.BASE_URL}{self.LANGUAGE_ENDPOINT}"
            async with session.get(url) as response:
                if response.status != 200:
                    raise ValueError(f"语言列表获取失败: HTTP {response.status}")
                data = await response.json(content_type=None)

            if data.get("result") != 1:
                raise ValueError(data.get("info") or "语言列表获取失败")

            lang_map: Dict[str, str] = {}
            id_to_service: Dict[str, str] = {}

            for item in data.get("list", []):
                lang_id = self._norm(item.get("id"))
                name = self._norm(item.get("name"))
                service_id = self._norm(item.get("serviceId"))

                if lang_id:
                    id_to_service[lang_id] = service_id or lang_id
                if name and lang_id:
                    lang_map[name] = lang_id
                if service_id and lang_id:
                    lang_map[service_id] = lang_id
                if lang_id:
                    lang_map[lang_id] = lang_id

            self._lang_id_map = lang_map
            self._id_to_service = id_to_service

    async def _resolve_language_id(self, lang: str) -> str:
        if not lang or lang in ("auto", "自动检测"):
            return "auto"

        await self._load_languages()
        lang_map = self._lang_id_map or {}

        for candidate in self.LANG_CODE_CANDIDATES.get(lang, [lang]):
            key = self._norm(candidate)
            if key in lang_map:
                return lang_map[key]

        fallback = self._norm(lang)
        if fallback in lang_map:
            return lang_map[fallback]

        raise ValueError(f"不支持的语言: {lang}")

    async def health_check(self) -> None:
        session = await self._ensure_session()
        url = f"{self.BASE_URL}{self.HEALTH_ENDPOINT}"
        async with session.get(url) as response:
            text = await response.text()
            if response.status != 200 or "SUCCESS" not in text:
                raise ValueError("连接失败")

    def _map_detected_language(self, raw_code: Optional[str]) -> Optional[str]:
        if not raw_code or raw_code == "auto":
            return None
        if self._id_to_service is None:
            return raw_code
        key = self._norm(raw_code)
        return self._id_to_service.get(key, raw_code)

    async def fanyi(self, text: str, source_lang: str, target_lang: str):
        if not text:
            return "", None

        from_id = await self._resolve_language_id(source_lang)
        to_id = await self._resolve_language_id(target_lang)

        use_marker_split = self._NL_MARKER in text
        if use_marker_split:
            parts = self._NL_SPLIT_RE.split(text)
            text_payload = [part for part in parts]
        else:
            parts = [text]
            text_payload = parts

        payload = {
            "from": from_id,
            "to": to_id,
            "text": json.dumps(text_payload, ensure_ascii=False),
        }

        session = await self._ensure_session()
        url = f"{self.BASE_URL}{self.TRANSLATE_ENDPOINT}"
        async with session.post(url, data=payload) as response:
            if response.status != 200:
                raise ValueError(f"翻译失败: HTTP {response.status}")
            data = await response.json(content_type=None)

        if data.get("result") != 1:
            raise ValueError(data.get("info") or "翻译失败")

        results = data.get("text") or []
        translated_parts = results if isinstance(results, list) else []
        if len(translated_parts) < len(parts):
            translated_parts += [""] * (len(parts) - len(translated_parts))

        if use_marker_split:
            translated = f" {self._NL_MARKER} ".join(part.strip() for part in translated_parts[: len(parts)])
        else:
            translated = translated_parts[0] if translated_parts else ""
        detected = self._map_detected_language(data.get("from"))
        return translated.strip(), detected
