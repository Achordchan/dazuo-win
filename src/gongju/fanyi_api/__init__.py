"""
翻译接口包
"""
from .google import GoogleAPI
from .openai_compat import OpenAICompatibleAPI
from .deepl import DeepLAPI

# 导出所有翻译接口
__all__ = ['GoogleAPI', 'OpenAICompatibleAPI', 'DeepLAPI']
