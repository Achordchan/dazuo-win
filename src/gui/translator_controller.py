import asyncio
import logging

from src.gongju.fanyi import sanitize_error_message
from src.gongju.fanyi_factory import build_translation_api

logger = logging.getLogger(__name__)


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
        try:
            logger.info(f"正在初始化翻译API: {api_name}")

            if hasattr(self, "translator_vm"):
                await self.translator_vm.cancel_and_wait(clear_output=False)

            self.status_indicator.set_status("connecting", "正在连接...")
            update_service_display(self)

            if getattr(self.fanyi, "current_api_name", None) is not None:
                await self.fanyi.close_current_api()

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
            update_service_display(self)
        finally:
            if new_api is not None and not assigned:
                try:
                    await new_api.close()
                except Exception:
                    pass
            desired_api_name = self.config.get("translation.api", "google")
            if not assigned and getattr(self.fanyi, "current_api_name", None) != desired_api_name:
                try:
                    await self.fanyi.close_current_api()
                except Exception as close_error:
                    logger.warning("关闭不匹配的旧翻译接口失败: %s", sanitize_error_message(close_error))
