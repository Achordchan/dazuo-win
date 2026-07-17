"""全局快捷键监听模块"""
import pyperclip
import logging
import ctypes
import sys
import time
import uuid
from typing import Any, Dict, List, Optional
from PyQt5.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal, QMimeData
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
    copy_translate_triggered = pyqtSignal(str)  # 信号：复制翻译触发

    # Hook 回调运行在 keyboard 后台线程；Qt 剪贴板必须在 GUI 线程访问。
    _clipboard_snapshot_request = pyqtSignal(object)
    _clipboard_restore_request = pyqtSignal(object)
    
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

        self._clipboard_snapshot_request.connect(
            self._handle_clipboard_snapshot_request, Qt.BlockingQueuedConnection
        )
        self._clipboard_restore_request.connect(
            self._handle_clipboard_restore_request, Qt.BlockingQueuedConnection
        )

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

    def _get_clipboard_sequence_number(self):
        if sys.platform != "win32":
            return None
        try:
            return int(ctypes.windll.user32.GetClipboardSequenceNumber())
        except Exception:
            return None

    def _read_clipboard_text(self) -> str:
        try:
            return pyperclip.paste() or ""
        except Exception:
            return ""

    def _write_clipboard_text(self, text: str) -> bool:
        try:
            pyperclip.copy(text or "")
            return True
        except Exception:
            return False

    def _mime_payload_from_clipboard(self, mime: Optional[QMimeData]) -> Dict[str, bytes]:
        """Copy MIME formats into plain Python bytes. No QMimeData leaves this helper."""
        payload: Dict[str, bytes] = {}
        if mime is None:
            return payload
        try:
            for fmt in mime.formats():
                data = mime.data(fmt)
                try:
                    payload[str(fmt)] = bytes(data)
                except Exception:
                    # QByteArray may already be bytes-like on some bindings.
                    payload[str(fmt)] = bytes(bytearray(data))
        except Exception as error:
            logger.debug("extract clipboard mime payload failed: %s", error)
            return {}
        return payload

    def _mime_data_from_payload(self, payload: Optional[Dict[str, bytes]]) -> Optional[QMimeData]:
        """Rebuild QMimeData on the GUI thread from plain Python bytes."""
        if not payload:
            return None
        try:
            mime = QMimeData()
            for fmt, data in payload.items():
                if not fmt:
                    continue
                raw = data if isinstance(data, (bytes, bytearray, memoryview)) else bytes(data)
                mime.setData(str(fmt), bytes(raw))
            if not mime.formats():
                return None
            return mime
        except Exception as error:
            logger.debug("rebuild clipboard mime failed: %s", error)
            return None

    def _on_gui_thread(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return True
        return QThread.currentThread() is app.thread()

    def _empty_clipboard_snapshot(self) -> dict:
        return {
            "text": "",
            "mime_formats": {},
            "has_mime": False,
        }

    def _snapshot_clipboard_on_gui(self) -> dict:
        """Capture full clipboard payload as plain Python data. Must run on GUI thread."""
        snapshot = self._empty_clipboard_snapshot()
        snapshot["text"] = self._read_clipboard_text()
        try:
            clipboard = QApplication.clipboard()
            mime = clipboard.mimeData() if clipboard is not None else None
            payload = self._mime_payload_from_clipboard(mime)
            if payload:
                snapshot["mime_formats"] = payload
                snapshot["has_mime"] = True
        except Exception as error:
            logger.debug("snapshot clipboard failed: %s", error)
        return snapshot

    def _restore_clipboard_snapshot_on_gui(self, snapshot: Optional[dict]) -> None:
        """Restore full clipboard payload. Must run on the GUI thread."""
        if not snapshot:
            return
        payload = snapshot.get("mime_formats")
        # Backward-compatible: older callers may still stash a QMimeData under "mime".
        legacy_mime = snapshot.get("mime")
        if snapshot.get("has_mime") or payload or isinstance(legacy_mime, QMimeData):
            try:
                clipboard = QApplication.clipboard()
                if isinstance(legacy_mime, QMimeData) and not payload:
                    restore = self._mime_data_from_payload(
                        self._mime_payload_from_clipboard(legacy_mime)
                    )
                else:
                    restore = self._mime_data_from_payload(
                        payload if isinstance(payload, dict) else None
                    )
                if restore is not None and clipboard is not None:
                    clipboard.setMimeData(restore)
                    return
            except Exception as error:
                logger.debug("restore clipboard mime failed: %s", error)
        # Fallback: plain text, including empty string to clear a leftover marker.
        self._write_clipboard_text(str(snapshot.get("text") or ""))

    def _handle_clipboard_snapshot_request(self, out: list) -> None:
        out.append(self._snapshot_clipboard_on_gui())

    def _handle_clipboard_restore_request(self, snapshot: object) -> None:
        if isinstance(snapshot, dict) or snapshot is None:
            self._restore_clipboard_snapshot_on_gui(snapshot)

    def _snapshot_clipboard(self) -> dict:
        """Capture clipboard from the GUI thread even when called by hook threads."""
        if self._on_gui_thread():
            return self._snapshot_clipboard_on_gui()
        out: List[dict] = []
        self._clipboard_snapshot_request.emit(out)
        if out:
            return out[0]
        # Fallback if the GUI thread could not service the request.
        fallback = self._empty_clipboard_snapshot()
        fallback["text"] = self._read_clipboard_text()
        return fallback

    def _restore_clipboard_snapshot(self, snapshot: Optional[dict]) -> None:
        if self._on_gui_thread():
            self._restore_clipboard_snapshot_on_gui(snapshot)
            return
        self._clipboard_restore_request.emit(snapshot)

    def _wait_for_windows_clipboard_change(
        self,
        previous_seq,
        timeout_seconds: float = 0.35,
        poll_seconds: float = 0.02,
    ):
        deadline = time.monotonic() + max(timeout_seconds, 0.05)
        last_text = ""
        while time.monotonic() < deadline:
            seq = self._get_clipboard_sequence_number()
            last_text = self._read_clipboard_text()
            if previous_seq is not None and seq is not None and seq != previous_seq and last_text.strip():
                return last_text, seq, True
            time.sleep(poll_seconds)
        last_text = self._read_clipboard_text()
        seq = self._get_clipboard_sequence_number()
        ready = (
            previous_seq is not None
            and seq is not None
            and seq != previous_seq
            and bool(last_text.strip())
        )
        return last_text, seq, ready

    def _wait_for_clipboard_marker_replace(
        self,
        marker: str,
        timeout_seconds: float = 0.45,
        poll_seconds: float = 0.02,
    ):
        """Non-Windows: prove a real copy by requiring the marker to be replaced."""
        deadline = time.monotonic() + max(timeout_seconds, 0.05)
        last_text = marker
        while time.monotonic() < deadline:
            last_text = self._read_clipboard_text()
            if last_text.strip() and last_text != marker:
                return last_text, True
            time.sleep(poll_seconds)
        last_text = self._read_clipboard_text()
        return last_text, bool(last_text.strip() and last_text != marker)

    def _trigger_translate(self):
        if self._is_triggering:
            return
        clipboard_snapshot = None
        marker = ""
        used_marker = False
        self._is_triggering = True
        try:
            keyboard_module = self._require_keyboard()
            previous_seq = self._get_clipboard_sequence_number()

            if previous_seq is not None:
                # Windows: clipboard generation number is the ground truth.
                # Do not rewrite clipboard content before the synthetic copy.
                keyboard_module.send(self._copy_sequence)
                new_text, new_seq, clipboard_ready = self._wait_for_windows_clipboard_change(previous_seq)
                if not clipboard_ready:
                    logger.info("clipboard sequence unchanged after copy; skip translate")
                    return
            else:
                # Non-Windows has no sequence number. Snapshot full clipboard first,
                # then write a one-shot marker. A successful synthetic copy must
                # replace the marker. If copy fails, always restore the snapshot
                # (including empty/image/file payloads) so the marker never sticks.
                clipboard_snapshot = self._snapshot_clipboard()
                marker = f"__DZFYQ_COPY_{uuid.uuid4().hex}__"
                if not self._write_clipboard_text(marker):
                    logger.info("failed to write clipboard marker; skip translate")
                    self._restore_clipboard_snapshot(clipboard_snapshot)
                    return
                used_marker = True
                keyboard_module.send(self._copy_sequence)
                new_text, clipboard_ready = self._wait_for_clipboard_marker_replace(marker)
                if not clipboard_ready:
                    # Retry once for slow apps.
                    keyboard_module.send(self._copy_sequence)
                    new_text, clipboard_ready = self._wait_for_clipboard_marker_replace(
                        marker,
                        timeout_seconds=0.25,
                    )
                if not clipboard_ready:
                    logger.info("clipboard marker not replaced after copy; skip translate")
                    self._restore_clipboard_snapshot(clipboard_snapshot)
                    return
                new_seq = None

            snapshot = new_text
            if snapshot and snapshot.strip() and snapshot != marker:
                self.copy_translate_triggered.emit(snapshot)
                logger.info(
                    "triggered copy-translate, text length=%s, seq=%s->%s, double_copy=%s, marker=%s",
                    len(snapshot),
                    previous_seq,
                    new_seq if previous_seq is not None else None,
                    self._use_double_copy,
                    used_marker,
                )
                self._combination_active = True
            else:
                logger.info("clipboard empty after copy; skip translate")
                if used_marker:
                    self._restore_clipboard_snapshot(clipboard_snapshot)
        except Exception as e:
            logger.error(f"处理复制翻译失败: {e}")
            try:
                if used_marker:
                    self._restore_clipboard_snapshot(clipboard_snapshot)
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

        previous_text = self._latest_text
        try_trigger = False
        if self._last_change_time is not None:
            delta_ms = (now - self._last_change_time) * 1000
            if delta_ms <= float(self._window_ms):
                try_trigger = True

        # 仅当窗口内连续两次都写入非空文本时才触发，避免任意程序连续改剪贴板误发翻译。
        if try_trigger:
            text = (new_text or "").strip()
            prev = (previous_text or "").strip()
            if text and prev:
                logger.info(f"检测到双复制（{int((now - self._last_change_time) * 1000)}ms）")
                self.double_copy_detected.emit(text)
            else:
                logger.info("检测到快速剪贴板变化，但缺少有效文本，跳过翻译")

        self._latest_text = new_text
        self._last_change_time = now
