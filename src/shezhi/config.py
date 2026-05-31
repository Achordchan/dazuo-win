import copy
import json
import os
import tempfile
import time
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
            if isinstance(data, dict):
                return data
            print("配置文件内容不是 JSON 对象，按损坏配置处理")
            self._backup_invalid_config()
            return {}
        except Exception as error:
            print(f"加载配置文件失败: {error}")
            self._backup_invalid_config()
            return {}

    def _backup_invalid_config(self) -> None:
        if not os.path.exists(self.config_file):
            return
        try:
            backup_base = f"{self.config_file}.invalid.{time.strftime('%Y%m%d_%H%M%S')}"
            backup_path = f"{backup_base}.bak"
            index = 1
            while os.path.exists(backup_path):
                backup_path = f"{backup_base}.{index}.bak"
                index += 1
            os.replace(self.config_file, backup_path)
            print(f"已备份损坏配置文件: {backup_path}")
        except Exception as error:
            print(f"备份损坏配置文件失败: {error}")

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

        if translation.get("api") == "deeplx":
            translation["api"] = "achord_builtin"
            changed = True
        if translation.get("api") in {"deepseek", "doubao", "achord"}:
            translation["api"] = "google"
            changed = True

        deepl = config.setdefault("deepl", {})
        if not isinstance(deepl, dict):
            config["deepl"] = copy.deepcopy(self._default_config["deepl"])
            changed = True

        if "deeplx" in config:
            del config["deeplx"]
            changed = True

        return changed

    def _validate_config(self, config: Dict[str, Any]) -> bool:
        changed = False
        translation = config.setdefault("translation", {})
        if not isinstance(translation, dict):
            config["translation"] = copy.deepcopy(self._default_config["translation"])
            return True
        if translation.get("source_lang") != "自动检测":
            translation["source_lang"] = "自动检测"
            changed = True
        if translation.get("target_lang") == "中文":
            translation["target_lang"] = "简体中文"
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
        temp_path = ""
        try:
            self._ensure_config_dir()
            fd, temp_path = tempfile.mkstemp(
                prefix="config.",
                suffix=".tmp",
                dir=self.config_dir,
                text=True,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(self._config, file, ensure_ascii=False, indent=4)
                file.write("\n")
            os.replace(temp_path, self.config_file)
        except Exception as error:
            if temp_path:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass
            print(f"保存配置文件失败: {error}")

    def reset(self) -> None:
        self._config = build_default_config()
        self.save()

    def get_all(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)
