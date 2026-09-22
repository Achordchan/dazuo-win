import logging
logger = logging.getLogger(__name__)

import html

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTextEdit, QPushButton, QComboBox, QLabel, QAction, QLineEdit,
                             QFrame, QMenu, QDialog, QApplication, QSystemTrayIcon,
                             QSizePolicy,
                             QGraphicsDropShadowEffect,
                             QMessageBox, QProgressDialog, QShortcut, QListView,
                             QStyledItemDelegate, QAbstractItemView, QStyle)
from PyQt5.QtCore import (Qt, QSize, QPropertyAnimation, QEasingCurve, QPoint, 
                         QRect, QRectF, QEvent, QSettings, QTimer, QMimeData, QUrl, pyqtSignal, QStringListModel)
from PyQt5.QtGui import (QIcon, QPainter, QPainterPath, QColor, QFont, QPen, QPalette,
                        QDesktopServices, QKeySequence, QCursor, QTextCursor)
import pyperclip
import json
import os
import asyncio
import sys
import configparser
import time
import ctypes
import subprocess
from typing import TYPE_CHECKING, Optional, Any

# 全局变量用于存储win32模块
win32gui: Optional[Any] = None
win32con: Optional[Any] = None
win32api: Optional[Any] = None

if sys.platform == 'win32':
    try:
        import win32gui
        import win32con
        import win32api
        import win32security
        import ntsecuritycon as con
        import win32process
    except ImportError:
        logger.warning("win32gui 模块未安装，窗口置顶功能将使用备选方案")

from .yangshi import MAIN_STYLE
from .tishi import TiShiKuang
from .themes import ThemeManager
from .shezhi_chuangkou import SheZhiChuangKou
from ..shezhi import Config
from src.gongju.fanyi import DaZaoFanYi
from .zhuangtai import ZhuangTaiZhiShiQi
from ..viewmodels.translator_viewmodel import TranslatorViewModel, TranslationContext
from ..gongju.kuaijiejian import ClipboardDoubleCopyMonitor, KuaiJieJianJianTing
from ..gongju.autostart import apply_macos_dock_visibility
from .gengxinrizhi import GengXinRiZhi
from .mini_chuangkou import MiniChuangKou
from .searchable_combo import SearchableComboBox
from .common_widgets import FuDongAnNiu, ShuRuKuang
from .dialog_utils import apply_dialog_theme
from .font_settings import apply_text_edit_font_size, clamp_text_font_size
from .icon_provider import themed_icon, resource_dir
from .output_widgets import ShuChuKuang, AITranslatingStatusBar, InfoTooltipPopup
from .title_bar import BiaoTiLan
from .tray import init_tray
from .hotkey_controller import HotkeyController
from .translation_panel_controller import TranslationPanelController
from .window_mode_controller import WindowModeController
from . import window_geometry as _window_geometry
from . import translator_controller as _translator_controller
from . import theme_controller as _theme_controller
from . import update_controller as _update_controller

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "window": {
        "width": 969,
        "height": 684,
        "x": 457,
        "y": 214
    }
}

class ZhuChuangKou(QMainWindow):
    # 添加主题变化信号
    theme_changed = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        
        # 初始化配置
        self.config = Config()
        if sys.platform == "darwin":
            apply_macos_dock_visibility(self.config.get("show_in_dock", True))
            app = QApplication.instance()
            if app:
                app.setQuitOnLastWindowClosed(self.config.get("show_in_dock", True))
        
        # 初始化Mini窗口
        self.mini_window = None
        self.is_mini_mode = False
        
        # 获取资源路径
        self.resource_dir = resource_dir()
        
        logger.info(f"Resource directory: {self.resource_dir}")
        
        # 检查所有使用的图标文件
        icons = ['copy.svg', 'switch.svg', 'source.svg', 'target.svg', 'logo.svg']
        for icon in icons:
            icon_path = os.path.join(self.resource_dir, icon)
            if os.path.exists(icon_path):
                logger.info(f"Found icon: {icon}")
            else:
                logger.warning(f"Missing icon: {icon}")
        
        # 设置应用程序图标
        icon_path = os.path.join(self.resource_dir, 'logo.svg')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            logger.info(f"Set window icon from: {icon_path}")
        else:
            logger.warning(f"Icon not found at: {icon_path}")

        init_tray(self)
        
        # 初始化翻译器
        self.fanyi = DaZaoFanYi()

        self.translator_vm = TranslatorViewModel(self.fanyi, parent=self)

        self._latest_ai_phase_text = None
        self._latest_ai_estimated_tokens = None
        
        # 设置窗口标志 - 无边框但可调整大小
        self.setWindowFlags(Qt.FramelessWindowHint)  # 无边框
        self.setAttribute(Qt.WA_TranslucentBackground)  # 透明背景
        
        # 设置最小窗口大小
        self.setMinimumSize(969, 684)
        
        # 加载窗口位置和大小
        self._load_window_geometry()
        
        # 创建界面
        self._create_ui()

        self._save_geometry_timer = QTimer(self)
        self._save_geometry_timer.setSingleShot(True)
        self._save_geometry_timer.timeout.connect(self._save_window_geometry)

        if self.centralWidget():
            self._install_resize_event_filters(self.centralWidget())
        
        # 加载主题
        self.theme_manager = ThemeManager()
        self._apply_theme(self.config.get("theme", "dark"))
        
        # 创建提示框
        self.tishi = TiShiKuang(self)

        self.translation_panel_controller = TranslationPanelController(self)
        self.translation_panel_controller.bind_view_model()
        self.window_mode_controller = WindowModeController(self)
        self.update_coordinator = _update_controller.ensure_update_coordinator(self)

        # 初始化拖动变量
        self._is_dragging = False
        self._drag_start_pos = None
        self._detected_lang_text = None

        self._last_copy_trigger_time = 0.0
        
        # 初始化快捷键监听器
        default_hotkey = "command+c,c" if sys.platform == "darwin" else "ctrl+c,c"
        hotkey = self.config.get("shortcuts.copy_translate", default_hotkey)
        self.hotkey_controller = HotkeyController(self, hotkey=hotkey)
        self.kuaijiejian = self.hotkey_controller.hotkey_listener
        self.clipboard_monitor = self.hotkey_controller.clipboard_monitor

        try:
            self.hotkey_controller.start()
        except Exception as e:
            logger.error(f"启动快捷键监听失败: {e}")
            if sys.platform == "darwin":
                self.tishi.showMessage("快捷键启动失败，请在系统设置启用辅助功能权限", type="error")
            else:
                self.tishi.showMessage("快捷键功能初始化失败", type="error")

        # 初始化翻译API
        loop = asyncio.get_event_loop()
        self._init_translation_api_task = loop.create_task(self._init_translation_api())
        
        # 显示主窗口
        self.show()
        
        # 在窗口显示后，使用QTimer延迟检查并显示更新日志
        QTimer.singleShot(1000, self._delayed_show_changelog)

        # 启动后 3 秒自动检查更新（仅一次）
        QTimer.singleShot(3000, self._check_update)
        
        # 如果配置中启用了Mini模式，则自动切换
        if self.config.get("mini_mode", False):
            self.set_mini_mode(True)

        if sys.platform == "darwin":
            app = QApplication.instance()
            if app:
                app.installEventFilter(self)
    
    def _delayed_show_changelog(self):
        """延迟显示更新日志"""
        _update_controller.delayed_show_changelog(self)

    def _is_macos_accessibility_enabled(self) -> bool:
        if sys.platform != "darwin":
            return True
        try:
            app_services = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
            )
            app_services.AXIsProcessTrusted.restype = ctypes.c_bool
            return bool(app_services.AXIsProcessTrusted())
        except Exception as e:
            logger.warning(f"检查辅助功能权限失败: {e}")
            return False

    def _prompt_macos_accessibility_if_needed(self) -> None:
        if sys.platform != "darwin":
            return
        if self.config.get("mac_accessibility_prompted", False):
            return
        if self._is_macos_accessibility_enabled():
            self.config.set("mac_accessibility_prompted", True)
            return

        message = QMessageBox(self)
        message.setWindowTitle("需要辅助功能权限")
        message.setText("为了启用全局快捷键，需要在系统设置里允许辅助功能权限。")
        message.setInformativeText("路径：系统设置 → 隐私与安全性 → 辅助功能。")
        open_button = message.addButton("打开系统设置", QMessageBox.AcceptRole)
        message.addButton("稍后再说", QMessageBox.RejectRole)
        apply_dialog_theme(message, self)
        message.exec_()

        self.config.set("mac_accessibility_prompted", True)
        if message.clickedButton() == open_button:
            try:
                subprocess.Popen([
                    "open",
                    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
                ])
            except Exception as e:
                logger.warning(f"打开系统设置失败: {e}")

    def _quit_app(self):
        """退出应用程序"""
        self.quit_application()

    def prepare_for_shutdown(self):
        """Stop UI-side resources before the event loop exits."""
        if getattr(self, "_shutdown_prepared", False):
            return

        self._shutdown_prepared = True
        self._is_quitting = True

        if hasattr(self, "hotkey_controller") and self.hotkey_controller:
            try:
                self.hotkey_controller.stop()
            except Exception as error:
                logger.warning(f"停止快捷键监听失败: {error}")

        if getattr(self, "mini_window", None):
            try:
                self.mini_window.close()
            except Exception:
                try:
                    self.mini_window.hide()
                except Exception:
                    pass

        if hasattr(self, "_save_window_geometry"):
            try:
                self._save_window_geometry()
            except Exception as error:
                logger.warning(f"保存窗口位置失败: {error}")

        if hasattr(self, "translator_vm"):
            try:
                self.translator_vm.cancel(clear_output=False)
            except Exception as error:
                logger.warning(f"取消翻译任务失败: {error}")

        if hasattr(self, "_init_translation_api_task") and self._init_translation_api_task:
            try:
                self._init_translation_api_task.cancel()
            except Exception:
                pass

        if hasattr(self, "tray_icon"):
            try:
                self.tray_icon.hide()
            except Exception:
                pass

    async def close_async_resources(self):
        """Close async translation resources, including local engine children."""
        init_task = getattr(self, "_init_translation_api_task", None)
        if init_task and not init_task.done():
            init_task.cancel()
            try:
                await init_task
            except asyncio.CancelledError:
                pass
            except Exception as error:
                logger.debug("等待翻译初始化任务结束失败: %s", error)

        if hasattr(self, "translator_vm"):
            try:
                await self.translator_vm.cancel_and_wait(clear_output=False)
            except Exception as error:
                logger.debug("等待翻译任务结束失败: %s", error)

        if hasattr(self, "fanyi") and hasattr(self.fanyi, "close_current_api"):
            try:
                await self.fanyi.close_current_api()
            except Exception as error:
                logger.warning(f"关闭翻译接口失败: {error}")

    def quit_application(self):
        if getattr(self, "_is_quitting", False):
            QApplication.quit()
            return

        self.prepare_for_shutdown()
        QApplication.quit()

    def show_main_window(self):
        self.window_mode_controller.show_main_window()

    def set_mini_mode(self, enabled: bool, show_hint: bool = True):
        self.window_mode_controller.set_mini_mode(enabled, show_hint=show_hint)

    def toggle_mini_window(self):
        self.window_mode_controller.toggle_mini_window()

    def reload_translation_api(self):
        loop = asyncio.get_event_loop()
        existing_task = getattr(self, "_init_translation_api_task", None)

        async def reload_once():
            if existing_task and not existing_task.done():
                existing_task.cancel()
                try:
                    await existing_task
                except asyncio.CancelledError:
                    pass
                except Exception as error:
                    logger.debug("等待旧翻译初始化任务结束失败: %s", error)
            await self._init_translation_api()

        self._init_translation_api_task = loop.create_task(reload_once())
    
    def _create_ui(self):
        """创建界面"""
        main_widget = QWidget()
        main_widget.setObjectName("centralWidget")
        self.setCentralWidget(main_widget)

        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.biaotilan = BiaoTiLan(self)
        main_layout.addWidget(self.biaotilan)

        content_widget = QWidget()
        content_widget.setObjectName('mainContent')
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(14, 10, 14, 14)
        content_layout.setSpacing(12)

        toolbar = QFrame()
        toolbar.setObjectName('translationToolbar')
        toolbar.setFixedHeight(58)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(8)

        source_container = QFrame()
        source_container.setObjectName('langPill')
        source_container.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        source_layout = QHBoxLayout(source_container)
        source_layout.setContentsMargins(10, 4, 8, 4)
        source_layout.setSpacing(6)
        source_label = QLabel('源语言')
        source_label.setObjectName('langPillLabel')
        source_layout.addWidget(source_label)
        self.source_lang_combo = SearchableComboBox()
        self.source_lang_combo.setObjectName('langComboPill')
        self.source_lang_combo.set_items([
            "自动检测",
            "简体中文", "繁体中文", "英语", "日语", "韩语", "法语",
            "德语", "西班牙语", "俄语", "意大利语", "葡萄牙语",
            "越南语", "泰语", "阿拉伯语",
        ])
        self.source_lang_combo.setCurrentIndex(0)
        self.source_lang_combo.currentIndexChanged.connect(self._on_source_lang_changed)
        source_layout.addWidget(self.source_lang_combo)
        self.source_chevron = QLabel()
        self.source_chevron.setObjectName('langPillChevron')
        self.source_chevron.setFixedSize(12, 12)
        source_layout.addWidget(self.source_chevron)
        toolbar_layout.addWidget(source_container)

        self.switch_button = QPushButton()
        self.switch_button.setObjectName('langSwitchButton')
        self.switch_button.setIcon(themed_icon("switch", self.config.get("theme", "dark"), "primary"))
        self.switch_button.setToolTip('互换语言')
        self.switch_button.setFixedSize(34, 34)
        self.switch_button.setIconSize(QSize(17, 17))
        self.switch_button.clicked.connect(self._switch_languages)
        self.switch_button.setEnabled(False)
        self.switch_button.setCursor(Qt.PointingHandCursor)
        toolbar_layout.addWidget(self.switch_button)

        target_container = QFrame()
        target_container.setObjectName('langPill')
        target_container.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        target_layout = QHBoxLayout(target_container)
        target_layout.setContentsMargins(10, 4, 8, 4)
        target_layout.setSpacing(6)
        target_label = QLabel('目标语言')
        target_label.setObjectName('langPillLabel')
        target_layout.addWidget(target_label)
        self.target_lang_combo = SearchableComboBox()
        self.target_lang_combo.setObjectName('langComboPill')
        self.target_lang_combo.set_items([
            "简体中文", "繁体中文", "英语", "日语", "韩语", "法语",
            "德语", "西班牙语", "俄语", "意大利语", "葡萄牙语",
            "越南语", "泰语", "阿拉伯语",
        ])
        self.target_lang_combo.currentIndexChanged.connect(self._on_target_lang_changed)
        target_layout.addWidget(self.target_lang_combo)
        self.target_chevron = QLabel()
        self.target_chevron.setObjectName('langPillChevron')
        self.target_chevron.setFixedSize(12, 12)
        target_layout.addWidget(self.target_chevron)
        toolbar_layout.addWidget(target_container)

        service_container = QFrame()
        service_container.setObjectName('serviceStatusPill')
        service_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        service_container.setMinimumWidth(0)
        service_layout = QHBoxLayout(service_container)
        service_layout.setContentsMargins(10, 4, 10, 4)
        service_layout.setSpacing(6)
        service_label = QLabel('翻译服务')
        service_label.setObjectName('serviceStatusLabel')
        service_layout.addWidget(service_label)
        self.service_icon_label = QLabel()
        self.service_icon_label.setObjectName('serviceIconLabel')
        self.service_icon_label.setFixedSize(16, 16)
        service_layout.addWidget(self.service_icon_label)
        self.service_display = QLabel("")
        self.service_display.setObjectName('serviceNameLabel')
        service_layout.addWidget(self.service_display)
        self.status_indicator = ZhuangTaiZhiShiQi(compact=True)
        self.status_indicator.retry_button.clicked.connect(self._retry_connection)
        service_layout.addWidget(self.status_indicator, 1)
        toolbar_layout.addWidget(service_container, 1)

        def create_toolbar_button(icon_name, tooltip, callback):
            button = QPushButton()
            button.setObjectName('toolbarIconButton')
            button.setFixedSize(34, 34)
            button.setIcon(themed_icon(icon_name, self.config.get('theme', 'dark'), 'secondary'))
            button.setIconSize(QSize(16, 16))
            button.setToolTip(tooltip)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(callback)
            return button

        self.toolbar_theme_button = create_toolbar_button('theme', '切换主题', self._on_theme_change)
        self.toolbar_mini_button = create_toolbar_button(
            'mini_mode',
            '切换到迷你窗口模式',
            lambda: self._toggle_mini_mode(True, show_hint=True),
        )
        self.toolbar_settings_button = create_toolbar_button('settings', '设置', self._on_settings)
        self.toolbar_actions = QWidget()
        self.toolbar_actions.setObjectName('toolbarActions')
        toolbar_actions_layout = QHBoxLayout(self.toolbar_actions)
        toolbar_actions_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_actions_layout.setSpacing(8)
        toolbar_actions_layout.addWidget(self.toolbar_theme_button)
        toolbar_actions_layout.addWidget(self.toolbar_mini_button)
        toolbar_actions_layout.addWidget(self.toolbar_settings_button)
        # 右侧三个按钮固定宽度，任何状态文本都不能挤压它们。
        actions_width = 3 * 34 + 2 * toolbar_actions_layout.spacing()
        self.toolbar_actions.setFixedWidth(max(actions_width, self.toolbar_actions.sizeHint().width()))
        self.toolbar_actions.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        toolbar_layout.addWidget(self.toolbar_actions, 0)
        content_layout.addWidget(toolbar)

        workspace = QWidget()
        workspace.setObjectName('translationWorkspace')
        self.translation_workspace_layout = QHBoxLayout(workspace)
        self.translation_workspace_layout.setContentsMargins(0, 0, 0, 0)
        self.translation_workspace_layout.setSpacing(12)

        self.source_panel = QFrame()
        self.source_panel.setObjectName('translationPanel')
        source_panel_layout = QVBoxLayout(self.source_panel)
        source_panel_layout.setContentsMargins(0, 0, 0, 0)
        source_panel_layout.setSpacing(0)

        source_header = QFrame()
        source_header.setObjectName('translationPanelHeader')
        source_header.setFixedHeight(42)
        source_header_layout = QHBoxLayout(source_header)
        source_header_layout.setContentsMargins(14, 0, 10, 0)
        source_header_layout.setSpacing(8)
        self.source_panel_icon = QLabel()
        self.source_panel_icon.setObjectName('translationPanelIcon')
        self.source_panel_icon.setFixedSize(16, 16)
        source_header_layout.addWidget(self.source_panel_icon)
        source_title = QLabel('原文')
        source_title.setObjectName('translationPanelTitle')
        source_header_layout.addWidget(source_title)
        source_header_layout.addStretch()
        self.clear_source_button = QPushButton()
        self.clear_source_button.setObjectName('panelActionButton')
        self.clear_source_button.setFixedSize(30, 30)
        self.clear_source_button.setIconSize(QSize(15, 15))
        self.clear_source_button.setToolTip('清空原文')
        self.clear_source_button.setCursor(Qt.PointingHandCursor)
        self.clear_source_button.setEnabled(False)
        source_header_layout.addWidget(self.clear_source_button)
        source_panel_layout.addWidget(source_header)

        self.input_text = ShuRuKuang("在此输入要翻译的文本...")
        self.input_text.setObjectName('sourceTextEdit')
        self.input_text.setMinimumHeight(0)
        self.input_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.input_text.textChanged.connect(self._vm_on_input_text_changed)
        self.input_text.textChanged.connect(
            lambda: self.clear_source_button.setEnabled(bool(self.input_text.toPlainText().strip()))
        )
        self.clear_source_button.clicked.connect(self.input_text.clear)
        source_panel_layout.addWidget(self.input_text, 1)

        self.target_panel = QFrame()
        self.target_panel.setObjectName('translationPanel')
        target_panel_layout = QVBoxLayout(self.target_panel)
        target_panel_layout.setContentsMargins(0, 0, 0, 0)
        target_panel_layout.setSpacing(0)

        target_header = QFrame()
        target_header.setObjectName('translationPanelHeader')
        target_header.setFixedHeight(42)
        target_header_layout = QHBoxLayout(target_header)
        target_header_layout.setContentsMargins(14, 0, 10, 0)
        target_header_layout.setSpacing(8)
        self.target_panel_icon = QLabel()
        self.target_panel_icon.setObjectName('translationPanelIcon')
        self.target_panel_icon.setFixedSize(16, 16)
        target_header_layout.addWidget(self.target_panel_icon)
        target_title = QLabel('译文')
        target_title.setObjectName('translationPanelTitle')
        target_header_layout.addWidget(target_title)
        target_header_layout.addStretch()
        self.copy_translation_button = QPushButton()
        self.copy_translation_button.setObjectName('panelActionButton')
        self.copy_translation_button.setFixedSize(30, 30)
        self.copy_translation_button.setIconSize(QSize(15, 15))
        self.copy_translation_button.setToolTip('复制译文')
        self.copy_translation_button.setCursor(Qt.PointingHandCursor)
        self.copy_translation_button.setEnabled(False)
        target_header_layout.addWidget(self.copy_translation_button)
        target_panel_layout.addWidget(target_header)

        self.output_text = ShuChuKuang()
        self.output_text.setObjectName('targetTextEdit')
        self.output_text.setMinimumHeight(0)
        self.output_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.output_text.set_header_copy_button_mode(True)
        self.output_text.textChanged.connect(
            lambda: self.copy_translation_button.setEnabled(
                bool(self.output_text.toPlainText().strip()) and not self.output_text._is_loading
            )
        )
        self.copy_translation_button.clicked.connect(self.output_text._on_copy)
        target_panel_layout.addWidget(self.output_text, 1)

        self.ai_status_bar = AITranslatingStatusBar()
        target_panel_layout.addWidget(self.ai_status_bar)

        self.translation_workspace_layout.addWidget(self.source_panel, 1)
        self.translation_workspace_layout.addWidget(self.target_panel, 1)
        self.translation_workspace_layout.setStretch(0, 1)
        self.translation_workspace_layout.setStretch(1, 1)
        content_layout.addWidget(workspace, 1)
        main_layout.addWidget(content_widget, 1)

        self._load_default_settings()
    
    def _load_default_settings(self):
        """加载默认设置"""
        self._update_service_display()
        self._apply_text_font_sizes()
        
        source_lang = self.config.get("translation.source_lang", "自动检测")
        source_index = self.source_lang_combo.findText(source_lang)
        self.source_lang_combo.setCurrentIndex(source_index if source_index >= 0 else 0)
        
        # 设置目标语言
        target_lang = self.config.get("translation.target_lang", "简体中文")
        if target_lang == "中文":  # 向后兼容
            target_lang = "简体中文"
        target_index = self.target_lang_combo.findText(target_lang)
        if target_index >= 0:
            self.target_lang_combo.setCurrentIndex(target_index)
        
    def _on_source_lang_changed(self, index):
        self.config.set("translation.source_lang", self.source_lang_combo.currentText().split(" (")[0])
        if self.input_text.toPlainText():
            self.translator_vm.translate_now(self.input_text.toPlainText(), self._get_vm_context())
    
    def _switch_languages(self):
        """切换源语言和目标语言"""
        # 获取当前选择的语言和文本
        source_text = self.source_lang_combo.currentText().split(" (")[0]
        target_text = self.target_lang_combo.currentText()
        input_text = self.input_text.toPlainText()
        output_text = self.output_text.toPlainText()
        
        # 如果源语言是自动检测
        if source_text == "自动检测" and hasattr(self, '_detected_lang'):
            # 将检测到的语言代码转换为显示名称
            lang_map = {v: k for k, v in self.fanyi._fanyi_jiekou.LANG_CODES.items()}
            detected_name = lang_map.get(self._detected_lang)
            
            if detected_name:
                # 将当前目标语言设为源语言
                self.source_lang_combo.setCurrentIndex(self.source_lang_combo.findText(target_text))
                
                # 将检测到的语言设为目标语言
                target_index = self.target_lang_combo.findText(detected_name)
                if target_index >= 0:
                    self.target_lang_combo.setCurrentIndex(target_index)
                
                # 交换文本
                self.input_text.setPlainText(output_text)
                self.output_text.clear()
                
                # 保存设置
                self.config.set("translation.source_lang", target_text)
                self.config.set("translation.target_lang", detected_name)
        else:
            # 正常的语言切换
            source_index = self.target_lang_combo.findText(source_text)
            target_index = self.source_lang_combo.findText(target_text)
            
            # 设置新的选择
            if source_index >= 0:
                self.target_lang_combo.setCurrentIndex(source_index)
            if target_index >= 0:
                self.source_lang_combo.setCurrentIndex(target_index)
            
            # 交换文本
            self.input_text.setPlainText(output_text)
            self.output_text.clear()
            
            # 保存设置
            self.config.set("translation.source_lang", self.source_lang_combo.currentText())
            self.config.set("translation.target_lang", self.target_lang_combo.currentText())
    
    def _debounce_translate(self):
        # Legacy entry point kept for compatibility; route through ViewModel.
        self._vm_on_input_text_changed()

    def _get_vm_context(self) -> TranslationContext:
        return self.translation_panel_controller.build_context()

    def _vm_on_input_text_changed(self):
        self.translation_panel_controller.on_input_text_changed()
    
    def _retry_connection(self):
        """重试连接"""
        _translator_controller.retry_connection(self)
    
    def _on_target_lang_changed(self, index):
        """目标语言改变时的处理"""
        # 如果有已翻译的文本，立即重新翻译
        if self.input_text.toPlainText():
            self.translator_vm.translate_now(self.input_text.toPlainText(), self._get_vm_context())
        
        # 保存设置
        self.config.set("translation.target_lang", self.target_lang_combo.currentText())
    
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.LeftButton and not self.isMaximized():
            edge = self._get_edge(event.pos())
            if edge:
                _window_geometry.begin_resize(self, edge, event.globalPos())
                self.setCursor(self._get_resize_cursor(edge))
                event.accept()
                return
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if hasattr(self, '_resize_edge') and self._resize_edge:
            self._perform_resize(event.globalPos())
            event.accept()
            return

        edge = None if self.isMaximized() else self._get_edge(event.pos())
        if edge != getattr(self, '_current_edge', None):
            self._current_edge = edge
            self.setCursor(self._get_resize_cursor(edge) if edge else Qt.ArrowCursor)
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if hasattr(self, '_resize_edge') and self._resize_edge:
            _window_geometry.end_resize(self)
            self.setCursor(Qt.ArrowCursor)
            self._schedule_save_window_geometry()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not getattr(self, '_resize_edge', None):
            _window_geometry.protect_window_size(self)

    def _perform_resize(self, global_pos: QPoint):
        _window_geometry.perform_resize(self, global_pos)

    def _install_resize_event_filters(self, root: QWidget):
        _window_geometry.install_resize_event_filters(self, root)

    def eventFilter(self, obj, event):
        if sys.platform == "darwin" and event.type() == QEvent.ApplicationActivate:
            if self.isHidden() and not self.config.get("mini_mode", False):
                self.showNormal()
                self.raise_()
                self.activateWindow()
            return super().eventFilter(obj, event)
        return _window_geometry.event_filter(self, obj, event, super().eventFilter)

    def _schedule_save_window_geometry(self):
        _window_geometry.schedule_save_window_geometry(self)

    def _save_window_geometry(self):
        _window_geometry.save_window_geometry(self)
    
    def _get_edge(self, pos):
        """获取鼠标位置对应的边缘"""
        return _window_geometry.get_edge(self, pos)

    def _get_resize_cursor(self, edge):
        """获取调整大小时鼠标样式"""
        return _window_geometry.get_resize_cursor(edge)

    def _load_window_geometry(self):
        """加载窗口位置和大小"""
        _window_geometry.load_window_geometry(self)

    def center(self):
        """将窗口居中显示"""
        _window_geometry.center_window(self)

    def _on_settings(self):
        """设置按钮点击事件处理"""
        try:
            logger.info("打开设置窗口")
            settings_dialog = SheZhiChuangKou(self)
            
            # 显示设置窗口并等待结果
            if settings_dialog.exec_() == QDialog.Accepted:
                logger.info("设置已保存，重新加载设置")
                default_hotkey = "command+c,c" if sys.platform == "darwin" else "ctrl+c,c"
                old_hotkey = getattr(getattr(self, "hotkey_controller", None), "hotkey_listener", None)
                old_hotkey_value = getattr(old_hotkey, "_hotkey", None)
                hotkey = self.config.get("shortcuts.copy_translate", default_hotkey)
                if hasattr(self, "hotkey_controller"):
                    try:
                        self.hotkey_controller.reload_hotkey(hotkey)
                    except Exception as error:
                        if old_hotkey_value:
                            self.config.set("shortcuts.copy_translate", old_hotkey_value)
                        self.tishi.showMessage(f"快捷键设置失败，已保留旧快捷键: {error}", type="error")

                theme_name = self.config.get("theme", "dark")
                self._apply_theme(theme_name)
                self._update_service_display()
                
                # 重新加载翻译设置
                source_lang = self.config.get("translation.source_lang", "自动检测")
                target_lang = self.config.get("translation.target_lang", "中文")
                
                # 更新语言选择框
                source_index = self.source_lang_combo.findText(source_lang)
                if source_index >= 0:
                    self.source_lang_combo.setCurrentIndex(source_index)
                    
                target_index = self.target_lang_combo.findText(target_lang)
                if target_index >= 0:
                    self.target_lang_combo.setCurrentIndex(target_index)
                
                # 重新初始化翻译API
                self.reload_translation_api()
                
                # 如果Mini窗口存在，更新其大小和透明度
                if self.mini_window:
                    opacity = self.config.get("mini_window_opacity", 0.95)
                    if hasattr(self.mini_window, "update_opacity"):
                        self.mini_window.update_opacity(opacity)
                    else:
                        try:
                            self.mini_window.setWindowOpacity(opacity)
                        except Exception:
                            pass
                    logger.info(f"已更新Mini窗口透明度: {opacity}")
                
                logger.info("设置更新完成")
            else:
                logger.info("设置已取消")
                
        except Exception as e:
            logger.error(f"打开设置窗口失败: {e}")
            self.tishi.showMessage("打开设置失败", type="error")

    def _on_history(self):
        """历史记录按钮点击事件处理"""
        try:
            logger.info("点击历史记录按钮")
            self.tishi.showMessage("历史记录功能开发中...", type="info")
            
            # TODO: 实现历史记录功能
            # 1. 保存翻译历史
            # 2. 显示历史记录窗口
            # 3. 支持历史记录搜索
            # 4. 支持复制和重新翻译
            
        except Exception as e:
            logger.error(f"处理历史记录点击事件失败: {e}")
            self.tishi.showMessage("历史记录功能暂不可用", type="error")

    def _on_theme_change(self):
        """主题切换按钮点击事件处理"""
        _theme_controller.on_theme_change(self)

    def _apply_theme(self, theme_name):
        """应用主题"""
        _theme_controller.apply_theme(self, theme_name)
        self._apply_text_font_sizes()

    def _apply_text_font_sizes(self):
        source_size = clamp_text_font_size(self.config.get("display.source_font_size", 16))
        target_size = clamp_text_font_size(self.config.get("display.target_font_size", 16))
        if hasattr(self, "input_text"):
            apply_text_edit_font_size(self.input_text, source_size)
        if hasattr(self, "output_text"):
            apply_text_edit_font_size(self.output_text, target_size)

    def apply_display_settings(self):
        self._apply_text_font_sizes()

    def _update_button_icons(self, theme_name):
        """更新按钮图标以适应主题"""
        _theme_controller.update_button_icons(self, theme_name)

    def _update_service_display(self):
        _translator_controller.update_service_display(self)

    async def _init_translation_api(self):
        """初始化翻译API"""
        return await _translator_controller.init_translation_api(self)

    async def _on_text_changed(self):
        # Legacy async path removed; ViewModel owns translation requests.
        self.translation_panel_controller.on_input_text_changed()

    def _reset_source_lang_text(self):
        """重置源语言文本显示"""
        try:
            # 只重置显示文本，不清除检测结果
            if self.source_lang_combo.currentText() != "自动检测":
                self.source_lang_combo.setItemText(0, "自动检测")
                logger.info("重置源语言显示为自动检测")
        except Exception as e:
            logger.error(f"重置源语言显示失败: {e}")

    def _show_main_window(self):
        """显示并激活主窗口（避免macOS下无响应）"""
        self.show_main_window()

    def _on_tray_icon_activated(self, reason):
        """处理托盘图标的激活事件"""
        if reason == QSystemTrayIcon.DoubleClick:
            # 双击托盘图标时显示主窗口
            self._show_main_window()
    
    def _on_update_available(self, version, notes, force_update):
        _update_controller.on_update_available(self, version, notes, force_update)

    def _on_update_error(self, error):
        _update_controller.on_update_error(self, error)

    def _on_update_complete(self, file_path):
        _update_controller.on_update_complete(self, file_path)

    def _check_update(self):
        """检查更新"""
        return _update_controller.check_update(self)

    def _on_update_progress(self, progress):
        _update_controller.on_update_progress(self, progress)

    def _check_update_with_message(self, feedback_owner=None):
        _update_controller.check_update_with_message(self, feedback_owner=feedback_owner)

    def _fallback_window_top(self):
        """使用Qt的方式实现窗口置顶"""
        try:
            # 使用 Qt 的替代方法
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.show()
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.show()
        except Exception as e:
            logger.error(f"窗口置顶失败: {e}")

    def _handle_copy_translate(self, text: str = ""):
        """处理复制后翻译的快捷键"""
        self.window_mode_controller.handle_copy_translate(text)

    def _handle_double_copy_text(self, text: str):
        self.window_mode_controller.handle_double_copy_text(text)

    def _start_translation(self):
        """开始翻译"""
        self.translation_panel_controller.start_translation()

    def _vm_on_output_text_changed(self, text: str):
        self.translation_panel_controller.on_output_text_changed(text)

    def _vm_on_is_translating_changed(self, translating: bool):
        self.translation_panel_controller.on_is_translating_changed(translating)

    def _vm_on_error_message_changed(self, message):
        self.translation_panel_controller.on_error_message_changed(message)

    def _vm_on_detected_source_language_changed(self, detected_lang):
        self.translation_panel_controller.on_detected_source_language_changed(detected_lang)

    def _vm_on_ai_phase_changed(self, phase):
        self.translation_panel_controller.on_ai_phase_changed(phase)

    def _vm_on_estimated_ai_tokens_changed(self, estimated):
        self.translation_panel_controller.on_estimated_ai_tokens_changed(estimated)

    def _vm_on_toast_message(self, message: str, toast_type: str):
        self.translation_panel_controller.on_toast_message(message, toast_type)

    def closeEvent(self, event):
        """窗口关闭事件"""
        if getattr(self, "_is_quitting", False):
            event.accept()
            super().closeEvent(event)
            return

        tray_visible = (
            getattr(self, "tray_available", False)
            and hasattr(self, "tray_icon")
            and self.tray_icon.isVisible()
        )
        if tray_visible:
            if sys.platform == "darwin" and self.config.get("show_in_dock", True):
                self.prepare_for_shutdown()
                event.accept()
                super().closeEvent(event)
                QApplication.quit()
                return
            if self.mini_window:
                self.mini_window.hide()
            self.hide()
            event.ignore()
            return

        self.prepare_for_shutdown()

        event.accept()
        super().closeEvent(event)
        if not tray_visible:
            QApplication.quit()
    
    def showEvent(self, event):
        """窗口显示事件"""
        super().showEvent(event)
        # 当主窗口显示时，关闭Mini模式
        if self.is_mini_mode:
            self.set_mini_mode(False)
    
    def _toggle_mini_mode(self, checked, show_hint=True):
        self.set_mini_mode(checked, show_hint=show_hint)
    
    def _show_mini_mode_hint(self):
        self.window_mode_controller.show_mini_mode_hint()
    
    def _toggle_mini_mode_shortcut(self):
        """通过快捷键切换Mini模式"""
        enabled = not self.is_mini_mode
        if hasattr(self, "mini_mode_action"):
            self.mini_mode_action.setChecked(enabled)
        self.set_mini_mode(enabled)
    
    def _toggle_mini_window(self):
        """切换Mini窗口的显示/隐藏状态"""
        self.toggle_mini_window()

    def _on_theme_changed(self, theme_name):
        """处理主题变化"""
        # ... existing code ...
        
        # 保存主题设置
        self.config.set("theme", theme_name)
        self.config.save()
        
        # 应用主题
        self._apply_theme()
        
        # 发送主题变化信号
        self.theme_changed.emit()

    def _on_mini_mode(self):
        """切换到Mini模式"""
        try:
            # 只初始化Mini窗口但不显示
            if not hasattr(self, "mini_window"):
                self.mini_window = MiniChuangKou(self)
            
            # 隐藏主窗口
            self.hide()
            
            # 设置为Mini模式
            self._toggle_mini_mode(True)
            
            logger.info("切换到Mini模式")
        except Exception as e:
            logger.error(f"切换到Mini模式失败: {e}")

    def _set_taskbar_icon(self):
        """设置任务栏图标"""
        try:
            if sys.platform == 'win32' and win32gui and win32con:
                # 只在Windows平台上执行
                taskbar_icon = QIcon(os.path.join(self.resource_dir, 'logo.svg'))
                window_id = int(self.winId())
                
                # 正确方式：使用win32gui模块的CreateIconFromResource处理图标
                hicon = taskbar_icon.pixmap(32, 32).toImage()
                
                # 尝试替代方法设置图标
                app_instance = QApplication.instance()
                if app_instance:
                    app_instance.setWindowIcon(taskbar_icon)
                    
                logger.info("成功设置任务栏图标")
        except Exception as e:
            logger.error(f"设置任务栏图标失败: {e}")
            # 使用更简单的方法设置图标
            try:
                self.setWindowIcon(QIcon(os.path.join(self.resource_dir, 'logo.svg')))
            except:
                pass

    async def _translate_and_show_mini(self, text_to_translate, service=None):
        await self.window_mode_controller.translate_and_show_mini(text_to_translate, service=service)

    def _load_config(self):
        """加载配置"""
        # 加载配置文件中的mini_mode设置
        mini_mode = self.config.get("mini_mode", False)
        
        # 应用迷你模式设置，但不显示提示
        if mini_mode:
            self._toggle_mini_mode(True, show_hint=False)
        
        # 其他配置加载代码...
