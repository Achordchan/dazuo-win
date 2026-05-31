"""翻译功能核心模块。"""

import logging
import re
from abc import ABC, abstractmethod
from typing import Iterable, Optional, Tuple


TranslationResult = Tuple[str, Optional[str]]
logger = logging.getLogger(__name__)


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
        if len(secret) >= 6:
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

    @property
    def current_api_name(self) -> Optional[str]:
        return self._api_name

    async def close_current_api(self):
        jiekou = self._fanyi_jiekou
        self._fanyi_jiekou = None
        self._api_name = None
        if jiekou:
            await jiekou.close()

    def set_fanyi_jiekou(self, jiekou: FanYiJieKou, api_name: Optional[str] = None):
        self._fanyi_jiekou = jiekou
        self._api_name = api_name

    async def replace_fanyi_jiekou(self, jiekou: FanYiJieKou, api_name: Optional[str] = None):
        old_jiekou = self._fanyi_jiekou
        self._fanyi_jiekou = jiekou
        self._api_name = api_name

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
    ) -> TranslationResult:
        if not self._fanyi_jiekou:
            raise ValueError("未设置翻译接口")
        if expected_api_name and self._api_name != expected_api_name:
            raise ValueError("当前翻译服务未连接，请重新选择或重试连接。")
        return await self._fanyi_jiekou.fanyi(text, source_lang, target_lang)
