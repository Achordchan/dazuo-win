import asyncio
import configparser
import json
import logging
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QToolTip,
    QVBoxLayout,
)

from .dialog_utils import apply_dialog_theme, install_chinese_context_menu, show_themed_message
from .gengxinrizhi import GengXinRiZhi
from ..gongju.update import Updater
from ..version import APP_VERSION

logger = logging.getLogger(__name__)


class UpdatePromptDialog(QDialog):
    def __init__(self, parent, version: str, notes: str, force_update: bool):
        super().__init__(parent)
        self.setWindowTitle("发现新版本")
        self.setFixedSize(520, 360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel("发现重要更新" if force_update else "发现新版本")
        title.setObjectName("updateTitle")
        subtitle = QLabel(f"版本 v{version}")
        subtitle.setObjectName("updateSubtitle")
        notes_label = QLabel("更新说明")
        notes_label.setObjectName("updateSection")

        notes_box = QTextBrowser()
        notes_box.setObjectName("updateNotes")
        notes_box.setText(notes or "暂无更新说明")
        notes_box.setOpenExternalLinks(True)
        notes_box.setReadOnly(True)
        install_chinese_context_menu(notes_box)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)
        action_row.addStretch()

        cancel_btn = QPushButton("稍后再说")
        cancel_btn.setObjectName("updateCancel")
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("立即更新")
        ok_btn.setObjectName("updateOk")
        ok_btn.clicked.connect(self.accept)

        if force_update:
            cancel_btn.setText("拒绝")

        action_row.addWidget(cancel_btn)
        action_row.addWidget(ok_btn)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(notes_label)
        layout.addWidget(notes_box)
        layout.addLayout(action_row)

        apply_dialog_theme(self, parent)


class UpdateProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("更新下载中")
        self.setFixedSize(460, 180)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        title = QLabel("正在下载更新")
        title.setObjectName("progressTitle")
        subtitle_text = "请保持网络连接，下载完成后将静默替换并重启"
        if sys.platform == "darwin":
            subtitle_text = "请保持网络连接，下载完成后将打开 DMG"
        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("progressSubtitle")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setObjectName("progressBar")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.progress_bar)

        apply_dialog_theme(self, parent)

    def set_progress(self, value: int):
        self.progress_bar.setValue(value)


class UpdateCoordinator:
    def __init__(self, owner):
        self.owner = owner
        self.updater = Updater()
        self.progress_dialog = None
        self._update_checking = False
        self._update_error_occurred = False
        self._modal_dialog_active = False
        self._pending_update_prompt = None
        self._update_operation_active = False
        self._feedback_owner = None

        self.updater.update_available.connect(self.on_update_available)
        self.updater.update_progress.connect(self.on_update_progress)
        self.updater.update_error.connect(self.on_update_error)
        self.updater.update_complete.connect(self.on_update_complete)

    def _consume_json_state(self, path: str):
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8-sig") as file:
                payload = json.load(file)
            return payload if isinstance(payload, dict) else {}
        except Exception as error:
            logger.warning(f"读取更新状态失败: {path}, {error}")
            return {}
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def report_previous_update_state(self):
        result = self._consume_json_state(self.updater._last_update_result_path())
        if result and result.get("status") == "success":
            self.updater._prune_update_backups()
        elif result and result.get("status") == "failed":
            log_path = result.get("log_path") or ""
            message = result.get("message") or "更新替换脚本未返回具体错误。"
            show_themed_message(
                self.owner,
                icon=QMessageBox.Warning,
                title="上次更新未完成",
                text=f"上次更新到 v{result.get('expected_version') or '新版本'} 失败。",
                informative_text=f"{message}\n\n日志：{log_path}" if log_path else message,
                buttons=QMessageBox.Ok,
            )

        pending = self._consume_json_state(self.updater._pending_update_path())
        if pending:
            expected_version = pending.get("expected_version") or ""
            if expected_version and expected_version != APP_VERSION:
                log_path = pending.get("log_path") or ""
                show_themed_message(
                    self.owner,
                    icon=QMessageBox.Warning,
                    title="上次更新未完成",
                    text=f"上次更新到 v{expected_version} 没有完成。",
                    informative_text=f"当前仍在运行 v{APP_VERSION}。\n\n日志：{log_path}" if log_path else f"当前仍在运行 v{APP_VERSION}。",
                    buttons=QMessageBox.Ok,
                )

    def load_first_run_state(self):
        config = configparser.ConfigParser()
        config_path = self._get_first_run_config_path()
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        if os.path.exists(config_path):
            config.read(config_path, encoding="utf-8")
        else:
            legacy_config_path = self._get_legacy_first_run_config_path()
            if legacy_config_path and os.path.exists(legacy_config_path):
                config.read(legacy_config_path, encoding="utf-8")
        if not config.has_section("App"):
            config.add_section("App")
        return config, config_path

    def persist_first_run_state(self, config, config_path) -> None:
        try:
            with open(config_path, "w", encoding="utf-8") as file:
                config.write(file)
            logger.info("成功更新配置文件")
        except Exception as error:
            logger.error(f"写入配置文件失败: {error}")

    def show_changelog_if_needed(self):
        self._modal_dialog_active = True
        try:
            self.report_previous_update_state()
            config, config_path = self.load_first_run_state()
            config_changed = False
            last_version = config.get("App", "last_version", fallback="")
            if last_version != APP_VERSION:
                config.set("App", "first_run", "0")
                config.set("App", "last_version", APP_VERSION)
                config_changed = True

            first_run = config.getint("App", "first_run", fallback=0)
            if first_run == 0:
                dialog = GengXinRiZhi(self.owner)
                dialog.setModal(True)
                dialog.exec_()
                config.set("App", "first_run", "1")
                config_changed = True

            if config_changed:
                self.persist_first_run_state(config, config_path)
        except Exception as error:
            logger.error(f"显示更新日志失败: {error}")
        finally:
            self._modal_dialog_active = False
            self._flush_pending_update_prompt()

    def check_update(self, show_no_update_message: bool = False):
        if self._update_checking or self._update_operation_active:
            return
        self._update_checking = True
        self._update_error_occurred = False

        async def run():
            try:
                has_update = await self.updater.check_update()
                if show_no_update_message and not has_update and not self._update_error_occurred:
                    self._show_latest_hint("当前已是最新版本")
            finally:
                self._update_checking = False
                self._feedback_owner = None

        asyncio.get_event_loop().create_task(run())

    def check_update_with_message(self, feedback_owner=None):
        if self._update_checking or self._update_operation_active:
            return
        self._feedback_owner = feedback_owner
        self.check_update(show_no_update_message=True)

    def on_update_available(self, version, notes, force_update):
        if self._modal_dialog_active:
            self._pending_update_prompt = (version, notes, force_update)
            return

        self._handle_update_available(version, notes, force_update)

    def _flush_pending_update_prompt(self):
        if self._modal_dialog_active or not self._pending_update_prompt:
            return
        version, notes, force_update = self._pending_update_prompt
        self._pending_update_prompt = None
        self._handle_update_available(version, notes, force_update)

    def _handle_update_available(self, version, notes, force_update):
        requested_force_update = bool(
            force_update or getattr(self.updater, "force_update_requested", False)
        )
        self._show_update_prompt(version, notes, requested_force_update)

    def _show_update_prompt(self, version, notes, force_update):
        self._modal_dialog_active = True
        try:
            dialog = UpdatePromptDialog(self.owner, version, notes, force_update)
            result = dialog.exec_()
        finally:
            self._modal_dialog_active = False
        if result == QDialog.Accepted:
            self._start_update_download()
            self._flush_pending_update_prompt()
            return

        if force_update:
            show_themed_message(
                self.owner,
                icon=QMessageBox.Critical,
                title="必须更新",
                text="此版本为重要更新，未更新将退出程序。",
                buttons=QMessageBox.Ok,
            )
            sys.exit(0)
        self._flush_pending_update_prompt()

    def on_update_progress(self, progress):
        if self.progress_dialog is not None:
            self.progress_dialog.set_progress(progress)

    def on_update_error(self, error):
        self._update_operation_active = False
        self._update_error_occurred = True
        show_themed_message(
            self.owner,
            icon=QMessageBox.Warning,
            title="更新失败",
            text=error,
            buttons=QMessageBox.Ok,
        )
        if self.progress_dialog is not None:
            self.progress_dialog.close()

        if getattr(self.updater, "force_update", False):
            show_themed_message(
                self.owner,
                icon=QMessageBox.Critical,
                title="更新失败",
                text="强制更新失败，程序将退出。",
                informative_text="请检查网络连接后重试。",
                buttons=QMessageBox.Ok,
            )
            sys.exit(1)

    def on_update_complete(self, file_path):
        if self.progress_dialog is not None:
            self.progress_dialog.close()

        force_update = getattr(self.updater, "force_update", False)
        if sys.platform == "win32":
            asyncio.get_event_loop().create_task(self._install_windows_update(file_path))
            return

        if force_update:
            if sys.platform == "darwin":
                show_themed_message(
                    self.owner,
                    icon=QMessageBox.Information,
                    title="下载完成",
                    text="更新已下载完成，将打开 DMG。",
                    informative_text="请手动将应用替换为新版本后重新启动。",
                    buttons=QMessageBox.Ok,
                )
                self._install_non_windows_update(file_path)
                return

        if sys.platform == "darwin":
            reply = show_themed_message(
                self.owner,
                icon=QMessageBox.Information,
                title="下载完成",
                text="更新已下载完成，将打开 DMG。",
                informative_text="请手动将应用替换为新版本后重新启动。",
                buttons=QMessageBox.Ok | QMessageBox.Cancel,
                default_button=QMessageBox.Ok,
                primary_button=QMessageBox.Ok,
            )
            if reply == QMessageBox.Ok:
                self._install_non_windows_update(file_path)
            else:
                self.updater.discard_downloaded_update(file_path)
                self._update_operation_active = False
            return

        show_themed_message(
            self.owner,
            icon=QMessageBox.Warning,
            title="暂不支持",
            text="当前平台暂不支持自动更新。",
            buttons=QMessageBox.Ok,
        )
        self.updater.discard_downloaded_update(file_path)
        self._update_operation_active = False

    def _start_update_download(self):
        if self._update_operation_active or getattr(self.updater, "download_in_progress", False):
            return
        self._update_operation_active = True
        self._ensure_progress_dialog()
        asyncio.get_event_loop().create_task(self.updater.download_update())

    def _install_non_windows_update(self, file_path: str):
        try:
            self.updater.install_update(file_path)
        except Exception as error:
            logger.error("安装更新失败: %s", error)
            self.on_update_error(f"安装更新失败: {error}")
        finally:
            self._update_operation_active = False

    async def _install_windows_update(self, file_path: str):
        try:
            await self._prepare_owner_for_update()
            self.updater.install_update(file_path)
        except Exception as error:
            logger.error(f"安装 Windows 更新失败: {error}")
            await self._restore_owner_after_failed_update()
            self.on_update_error(f"安装更新失败: {error}")
        finally:
            self._update_operation_active = False

    async def _prepare_owner_for_update(self):
        if hasattr(self.owner, "translator_vm"):
            try:
                await asyncio.wait_for(self.owner.translator_vm.cancel_and_wait(clear_output=False), timeout=5)
            except Exception as error:
                logger.warning(f"取消翻译任务失败: {error}")

        init_task = getattr(self.owner, "_init_translation_api_task", None)
        if init_task and not init_task.done():
            init_task.cancel()
            try:
                await asyncio.wait_for(init_task, timeout=5)
            except asyncio.CancelledError:
                pass
            except Exception as error:
                logger.warning(f"等待翻译初始化任务结束失败: {error}")

        fanyi = getattr(self.owner, "fanyi", None)
        if fanyi and hasattr(fanyi, "close_current_api"):
            await asyncio.wait_for(fanyi.close_current_api(), timeout=8)

    async def _restore_owner_after_failed_update(self):
        # install_update may fail after translation APIs were closed.
        # Bring the previously selected service back so the app remains usable.
        owner = self.owner
        try:
            if hasattr(owner, "reload_translation_api"):
                owner.reload_translation_api()
                task = getattr(owner, "_init_translation_api_task", None)
                if task is not None:
                    await asyncio.wait_for(task, timeout=15)
                return
            if hasattr(owner, "_init_translation_api"):
                task = asyncio.get_event_loop().create_task(owner._init_translation_api())
                await asyncio.wait_for(task, timeout=15)
        except Exception as error:
            logger.warning(f"安装失败后恢复翻译服务失败: {error}")

    def _ensure_progress_dialog(self):
        if self.progress_dialog is None:
            self.progress_dialog = UpdateProgressDialog(self.owner)
        apply_dialog_theme(self.progress_dialog, self.owner)
        self.progress_dialog.show()
        self.progress_dialog.raise_()

    def _show_latest_hint(self, message: str):
        feedback_owner = getattr(self, "_feedback_owner", None) or self.owner
        if hasattr(feedback_owner, "check_update_button"):
            try:
                button = feedback_owner.check_update_button
                pos = button.mapToGlobal(button.rect().center())
                QToolTip.showText(pos, message, button, button.rect(), 3000)
            except Exception:
                pass

        if hasattr(feedback_owner, "update_status_label"):
            try:
                feedback_owner.update_status_label.setText(message)
                feedback_owner.update_status_label.show()
            except Exception:
                pass

    def _get_first_run_config_path(self) -> str:
        return os.path.join(os.path.expanduser("~"), ".dzfyq", "first_run.ini")

    def _get_legacy_first_run_config_path(self) -> str:
        if getattr(sys, "frozen", False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_path, "src", "config", "first_run.ini")


def ensure_update_coordinator(owner):
    coordinator = getattr(owner, "update_coordinator", None)
    if coordinator is None:
        coordinator = UpdateCoordinator(owner)
        owner.update_coordinator = coordinator
    return coordinator


def delayed_show_changelog(owner):
    ensure_update_coordinator(owner).show_changelog_if_needed()


def on_update_available(owner, version, notes, force_update):
    ensure_update_coordinator(owner).on_update_available(version, notes, force_update)


def on_update_error(owner, error):
    ensure_update_coordinator(owner).on_update_error(error)


def on_update_complete(owner, file_path):
    ensure_update_coordinator(owner).on_update_complete(file_path)


def check_update(owner):
    ensure_update_coordinator(owner).check_update(show_no_update_message=False)


def on_update_progress(owner, progress):
    ensure_update_coordinator(owner).on_update_progress(progress)


def check_update_with_message(owner, feedback_owner=None):
    ensure_update_coordinator(owner).check_update_with_message(feedback_owner=feedback_owner)
