"""
翻译功能核心模块
"""
from abc import ABC, abstractmethod

class FanYiJieKou(ABC):
    """翻译接口抽象基类"""
    
    @abstractmethod
    async def fanyi(self, text: str, source_lang: str, target_lang: str) -> str:
        """执行翻译
        
        Args:
            text: 要翻译的文本
            source_lang: 源语言
            target_lang: 目标语言
            
        Returns:
            str: 翻译结果
            
        Raises:
            ValueError: 翻译失败时抛出
        """
        pass

class DaZaoFanYi:
    """大佐翻译官核心类"""
    
    def __init__(self):
        """初始化翻译器"""
        self._fanyi_jiekou = None
    
    async def close_current_api(self):
        """关闭当前翻译接口的会话"""
        if self._fanyi_jiekou:
            await self._fanyi_jiekou.close()
            self._fanyi_jiekou = None
    
    def set_fanyi_jiekou(self, jiekou: FanYiJieKou):
        """设置翻译接口"""
        self._fanyi_jiekou = jiekou
    
    async def fanyi(self, text: str, source_lang: str, target_lang: str) -> str:
        """执行翻译"""
        if not self._fanyi_jiekou:
            raise ValueError("未设置翻译接口")
        return await self._fanyi_jiekou.fanyi(text, source_lang, target_lang) 