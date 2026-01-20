"""
Google翻译接口
使用非官方的 Google Translate API
"""
import aiohttp
import json
from urllib.parse import urlencode
import ssl
import certifi
import os
from typing import Dict, Tuple, Optional
import time
import asyncio
import logging

logger = logging.getLogger(__name__)

class GoogleAPI:
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
    
    def __init__(self):
        """初始化"""
        self.base_url = "https://translate.googleapis.com/translate_a/single"
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
        
        # 并发控制
        self._semaphore = asyncio.Semaphore(5)
        
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
                ssl=False  # 禁用SSL验证以提高速度
            )
            
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                connector=connector,
                timeout=self._timeout,
                trust_env=True
            )
        return self.session
    
    async def fanyi(self, text: str, source_lang: str, target_lang: str) -> tuple[str, Optional[str]]:
        """执行翻译"""
        if not text:
            return "", None
        
        try:
            # 检查缓存
            cache_key = f"{text}|{source_lang}|{target_lang}"
            if cache_key in self._cache:
                return self._cache[cache_key], None
            
            try:
                async with self._semaphore:  # 使用信号量控制并发
                    source_code = self.LANG_CODES.get(source_lang, "auto")
                    target_code = self.LANG_CODES.get(target_lang, "zh-CN")
                    
                    params = {
                        "client": "gtx",
                        "sl": source_code,
                        "tl": target_code,
                        "dt": ["t", "ld"],
                        "q": text
                    }
                    
                    session = await self._ensure_session()
                    try:
                        async with session.get(self.base_url, params=params) as response:
                            if response.status == 200:
                                data = await response.json(content_type=None)
                                
                                # 提取翻译结果
                                translated_text = ""
                                detected_lang = None
                                
                                if data and isinstance(data[0], list):
                                    for item in data[0]:
                                        if item and item[0]:
                                            translated_text += item[0]
                                    
                                    # 获取检测到的语言
                                    if len(data) > 2 and isinstance(data[2], str):
                                        detected_lang = data[2]
                                    elif len(data) > 8 and data[8] and isinstance(data[8][0], list):
                                        detected_lang = data[8][0][0]
                                    
                                    logger.info(f"检测到的语言: {detected_lang}")
                                    
                                    # 确保返回正确的语言代码
                                    if detected_lang:
                                        # 将 Google 的语言代码映射到我们的代码
                                        lang_map = {
                                            'en': 'en',     # 英语
                                            'zh-CN': 'zh-CN', # 中文
                                            'ja': 'ja',     # 日语
                                            'ko': 'ko',     # 韩语
                                            'fr': 'fr',     # 法语
                                            'de': 'de',     # 德语
                                            'es': 'es',     # 西班牙语
                                            'ru': 'ru',     # 俄语
                                            'it': 'it',     # 意大利语
                                            'pt': 'pt',     # 葡萄牙语
                                            'vi': 'vi',     # 越南语
                                            'th': 'th',     # 泰语
                                            'ar': 'ar'      # 阿拉伯语
                                        }
                                        detected_lang = lang_map.get(detected_lang, detected_lang)
                                    
                                    # 缓存结果
                                    if len(self._cache) >= self._cache_size:
                                        self._cache.pop(next(iter(self._cache)))
                                    self._cache[cache_key] = translated_text.strip()
                                    
                                    return translated_text.strip(), detected_lang
                                
                            raise ValueError(f"翻译服务器返回错误: HTTP {response.status}")
                    except aiohttp.ClientConnectorError:
                        raise ValueError("无法连接到 Google 翻译服务，请检查网络连接或代理设置")
                    except aiohttp.ClientError as e:
                        raise ValueError(f"网络错误: {str(e)}，请检查网络连接")
                    
            except asyncio.TimeoutError:
                raise ValueError("连接超时，请检查网络状态")
            
        except Exception as e:
            error_msg = str(e)
            if "无法连接" in error_msg or "网络错误" in error_msg:
                print(f"Google 翻译连接错误: {error_msg}")
            else:
                print(f"Google 翻译错误: {error_msg}")
            raise ValueError(error_msg)
    
    async def close(self):
        """关闭会话"""
        if self.session:
            await self.session.close()
            self.session = None