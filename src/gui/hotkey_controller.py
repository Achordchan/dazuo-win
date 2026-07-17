import logging
import sys

from ..gongju.kuaijiejian import ClipboardDoubleCopyMonitor, KuaiJieJianJianTing

logger = logging.getLogger(__name__)


class HotkeyController:
    def __init__(self, main_window, hotkey: str):
        self.main_window = main_window
        self.hotkey_listener = KuaiJieJianJianTing(hotkey=hotkey)
        self.hotkey_listener.copy_translate_triggered.connect(self.main_window._handle_copy_translate)

        self.clipboard_monitor = ClipboardDoubleCopyMonitor(main_window)
        self.clipboard_monitor.double_copy_detected.connect(self.main_window._handle_double_copy_text)
        self._started = False

    def start(self) -> None:
        if sys.platform == "darwin":
            self.main_window._prompt_macos_accessibility_if_needed()

        if sys.platform != "darwin" or self.main_window._is_macos_accessibility_enabled():
            self.hotkey_listener.start()
            # 不默认启动剪贴板双复制监视器：它无法区分来源，容易把普通程序剪贴板变化误发到远程翻译。
            # 如需兼容特殊环境，请显式调用 start_clipboard_monitor()。
            self._started = True
            logger.info("成功启动快捷键监听")
            return

        self._started = False
        self.main_window.tishi.showMessage("请在系统设置启用辅助功能权限后重启应用", type="warning")

    def stop(self) -> None:
        try:
            self.hotkey_listener.stop()
            self._started = False
        except Exception as error:
            logger.error(f"停止快捷键监听失败: {error}")

        try:
            self.clipboard_monitor.stop()
        except Exception as error:
            logger.error(f"停止剪贴板监听失败: {error}")

    def reload_hotkey(self, hotkey: str) -> None:
        self.hotkey_listener.set_hotkey(hotkey)
        self._started = bool(getattr(self.hotkey_listener, "is_running", False))

    def start_clipboard_monitor(self) -> None:
        self.clipboard_monitor.start()
