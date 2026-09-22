"""
微软翻译接口

两种模式：
1. 免费模式（默认）：复用 Bing 翻译网页（bing.com/translator）的公开接口，
   无需 API Key，中国大陆可直接访问（cn.bing.com）。
2. Azure 模式：填写 Azure 翻译资源的 API Key（可选区域）后，
   使用官方 api.cognitive.microsofttranslator.com 接口。
"""
import asyncio
import json
import logging
import re
import time
from typing import Optional
from urllib.parse import urlencode

import aiohttp

from ..fanyi import (
    FanYiJieKou,
    TranslationServiceError,
    describe_connection_error,
    describe_http_status,
)
from ...version import APP_VERSION

logger = logging.getLogger(__name__)

SERVICE_NAME = "微软翻译"
ALTERNATIVES = "Achord 内置引擎"

_EDGE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
)

_IG_PATTERN = re.compile(r'IG:"([^"]+)"')
_IID_PATTERN = re.compile(r'data-iid="([^"]+)"')
_PARAMS_PATTERN = re.compile(r"params_AbusePreventionHelper\s*=\s*(\[[^\]]+\])")

# Bing 网页接口单次请求上限为 1000 字符；Azure 官方接口上限更大，这里保守拆分。
WEB_CHUNK_LIMIT = 1000
AZURE_CHUNK_LIMIT = 5000


def _is_cjk_char(char: str) -> bool:
    """中日韩文字及其全角标点：这些文字之间不需要空格分隔。"""
    if not char:
        return False
    code = ord(char)
    return (
        0x2E80 <= code <= 0x2FFF  # CJK 部首补充 / 康熙部首
        or 0x3000 <= code <= 0x303F  # CJK 标点（。、「」等）
        or 0x3040 <= code <= 0x30FF  # 平假名 / 片假名
        or 0x3100 <= code <= 0x312F  # 注音
        or 0x3400 <= code <= 0x4DBF  # CJK 扩展 A
        or 0x4E00 <= code <= 0x9FFF  # CJK 统一表意文字
        or 0xAC00 <= code <= 0xD7AF  # 谚文
        or 0xF900 <= code <= 0xFAFF  # CJK 兼容表意文字
        or 0xFF00 <= code <= 0xFFEF  # 全角 ASCII / 全角标点
        or 0x20000 <= code <= 0x3134F  # CJK 扩展 B-G
    )


def join_translated_chunks(parts: list[tuple[str, str, str]]) -> str:
    """把 (前导空白, 译文, 尾随空白) 列表拼回完整译文。

    源文本里的分段边界空白原样还原；若源边界没有空白（例如中文按“。”切分），
    而两侧译文都是非中日韩文字（如英文），则补一个空格，避免 “sentence.Next” 粘连。
    """
    result = ""
    for leading, translated, trailing in parts:
        segment = f"{leading}{translated}{trailing}"
        if not segment:
            continue
        if (
            result
            and not result[-1].isspace()
            and not segment[0].isspace()
            and not _is_cjk_char(result[-1])
            and not _is_cjk_char(segment[0])
        ):
            result += " "
        result += segment
    return result


def split_text_for_translation(text: str, limit: int) -> list[str]:
    """把长文本拆成不超过 limit 的片段，尽量在换行/句末/空格处切分。"""
    if limit <= 0 or len(text) <= limit:
        return [text] if text else []

    chunks: list[str] = []
    remaining = text
    separators = ("\n", "。", "！", "？", ". ", "! ", "? ", "；", "; ", "，", ", ", " ")
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = -1
        for separator in separators:
            position = window.rfind(separator)
            if position > limit // 4:
                cut = position + len(separator)
                break
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        chunks.append(remaining)
    return chunks


class MicrosoftAPI(FanYiJieKou):
    """微软翻译接口实现（Bing 网页免费接口 / Azure 官方接口）"""

    LANG_CODES = {
        "简体中文": "zh-Hans",
        "中文": "zh-Hans",
        "繁体中文": "zh-Hant",
        "英语": "en",
        "日语": "ja",
        "韩语": "ko",
        "法语": "fr",
        "德语": "de",
        "西班牙语": "es",
        "俄语": "ru",
        "意大利语": "it",
        "葡萄牙语": "pt",
        "越南语": "vi",
        "泰语": "th",
        "阿拉伯语": "ar",
        "自动检测": "auto-detect",
    }

    DETECTED_LANG_CODES = {
        "zh-Hans": "简体中文",
        "zh-Hant": "繁体中文",
        "zh": "简体中文",
        "en": "英语",
        "ja": "日语",
        "ko": "韩语",
        "fr": "法语",
        "de": "德语",
        "es": "西班牙语",
        "ru": "俄语",
        "it": "意大利语",
        "pt": "葡萄牙语",
        "pt-pt": "葡萄牙语",
        "vi": "越南语",
        "th": "泰语",
        "ar": "阿拉伯语",
    }

    WEB_ENTRY_URL = "https://www.bing.com/translator"
    AZURE_URL = "https://api.cognitive.microsofttranslator.com/translate"

    def __init__(self, api_key: str = "", region: str = ""):
        self.api_key = (api_key or "").strip()
        self.region = (region or "").strip()
        self.mode = "azure" if self.api_key else "web"

        self.session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=15)
        self._semaphore = asyncio.Semaphore(3)
        self._token_lock = asyncio.Lock()

        # Bing 网页会话参数
        self._host = "www.bing.com"
        self._ig: Optional[str] = None
        self._iid: Optional[str] = None
        self._key: Optional[int] = None
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

        self._cache: dict[str, tuple[str, Optional[str]]] = {}
        self._cache_size = 1000

    # ------------------------------------------------------------------
    # 通用
    # ------------------------------------------------------------------
    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            headers = {
                "User-Agent": _EDGE_UA,
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            if self.mode == "azure":
                headers["Ocp-Apim-Subscription-Key"] = self.api_key
                if self.region:
                    headers["Ocp-Apim-Subscription-Region"] = self.region
                headers["User-Agent"] = f"DaZuoFanYiGuan/{APP_VERSION}"
            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=self._timeout,
                trust_env=True,
            )
        return self.session

    def _describe(self, error: Exception) -> TranslationServiceError:
        return describe_connection_error(
            error,
            SERVICE_NAME,
            overseas_required=False,
            alternatives=ALTERNATIVES,
        )

    @staticmethod
    def _status_error(status: int, detail: str = "") -> TranslationServiceError:
        return describe_http_status(
            status,
            SERVICE_NAME,
            overseas_required=False,
            alternatives=ALTERNATIVES,
            detail=detail,
        )

    @staticmethod
    def parse_translation_response(data) -> tuple[str, Optional[str]]:
        """解析 Bing 网页接口与 Azure 官方接口共用的响应格式。

        [{"detectedLanguage": {"language": "en"}, "translations": [{"text": "...", "to": "zh-Hans"}]}]
        """
        if isinstance(data, dict):
            # 网页接口令牌过期/被拒时会返回 {"statusCode": 205/400/...}
            status = data.get("statusCode") or data.get("StatusCode")
            if status:
                raise TranslationServiceError(
                    f"{SERVICE_NAME}返回状态 {status}。",
                    kind="server",
                    short="令牌过期" if int(status) == 205 else "服务异常",
                )
            error = data.get("error")
            if isinstance(error, dict):
                raise TranslationServiceError(
                    f"{SERVICE_NAME}返回错误：{error.get('message') or error}",
                    kind="server",
                )
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise TranslationServiceError(f"{SERVICE_NAME}返回了无法识别的结果。", kind="server")
        item = data[0]
        translations = item.get("translations") or []
        if not translations:
            raise TranslationServiceError(f"{SERVICE_NAME}未返回翻译结果。", kind="server")
        translated = str(translations[0].get("text") or "")
        detected = None
        detected_info = item.get("detectedLanguage")
        if isinstance(detected_info, dict):
            detected = detected_info.get("language") or None
        return translated, detected

    @staticmethod
    def parse_web_page(html: str) -> tuple[str, str, int, str, int]:
        """从 Bing 翻译页面提取 IG、IID、key、token 和有效期（毫秒）。"""
        ig_match = _IG_PATTERN.search(html or "")
        iid_match = _IID_PATTERN.search(html or "")
        params_match = _PARAMS_PATTERN.search(html or "")
        if not (ig_match and iid_match and params_match):
            raise TranslationServiceError(
                f"{SERVICE_NAME}页面结构已变化，暂时无法获取访问令牌，请稍后重试或改用{ALTERNATIVES}。",
                kind="server",
                short="令牌获取失败",
            )
        try:
            params = json.loads(params_match.group(1))
            key = int(params[0])
            token = str(params[1])
            expiry_ms = int(params[2]) if len(params) > 2 else 3600000
        except (ValueError, TypeError, IndexError, json.JSONDecodeError) as error:
            raise TranslationServiceError(
                f"{SERVICE_NAME}访问令牌解析失败，请稍后重试。",
                kind="server",
                short="令牌获取失败",
            ) from error
        return ig_match.group(1), iid_match.group(1), key, token, expiry_ms

    # ------------------------------------------------------------------
    # 免费网页模式
    # ------------------------------------------------------------------
    def _web_token_valid(self) -> bool:
        return bool(self._token and self._ig and self._iid) and time.monotonic() < self._token_expires_at

    async def _refresh_web_token(self, force: bool = False) -> None:
        async with self._token_lock:
            if not force and self._web_token_valid():
                return
            session = await self._ensure_session()
            try:
                async with session.get(self.WEB_ENTRY_URL, allow_redirects=True) as response:
                    if response.status != 200:
                        raise self._status_error(response.status)
                    html = await response.text()
                    host = response.url.host or "www.bing.com"
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                raise self._describe(error) from error

            ig, iid, key, token, expiry_ms = self.parse_web_page(html)
            self._host = host
            self._ig = ig
            self._iid = iid
            self._key = key
            self._token = token
            # 提前 60 秒过期，避免边界抖动
            self._token_expires_at = time.monotonic() + max(60.0, expiry_ms / 1000.0 - 60.0)
            logger.info("微软翻译（Bing 网页）令牌已刷新，host=%s", host)

    def _web_translate_url(self) -> str:
        query = urlencode({"isVertical": "1", "IG": self._ig or "", "IID": self._iid or ""})
        return f"https://{self._host}/ttranslatev3?{query}"

    async def _translate_web_chunk(self, text: str, source_code: str, target_code: str) -> tuple[str, Optional[str]]:
        await self._refresh_web_token()
        session = await self._ensure_session()
        for attempt in range(2):
            form = {
                "fromLang": source_code,
                "to": target_code,
                "text": text,
                "token": self._token or "",
                "key": str(self._key or ""),
                "tryFetchingGenderDebiasedTranslations": "true",
            }
            headers = {
                "Referer": f"https://{self._host}/translator",
                "Origin": f"https://{self._host}",
            }
            try:
                async with session.post(self._web_translate_url(), data=form, headers=headers) as response:
                    body = await response.text()
                    if response.status in (200, 205) and not body.strip():
                        # 空响应通常代表令牌失效，刷新后重试一次
                        if attempt == 0:
                            await self._refresh_web_token(force=True)
                            continue
                        raise TranslationServiceError(
                            f"{SERVICE_NAME}未返回结果，请稍后重试。",
                            kind="server",
                        )
                    if response.status != 200:
                        raise self._status_error(response.status)
                    try:
                        data = json.loads(body)
                    except json.JSONDecodeError as error:
                        raise TranslationServiceError(
                            f"{SERVICE_NAME}返回了无法识别的结果。",
                            kind="server",
                        ) from error
                    try:
                        return self.parse_translation_response(data)
                    except TranslationServiceError as error:
                        if attempt == 0 and getattr(error, "short", "") == "令牌过期":
                            await self._refresh_web_token(force=True)
                            continue
                        raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                raise self._describe(error) from error
        raise TranslationServiceError(f"{SERVICE_NAME}请求失败，请稍后重试。", kind="server")

    # ------------------------------------------------------------------
    # Azure 官方模式
    # ------------------------------------------------------------------
    async def _translate_azure_chunk(self, text: str, source_code: str, target_code: str) -> tuple[str, Optional[str]]:
        session = await self._ensure_session()
        params = {"api-version": "3.0", "to": target_code}
        if source_code and source_code != "auto-detect":
            params["from"] = source_code
        try:
            async with session.post(self.AZURE_URL, params=params, json=[{"Text": text}]) as response:
                if response.status != 200:
                    detail = ""
                    try:
                        payload = await response.json(content_type=None)
                        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
                            detail = str(payload["error"].get("message") or "")[:200]
                    except Exception:
                        pass
                    raise self._status_error(response.status, detail)
                data = await response.json(content_type=None)
                return self.parse_translation_response(data)
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise self._describe(error) from error

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    async def _translate_text(self, text: str, source_code: str, target_code: str) -> tuple[str, Optional[str]]:
        limit = AZURE_CHUNK_LIMIT if self.mode == "azure" else WEB_CHUNK_LIMIT
        translate_chunk = self._translate_azure_chunk if self.mode == "azure" else self._translate_web_chunk
        parts: list[tuple[str, str, str]] = []
        detected: Optional[str] = None
        for chunk in split_text_for_translation(text, limit):
            core = chunk.strip()
            if not core:
                parts.append(("", chunk, ""))
                continue
            # 服务端通常会去掉译文首尾空白，分段边界的空格/换行由这里单独保留并还原；
            # 源边界没有空白而译文需要（如中文→英文）时，由 join_translated_chunks 补空格。
            leading = chunk[: len(chunk) - len(chunk.lstrip())]
            trailing = chunk[len(chunk.rstrip()):]
            translated, chunk_detected = await translate_chunk(core, source_code, target_code)
            parts.append((leading, translated.strip(), trailing))
            if detected is None and chunk_detected:
                detected = chunk_detected
        return join_translated_chunks(parts).strip(), detected

    async def fanyi(self, text: str, source_lang: str, target_lang: str) -> tuple[str, Optional[str]]:
        if not text:
            return "", None

        target_code = self.LANG_CODES.get(target_lang)
        if not target_code or target_code == "auto-detect":
            raise TranslationServiceError(
                f"{SERVICE_NAME}暂不支持目标语言：{target_lang}",
                kind="config",
                short="语言不支持",
            )
        source_code = self.LANG_CODES.get(source_lang, "auto-detect")

        cache_key = f"{text}|{source_code}|{target_code}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        async with self._semaphore:
            translated, detected = await self._translate_text(text, source_code, target_code)

        logger.info("微软翻译检测到的语言: %s", detected)
        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[cache_key] = (translated, detected)
        return translated, detected

    async def close(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None

    async def health_check(self) -> None:
        translated, _ = await self._translate_text("hello", "en", "zh-Hans")
        if not translated:
            raise TranslationServiceError(
                f"{SERVICE_NAME}健康检查返回空结果，请稍后重试或改用{ALTERNATIVES}。",
                kind="server",
            )
