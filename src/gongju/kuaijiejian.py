"""全局快捷键监听模块"""
import pyperclip
import logging
import ctypes
import sys
import time
from typing import Any, List, Optional
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication

try:
    import keyboard
except Exception as error:  # pragma: no cover - depends on optional OS hook package
    keyboard = None
    _keyboard_import_error = error
else:
    _keyboard_import_error = None

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def is_admin():
    """检查是否具有管理员权限"""
    try:
        if sys.platform == 'win32':
            return ctypes.windll.shell32.IsUserAnAdmin()
        return False  # 非 Windows 平台返回 False
    except Exception as e:
        logger.error(f"检查管理员权限失败: {e}")
        return False

class KuaiJieJianJianTing(QObject):
    """快捷键监听器"""
    copy_translate_triggered = pyqtSignal()  # 信号：复制翻译触发
    
    def __init__(self, hotkey: str = "ctrl+c,c"):
        super().__init__()
        self._modifier_key = "command" if sys.platform == "darwin" else "ctrl"
        self._double_copy_hotkey = f"{self._modifier_key}+c,c"
        self._copy_sequence = f"{self._modifier_key}+c"
        self._hotkey = self._normalize_hotkey(hotkey)
        self._is_modifier_pressed = False
        self._last_modifier_time = 0
        self._last_c_time = 0
        self._combination_active = False
        self._hotkey_handle = None
        self._key_hook_handles: List[Any] = []
        self._is_triggering = False
        self._use_double_copy = self._hotkey == self._double_copy_hotkey
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def _require_keyboard(self):
        if keyboard is None:
            raise RuntimeError(f"缺少 keyboard 依赖，无法启动快捷键监听: {_keyboard_import_error}")
        return keyboard
    
    def start(self):
        """启动快捷键监听"""
        try:
            self.stop()
            keyboard_module = self._require_keyboard()
            self._hotkey_handle = None
            self._key_hook_handles = []
            self._is_triggering = False
            self._use_double_copy = self._hotkey == self._double_copy_hotkey

            if self._use_double_copy:
                self._key_hook_handles.append(
                    keyboard_module.on_press_key(self._modifier_key, self._on_modifier_press, suppress=False)
                )
                self._key_hook_handles.append(
                    keyboard_module.on_release_key(self._modifier_key, self._on_modifier_release, suppress=False)
                )
                self._key_hook_handles.append(
                    keyboard_module.on_press_key('c', self._on_c_press, suppress=False)
                )
            else:
                if not self._hotkey:
                    self._hotkey = self._double_copy_hotkey
                    self._use_double_copy = True
                    self.start()
                    return
                self._hotkey_handle = keyboard_module.add_hotkey(
                    self._hotkey,
                    self._on_hotkey_trigger,
                    suppress=False,
                )

            self._is_running = True
            logger.info("快捷键监听器启动成功")
        except Exception as e:
            self._is_running = False
            self._remove_registered_hooks()
            logger.error(f"快捷键监听器启动失败: {e}")
            raise
    
    def stop(self):
        """停止快捷键监听"""
        try:
            self._remove_registered_hooks()
            self._is_triggering = False
            self._is_modifier_pressed = False
            self._combination_active = False
            self._is_running = False
            logger.info("快捷键监听器已停止")
        except Exception as e:
            logger.error(f"停止快捷键监听器失败: {e}")

    def _remove_registered_hooks(self):
        if keyboard is None:
            self._hotkey_handle = None
            self._key_hook_handles = []
            return

        if self._hotkey_handle is not None:
            try:
                keyboard.remove_hotkey(self._hotkey_handle)
            except Exception:
                try:
                    keyboard.unhook(self._hotkey_handle)
                except Exception as error:
                    logger.debug("移除快捷键 hook 失败: %s", error)
            self._hotkey_handle = None

        for handle in self._key_hook_handles:
            try:
                if callable(handle):
                    handle()
                else:
                    keyboard.unhook(handle)
            except Exception:
                try:
                    keyboard.unhook(handle)
                except Exception as error:
                    logger.debug("移除按键 hook 失败: %s", error)
        self._key_hook_handles = []

    def set_hotkey(self, hotkey: str):
        normalized = self._normalize_hotkey(hotkey)
        if normalized == self._hotkey:
            if not self._is_running:
                self.start()
            return
        old_hotkey = self._hotkey
        old_use_double_copy = self._use_double_copy
        self._hotkey = normalized
        try:
            self.start()
        except Exception:
            self._hotkey = old_hotkey
            self._use_double_copy = old_use_double_copy
            try:
                self.start()
            except Exception as restore_error:
                logger.error("恢复旧快捷键失败: %s", restore_error)
            raise

    def _normalize_hotkey(self, hotkey: str) -> str:
        normalized = (hotkey or "").strip().lower().replace(" ", "")
        if sys.platform == "darwin":
            normalized = normalized.replace("cmd+", "command+")
            normalized = normalized.replace("meta+", "command+")
            normalized = normalized.replace("cmd,", "command,")
            normalized = normalized.replace("meta,", "command,")
        return normalized

    def _on_hotkey_trigger(self):
        self._trigger_translate()

    def _trigger_translate(self):
        if self._is_triggering:
            return
        old_text = ""
        self._is_triggering = True
        try:
            keyboard_module = self._require_keyboard()
            old_text = pyperclip.paste()
            keyboard_module.send(self._copy_sequence)
            time.sleep(0.1)
            new_text = pyperclip.paste()

            if new_text and new_text.strip():
                self.copy_translate_triggered.emit()
                logger.info(f"触发复制翻译，文本长度: {len(new_text)}")
                self._combination_active = True
            else:
                logger.info("未选中文本，不触发翻译")
                if old_text and old_text != new_text:
                    pyperclip.copy(old_text)
        except Exception as e:
            logger.error(f"处理复制翻译失败: {e}")
            try:
                if old_text:
                    pyperclip.copy(old_text)
            except Exception:
                pass
        finally:
            self._is_triggering = False
    
    def _on_modifier_press(self, event):
        """修饰键按下事件处理"""
        if not self._is_modifier_pressed:
            self._is_modifier_pressed = True
            self._last_modifier_time = time.time()
            self._combination_active = False
    
    def _on_modifier_release(self, event):
        """修饰键释放事件处理"""
        self._is_modifier_pressed = False
        self._combination_active = False
    
    def _on_c_press(self, event):
        """C 键按下事件处理"""
        if self._is_triggering:
            return
        current_time = time.time()
        
        # 只有在修饰键按下的状态下才处理
        if self._is_modifier_pressed:
            # 检查是否是快速的双击 C
            if (current_time - self._last_c_time) < 0.3:  # 300ms内的双击C
                self._last_c_time = current_time
                self._trigger_translate()
                return
            
            self._last_c_time = current_time
    
    def __del__(self):
        """析构函数，确保停止监听"""
        self.stop() 


class ClipboardDoubleCopyMonitor(QObject):
    double_copy_detected = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self._is_running = False
        self._window_ms = 550
        self._poll_interval_ms = 180

        self._last_seq: Optional[int] = None
        self._last_change_time: Optional[float] = None
        self._latest_text: Optional[str] = None

    def start(self, window_ms: int = 550, poll_interval_ms: int = 180):
        self.stop()
        self._is_running = True
        self._window_ms = int(window_ms)
        self._poll_interval_ms = int(poll_interval_ms)
        self._last_seq = self._get_clipboard_sequence_number()
        self._last_change_time = None
        self._latest_text = self._read_clipboard_text()

        self._timer.start(self._poll_interval_ms)
        logger.info("剪贴板监听已启动")

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
        self._is_running = False
        self._last_change_time = None

    def _get_clipboard_sequence_number(self) -> Optional[int]:
        if sys.platform != 'win32':
            return None
        try:
            return int(ctypes.windll.user32.GetClipboardSequenceNumber())
        except Exception:
            return None

    def _read_clipboard_text(self) -> str:
        try:
            cb = QApplication.clipboard()
            text = cb.text() or ""
            return text
        except Exception:
            return ""

    def _tick(self):
        if not self._is_running:
            return

        seq = self._get_clipboard_sequence_number()
        now = time.monotonic()
        new_text = self._read_clipboard_text()

        if seq is not None:
            if self._last_seq is not None and seq == self._last_seq:
                return
            self._last_seq = seq
        else:
            # 非 Windows 或无法获取 changeCount 时：退化为“文本变化”检测，避免每个 tick 都当作一次变化。
            if self._latest_text is not None and new_text == self._latest_text:
                return

        try_trigger = False
        if self._last_change_time is not None:
            delta_ms = (now - self._last_change_time) * 1000
            if delta_ms <= float(self._window_ms):
                try_trigger = True

        if try_trigger:
            text = new_text or self._latest_text or ""
            if text.strip():
                logger.info(f"检测到双复制（{int((now - self._last_change_time) * 1000)}ms）")
                self.double_copy_detected.emit(text)
            else:
                logger.info("检测到双复制，但剪贴板无文本")

        self._latest_text = new_text
        self._last_change_time = now
