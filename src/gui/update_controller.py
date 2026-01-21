import logging
logger = logging.getLogger(__name__)

import configparser
import os
import sys
import asyncio

from PyQt5.QtWidgets import (QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QProgressBar, QTextBrowser, QToolTip)
from PyQt5.QtCore import Qt

from .gengxinrizhi import GengXinRiZhi
from ..version import APP_VERSION
from ..gongju.update import Updater


class UpdatePromptDialog(QDialog):
    def __init__(self, parent, version: str, notes: str, force_update: bool):
        super().__init__(parent)
        self.setWindowTitle("发现新版本")
        self.setFixedSize(520, 360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._accepted = False

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
            ok_btn.setText("立即更新")

        action_row.addWidget(cancel_btn)
        action_row.addWidget(ok_btn)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(notes_label)
        layout.addWidget(notes_box)
        layout.addLayout(action_row)

        self.setStyleSheet(
            "QDialog { background: #f6f8fb; }"
            "#updateTitle { font-size: 18px; font-weight: 600; color: #1f2a37; }"
            "#updateSubtitle { font-size: 12px; color: #6b7280; }"
            "#updateSection { font-size: 12px; color: #374151; margin-top: 6px; }"
            "#updateNotes { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px;"
            " padding: 10px; font-size: 12px; color: #374151; }"
            "#updateCancel { background: #e5e7eb; color: #374151; border-radius: 8px; padding: 6px 16px; }"
            "#updateCancel:hover { background: #d1d5db; }"
            "#updateOk { background: #1f7ae0; color: #ffffff; border-radius: 8px; padding: 6px 18px; }"
            "#updateOk:hover { background: #1768bd; }"
        )


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
        subtitle = QLabel("请保持网络连接，下载完成后会自动安装")
        subtitle.setObjectName("progressSubtitle")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setObjectName("progressBar")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.progress_bar)

        self.setStyleSheet(
            "QDialog { background: #f6f8fb; }"
            "#progressTitle { font-size: 16px; font-weight: 600; color: #1f2a37; }"
            "#progressSubtitle { font-size: 12px; color: #6b7280; }"
            "#progressBar { height: 14px; border-radius: 7px; background: #e5e7eb; }"
            "#progressBar::chunk { border-radius: 7px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            " stop:0 #18a058, stop:1 #1f7ae0); }"
        )

    def set_progress(self, value: int):
        self.progress_bar.setValue(value)


def delayed_show_changelog(self):
    """延迟显示更新日志"""
    try:
        config = configparser.ConfigParser()

        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        config_path = os.path.join(base_path, 'src', 'config', 'first_run.ini')
        logger.info(f"配置文件路径: {config_path}")

        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        if os.path.exists(config_path):
            config.read(config_path, encoding='utf-8')
            logger.info("成功读取配置文件")

        if not config.has_section('App'):
            config.add_section('App')
            logger.info("创建新的App配置段")

        config_changed = False
        last_version = config.get('App', 'last_version', fallback="")
        if last_version != APP_VERSION:
            config.set('App', 'first_run', '0')
            config.set('App', 'last_version', APP_VERSION)
            config_changed = True

        first_run = config.getint('App', 'first_run', fallback=0)
        logger.info(f"当前first_run值: {first_run}")

        if first_run == 0:
            dialog = GengXinRiZhi(self)
            dialog.setModal(True)
            dialog.exec_()

            config.set('App', 'first_run', '1')
            config_changed = True
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    config.write(f)
                logger.info("成功更新配置文件")
            except Exception as e:
                logger.error(f"写入配置文件失败: {e}")
                if sys.platform == 'win32':
                    try:
                        import win32security
                        import ntsecuritycon as con
                        import win32api
                        import win32con

                        user_sid = win32security.GetTokenInformation(
                            win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY),
                            win32security.TokenUser
                        )[0]

                        sd = win32security.SECURITY_DESCRIPTOR()
                        sd.Initialize()
                        sd.SetSecurityDescriptorOwner(user_sid, False)

                        dacl = win32security.ACL()
                        dacl.Initialize()
                        dacl.AddAccessAllowedAce(
                            win32security.ACL_REVISION,
                            con.FILE_ALL_ACCESS,
                            user_sid
                        )
                        sd.SetSecurityDescriptorDacl(1, dacl, 0)

                        win32security.SetFileSecurity(
                            config_path,
                            win32security.DACL_SECURITY_INFORMATION,
                            sd
                        )

                        with open(config_path, 'w', encoding='utf-8') as f:
                            config.write(f)
                        logger.info("使用管理员权限成功更新配置文件")
                    except Exception as e2:
                        logger.error(f"使用管理员权限写入配置文件失败: {e2}")

        if config_changed and first_run != 0:
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    config.write(f)
                logger.info("成功更新配置文件")
            except Exception as e:
                logger.error(f"写入配置文件失败: {e}")

    except Exception as e:
        logger.error(f"显示更新日志失败: {e}")


def on_update_available(self, version, notes, force_update):
    """有新版本可用时的处理"""
    dialog = UpdatePromptDialog(self, version, notes, force_update)
    result = dialog.exec_()

    if result == QDialog.Accepted:
        _ensure_progress_dialog(self)
        _start_download(self)
        return

    if force_update:
        QMessageBox.critical(
            self,
            "必须更新",
            "此版本为重要更新，未更新将退出程序。",
            QMessageBox.Ok
        )
        sys.exit(0)


def on_update_error(self, error):
    """更新错误处理"""
    self._update_error_occurred = True
    QMessageBox.warning(self, "更新失败", error)
    if hasattr(self, 'progress_dialog'):
        self.progress_dialog.close()

    if getattr(self, 'updater', None) is not None and getattr(self.updater, 'force_update', False):
        QMessageBox.critical(
            self,
            "更新失败",
            "强制更新失败，程序将退出。\n请检查网络连接后重试。",
            QMessageBox.Ok
        )
        sys.exit(1)


def on_update_complete(self, file_path):
    """更新下载完成的处理"""
    if hasattr(self, 'progress_dialog'):
        self.progress_dialog.close()

    if getattr(self, 'updater', None) is not None and getattr(self.updater, 'force_update', False):
        if sys.platform == "darwin":
            QMessageBox.information(
                self,
                "下载完成",
                "更新已下载完成，将打开 DMG。\n\n请手动将应用替换为新版本后重新启动。",
                QMessageBox.Ok
            )
            self.updater.install_update(file_path)
            return
        QMessageBox.information(
            self,
            "下载完成",
            "更新已下载完成，程序将自动安装更新并重启。",
            QMessageBox.Ok
        )
        self.updater.install_update(file_path)
        return

    if sys.platform == "darwin":
        reply = QMessageBox.information(
            self,
            "下载完成",
            "更新已下载完成，将打开 DMG。\n\n请手动将应用替换为新版本后重新启动。",
            QMessageBox.Ok | QMessageBox.Cancel
        )
        if reply == QMessageBox.Ok:
            self.updater.install_update(file_path)
        return

    reply = QMessageBox.information(
        self,
        "下载完成",
        "更新已下载完成，点击确定开始安装。\n安装程序启动后，当前程序将自动关闭。",
        QMessageBox.Ok | QMessageBox.Cancel
    )

    if reply == QMessageBox.Ok:
        self.updater.install_update(file_path)


def check_update(self):
    """检查更新"""
    _start_check(self, show_no_update_message=False)


def on_update_progress(self, progress):
    """更新进度处理"""
    if hasattr(self, 'progress_dialog'):
        self.progress_dialog.set_progress(progress)


def check_update_with_message(self):
    """手动检查更新（带提示消息）"""
    _start_check(self, show_no_update_message=True)


def _ensure_updater(self):
    if getattr(self, 'updater', None) is None:
        self.updater = Updater()
        self.updater.update_available.connect(lambda v, n, f: on_update_available(self, v, n, f))
        self.updater.update_progress.connect(lambda p: on_update_progress(self, p))
        self.updater.update_error.connect(lambda e: on_update_error(self, e))
        self.updater.update_complete.connect(lambda path: on_update_complete(self, path))


def _ensure_progress_dialog(self):
    if getattr(self, 'progress_dialog', None) is None:
        self.progress_dialog = UpdateProgressDialog(self)
    self.progress_dialog.show()
    self.progress_dialog.raise_()


def _show_latest_hint(self, message: str):
    if hasattr(self, "check_update_button"):
        try:
            pos = self.check_update_button.mapToGlobal(self.check_update_button.rect().center())
            QToolTip.showText(pos, message, self.check_update_button, self.check_update_button.rect(), 3000)
        except Exception:
            pass

    if hasattr(self, "update_status_label"):
        try:
            self.update_status_label.setText(f"✔ {message}")
            self.update_status_label.show()
        except Exception:
            pass


def _start_check(self, show_no_update_message: bool):
    if getattr(self, '_update_checking', False):
        return
    self._update_checking = True
    _ensure_updater(self)

    async def _run():
        try:
            has_update = await self.updater.check_update()
            if show_no_update_message and not has_update and not getattr(self, '_update_error_occurred', False):
                _show_latest_hint(self, "当前已是最新版本")
        finally:
            self._update_checking = False

    loop = asyncio.get_event_loop()
    loop.create_task(_run())


def _start_download(self):
    async def _run():
        await self.updater.download_update()

    loop = asyncio.get_event_loop()
    loop.create_task(_run())
