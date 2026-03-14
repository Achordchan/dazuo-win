"""翻译功能核心模块。"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple


TranslationResult = Tuple[str, Optional[str]]


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

    async def close_current_api(self):
        if self._fanyi_jiekou:
            await self._fanyi_jiekou.close()
            self._fanyi_jiekou = None

    def set_fanyi_jiekou(self, jiekou: FanYiJieKou):
        self._fanyi_jiekou = jiekou

    async def fanyi(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        if not self._fanyi_jiekou:
            raise ValueError("未设置翻译接口")
        return await self._fanyi_jiekou.fanyi(text, source_lang, target_lang)
