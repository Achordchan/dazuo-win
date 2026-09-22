"""翻译功能核心模块。"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import Iterable, Optional, Tuple


TranslationResult = Tuple[str, Optional[str]]
logger = logging.getLogger(__name__)


class TranslationServiceError(ValueError):
    """带有错误类别与简短提示的翻译服务错误。

    kind 取值：
      - network_blocked: 需要海外网络（代理/VPN）才能访问
      - network: 普通网络连接失败
      - timeout: 请求超时
      - rate_limited: 被服务方限流（HTTP 429）
      - auth: 密钥缺失或无效
      - config: 配置不完整
      - server: 服务端返回错误
      - not_connected: 翻译服务尚未连接
      - unknown: 其他
    """

    def __init__(self, message: str, kind: str = "unknown", short: Optional[str] = None):
        super().__init__(message)
        self.kind = kind
        self.short = short or _DEFAULT_SHORT_LABELS.get(kind, "服务异常")


_DEFAULT_SHORT_LABELS = {
    "network_blocked": "需海外网络",
    "network": "连接失败",
    "timeout": "连接超时",
    "rate_limited": "请求受限",
    "auth": "密钥无效",
    "config": "配置不完整",
    "server": "服务异常",
    "not_connected": "未连接",
    "unknown": "连接失败",
}


def error_kind(error) -> str:
    return getattr(error, "kind", "unknown") or "unknown"


def error_short_label(error, default: str = "连接失败") -> str:
    short = getattr(error, "short", None)
    if short:
        return str(short)
    message = str(error or "")
    if "API密钥" in message or "API Key" in message:
        return "密钥无效"
    if "429" in message or "过于频繁" in message:
        return "请求受限"
    if "超时" in message:
        return "连接超时"
    return default


def describe_connection_error(
    error,
    service_name: str,
    *,
    overseas_required: bool = False,
    alternatives: Optional[str] = None,
) -> TranslationServiceError:
    """把 aiohttp / asyncio 抛出的底层网络错误转换为面向用户的精确提示。"""
    import aiohttp  # 延迟导入，避免测试环境不必要的依赖初始化

    alt_hint = f"，或改用{alternatives}" if alternatives else ""
    if isinstance(error, TranslationServiceError):
        return error
    if isinstance(error, aiohttp.ClientConnectorCertificateError):
        return TranslationServiceError(
            f"{service_name}证书校验失败，请检查代理软件或系统证书设置{alt_hint}。",
            kind="network",
            short="证书错误",
        )
    if isinstance(error, aiohttp.ClientProxyConnectionError):
        return TranslationServiceError(
            f"无法连接到代理服务器，请确认代理软件已启动并检查系统代理设置{alt_hint}。",
            kind="network",
            short="代理不可用",
        )
    is_timeout = isinstance(error, (asyncio.TimeoutError, aiohttp.ServerTimeoutError))
    is_connect_error = isinstance(
        error,
        (aiohttp.ClientConnectorError, aiohttp.ClientOSError, aiohttp.ServerDisconnectedError, ConnectionError),
    )
    if is_timeout or is_connect_error:
        if overseas_required:
            return TranslationServiceError(
                f"无法连接到 {service_name}。{service_name}在中国大陆无法直接访问，"
                f"请确认已开启可以访问海外网站的网络（代理/VPN），并让本程序走系统代理{alt_hint}。",
                kind="network_blocked",
            )
        if is_timeout:
            return TranslationServiceError(
                f"连接 {service_name} 超时，请检查网络连接后重试{alt_hint}。",
                kind="timeout",
            )
        return TranslationServiceError(
            f"无法连接到 {service_name}，请检查网络连接或代理设置{alt_hint}。",
            kind="network",
        )
    if isinstance(error, aiohttp.ClientError):
        return TranslationServiceError(
            f"{service_name}网络错误：{error}，请检查网络连接{alt_hint}。",
            kind="network",
        )
    return TranslationServiceError(f"{service_name}出错：{error}", kind="unknown")


def describe_http_status(
    status: int,
    service_name: str,
    *,
    overseas_required: bool = False,
    alternatives: Optional[str] = None,
    detail: str = "",
) -> TranslationServiceError:
    """把非 200 的 HTTP 状态码转换为面向用户的精确提示。"""
    alt_hint = f"，或改用{alternatives}" if alternatives else ""
    detail_text = f"（{detail}）" if detail else ""
    if status == 429:
        message = (
            f"{service_name}暂时限制了当前网络的访问（HTTP 429）。"
            f"请稍后再试"
            + ("、更换代理节点" if overseas_required else "")
            + f"{alt_hint}。"
        )
        return TranslationServiceError(message, kind="rate_limited")
    if status in (401, 403):
        if overseas_required:
            message = (
                f"{service_name}拒绝了当前网络的访问（HTTP {status}），"
                f"通常是代理节点被识别为异常流量，请更换节点{alt_hint}。"
            )
            return TranslationServiceError(message, kind="rate_limited", short="访问被拒")
        return TranslationServiceError(
            f"{service_name}认证失败（HTTP {status}）{detail_text}，请检查 API Key 是否正确。",
            kind="auth",
        )
    if status >= 500:
        return TranslationServiceError(
            f"{service_name}服务端暂时不可用（HTTP {status}）{detail_text}，请稍后重试{alt_hint}。",
            kind="server",
        )
    return TranslationServiceError(
        f"{service_name}返回错误：HTTP {status}{detail_text}。",
        kind="server",
    )


_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[-_\s]?key\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)([^\s,;]+)"),
    re.compile(r"(?i)(DeepL-Auth-Key\s+)([^\s,;]+)"),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b"),
    re.compile(r"\b([A-Za-z0-9_-]{12,}:fx)\b"),
)


def sanitize_error_message(error, secrets: Iterable[str] = ()) -> str:
    """Return an end-user safe error string with known API keys redacted."""
    message = str(error)

    for secret in secrets or ():
        secret = (secret or "").strip()
        if len(secret) >= 4:
            message = message.replace(secret, "[已隐藏]")

    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            message = pattern.sub(lambda match: f"{match.group(1)}[已隐藏]", message)
        else:
            message = pattern.sub("[已隐藏]", message)

    return message


class FanYiJieKou(ABC):
    """翻译接口抽象基类。"""

    @abstractmethod
    async def fanyi(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        pass

    @abstractmethod
    async def health_check(self) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass


class DaZaoFanYi:
    """大佐翻译官核心类。"""

    def __init__(self):
        self._fanyi_jiekou: Optional[FanYiJieKou] = None
        self._api_name: Optional[str] = None
        self._api_generation: int = 0
        # 连接状态：idle / connecting / connected / error
        self._connection_state: str = "idle"
        self._last_connection_error: Optional[str] = None

    @property
    def connection_state(self) -> str:
        return self._connection_state

    @property
    def last_connection_error(self) -> Optional[str]:
        return self._last_connection_error

    def set_connection_state(self, state: str, error: Optional[str] = None) -> None:
        self._connection_state = state
        self._last_connection_error = str(error) if error else None

    def not_connected_error(self) -> TranslationServiceError:
        """当没有可用翻译接口时，给出说明原因的错误。"""
        if self._connection_state == "connecting":
            return TranslationServiceError(
                "翻译服务正在连接，请稍候再试。",
                kind="not_connected",
                short="正在连接",
            )
        if self._last_connection_error:
            return TranslationServiceError(
                f"翻译服务未连接：{self._last_connection_error} "
                "可点击“重试”重新连接，或在设置中更换翻译服务。",
                kind="not_connected",
            )
        return TranslationServiceError(
            "翻译服务尚未连接，请点击“重试”或在设置中选择可用的翻译服务。",
            kind="not_connected",
        )

    @property
    def current_api_name(self) -> Optional[str]:
        return self._api_name

    @property
    def current_api_generation(self) -> int:
        return self._api_generation

    async def close_current_api(self):
        jiekou = self._fanyi_jiekou
        self._fanyi_jiekou = None
        self._api_name = None
        self._api_generation += 1
        if jiekou:
            await jiekou.close()

    def set_fanyi_jiekou(self, jiekou: FanYiJieKou, api_name: Optional[str] = None):
        self._fanyi_jiekou = jiekou
        self._api_name = api_name
        self._api_generation += 1

    async def replace_fanyi_jiekou(self, jiekou: FanYiJieKou, api_name: Optional[str] = None):
        old_jiekou = self._fanyi_jiekou
        self._fanyi_jiekou = jiekou
        self._api_name = api_name
        self._api_generation += 1

        if old_jiekou and old_jiekou is not jiekou:
            try:
                await old_jiekou.close()
            except Exception as error:
                logger.warning("关闭旧翻译接口失败: %s", sanitize_error_message(error, [getattr(old_jiekou, "api_key", "")]))

    async def fanyi(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        expected_api_name: Optional[str] = None,
        expected_api_generation: Optional[int] = None,
    ) -> TranslationResult:
        if not self._fanyi_jiekou:
            raise self.not_connected_error()
        if expected_api_name and self._api_name != expected_api_name:
            raise ValueError("当前翻译服务未连接，请重新选择或重试连接。")
        if expected_api_generation is not None and self._api_generation != expected_api_generation:
            raise ValueError("当前翻译服务已切换，请重新翻译。")
        return await self._fanyi_jiekou.fanyi(text, source_lang, target_lang)
