import asyncio
import copy
import logging

from src.gongju.fanyi import sanitize_error_message
from src.gongju.fanyi_factory import build_translation_api

logger = logging.getLogger(__name__)

def _snapshot_translation_config(config, api_name):
    snapshot = {"translation.api": api_name}
    if api_name == "deepl":
        snapshot.update(
            {
                "deepl.api_key": config.get("deepl.api_key", ""),
                "deepl.account_type": config.get("deepl.account_type", ""),
            }
        )
    elif api_name == "openai_compat":
        vendor = config.get("openai_compat.vendor", "OpenAI")
        profile = {
            "base_url": config.get("openai_compat.base_url", ""),
            "model": config.get("openai_compat.model", ""),
            "api_key": config.get("openai_compat.api_key", ""),
        }
        snapshot.update(
            {
                "openai_compat.vendor": vendor,
                "openai_compat.base_url": profile["base_url"],
                "openai_compat.model": profile["model"],
                "openai_compat.api_key": profile["api_key"],
                "openai_compat.profiles": {vendor: profile},
            }
        )
    return copy.deepcopy(snapshot)


def ensure_translation_rollback_snapshot(config, api_name):
    """Preserve the target service config before settings overwrite it."""
    working_configs = copy.deepcopy(
        config.get("translation.last_working_configs", {})
    )
    if not isinstance(working_configs, dict):
        working_configs = {}
    if api_name not in working_configs:
        working_configs[api_name] = _snapshot_translation_config(config, api_name)
    return working_configs


def _restore_translation_config(config, snapshot) -> bool:
    if not snapshot:
        return False
    restored = copy.deepcopy(snapshot)
    profile_snapshot = restored.get("openai_compat.profiles")
    if isinstance(profile_snapshot, dict):
        current_profiles = config.get("openai_compat.profiles", {})
        if not isinstance(current_profiles, dict):
            current_profiles = {}
        merged_profiles = copy.deepcopy(current_profiles)
        merged_profiles.update(profile_snapshot)
        restored["openai_compat.profiles"] = merged_profiles
    if hasattr(config, "update_many"):
        return bool(config.update_many(restored))
    try:
        for key, value in restored.items():
            config.set(key, copy.deepcopy(value), save=False)
        return bool(config.save())
    except TypeError:
        for key, value in restored.items():
            config.set(key, copy.deepcopy(value))
        return True


def update_service_display(self):
    api_name = self.config.get("translation.api", "google")
    if api_name == "openai_compat":
        vendor = self.config.get("openai_compat.vendor", "OpenAI")
        self.service_display.setText(f"{vendor}")
    elif api_name == "deepl":
        self.service_display.setText("DeepL")
    elif api_name == "achord_builtin":
        self.service_display.setText("Achord 内置引擎")
    else:
        self.service_display.setText("Google")


def retry_connection(self):
    if hasattr(self, "reload_translation_api"):
        self.reload_translation_api()
        return
    loop = asyncio.get_event_loop()
    loop.create_task(_init_translation_api(self))


async def init_translation_api(self):
    return await _init_translation_api(self)


def _translation_error_secrets(self, api=None):
    secrets = [
        self.config.get("deepl.api_key", ""),
        self.config.get("openai_compat.api_key", ""),
    ]
    if api is not None:
        secrets.append(getattr(api, "api_key", ""))
    return secrets


async def _init_translation_api(self):
    lock = getattr(self, "_translation_api_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        self._translation_api_lock = lock
    generation = getattr(self, "_translation_api_generation", 0) + 1
    self._translation_api_generation = generation

    new_api = None
    assigned = False
    async with lock:
        if generation != getattr(self, "_translation_api_generation", generation):
            return
        api_name = self.config.get("translation.api", "google")
        previous_api_name = getattr(self.fanyi, "current_api_name", None)
        working_configs = copy.deepcopy(
            self.config.get("translation.last_working_configs", {})
        )
        if not isinstance(working_configs, dict):
            working_configs = {}
        in_memory_configs = getattr(self, "_last_working_translation_configs", {})
        if isinstance(in_memory_configs, dict):
            working_configs.update(copy.deepcopy(in_memory_configs))
        try:
            logger.info(f"正在初始化翻译API: {api_name}")

            if hasattr(self, "translator_vm"):
                await self.translator_vm.cancel_and_wait(clear_output=False)

            self.status_indicator.set_status("connecting", "正在连接...")
            update_service_display(self)

            # Build and validate the new API first; only then replace the live one.
            new_api = build_translation_api(self.config)
            await new_api.health_check()

            desired_api_name = self.config.get("translation.api", "google")
            if generation != getattr(self, "_translation_api_generation", generation) or desired_api_name != api_name:
                logger.info("丢弃过期翻译API初始化结果: %s -> %s", api_name, desired_api_name)
                return

            if hasattr(self.fanyi, "replace_fanyi_jiekou"):
                await self.fanyi.replace_fanyi_jiekou(new_api, api_name=api_name)
            else:
                await self.fanyi.close_current_api()
                self.fanyi.set_fanyi_jiekou(new_api, api_name=api_name)

            assigned = True
            working_configs[api_name] = _snapshot_translation_config(self.config, api_name)
            self._last_working_translation_configs = working_configs
            if hasattr(self.config, "update_many"):
                if not self.config.update_many(
                    {"translation.last_working_configs": working_configs}
                ):
                    logger.warning("保存最后可用翻译配置失败。")
            else:
                self.config.set("translation.last_working_configs", working_configs)
            self.status_indicator.set_status("normal", "已连接")

            if self.input_text.toPlainText():
                self.translator_vm.translate_now(self.input_text.toPlainText(), self._get_vm_context())

        except Exception as error:
            error_msg = sanitize_error_message(error, _translation_error_secrets(self, new_api))
            if "API密钥" in error_msg:
                self.status_indicator.set_status("error", "未设置API密钥")
            elif "无法连接" in error_msg or "网络错误" in error_msg:
                self.status_indicator.set_status("error", "连接失败")
            else:
                self.status_indicator.set_status("error", "连接失败")

            logger.error("初始化翻译API出错: %s", error_msg)
            if hasattr(self, "tishi"):
                self.tishi.showMessage(f"API连接失败: {error_msg}", type="error")
            # Keep the previously working service and restore its complete config.
            restored = False
            failed_service_config = working_configs.get(api_name)
            if failed_service_config:
                try:
                    rollback_config = copy.deepcopy(failed_service_config)
                    if previous_api_name:
                        rollback_config["translation.api"] = previous_api_name
                    restored = _restore_translation_config(self.config, rollback_config)
                except Exception as rollback_error:
                    logger.warning(
                        "回滚翻译服务配置失败: %s",
                        sanitize_error_message(rollback_error),
                    )
            elif previous_api_name and previous_api_name != api_name:
                try:
                    if hasattr(self.config, "update_many"):
                        restored = bool(
                            self.config.update_many({"translation.api": previous_api_name})
                        )
                    else:
                        restored = bool(
                            self.config.set("translation.api", previous_api_name)
                        )
                except Exception as rollback_error:
                    logger.warning(
                        "回滚翻译服务配置失败: %s",
                        sanitize_error_message(rollback_error),
                    )
            update_service_display(self)
            if restored and getattr(self.fanyi, "current_api_name", None) == previous_api_name:
                self.status_indicator.set_status("normal", "已连接")
        finally:
            if new_api is not None and not assigned:
                try:
                    await new_api.close()
                except Exception:
                    pass
