import logging
logger = logging.getLogger(__name__)

import asyncio

from src.gongju.fanyi_api import GoogleAPI, OpenAICompatibleAPI, AchordAPI


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
    """重试连接"""
    api_name = self.config.get("translation.api", "google")

    async def retry():
        try:
            await self.fanyi.close_current_api()

            new_api = None
            if api_name == "google":
                new_api = GoogleAPI()
            elif api_name == "openai_compat":
                base_url = self.config.get("openai_compat.base_url")
                model = self.config.get("openai_compat.model")
                api_key = self.config.get("openai_compat.api_key")
                if not api_key:
                    self.status_indicator.set_status("error", "未设置API密钥")
                    return
                new_api = OpenAICompatibleAPI(base_url=base_url, model=model, api_key=api_key)
            elif api_name == "achord":
                new_api = AchordAPI()

            if new_api:
                self.status_indicator.set_status("normal", "正在连接...")
                if hasattr(new_api, "health_check"):
                    await new_api.health_check()
                else:
                    await new_api.fanyi("test", "自动检测", "中文")

                self.fanyi.set_fanyi_jiekou(new_api)
                self.status_indicator.set_status("normal", "已连接")
                update_service_display(self)

                if self.input_text.toPlainText():
                    self.translator_vm.translate_now(self.input_text.toPlainText(), self._get_vm_context())

        except Exception as e:
            error_msg = str(e)
            if "无法连接" in error_msg or "网络错误" in error_msg:
                self.status_indicator.set_status("error", "连接失败")
            else:
                self.status_indicator.set_status("error", "未设置API密钥" if "API密钥" in error_msg else "连接失败")

            if hasattr(self, 'tishi'):
                self.tishi.showMessage(f"API连接失败: {error_msg}", type="error")
            update_service_display(self)

    loop = asyncio.get_event_loop()
    loop.create_task(retry())


async def init_translation_api(self):
    """初始化翻译API"""
    try:
        api_name = self.config.get("translation.api", "google")
        logger.info(f"正在初始化翻译API: {api_name}")

        self.status_indicator.set_status("normal", "正在连接...")
        update_service_display(self)

        await self.fanyi.close_current_api()

        new_api = None
        if api_name == "google":
            new_api = GoogleAPI()
            try:
                await new_api.fanyi("test", "自动检测", "中文")
                self.fanyi.set_fanyi_jiekou(new_api)
                self.status_indicator.set_status("normal", "已连接")
            except ValueError as e:
                await new_api.close()
                error_msg = str(e)
                if "无法连接" in error_msg or "网络错误" in error_msg:
                    self.status_indicator.set_status("error", "连接失败")
                    raise ValueError("无法访问服务器")
                raise
        elif api_name == "openai_compat":
            base_url = self.config.get("openai_compat.base_url")
            model = self.config.get("openai_compat.model")
            api_key = self.config.get("openai_compat.api_key")
            if not api_key:
                self.status_indicator.set_status("error", "未设置API密钥")
                raise ValueError("未设置API密钥")
            new_api = OpenAICompatibleAPI(base_url=base_url, model=model, api_key=api_key)
        elif api_name == "achord":
            new_api = AchordAPI()
        else:
            self.status_indicator.set_status("error", "未知服务")
            raise ValueError("未知服务")

        if new_api:
            try:
                if hasattr(new_api, "health_check"):
                    await new_api.health_check()
                else:
                    await new_api.fanyi("test", "自动检测", "中文")
                self.fanyi.set_fanyi_jiekou(new_api)
                self.status_indicator.set_status("normal", "已连接")

                if self.input_text.toPlainText():
                    self.translator_vm.translate_now(self.input_text.toPlainText(), self._get_vm_context())
            except Exception:
                await new_api.close()
                self.status_indicator.set_status("error", "连接失败")
                raise ValueError("连接失败")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"初始化翻译API出错: {error_msg}")
        if hasattr(self, 'tishi'):
            self.tishi.showMessage(f"API连接失败: {error_msg}", type="error")
        update_service_display(self)
