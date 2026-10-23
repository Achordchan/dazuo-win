"""用真实 Qt/qasync 调度验证弹窗期间的连接恢复；网络和安装操作只在测试中替换。"""
import asyncio
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import traceback
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen")

from tools.smoke_tests import temporary_profile


def check_logging():
    # 模拟第三方模块已配置控制台日志，应用仍须可靠地安装文件日志。
    logging.basicConfig(level=logging.WARNING)
    from src.main import setup_logging

    setup_logging()
    setup_logging()
    handlers = [h for h in logging.getLogger().handlers if isinstance(h, logging.FileHandler)]
    assert len(handlers) == 1, handlers
    logging.info("connection-retry-log-check 中文")
    for handler in handlers:
        handler.flush()
    assert "connection-retry-log-check 中文" in Path(handlers[0].baseFilename).read_text(encoding="utf-8")


def run_case(case):
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QTextEdit, QWidget
    import qasync
    from src.gongju.fanyi import DaZaoFanYi, TranslationServiceError
    from src.gui import dialog_utils, translator_controller, update_controller
    from src.gui.zhuchuangkou import ZhuChuangKou
    from src.gui.zhuangtai import ZhuangTaiZhiShiQi
    from src.shezhi.config import Config
    from src.viewmodels.translator_viewmodel import TranslationContext, TranslatorViewModel

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    failures = []
    loop.set_exception_handler(lambda _loop, ctx: failures.append(str(ctx.get("exception") or ctx["message"])))
    owner = QWidget()
    owner.config = Config()
    owner.config.set("translation.api", "microsoft")
    owner.fanyi = DaZaoFanYi()
    owner.translator_vm = TranslatorViewModel(owner.fanyi)
    owner.service_display = QLabel(owner)
    owner.status_indicator = ZhuangTaiZhiShiQi(owner)
    owner.input_text = QTextEdit(owner)
    owner.input_text.setPlainText("hello")
    owner.tishi = SimpleNamespace(showMessage=Mock())
    owner._get_vm_context = lambda: TranslationContext("microsoft", owner.fanyi.current_api_generation, "英语", "简体中文", None)
    owner._init_translation_api = lambda: translator_controller.init_translation_api(owner)
    owner.reload_translation_api = lambda: ZhuChuangKou.reload_translation_api(owner)
    outputs = []
    owner.translator_vm.output_text_changed.connect(outputs.append)
    coordinator = update_controller.UpdateCoordinator(owner)
    coordinator._start_update_download = Mock()
    coordinator._install_non_windows_update = Mock()
    coordinator.updater.discard_downloaded_update = Mock()
    dialogs = []
    prompt_result = QDialog.Accepted if case == "accept" else QDialog.Rejected

    class Prompt(update_controller.UpdatePromptDialog):
        def __init__(self, *args):
            super().__init__(*args)
            dialogs.append(self)
            self.setAttribute(Qt.WA_DontShowOnScreen)

    class Message(QMessageBox):
        def __init__(self, *args):
            super().__init__(*args)
            dialogs.append(self)
            self.setAttribute(Qt.WA_DontShowOnScreen)

    instances = []
    def build_api(_config):
        api = SimpleNamespace(fanyi=AsyncMock(return_value=("你好", "en")), close=AsyncMock())
        async def health():
            await asyncio.sleep(0.04)
            if case == "retry_after_failure" and len(instances) == 1:
                raise TranslationServiceError("模拟连接超时", kind="timeout")
        api.health_check = health
        instances.append(api)
        return api

    async def exercise():
        owner.reload_translation_api()
        await asyncio.sleep(0.01)
        if case in {"error", "forced_error"}:
            coordinator.updater.force_update = case == "forced_error"
            coordinator.updater.update_error.emit("模拟更新失败")
            assert coordinator._update_error_occurred
        elif case in {"mac_accept", "mac_cancel"}:
            with patch.object(update_controller.sys, "platform", "darwin"):
                coordinator.on_update_complete("unused.dmg")
            coordinator._install_non_windows_update.assert_not_called()
        elif case == "message":
            dialog_utils.open_themed_message(owner, icon=QMessageBox.Information, title="验证成功", text="验证已完成")
        else:
            coordinator.updater.update_available.emit("9.9.9", "更新说明", case == "forced_reject")
            coordinator._start_update_download.assert_not_called()
            assert coordinator._modal_dialog_active
            if case == "pending":
                coordinator.updater.update_available.emit("9.9.10", "下一条更新", False)
                assert len(dialogs) == 1
        await owner._init_translation_api_task
        assert not owner._translation_api_lock.locked()
        # 弹窗尚未关闭时旧任务已经完成，并且重试可以重新建立连接。
        assert dialogs[0].isVisible()
        translator_controller.retry_connection(owner)
        await owner._init_translation_api_task
        await owner.translator_vm._translation_task
        assert owner.fanyi.connection_state == "connected"
        assert outputs[-1] == "你好"
        assert len(instances) == 2
        assert not owner._translation_api_lock.locked()
        closed = 0
        while closed < len(dialogs):
            dialog = dialogs[closed]
            result = prompt_result if isinstance(dialog, Prompt) else (
                QMessageBox.Cancel if case == "mac_cancel" else QMessageBox.Ok
            )
            dialog.done(result)
            closed += 1
            await asyncio.sleep(0)
        if case == "accept":
            coordinator._start_update_download.assert_called_once()
        elif case == "mac_accept":
            coordinator._install_non_windows_update.assert_called_once_with("unused.dmg")
        elif case == "mac_cancel":
            coordinator.updater.discard_downloaded_update.assert_called_once_with("unused.dmg")
            coordinator._install_non_windows_update.assert_not_called()
        elif case == "forced_reject":
            exit_mock.assert_called_once_with(0)
        elif case == "forced_error":
            exit_mock.assert_called_once_with(1)
        else:
            coordinator._start_update_download.assert_not_called()
        if case == "pending":
            assert len(dialogs) == 2
            assert coordinator._pending_update_prompt is None
        assert not coordinator._modal_dialog_active
        await owner.translator_vm.cancel_and_wait(False)
        await owner.fanyi.close_current_api()

    watchdog = QTimer()
    watchdog.setSingleShot(True)
    def timeout():
        failures.append("Qt watchdog: connection/retry did not finish within 3 seconds")
        for widget in app.topLevelWidgets():
            widget.close()
        loop.stop()
    watchdog.timeout.connect(timeout)
    with patch.object(translator_controller, "build_translation_api", side_effect=build_api), patch.object(update_controller, "UpdatePromptDialog", Prompt), patch.object(dialog_utils, "QMessageBox", Message), patch.object(update_controller.sys, "exit") as exit_mock:
        task = loop.create_task(exercise())
        task.add_done_callback(lambda _task: loop.stop())
        watchdog.start(3000)
        loop.run_forever()
        watchdog.stop()
        if task.done():
            try:
                task.result()
            except Exception:
                failures.append(traceback.format_exc())
        for widget in app.topLevelWidgets():
            widget.close()
        for pending in asyncio.all_tasks(loop):
            pending._log_destroy_pending = False
        loop.close()
    assert not failures, json.dumps(failures, ensure_ascii=False)


def main():
    if len(sys.argv) == 2:
        with temporary_profile():
            try:
                if sys.argv[1] == "logging":
                    check_logging()
                else:
                    run_case(sys.argv[1])
            finally:
                logging.shutdown()
        return
    for case in ("reject", "accept", "error", "retry_after_failure", "pending", "forced_reject", "forced_error", "mac_accept", "mac_cancel", "message", "logging"):
        result = subprocess.run([sys.executable, __file__, case], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        assert result.returncode == 0, f"{case}\n{result.stdout}\n{result.stderr}"
        print(f"ok {case}")


if __name__ == "__main__":
    main()
