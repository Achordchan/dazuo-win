import asyncio
import logging

from src.gongju.fanyi_factory import build_translation_api

logger = logging.getLogger(__name__)


def update_service_display(self):
    api_name = self.config.get("translation.api", "google")
    if api_name == "openai_compat":
        vendor = self.config.get("openai_compat.vendor", "OpenAI")
        self.service_display.setText(f"{vendor}")
    elif api_name == "achord":
        self.service_display.setText("Achord自研模型")
    else:
        self.service_display.setText("Google")


def retry_connection(self):
    async def retry():
        await _init_translation_api(self)

    loop = asyncio.get_event_loop()
    loop.create_task(retry())


async def init_translation_api(self):
    return await _init_translation_api(self)


async def _init_translation_api(self):
    new_api = None
    assigned = False
    try:
        api_name = self.config.get("translation.api", "google")
        logger.info(f"正在初始化翻译API: {api_name}")

        self.status_indicator.set_status("normal", "正在连接...")
        update_service_display(self)

        if hasattr(self, "translator_vm"):
            await self.translator_vm.cancel_and_wait(clear_output=False)

        await self.fanyi.close_current_api()
        new_api = build_translation_api(self.config)

        try:
            await new_api.health_check()
            self.fanyi.set_fanyi_jiekou(new_api)
            assigned = True
            self.status_indicator.set_status("normal", "已连接")

            if self.input_text.toPlainText():
                self.translator_vm.translate_now(self.input_text.toPlainText(), self._get_vm_context())
        except Exception:
            await new_api.close()
            self.status_indicator.set_status("error", "连接失败")
            raise

    except Exception as error:
        error_msg = str(error)
        if "API密钥" in error_msg:
            self.status_indicator.set_status("error", "未设置API密钥")
        elif "无法连接" in error_msg or "网络错误" in error_msg:
            self.status_indicator.set_status("error", "连接失败")
        else:
            self.status_indicator.set_status("error", "连接失败")

        logger.error(f"初始化翻译API出错: {error_msg}")
        if hasattr(self, "tishi"):
            self.tishi.showMessage(f"API连接失败: {error_msg}", type="error")
        update_service_display(self)
    finally:
        if new_api is not None and not assigned:
            try:
                await new_api.close()
            except Exception:
                pass
