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
from src.gongju.fanyi_api import GoogleAPI, OpenAICompatibleAPI
from .zhuangtai import ZhuangTaiZhiShiQi
from ..viewmodels.translator_viewmodel import TranslatorViewModel, TranslationContext
from ..gongju.kuaijiejian import ClipboardDoubleCopyMonitor, KuaiJieJianJianTing
from ..gongju.autostart import apply_macos_dock_visibility
from .gengxinrizhi import GengXinRiZhi
from .mini_chuangkou import MiniChuangKou
from .searchable_combo import SearchableComboBox
from .common_widgets import FuDongAnNiu, ShuRuKuang
from .output_widgets import ShuChuKuang, AITranslatingStatusBar, InfoTooltipPopup
from .title_bar import BiaoTiLan
from .tray import init_tray
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
        if getattr(sys, 'frozen', False):
            self.resource_dir = os.path.join(sys._MEIPASS, 'src', 'ziyuan')
        else:
            self.resource_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'src', 'ziyuan')
        
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
        self.translator_vm.output_text_changed.connect(self._vm_on_output_text_changed)
        self.translator_vm.is_translating_changed.connect(self._vm_on_is_translating_changed)
        self.translator_vm.error_message_changed.connect(self._vm_on_error_message_changed)
        self.translator_vm.detected_source_language_changed.connect(self._vm_on_detected_source_language_changed)
        self.translator_vm.ai_phase_changed.connect(self._vm_on_ai_phase_changed)
        self.translator_vm.estimated_ai_tokens_changed.connect(self._vm_on_estimated_ai_tokens_changed)
        self.translator_vm.toast_message.connect(self._vm_on_toast_message)

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
        
        # 初始化拖动变量
        self._is_dragging = False
        self._drag_start_pos = None
        self._detected_lang_text = None

        self._last_copy_trigger_time = 0.0
        
        # 初始化快捷键监听器
        default_hotkey = "command+c,c" if sys.platform == "darwin" else "ctrl+c,c"
        hotkey = self.config.get("shortcuts.copy_translate", default_hotkey)
        self.kuaijiejian = KuaiJieJianJianTing(hotkey=hotkey)
        self.kuaijiejian.copy_translate_triggered.connect(self._handle_copy_translate)

        if sys.platform == "darwin":
            self._prompt_macos_accessibility_if_needed()

        try:
            if sys.platform != "darwin" or self._is_macos_accessibility_enabled():
                self.kuaijiejian.start()
                logger.info("成功启动快捷键监听")
            else:
                self.tishi.showMessage("请在系统设置启用辅助功能权限后重启应用", type="warning")
        except Exception as e:
            logger.error(f"启动快捷键监听失败: {e}")
            if sys.platform == "darwin":
                self.tishi.showMessage("快捷键启动失败，请在系统设置启用辅助功能权限", type="error")
            else:
                self.tishi.showMessage("快捷键功能初始化失败", type="error")

        self.clipboard_monitor = None

        # 初始化翻译API
        loop = asyncio.get_event_loop()
        loop.create_task(self._init_translation_api())
        
        # 显示主窗口
        self.show()
        
        # 在窗口显示后，使用QTimer延迟检查并显示更新日志
        QTimer.singleShot(1000, self._delayed_show_changelog)

        # 启动后 3 秒自动检查更新（仅一次）
        QTimer.singleShot(3000, self._check_update)
        
        # 如果配置中启用了Mini模式，则自动切换
        if self.config.get("mini_mode", False):
            self._toggle_mini_mode(True)

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

    def eventFilter(self, obj, event):
        if sys.platform == "darwin" and event.type() == QEvent.ApplicationActivate:
            if self.isHidden() and not self.config.get("mini_mode", False):
                self.showNormal()
                self.raise_()
                self.activateWindow()
        return super().eventFilter(obj, event)
    
    def _quit_app(self):
        """退出应用程序"""
        self.tray_icon.hide()  # 确保在退出前隐藏托盘图标
        QApplication.quit()
    
    def _create_ui(self):
        """创建界面"""
        # 创建主部件
        main_widget = QWidget()
        main_widget.setObjectName("centralWidget")
        self.setCentralWidget(main_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 添加自定义标题栏
        self.biaotilan = BiaoTiLan(self)
        main_layout.addWidget(self.biaotilan)
        
        # 创建内容区域
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 10, 20, 20)
        content_layout.setSpacing(15)
        
        # 创建语言与服务区域（同一行）
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)
        
        # 源语言选择
        source_container = QFrame()
        source_container.setObjectName("langPill")
        source_container.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        source_layout = QHBoxLayout(source_container)
        source_layout.setContentsMargins(10, 4, 10, 4)
        source_layout.setSpacing(6)
        source_label = QLabel("源语言")
        source_label.setObjectName("langPillLabel")
        source_layout.addWidget(source_label)
        self.source_lang_combo = SearchableComboBox()
        self.source_lang_combo.setObjectName("langComboPill")
        self.source_lang_combo.set_items([
            "自动检测",
            "简体中文", "繁体中文", "英语", "日语", "韩语", "法语",
            "德语", "西班牙语", "俄语", "意大利语", "葡萄牙语",
            "越南语", "泰语", "阿拉伯语",
        ])
        self.source_lang_combo.setCurrentIndex(0)
        source_layout.addWidget(self.source_lang_combo)
        source_chevron = QLabel("▾")
        source_chevron.setObjectName("langPillChevron")
        source_layout.addWidget(source_chevron)
        header_layout.addWidget(source_container)
        
        # 添加互转按钮
        self.switch_button = QPushButton()
        self.switch_button.setObjectName("langSwitchButton")
        self.switch_button.setIcon(QIcon("src/ziyuan/switch.svg"))
        self.switch_button.setToolTip("互换语言")
        self.switch_button.setFixedSize(28, 28)
        self.switch_button.setIconSize(QSize(24, 24))
        self.switch_button.clicked.connect(self._switch_languages)
        self.switch_button.setEnabled(False)  # 初始状态用
        header_layout.addWidget(self.switch_button)
        
        # 目标语言选择
        target_container = QFrame()
        target_container.setObjectName("langPill")
        target_container.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        target_layout = QHBoxLayout(target_container)
        target_layout.setContentsMargins(10, 4, 10, 4)
        target_layout.setSpacing(6)
        target_label = QLabel("目标语言")
        target_label.setObjectName("langPillLabel")
        target_layout.addWidget(target_label)
        self.target_lang_combo = SearchableComboBox()
        self.target_lang_combo.setObjectName("langComboPill")
        self.target_lang_combo.set_items([
            "简体中文", "繁体中文", "英语", "日语", "韩语", "法语",
            "德语", "西班牙语", "俄语", "意大利语", "葡萄牙语",
            "越南语", "泰语", "阿拉伯语",
        ])
        self.target_lang_combo.currentIndexChanged.connect(self._on_target_lang_changed)
        target_layout.addWidget(self.target_lang_combo)
        target_chevron = QLabel("▾")
        target_chevron.setObjectName("langPillChevron")
        target_layout.addWidget(target_chevron)
        header_layout.addWidget(target_container)
        
        # 翻译服务状态区
        service_container = QFrame()
        service_container.setObjectName("serviceStatusPill")
        service_container.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        service_layout = QHBoxLayout(service_container)
        service_layout.setContentsMargins(10, 4, 10, 4)
        service_layout.setSpacing(6)
        service_label = QLabel("当前翻译服务提供")
        service_label.setObjectName("serviceStatusLabel")
        service_layout.addWidget(service_label)
        service_sparkle = QLabel("✦")
        service_sparkle.setObjectName("serviceSparkle")
        service_layout.addWidget(service_sparkle)
        self.service_display = QLabel("")
        self.service_display.setObjectName("serviceNameLabel")
        service_layout.addWidget(self.service_display)
        self.status_indicator = ZhuangTaiZhiShiQi(compact=True)
        self.status_indicator.retry_button.clicked.connect(self._retry_connection)
        service_layout.addWidget(self.status_indicator)
        header_layout.addWidget(service_container)
        
        header_layout.addStretch()
        content_layout.addLayout(header_layout)
        
        # 添加
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        content_layout.addWidget(separator)
        
        # 创建右布局的文本区域
        text_layout = QHBoxLayout()
        text_layout.setSpacing(20)
        
        # 左侧输入区域
        self.input_text = ShuRuKuang("在此输入要翻译的文本...")
        self.input_text.textChanged.connect(self._vm_on_input_text_changed)
        text_layout.addWidget(self.input_text)
        
        # 右侧输出区域
        output_container = QWidget()
        output_layout = QVBoxLayout(output_container)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(0)

        self.output_text = ShuChuKuang()
        output_layout.addWidget(self.output_text)

        self.ai_status_bar = AITranslatingStatusBar()
        output_layout.addWidget(self.ai_status_bar)

        text_layout.addWidget(output_container)
        
        # 置右域比例为1:1
        text_layout.setStretch(0, 1)  # 输入区域
        text_layout.setStretch(1, 1)  # 输出区域
        
        content_layout.addLayout(text_layout)
        main_layout.addWidget(content_widget)
        
        # 加载默认设置
        self._load_default_settings()
    
    def _load_default_settings(self):
        """加载默认设置"""
        self._update_service_display()
        
        # 强制设置源语言为自动检测
        self.source_lang_combo.setCurrentIndex(0)  # 自动检测总是第一个选项
        
        # 设置目标语言
        target_lang = self.config.get("translation.target_lang", "简体中文")
        if target_lang == "中文":  # 向后兼容
            target_lang = "简体中文"
        target_index = self.target_lang_combo.findText(target_lang)
        if target_index >= 0:
            self.target_lang_combo.setCurrentIndex(target_index)
        
        # 保存设置以确保源语言是自动检测
        self.config.set("translation.source_lang", "自动检测")
    
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
        """使用防抖处理翻译请求"""
        if hasattr(self, '_translate_timer'):
            self._translate_timer.stop()
        
        # 如果本很短，可以更快地触发翻译
        text = self.input_text.toPlainText()
        delay = 200 if len(text) < 10 else 500  # 短文本200ms，长文本500ms
        
        self._translate_timer = QTimer()
        self._translate_timer.setSingleShot(True)
        self._translate_timer.timeout.connect(lambda: asyncio.create_task(self._on_text_changed()))
        self._translate_timer.start(delay)

    def _get_vm_context(self) -> TranslationContext:
        api_name = self.config.get("translation.api", "google")
        source_lang = self.source_lang_combo.currentText().split(" (")[0]
        target_lang = self.target_lang_combo.currentText()
        ai_model_name = None
        if api_name == "openai_compat":
            ai_model_name = self.config.get("openai_compat.model")
        return TranslationContext(
            api_name=api_name,
            source_lang=source_lang,
            target_lang=target_lang,
            ai_model_name=ai_model_name,
        )

    def _vm_on_input_text_changed(self):
        text = self.input_text.toPlainText()
        ctx = self._get_vm_context()
        self.translator_vm.set_input_text(text, ctx)
    
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
    
    def __del__(self):
        """析构函数，确保关闭所有会话"""
        if hasattr(self, 'fanyi'):
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.fanyi.close_current_api())
    
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.LeftButton and not self.isMaximized():
            edge = self._get_edge(event.pos())
            if edge:
                self._resize_edge = edge
                self.setCursor(self._get_resize_cursor(edge))
                self._resize_start_pos = event.globalPos()
                self._resize_start_geometry = QRect(self.geometry())
                self._is_dragging = False
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
            self._resize_edge = None
            self.setCursor(Qt.ArrowCursor)
            self._schedule_save_window_geometry()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _perform_resize(self, global_pos: QPoint):
        _window_geometry.perform_resize(self, global_pos)

    def _install_resize_event_filters(self, root: QWidget):
        _window_geometry.install_resize_event_filters(self, root)

    def eventFilter(self, obj, event):
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
                hotkey = self.config.get("shortcuts.copy_translate", default_hotkey)
                if hasattr(self, "kuaijiejian"):
                    self.kuaijiejian.set_hotkey(hotkey)
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
                loop = asyncio.get_event_loop()
                loop.create_task(self._init_translation_api())
                
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

    def _update_button_icons(self, theme_name):
        """更新按钮图标以适应主题"""
        _theme_controller.update_button_icons(self, theme_name)

    def _update_service_display(self):
        _translator_controller.update_service_display(self)

    async def _init_translation_api(self):
        """初始化翻译API"""
        return await _translator_controller.init_translation_api(self)

    async def _on_text_changed(self):
        """输入文本变化时触发翻译"""
        try:
            input_text = self.input_text.toPlainText()
            if not input_text:
                self.output_text.clear()
                self._reset_source_lang_text()
                self.switch_button.setEnabled(False)  # 无内容时禁用互转按钮
                return
            
            # 显示加载动画
            self.output_text.start_loading()
            
            try:
                source_lang = self.source_lang_combo.currentText().split(" (")[0]
                target_lang = self.target_lang_combo.currentText()
                
                # 按行分割文本并去除空行
                lines = [line for line in input_text.split('\n') if line.strip()]
                
                # 如果没有非空行，直接返回空结果
                if not lines:
                    self.output_text.stop_loading()
                    self.output_text.setPlainText("")
                    return
                
                # 使用第一个非空行进行语言检测
                first_result, detected_lang = await self.fanyi.fanyi(lines[0], source_lang, target_lang)
                
                # 更新语言检测显示
                if source_lang == "自动检测" and detected_lang:
                    try:
                        lang_map = {v: k for k, v in self.fanyi._fanyi_jiekou.LANG_CODES.items()}
                        detected_name = lang_map.get(detected_lang, detected_lang)
                        self._detected_lang = detected_lang
                        self._detected_lang_text = f"自动检测 ({detected_name})"
                        
                        # 强制更新显示
                        self.source_lang_combo.setItemText(0, self._detected_lang_text)
                        logger.info(f"更新语言检测显示: {self._detected_lang_text}")
                    except Exception as e:
                        logger.error(f"更新语言检测显示失败: {e}")
                
                # 备翻译结果
                translated_lines = []
                current_line_index = 0
                
                # 处理原始文本中的每一行，保持空行
                for original_line in input_text.split('\n'):
                    if not original_line.strip():
                        # 保持空行
                        translated_lines.append('')
                    else:
                        # 对于非空行，使用翻译结果
                        if current_line_index == 0:
                            # 第一个非空行已经翻译过了
                            leading_spaces = len(original_line) - len(original_line.lstrip())
                            translated_lines.append(' ' * leading_spaces + first_result)
                        else:
                            # 翻译其他非空行
                            leading_spaces = len(original_line) - len(original_line.lstrip())
                            result, _ = await self.fanyi.fanyi(original_line.strip(), source_lang, target_lang)
                            translated_lines.append(' ' * leading_spaces + result)
                        current_line_index += 1
                
                # 停止加载动画
                self.output_text.stop_loading()
                
                # 合并结果
                final_result = '\n'.join(translated_lines)
                self.output_text.setPlainText(final_result)
                
                # 有翻译结果时启用互转按钮
                self.switch_button.setEnabled(bool(final_result.strip()))
                
                logger.info("翻译完成")
                
            except Exception as e:
                self.output_text.stop_loading()
                logger.error(f"翻译过程出错: {e}")
                self.tishi.showMessage(f"翻译出错: {str(e)}", type="error")
                self.switch_button.setEnabled(False)  # 出错时禁用互转按钮
                
        except Exception as e:
            self.output_text.stop_loading()
            logger.error(f"处理错误: {e}")
            self.tishi.showMessage(f"处理错误: {str(e)}", type="error")
            self.switch_button.setEnabled(False)  # 出错时禁用互转按钮

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
        if self.isHidden():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

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

    def _check_update_with_message(self):
        _update_controller.check_update_with_message(self)

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

    def _handle_copy_translate(self):
        """处理复制后翻译的快捷键"""
        now = time.monotonic()
        # 避免与剪贴板双复制监听重复触发
        if now - getattr(self, '_last_copy_trigger_time', 0.0) < 0.35:
            return
        self._last_copy_trigger_time = now

        text = pyperclip.paste().strip()
        if not text:
            self.tishi.showMessage("剪贴板为空", type="warning")
            return
            
        # 不论窗口状态如何，只要不是迷你模式，就确保主窗口显示并位于前台
        if not self.config.get("mini_mode", False):
            # 恢复窗口并激活
            self.showNormal()
            self.raise_()
            self.activateWindow()
            logger.info("通过快捷键激活主窗口")
            
        if self.config.get("mini_mode", False):
            # 如果启用了迷你模式，则在迷你窗口中显示翻译
            if not hasattr(self, 'mini_window') or not self.mini_window:
                # 初始化迷你窗口
                self.mini_window = MiniChuangKou(self)
                
            # 直接使用翻译和显示方法
            asyncio.ensure_future(self._translate_and_show_mini(text))
        else:
            # 正常模式，在主窗口中显示翻译
            self.input_text.setPlainText(text)
            self.translator_vm.translate_now(text, self._get_vm_context())

    def _handle_double_copy_text(self, text: str):
        now = time.monotonic()
        if now - getattr(self, '_last_copy_trigger_time', 0.0) < 0.35:
            return
        self._last_copy_trigger_time = now

        if not text or not text.strip():
            if hasattr(self, 'tishi'):
                self.tishi.showMessage("剪贴板为空", type="warning")
            return

        if not self.config.get("mini_mode", False):
            self.showNormal()
            self.raise_()
            self.activateWindow()

        if self.config.get("mini_mode", False):
            if not hasattr(self, 'mini_window') or not self.mini_window:
                self.mini_window = MiniChuangKou(self)
            asyncio.ensure_future(self._translate_and_show_mini(text))
            return

        self.input_text.setPlainText(text)
        self.translator_vm.translate_now(text, self._get_vm_context())

    def _start_translation(self):
        """开始翻译"""
        self.translator_vm.translate_now(self.input_text.toPlainText(), self._get_vm_context())

    def _vm_on_output_text_changed(self, text: str):
        self.output_text.stop_loading()
        self.output_text.setPlainText(text or "")
        self.switch_button.setEnabled(bool((text or "").strip()))

        if not (text or "").strip():
            self.output_text.clear_ai_info()
            return

        if self.config.get("translation.api", "google") != "openai_compat":
            self.output_text.clear_ai_info()
            return

        model, duration_ms, estimated_tokens = self.translator_vm.get_last_ai_info()
        if model and duration_ms is not None:
            self.output_text.set_ai_info(model=model, duration_ms=duration_ms, estimated_tokens=estimated_tokens)
        else:
            self.output_text.clear_ai_info()

    def _vm_on_is_translating_changed(self, translating: bool):
        if translating:
            self.output_text.start_loading()
            self.output_text.clear_ai_info()
            self.status_indicator.set_status("normal", "正在翻译...")

            if self.config.get("translation.api", "google") == "openai_compat":
                model = self.config.get("openai_compat.model")
                self.ai_status_bar.set_context(model=model, phase=self._latest_ai_phase_text, estimated_tokens=self._latest_ai_estimated_tokens)
                self.ai_status_bar.start()
            else:
                self.ai_status_bar.stop()
            return

        self.output_text.stop_loading()
        self.status_indicator.set_status("normal")
        self.ai_status_bar.stop()

    def _vm_on_error_message_changed(self, message):
        if message:
            self.output_text.stop_loading()
            self.switch_button.setEnabled(False)
            self.status_indicator.set_status("error", str(message))
            return

        self.status_indicator.set_status("normal")

    def _vm_on_detected_source_language_changed(self, detected_lang):
        if not detected_lang:
            self._reset_source_lang_text()
            return

        try:
            lang_map = {v: k for k, v in self.fanyi._fanyi_jiekou.LANG_CODES.items()}
            detected_name = lang_map.get(detected_lang, detected_lang)
            self._detected_lang = detected_lang
            self._detected_lang_text = f"自动检测 ({detected_name})"
            self.source_lang_combo.setItemText(0, self._detected_lang_text)
        except Exception as e:
            logger.error(f"更新语言检测显示失败: {e}")

    def _vm_on_ai_phase_changed(self, phase):
        self._latest_ai_phase_text = str(phase) if phase else None
        if phase:
            self.status_indicator.set_status("normal", str(phase))

        if self.config.get("translation.api", "google") == "openai_compat" and getattr(self, 'ai_status_bar', None):
            model = self.config.get("openai_compat.model")
            self.ai_status_bar.set_context(model=model, phase=self._latest_ai_phase_text, estimated_tokens=self._latest_ai_estimated_tokens)

    def _vm_on_estimated_ai_tokens_changed(self, estimated):
        self._latest_ai_estimated_tokens = estimated
        if self.config.get("translation.api", "google") == "openai_compat" and getattr(self, 'ai_status_bar', None):
            model = self.config.get("openai_compat.model")
            self.ai_status_bar.set_context(model=model, phase=self._latest_ai_phase_text, estimated_tokens=self._latest_ai_estimated_tokens)

    def _vm_on_toast_message(self, message: str, toast_type: str):
        if hasattr(self, 'tishi'):
            self.tishi.showMessage(message, type=toast_type)

    def closeEvent(self, event):
        """窗口关闭事件"""
        if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            if sys.platform == "darwin" and self.config.get("show_in_dock", True):
                event.accept()
                super().closeEvent(event)
                return
            if self.mini_window:
                self.mini_window.hide()
            self.hide()
            event.ignore()
            return

        if self.mini_window:
            self.mini_window.close()

        if hasattr(self, 'clipboard_monitor') and self.clipboard_monitor:
            try:
                self.clipboard_monitor.stop()
            except Exception:
                pass

        if hasattr(self, '_save_window_geometry'):
            self._save_window_geometry()

        if hasattr(self, 'fanyi') and hasattr(self.fanyi, 'close_current_api'):
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self.fanyi.close_current_api())
            except Exception:
                pass

        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()

        event.accept()
        super().closeEvent(event)
    
    def showEvent(self, event):
        """窗口显示事件"""
        super().showEvent(event)
        # 当主窗口显示时，关闭Mini模式
        if self.is_mini_mode:
            self._toggle_mini_mode(False)
    
    async def _handle_mini_text_changed(self):
        """处理Mini窗口的文本变化"""
        if not self.mini_window:
            return
        
        text = self.mini_window.input_text.toPlainText().strip()
        if not text:
            self.mini_window.output_text.clear()
            return
        
        try:
            # 开始翻译动画
            self.mini_window.start_loading()
            
            # 获取翻译结果
            result = await self.fanyi.fanyi(
                text,
                source_lang="auto",
                target_lang=self.target_lang_combo.currentText()
            )
            
            # 处理可能的元组结果
            if isinstance(result, tuple):
                result_text = result[0]  # 获取元组中的第一个元素
            else:
                result_text = result
            
            # 显示翻译结果
            self.mini_window.stop_loading()
            self.mini_window.output_text.setPlainText(result_text)
            
            # 调整窗口大小
            self.mini_window._adjust_window_size()
            
            logger.info(f"Mini窗口翻译完成: {text} -> {result_text[:50]}...")
            
        except Exception as e:
            logger.error(f"Mini窗口翻译失败: {e}")
            self.mini_window.stop_loading()
            self.mini_window.output_text.setPlainText("翻译失败，请重试")
    
    def _toggle_mini_mode(self, checked, show_hint=True):
        """切换Mini模式
        
        参数:
            checked: 是否启用迷你模式
            show_hint: 是否显示切换提示，默认为True
        """
        self.is_mini_mode = checked
        
        if checked:
            # 初始化Mini窗口但不显示
            if not hasattr(self, "mini_window") or not self.mini_window:
                self.mini_window = MiniChuangKou(self)
            
            # 切换到Mini模式时只隐藏主窗口，不显示Mini窗口
            self.hide()
            
            # 只有在手动切换时才显示提示（show_hint=True）
            if show_hint:
                self._show_mini_mode_hint()
            
            logger.info("已切换到Mini模式（窗口隐藏）")
        else:
            # 关闭Mini窗口，显示主窗口
            if hasattr(self, "mini_window") and self.mini_window:
                self.mini_window.hide()
            
            # 显示主窗口
            self.show()
            self.activateWindow()
            logger.info("已切换到正常模式")
        
        # 更新托盘菜单的选中状态
        self.mini_mode_action.setChecked(checked)
        
        # 保存设置
        self.config.set("mini_mode", checked)
        self.config.save()
    
    def _show_mini_mode_hint(self):
        """显示迷你模式切换提示"""
        try:
            # 创建一个独立的顶层窗口作为提示
            hint = QFrame(None)
            hint.setWindowFlags(
                Qt.FramelessWindowHint | 
                Qt.WindowStaysOnTopHint | 
                Qt.Tool |
                Qt.X11BypassWindowManagerHint  # 确保在所有平台上都能显示在最顶层
            )
            hint.setAttribute(Qt.WA_TranslucentBackground)
            hint.setAttribute(Qt.WA_ShowWithoutActivating)
            
            # 设置边框样式
            hint.setFrameShape(QFrame.StyledPanel)
            hint.setStyleSheet("""
                QFrame {
                    background-color: rgba(40, 167, 69, 0.9);
                    border-radius: 20px;
                    border: 1px solid rgba(40, 167, 69, 1.0);
                }
            """)
            
            # 创建布局
            layout = QVBoxLayout(hint)
            layout.setContentsMargins(15, 10, 15, 10)
            
            # 创建标签
            msg_label = QLabel("已切换到迷你窗口模式")
            msg_label.setStyleSheet("""
                color: white;
                font-size: 14px;
                font-weight: bold;
            """)
            msg_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(msg_label)
            
            # 计算显示位置 - 屏幕中央偏下
            screen = QApplication.desktop().screenGeometry()
            hint_width = 240
            hint_height = 60
            x = (screen.width() - hint_width) // 2
            y = int(screen.height() * 0.75)
            
            hint.setGeometry(x, y, hint_width, hint_height)
            
            # 强制显示并置于顶层
            hint.show()
            hint.raise_()
            
            # 添加淡出动画效果
            def fade_out_and_close():
                """创建淡出效果并关闭提示窗口"""
                animation = QPropertyAnimation(hint, b"windowOpacity")
                animation.setDuration(500)  # 500毫秒淡出
                animation.setStartValue(1.0)
                animation.setEndValue(0.0)
                animation.finished.connect(hint.deleteLater)  # 动画结束后删除窗口
                animation.start()
            
            # 2秒后开始淡出
            QTimer.singleShot(2000, fade_out_and_close)
            
            logger.info("显示迷你模式切换提示")
        except Exception as e:
            logger.error(f"显示迷你模式切换提示失败: {e}")
            logger.exception("详细错误信息")  # 记录详细的错误堆栈信息
    
    def _toggle_mini_mode_shortcut(self):
        """通过快捷键切换Mini模式"""
        # 不论窗口状态如何，只要不是迷你模式，就确保主窗口显示并位于前台
        if not self.is_mini_mode:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            logger.info("通过模式切换快捷键激活主窗口")
            return
        
        # 切换模式
        self.mini_mode_action.setChecked(not self.mini_mode_action.isChecked())
        self._toggle_mini_mode(self.mini_mode_action.isChecked())
    
    def _toggle_mini_window(self):
        """切换Mini窗口的显示/隐藏状态"""
        if self.is_mini_mode and self.mini_window:
            if self.mini_window.isVisible():
                self.mini_window.hide()
                logger.info("隐藏Mini窗口")
            else:
                self.mini_window.show_at_cursor()
                logger.info("显示Mini窗口")

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
        """在Mini窗口中翻译并显示文本"""
        try:
            # 确保Mini窗口已初始化
            if not hasattr(self, "mini_window") or not self.mini_window:
                self.mini_window = MiniChuangKou(self)
                
            # 先确保窗口处于初始状态 - 重置大小和内容
            self.mini_window.resize(300, 60)
            self.mini_window.output_text.clear()  # 使用clear更彻底清空内容
            
            # 显示窗口并开始加载
            self.mini_window.show_at_cursor()
            self.mini_window.start_loading()
            
            # 记录当前翻译的文本
            current_translation_text = text_to_translate
            logger.info(f"开始翻译: '{text_to_translate[:20]}...'")
                
            # 使用指定的服务或默认服务翻译
            service = service or self.config.get('default_service', 'google')
                
            # 执行翻译
            translation_result = await self.fanyi.fanyi(
                text_to_translate, 
                source_lang="auto",
                target_lang=self.target_lang_combo.currentText()
            )
                
            # 翻译结果处理 - 从元组中提取文本内容
            if isinstance(translation_result, tuple):
                # 元组形式的结果，取第一个元素作为翻译文本
                translation_text = translation_result[0]
                logger.info(f"翻译结果为元组: {translation_result}")
            else:
                # 字符串形式的结果，直接使用
                translation_text = translation_result
                
            if not translation_text:
                # 翻译失败，显示错误
                self.mini_window.stop_loading()
                self.mini_window.output_text.setText("翻译失败，请重试")
                return
                
            # 显示翻译结果
            self.mini_window.stop_loading()
            self.mini_window.output_text.setText(translation_text)
            
            # 确保窗口大小适应内容
            self.mini_window._adjust_window_size_for_text(translation_text)
                
            logger.info(f"Mini窗口已显示翻译结果: '{current_translation_text[:20]}...' -> '{translation_text[:20]}...'")
        except Exception as e:
            logger.error(f"Mini窗口翻译失败: {e}")
            if hasattr(self, "mini_window") and self.mini_window:
                self.mini_window.stop_loading()
                self.mini_window.output_text.setText(f"翻译失败: {str(e)}")

    def _load_config(self):
        """加载配置"""
        # 加载配置文件中的mini_mode设置
        mini_mode = self.config.get("mini_mode", False)
        
        # 应用迷你模式设置，但不显示提示
        if mini_mode:
            self._toggle_mini_mode(True, show_hint=False)
        
        # 其他配置加载代码...