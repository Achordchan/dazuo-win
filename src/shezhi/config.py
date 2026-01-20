import json
import os
import sys
from typing import Any, Dict, Optional

class Config:
    """配置管理类
    
    用于管理应用程序的配置信息，包括主题、窗口位置、API密钥等
    配置数据以JSON格式存储在用户目录下
    """
    
    def __init__(self):
        """初始化配置管理器"""
        # 设置配置文件路径
        self.config_dir = os.path.expanduser("~/.dzfyq")
        self.config_file = os.path.join(self.config_dir, "config.json")
        
        default_hotkey = "command+c,c" if sys.platform == "darwin" else "ctrl+c,c"

        # 默认配置
        self._default_config = {
            "theme": "dark",  # 默认深色主题
            "window": {
                "width": 857,
                "height": 620,
                "x": None,
                "y": None
            },
            "shortcuts": {
                "copy_translate": default_hotkey
            },
            "auto_start": False,
            "show_in_dock": True,
            "mac_accessibility_prompted": False,
            "translation": {
                "api": "google",  # 默认使用Google翻译
                "source_lang": "自动检测",  # 默认使用自动检测
                "target_lang": "中文"
            },
            "openai_compat": {
                "vendor": "智谱",
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                "model": "glm-4-flash",
                "api_key": "",
                "profiles": {}
            }
        }
        
        # 当前配置
        self._config = {}
        
        # 加载配置
        self._ensure_config_dir()
        self.load()

        openai_compat = self._config.setdefault("openai_compat", {})
        if "profiles" not in openai_compat or not isinstance(openai_compat.get("profiles"), dict):
            vendor = openai_compat.get("vendor", self._default_config["openai_compat"]["vendor"])
            base_url = openai_compat.get("base_url", self._default_config["openai_compat"]["base_url"])
            model = openai_compat.get("model", self._default_config["openai_compat"]["model"])
            api_key = openai_compat.get("api_key", self._default_config["openai_compat"]["api_key"])
            openai_compat["profiles"] = {
                vendor: {
                    "base_url": base_url,
                    "model": model,
                    "api_key": api_key,
                }
            }
            self.save()
        legacy_api = self._config.get("translation", {}).get("api")
        if legacy_api in {"deepseek", "doubao"}:
            self._config.setdefault("translation", {})["api"] = "google"
            self.save()
        
        # 确保源语言始终是自动检测
        if self._config.get("translation", {}).get("source_lang") != "自动检测":
            self._config["translation"]["source_lang"] = "自动检测"
            self.save()
    
    def _ensure_config_dir(self) -> None:
        """确保配置目录存在"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值
        
        Args:
            key: 配置键，支持点号分隔的多级键，如 "window.width"
            default: 默认值，当配置项不存在时返回
            
        Returns:
            配置值或默认值
        """
        try:
            value = self._config
            for k in key.split('.'):
                value = value[k]
            return value
        except (KeyError, TypeError):
            try:
                value = self._default_config
                for k in key.split('.'):
                    value = value[k]
                return value
            except (KeyError, TypeError):
                return default
    
    def set(self, key: str, value: Any) -> None:
        """设置配置值
        
        Args:
            key: 配置键，支持点号分隔的多级键
            value: 配置值
        """
        keys = key.split('.')
        current = self._config
        
        # 遍历到最后一个键之前
        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        
        # 设置最后一个键的值
        current[keys[-1]] = value
        
        # 保存配置
        self.save()
    
    def load(self) -> None:
        """从文件加载配置
        
        如果配置文件不存在或无效，将使用默认配置
        """
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            else:
                self._config = self._default_config.copy()
                self.save()  # 保存默认配置
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            self._config = self._default_config.copy()
            self.save()  # 保存默认配置
    
    def save(self) -> None:
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存配置文件失败: {e}")
    
    def reset(self) -> None:
        """重置为默认配置"""
        self._config = self._default_config.copy()
        self.save()
    
    def get_all(self) -> Dict:
        """获取所有配置
        
        Returns:
            当前所有配置的副本
        """
        return self._config.copy() 