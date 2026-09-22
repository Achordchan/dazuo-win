import asyncio
import copy
import logging

from src.gongju.fanyi import error_kind, error_short_label, sanitize_error_message
from src.gongju.fanyi_factory import SERVICE_DISPLAY_NAMES, build_translation_api

logger = logging.getLogger(__name__)

def _snapshot_translation_config(config, api_name):
    snapshot = {"translation.api": api_name}
    if api_name == "microsoft":
        snapshot.update(
            {
                "microsoft.api_key": config.get("microsoft.api_key", ""),
                "microsoft.region": config.get("microsoft.region", ""),
            }
        )
    elif api_name == "deepl":
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


def service_display_name(config, api_name=None) -> str:
    api_name = api_name or config.get("translation.api", "google")
    if api_name == "openai_compat":
        return str(config.get("openai_compat.vendor", "OpenAI"))
    return SERVICE_DISPLAY_NAMES.get(api_name, "Google")


def update_service_display(self):
    self.service_display.setText(service_display_name(self.config))


def _infer_error_kind(error, error_msg: str) -> str:
    kind = error_kind(error) if error is not None else "unknown"
    if kind != "unknown":
        return kind
    text = error_msg or ""
    if "海外网站" in text or "无法直接访问" in text:
        return "network_blocked"
    if "429" in text or "过于频繁" in text or "限制了当前网络" in text or "访问被拒" in text:
        return "rate_limited"
    if "超时" in text:
        return "timeout"
    if "API密钥" in text or "API Key" in text or "认证失败" in text:
        return "auth"
    if "未连接" in text or "尚未连接" in text or "正在连接" in text:
        return "not_connected"
    if "无法连接" in text or "网络错误" in text or "代理" in text:
        return "network"
    if "配置不完整" in text or "未设置" in text:
        return "config"
    return "unknown"


def _set_error_status(status_indicator, label: str, detail: str) -> None:
    """状态栏显示简短标签；旧版/测试用的状态组件可能不支持 detail 参数。"""
    try:
        status_indicator.set_status("error", label, detail=detail)
    except TypeError:
        status_indicator.set_status("error", label)


def status_label_for_error(error, error_msg: str, prefix: str = "连接失败") -> str:
    """状态栏只有很窄的空间，用简短标签概括失败原因；完整信息放在提示气泡和 tooltip。"""
    kind = _infer_error_kind(error, error_msg)
    if kind == "network_blocked":
        return f"{prefix}：需海外网络"
    if kind == "rate_limited":
        return f"{prefix}：请求受限"
    if kind == "timeout":
        return f"{prefix}：超时"
    if kind == "auth":
        return "未设置或密钥无效"
    if kind == "config":
        return "配置不完整"
    if kind == "not_connected":
        return "服务未连接"
    if kind == "server":
        return f"{prefix}：服务异常"
    if kind == "network":
        return f"{prefix}：网络不可达"
    short = error_short_label(error, "") if error is not None else ""
    return f"{prefix}：{short}" if short else prefix


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
        self.config.get("microsoft.api_key", ""),
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
            if hasattr(self.fanyi, "set_connection_state"):
                self.fanyi.set_connection_state("connecting")

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
            if hasattr(self.fanyi, "set_connection_state"):
                self.fanyi.set_connection_state("connected")
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
            service_label = service_display_name(self.config, api_name)
            _set_error_status(
                self.status_indicator,
                status_label_for_error(error, error_msg),
                f"{service_label}：{error_msg}",
            )

            logger.error("初始化翻译API出错: %s", error_msg)
            if hasattr(self, "tishi"):
                self.tishi.showMessage(f"{service_label}连接失败：{error_msg}", type="error")
            # 记录失败原因：在用户点击“重试”或更换服务之前，翻译请求会直接提示该原因。
            if hasattr(self.fanyi, "set_connection_state"):
                if getattr(self.fanyi, "current_api_name", None) is None:
                    self.fanyi.set_connection_state("error", error_msg)
                else:
                    # 旧服务仍然可用，继续使用它
                    self.fanyi.set_connection_state("connected")
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
                if hasattr(self.fanyi, "set_connection_state"):
                    self.fanyi.set_connection_state("connected")
                self.status_indicator.set_status("normal", "已连接")
                if hasattr(self, "tishi"):
                    self.tishi.showMessage(
                        f"已继续使用 {service_display_name(self.config, previous_api_name)}。",
                        type="info",
                    )
        finally:
            if new_api is not None and not assigned:
                try:
                    await new_api.close()
                except Exception:
                    pass
