"""
Google翻译接口
使用非官方的 Google Translate 网页接口。

Google 在中国大陆无法直接访问，需要能访问海外网站的网络。
主接口 translate.googleapis.com 对部分代理出口 IP 会返回 HTTP 429 "Sorry" 页面，
因此这里额外实现了 clients5.google.com 备用接口，两者任一可用即可翻译。
"""
import aiohttp
import ssl
import certifi
from typing import Optional
import asyncio
import logging

from ..fanyi import (
    FanYiJieKou,
    TranslationServiceError,
    describe_connection_error,
    describe_http_status,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "Google 翻译"
ALTERNATIVES = "微软翻译或 Achord 内置引擎"


class GoogleAPI(FanYiJieKou):
    """Google翻译接口实现"""

    # 语言代码映射
    LANG_CODES = {
        "简体中文": "zh-CN",
        "繁体中文": "zh-TW",
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
        "自动检测": "auto"
    }

    PRIMARY_URL = "https://translate.googleapis.com/translate_a/single"
    FALLBACK_URL = "https://clients5.google.com/translate_a/t"

    def __init__(self):
        """初始化"""
        self.base_url = self.PRIMARY_URL
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://translate.google.com/"
        }

        # 缓存设置
        self._cache = {}
        self._cache_size = 1000

        # 连接设置
        self._timeout = aiohttp.ClientTimeout(
            total=10,
            connect=5,
            sock_read=5
        )
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())

        # 并发控制
        self._semaphore = asyncio.Semaphore(5)

        # 主接口被拒绝（429/403）后优先使用备用接口
        self._prefer_fallback = False

        self.session = None

    async def _ensure_session(self):
        """确保会话存在"""
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                force_close=False,
                enable_cleanup_closed=True,
                keepalive_timeout=30.0,
                ttl_dns_cache=300,
                ssl=self._ssl_context
            )

            self.session = aiohttp.ClientSession(
                headers=self.headers,
                connector=connector,
                timeout=self._timeout,
                trust_env=True
            )
        return self.session

    # ------------------------------------------------------------------
    # 响应解析（纯函数，便于测试）
    # ------------------------------------------------------------------
    @staticmethod
    def parse_primary_response(data) -> tuple[str, Optional[str]]:
        """解析 translate_a/single 的响应。"""
        if not data or not isinstance(data, list) or not isinstance(data[0], list):
            raise TranslationServiceError(f"{SERVICE_NAME}返回了无法识别的结果。", kind="server")
        translated_text = ""
        for item in data[0]:
            if item and item[0]:
                translated_text += item[0]
        detected_lang = None
        if len(data) > 2 and isinstance(data[2], str):
            detected_lang = data[2]
        elif len(data) > 8 and data[8] and isinstance(data[8][0], list):
            detected_lang = data[8][0][0]
        return translated_text.strip(), detected_lang

    @staticmethod
    def parse_fallback_response(data, source_is_auto: bool) -> tuple[str, Optional[str]]:
        """解析 clients5 translate_a/t 的响应。

        sl=auto 时返回 [[译文, 检测语言]]；指定 sl 时返回 [译文]。
        """
        if not data or not isinstance(data, list):
            raise TranslationServiceError(f"{SERVICE_NAME}返回了无法识别的结果。", kind="server")
        first = data[0]
        if isinstance(first, list):
            translated = str(first[0]) if first else ""
            detected = str(first[1]) if len(first) > 1 and first[1] else None
            return translated.strip(), detected
        if isinstance(first, str):
            return first.strip(), None
        raise TranslationServiceError(f"{SERVICE_NAME}返回了无法识别的结果。", kind="server")

    @staticmethod
    def _status_error(status: int) -> TranslationServiceError:
        return describe_http_status(
            status,
            SERVICE_NAME,
            overseas_required=True,
            alternatives=ALTERNATIVES,
        )

    # ------------------------------------------------------------------
    # 请求
    # ------------------------------------------------------------------
    async def _request_primary(self, session, text: str, source_code: str, target_code: str):
        params = {
            "client": "gtx",
            "sl": source_code,
            "tl": target_code,
            "dt": ["t", "ld"],
            "q": text,
        }
        async with session.get(self.PRIMARY_URL, params=params) as response:
            if response.status != 200:
                raise self._status_error(response.status)
            data = await response.json(content_type=None)
            return self.parse_primary_response(data)

    async def _request_fallback(self, session, text: str, source_code: str, target_code: str):
        params = {
            "client": "dict-chrome-ex",
            "sl": source_code,
            "tl": target_code,
            "q": text,
        }
        async with session.get(self.FALLBACK_URL, params=params) as response:
            if response.status != 200:
                raise self._status_error(response.status)
            data = await response.json(content_type=None)
            return self.parse_fallback_response(data, source_code == "auto")

    async def _translate_with_fallback(self, text: str, source_code: str, target_code: str):
        """先尝试首选接口，被拒绝或出错时切换到另一接口。"""
        session = await self._ensure_session()
        order = (
            ("fallback", "primary") if self._prefer_fallback else ("primary", "fallback")
        )
        requests = {"primary": self._request_primary, "fallback": self._request_fallback}
        first_error: Optional[Exception] = None
        for index, endpoint in enumerate(order):
            request = requests[endpoint]
            try:
                result = await request(session, text, source_code, target_code)
                if index == 1:
                    # 第二个接口成功，后续请求直接走它，减少无效请求
                    self._prefer_fallback = endpoint == "fallback"
                return result
            except (TranslationServiceError, aiohttp.ClientError, asyncio.TimeoutError) as error:
                described = describe_connection_error(
                    error,
                    SERVICE_NAME,
                    overseas_required=True,
                    alternatives=ALTERNATIVES,
                )
                logger.warning(
                    "Google 翻译%s接口失败: %s",
                    "备用" if endpoint == "fallback" else "主",
                    described,
                )
                if first_error is None:
                    first_error = described
                # 一个域名超时/连不上不代表另一个也不通（分流代理、DNS 故障、单点故障），
                # 继续尝试另一接口；两者都失败时报告首个错误。
        assert first_error is not None
        raise first_error

    async def fanyi(self, text: str, source_lang: str, target_lang: str) -> tuple[str, Optional[str]]:
        """执行翻译"""
        if not text:
            return "", None

        # 检查缓存
        cache_key = f"{text}|{source_lang}|{target_lang}"
        if cache_key in self._cache:
            return self._cache[cache_key], None

        async with self._semaphore:  # 使用信号量控制并发
            source_code = self.LANG_CODES.get(source_lang, "auto")
            target_code = self.LANG_CODES.get(target_lang, "zh-CN")
            translated_text, detected_lang = await self._translate_with_fallback(
                text, source_code, target_code
            )

        logger.info(f"检测到的语言: {detected_lang}")

        # 缓存结果
        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[cache_key] = translated_text

        return translated_text, detected_lang

    async def close(self):
        """关闭会话"""
        if self.session:
            await self.session.close()
            self.session = None

    async def health_check(self) -> None:
        """连通性检查：任一接口可用即视为正常，否则给出精确的失败原因。"""
        translated, _ = await self._translate_with_fallback("hello", "en", "zh-CN")
        if not translated:
            raise TranslationServiceError(
                f"{SERVICE_NAME}健康检查返回空结果，请稍后重试或改用{ALTERNATIVES}。",
                kind="server",
            )
