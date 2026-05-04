import copy
import json
import os
from typing import Any, Dict

from .config_defaults import build_default_config


class Config:
    """配置管理类。"""

    def __init__(self):
        self.config_dir = os.path.expanduser("~/.dzfyq")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self._default_config = build_default_config()
        self._config: Dict[str, Any] = {}

        self._ensure_config_dir()
        self.load()

    def _ensure_config_dir(self) -> None:
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

    def _load_raw_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_file):
            return {}

        try:
            with open(self.config_file, "r", encoding="utf-8") as file:
                data = json.load(file)
                return data if isinstance(data, dict) else {}
        except Exception as error:
            print(f"加载配置文件失败: {error}")
            return {}

    def _merge_dicts(self, defaults: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
        merged = copy.deepcopy(defaults)
        for key, value in current.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _migrate_legacy_config(self, config: Dict[str, Any]) -> bool:
        changed = False
        openai_compat = config.setdefault("openai_compat", {})
        if not isinstance(openai_compat, dict):
            config["openai_compat"] = copy.deepcopy(self._default_config["openai_compat"])
            openai_compat = config["openai_compat"]
            changed = True

        profiles = openai_compat.get("profiles")
        if not isinstance(profiles, dict):
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
            changed = True

        translation = config.setdefault("translation", {})
        if not isinstance(translation, dict):
            config["translation"] = copy.deepcopy(self._default_config["translation"])
            translation = config["translation"]
            changed = True

        if translation.get("api") in {"deepseek", "doubao", "achord"}:
            translation["api"] = "google"
            changed = True

        deepl = config.setdefault("deepl", {})
        if not isinstance(deepl, dict):
            config["deepl"] = copy.deepcopy(self._default_config["deepl"])
            changed = True

        return changed

    def _validate_config(self, config: Dict[str, Any]) -> bool:
        changed = False
        translation = config.setdefault("translation", {})
        if translation.get("source_lang") != "自动检测":
            translation["source_lang"] = "自动检测"
            changed = True
        return changed

    def _save_if_changed(self, previous: Dict[str, Any]) -> None:
        if previous != self._config:
            self.save()

    def get(self, key: str, default: Any = None) -> Any:
        try:
            value: Any = self._config
            for part in key.split("."):
                value = value[part]
            return value
        except (KeyError, TypeError):
            try:
                value = self._default_config
                for part in key.split("."):
                    value = value[part]
                return value
            except (KeyError, TypeError):
                return default

    def set(self, key: str, value: Any) -> None:
        current = self._config
        keys = key.split(".")
        for part in keys[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[keys[-1]] = value
        self.save()

    def load(self) -> None:
        previous = copy.deepcopy(self._config)
        raw = self._load_raw_config()
        merged = self._merge_dicts(self._default_config, raw)
        self._config = merged

        migrated = self._migrate_legacy_config(self._config)
        validated = self._validate_config(self._config)
        if not raw:
            previous = {}
        if migrated or validated or not os.path.exists(self.config_file):
            self._save_if_changed(previous)

    def save(self) -> None:
        try:
            self._ensure_config_dir()
            with open(self.config_file, "w", encoding="utf-8") as file:
                json.dump(self._config, file, ensure_ascii=False, indent=4)
        except Exception as error:
            print(f"保存配置文件失败: {error}")

    def reset(self) -> None:
        self._config = build_default_config()
        self.save()

    def get_all(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)
