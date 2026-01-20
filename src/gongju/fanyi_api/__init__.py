"""
翻译接口包
"""
from .google import GoogleAPI
from .openai_compat import OpenAICompatibleAPI
from .achord import AchordAPI

# 导出所有翻译接口
__all__ = ['GoogleAPI', 'OpenAICompatibleAPI', 'AchordAPI']