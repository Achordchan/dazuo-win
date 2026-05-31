import asyncio
import logging
import time

import pyperclip
from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout

from .dialog_utils import get_dialog_palette, to_rgba
from .mini_chuangkou import MiniChuangKou

logger = logging.getLogger(__name__)


class WindowModeController:
    def __init__(self, main_window):
        self.main_window = main_window

    def ensure_mini_window(self):
        if not getattr(self.main_window, "mini_window", None):
            self.main_window.mini_window = MiniChuangKou(self.main_window)
        return self.main_window.mini_window

    def set_mini_mode(self, enabled: bool, show_hint: bool = True):
        self.main_window.is_mini_mode = enabled

        if enabled:
            self.ensure_mini_window()
            self.main_window.hide()
            if show_hint:
                self.show_mini_mode_hint()
            logger.info("已切换到Mini模式（窗口隐藏）")
        else:
            if getattr(self.main_window, "mini_window", None):
                self.main_window.mini_window.hide()
            self.main_window.show()
            self.main_window.activateWindow()
            logger.info("已切换到正常模式")

        if hasattr(self.main_window, "mini_mode_action"):
            self.main_window.mini_mode_action.setChecked(enabled)
        if hasattr(self.main_window, "toggle_mini_window_action"):
            self.main_window.toggle_mini_window_action.setEnabled(enabled)
        if hasattr(self.main_window, "toggle_mini_window_shortcut"):
            self.main_window.toggle_mini_window_shortcut.setEnabled(enabled)

        self.main_window.config.set("mini_mode", enabled)
        self.main_window.config.save()

    def toggle_mini_window(self):
        if not self.main_window.is_mini_mode:
            return

        mini_window = self.ensure_mini_window()
        if mini_window.isVisible():
            mini_window.hide()
            logger.info("隐藏Mini窗口")
        else:
            mini_window.show_at_cursor()
            logger.info("显示Mini窗口")

    def show_main_window(self):
        if self.main_window.isHidden():
            self.main_window.showNormal()
        else:
            self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def handle_copy_translate(self):
        now = time.monotonic()
        if now - getattr(self.main_window, "_last_copy_trigger_time", 0.0) < 0.35:
            return
        self.main_window._last_copy_trigger_time = now

        text = pyperclip.paste().strip()
        if not text:
            self.main_window.tishi.showMessage("剪贴板为空", type="warning")
            return

        if not self.main_window.config.get("mini_mode", False):
            self.show_main_window()

        if self.main_window.config.get("mini_mode", False):
            self.ensure_mini_window()
            asyncio.ensure_future(self.translate_and_show_mini(text))
            return

        self.main_window.input_text.setPlainText(text)
        self.main_window.translator_vm.translate_now(text, self.main_window._get_vm_context())

    def handle_double_copy_text(self, text: str):
        now = time.monotonic()
        if now - getattr(self.main_window, "_last_copy_trigger_time", 0.0) < 0.35:
            return
        self.main_window._last_copy_trigger_time = now

        if not text or not text.strip():
            self.main_window.tishi.showMessage("剪贴板为空", type="warning")
            return

        if not self.main_window.config.get("mini_mode", False):
            self.show_main_window()

        if self.main_window.config.get("mini_mode", False):
            self.ensure_mini_window()
            asyncio.ensure_future(self.translate_and_show_mini(text))
            return

        self.main_window.input_text.setPlainText(text)
        self.main_window.translator_vm.translate_now(text, self.main_window._get_vm_context())

    async def translate_and_show_mini(self, text_to_translate, service=None):
        try:
            mini_window = self.ensure_mini_window()
            mini_window.resize(300, 60)
            mini_window.output_text.clear()
            mini_window.show_at_cursor()
            mini_window.start_loading()

            translation_result = await self.main_window.fanyi.fanyi(
                text_to_translate,
                source_lang="auto",
                target_lang=self.main_window.target_lang_combo.currentText(),
            )

            translation_text = translation_result[0] if isinstance(translation_result, tuple) else translation_result
            if not translation_text:
                mini_window.stop_loading()
                mini_window.output_text.setText("翻译失败，请重试")
                return

            mini_window.stop_loading()
            mini_window.output_text.setText(translation_text)
            mini_window._adjust_window_size_for_text(translation_text)
            logger.info(f"Mini窗口已显示翻译结果: '{text_to_translate[:20]}...' -> '{translation_text[:20]}...'")
        except Exception as error:
            logger.error(f"Mini窗口翻译失败: {error}")
            if getattr(self.main_window, "mini_window", None):
                self.main_window.mini_window.stop_loading()
                self.main_window.mini_window.output_text.setText(f"翻译失败: {error}")

    def show_mini_mode_hint(self):
        try:
            palette = get_dialog_palette(self.main_window)
            hint = QFrame(None)
            hint.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.X11BypassWindowManagerHint
            )
            hint.setAttribute(Qt.WA_TranslucentBackground)
            hint.setAttribute(Qt.WA_ShowWithoutActivating)
            hint.setFrameShape(QFrame.StyledPanel)
            hint.setStyleSheet(
                "QFrame {"
                f"background-color: {to_rgba(palette.progress_start, 0.92)};"
                "border-radius: 20px;"
                f"border: 1px solid {palette.progress_start};"
                "}"
            )

            layout = QVBoxLayout(hint)
            layout.setContentsMargins(15, 10, 15, 10)

            msg_label = QLabel("已切换到迷你窗口模式")
            msg_label.setStyleSheet(f"color: {palette.text}; font-size: 14px; font-weight: bold;")
            msg_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(msg_label)

            screen = QApplication.desktop().screenGeometry()
            hint_width = 240
            hint_height = 60
            x = (screen.width() - hint_width) // 2
            y = int(screen.height() * 0.75)
            hint.setGeometry(x, y, hint_width, hint_height)
            hint.show()
            hint.raise_()

            def fade_out_and_close():
                animation = QPropertyAnimation(hint, b"windowOpacity")
                animation.setDuration(500)
                animation.setStartValue(1.0)
                animation.setEndValue(0.0)
                animation.setEasingCurve(QEasingCurve.InOutQuad)
                animation.finished.connect(hint.deleteLater)
                animation.start()

            QTimer.singleShot(2000, fade_out_and_close)
            logger.info("显示迷你模式切换提示")
        except Exception as error:
            logger.error(f"显示迷你模式切换提示失败: {error}")
