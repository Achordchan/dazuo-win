import asyncio
import configparser
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

from .dialog_utils import apply_dialog_theme, show_themed_message
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

        self.updater.update_available.connect(self.on_update_available)
        self.updater.update_progress.connect(self.on_update_progress)
        self.updater.update_error.connect(self.on_update_error)
        self.updater.update_complete.connect(self.on_update_complete)

    def load_first_run_state(self):
        config = configparser.ConfigParser()
        config_path = self._get_first_run_config_path()
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        if os.path.exists(config_path):
            config.read(config_path, encoding="utf-8")
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
        try:
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

    def check_update(self, show_no_update_message: bool = False):
        if self._update_checking:
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

        asyncio.get_event_loop().create_task(run())

    def check_update_with_message(self):
        self.check_update(show_no_update_message=True)

    def on_update_available(self, version, notes, force_update):
        dialog = UpdatePromptDialog(self.owner, version, notes, force_update)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self._ensure_progress_dialog()
            asyncio.get_event_loop().create_task(self.updater.download_update())
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

    def on_update_progress(self, progress):
        if self.progress_dialog is not None:
            self.progress_dialog.set_progress(progress)

    def on_update_error(self, error):
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
            self.updater.install_update(file_path)
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
                self.updater.install_update(file_path)
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
                self.updater.install_update(file_path)
            else:
                self.updater.discard_downloaded_update(file_path)
            return

        show_themed_message(
            self.owner,
            icon=QMessageBox.Warning,
            title="暂不支持",
            text="当前平台暂不支持自动更新。",
            buttons=QMessageBox.Ok,
        )
        self.updater.discard_downloaded_update(file_path)

    def _ensure_progress_dialog(self):
        if self.progress_dialog is None:
            self.progress_dialog = UpdateProgressDialog(self.owner)
        apply_dialog_theme(self.progress_dialog, self.owner)
        self.progress_dialog.show()
        self.progress_dialog.raise_()

    def _show_latest_hint(self, message: str):
        if hasattr(self.owner, "check_update_button"):
            try:
                pos = self.owner.check_update_button.mapToGlobal(self.owner.check_update_button.rect().center())
                QToolTip.showText(pos, message, self.owner.check_update_button, self.owner.check_update_button.rect(), 3000)
            except Exception:
                pass

        if hasattr(self.owner, "update_status_label"):
            try:
                self.owner.update_status_label.setText(f"✔ {message}")
                self.owner.update_status_label.show()
            except Exception:
                pass

    def _get_first_run_config_path(self) -> str:
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


def check_update_with_message(owner):
    ensure_update_coordinator(owner).check_update_with_message()
