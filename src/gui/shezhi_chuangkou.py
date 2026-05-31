from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                           QLineEdit, QPushButton, QComboBox, QWidget, QGroupBox,
                           QTabWidget, QMessageBox, QScrollArea, QCheckBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QApplication
from .dialog_utils import build_menu_stylesheet, show_themed_message
from .themes import ThemeManager
from .gengxinrizhi import GengXinRiZhi
from . import update_controller as _update_controller
from ..shezhi import Config
from ..shezhi.config_defaults import VENDOR_DEFAULTS
from ..gongju.autostart import configure_autostart, apply_macos_dock_visibility, is_autostart_enabled
from ..gongju.achord_engine import AchordEngineUpdater, compare_versions
from ..gongju.fanyi_api.deepl import infer_deepl_plan, verify_deepl_auth
from ..version import APP_VERSION
import asyncio
import time
import sys


class HotkeyEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._modifier_key = "command" if sys.platform == "darwin" else "ctrl"
        modifier_label = "Command" if sys.platform == "darwin" else "Ctrl"
        self.setReadOnly(True)
        self.setPlaceholderText(f"点击后按下组合键（至少三个键），支持 {modifier_label}+C+C")
        self._last_combo = None
        self._last_time = 0.0

    def _normalize_combo(self, combo: str) -> str:
        normalized = (combo or "").strip().lower().replace(" ", "")
        if sys.platform == "darwin":
            normalized = normalized.replace("meta+", "command+")
            normalized = normalized.replace("cmd+", "command+")
        return normalized

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Backspace, Qt.Key_Delete):
            self.clear()
            self._last_combo = None
            return

        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return

        if event.modifiers() == Qt.NoModifier:
            return

        seq = QKeySequence(event.modifiers() | key).toString(QKeySequence.PortableText)
        if not seq:
            return

        normalized = self._normalize_combo(seq)
        if normalized == f"{self._modifier_key}+c":
            now = time.monotonic()
            if self._last_combo == normalized and now - self._last_time < 0.5:
                self.setText(f"{self._modifier_key}+c,c")
                self._last_combo = None
                return
            self._last_combo = normalized
            self._last_time = now
            self.setText(normalized)
            return

        self._last_combo = normalized
        self._last_time = time.monotonic()
        self.setText(normalized)


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


def install_chinese_line_edit_menu(line_edit: QLineEdit):
    line_edit.setContextMenuPolicy(Qt.CustomContextMenu)

    def show_menu(pos):
        menu = line_edit.createStandardContextMenu()
        labels = {
            "Undo": "撤销",
            "Redo": "重做",
            "Cut": "剪切",
            "Copy": "复制",
            "Paste": "粘贴",
            "Delete": "删除",
            "Clear": "清空",
            "Select All": "全选",
        }
        for action in menu.actions():
            raw_text = action.text()
            if not raw_text:
                continue

            label, separator, shortcut = raw_text.partition("\t")
            normalized = (
                label.replace("&", "")
                .replace("...", "")
                .replace("…", "")
                .strip()
            )
            if normalized in labels:
                action.setText(labels[normalized] + (separator + shortcut if separator else ""))
        menu.setStyleSheet(build_menu_stylesheet(line_edit))
        menu.exec_(line_edit.mapToGlobal(pos))

    line_edit.customContextMenuRequested.connect(show_menu)


class SheZhiChuangKou(QDialog):
    """设置窗口类"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("设置")
        self.setFixedSize(600, 640)
        self.setObjectName("settingsDialog")
        
        # 设置窗口属性
        self.setWindowFlags(Qt.Dialog | Qt.MSWindowsFixedSizeDialogHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        
        # 初始化配置
        self.config = Config()
        
        # 创建主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(24)
        
        if self.parent and hasattr(self.parent, 'config'):
            theme_key = self.parent.config.get("theme", "dark")
            theme_map = {
                "dark": "深色主题",
                "light": "浅色主题",
                "pink": "粉色主题"
            }
            display_name = theme_map.get(theme_key, "深色主题")
            self.setStyleSheet(ThemeManager.get_theme_style(display_name))
        
        tabs = QTabWidget()
        tabs.setObjectName("settingsTabs")

        # 基础设置
        base_content = QWidget()
        base_content.setObjectName("settingsTabContent")
        base_layout = QVBoxLayout(base_content)
        base_layout.setSpacing(16)

        shortcut_group = QGroupBox("快捷键")
        shortcut_layout = QVBoxLayout()
        shortcut_layout.setSpacing(8)
        shortcut_label = QLabel("激活翻译：")
        self.copy_hotkey_input = HotkeyEdit()
        hotkey_modifier = "Command" if sys.platform == "darwin" else "Ctrl"
        shortcut_help = QLabel(f"点击输入框后按组合键（至少三个键），支持 {hotkey_modifier}+C+C")
        shortcut_help.setProperty("help", "true")
        shortcut_layout.addWidget(shortcut_label)
        shortcut_layout.addWidget(self.copy_hotkey_input)
        shortcut_layout.addWidget(shortcut_help)
        shortcut_group.setLayout(shortcut_layout)

        startup_group = QGroupBox("启动")
        startup_layout = QVBoxLayout()
        startup_layout.setSpacing(8)
        self.auto_start_checkbox = QCheckBox("开机自启")
        startup_layout.addWidget(self.auto_start_checkbox)
        if sys.platform == "darwin":
            self.show_in_dock_checkbox = QCheckBox("显示在程序坞")
            startup_layout.addWidget(self.show_in_dock_checkbox)
        startup_group.setLayout(startup_layout)

        update_group = QGroupBox("更新")
        update_layout = QVBoxLayout()
        update_layout.setSpacing(10)

        version_label = QLabel(f"当前版本：v{APP_VERSION}")
        self.check_update_button = QPushButton("检测更新")
        self.check_update_button.setFixedHeight(34)
        self.check_update_button.clicked.connect(self._on_check_update_clicked)

        self.changelog_button = QPushButton("查看更新说明")
        self.changelog_button.setFixedHeight(34)
        self.changelog_button.clicked.connect(self._on_show_changelog)

        update_button_row = QHBoxLayout()
        update_button_row.setSpacing(12)
        update_button_row.addWidget(self.check_update_button)
        update_button_row.addWidget(self.changelog_button)
        self.update_status_label = QLabel("")
        self.update_status_label.setObjectName("updateStatusLabel")
        self.update_status_label.setVisible(False)
        update_button_row.addWidget(self.update_status_label)
        update_button_row.addStretch()

        update_layout.addWidget(version_label)
        update_layout.addLayout(update_button_row)
        update_group.setLayout(update_layout)

        base_layout.addWidget(shortcut_group)
        base_layout.addWidget(startup_group)
        base_layout.addWidget(update_group)
        base_layout.addStretch()

        base_scroll = QScrollArea()
        base_scroll.setWidgetResizable(True)
        base_scroll.setObjectName("baseSettingsScroll")
        base_scroll.setFrameShape(QScrollArea.NoFrame)
        base_scroll.setWidget(base_content)
        tabs.addTab(base_scroll, "基础设置")

        # 翻译设置
        translation_content = QWidget()
        translation_content.setObjectName("settingsTabContent")
        translation_layout = QVBoxLayout(translation_content)
        translation_layout.setSpacing(16)

        service_group = QGroupBox("翻译服务")
        service_layout = QVBoxLayout()
        service_layout.setSpacing(12)

        service_container = QVBoxLayout()
        service_container.setSpacing(4)
        service_label = QLabel("当前使用:")
        self.translation_api_combo = QComboBox()
        self.translation_api_combo.addItems(["Google（默认）", "DeepL", "Achord 内置引擎", "AI（通用接口）"])
        service_help = QLabel("在这里选择翻译引擎")
        service_help.setProperty("help", "true")
        service_container.addWidget(service_label)
        service_container.addWidget(self.translation_api_combo)
        service_container.addWidget(service_help)
        service_layout.addLayout(service_container)

        self.ai_settings_group = QGroupBox("模型设置")
        ai_layout = QVBoxLayout()
        ai_layout.setSpacing(22)
        ai_layout.setContentsMargins(20, 24, 20, 24)

        vendor_container = QVBoxLayout()
        vendor_container.setSpacing(10)
        vendor_label = QLabel("模型厂家:")
        self.vendor_combo = NoWheelComboBox()
        self.vendor_combo.addItems(["智谱", "OpenAI", "DeepSeek", "通义千问(Qwen)", "字节豆包", "Google Gemini", "自定义"])
        vendor_help = QLabel("选择厂家后会预填URL与模型名（你仍可手动修改）")
        vendor_help.setProperty("help", "true")
        vendor_container.addWidget(vendor_label)
        vendor_container.addWidget(self.vendor_combo)
        vendor_container.addWidget(vendor_help)
        ai_layout.addLayout(vendor_container)

        url_container = QVBoxLayout()
        url_container.setSpacing(10)
        url_label = QLabel("模型URL:")
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("例如：https://open.bigmodel.cn/api/paas/v4")
        url_help = QLabel("填写 OpenAI-compatible 的 base_url")
        url_help.setProperty("help", "true")
        url_container.addWidget(url_label)
        url_container.addWidget(self.base_url_input)
        url_container.addWidget(url_help)
        ai_layout.addLayout(url_container)

        model_container = QVBoxLayout()
        model_container.setSpacing(10)
        model_label = QLabel("模型名称:")
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("例如：glm-4-flash / gpt-4o-mini")
        model_help = QLabel("填写模型ID（由厂家定义）")
        model_help.setProperty("help", "true")
        model_container.addWidget(model_label)
        model_container.addWidget(self.model_input)
        model_container.addWidget(model_help)
        ai_layout.addLayout(model_container)

        key_container = QVBoxLayout()
        key_container.setSpacing(10)
        key_label = QLabel("API Key:")
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("请输入 API Key")
        key_help = QLabel("密钥将保存在本地配置文件中")
        key_help.setProperty("help", "true")
        key_container.addWidget(key_label)
        key_container.addWidget(self.api_key_input)
        key_container.addWidget(key_help)
        ai_layout.addLayout(key_container)

        self.ai_settings_group.setLayout(ai_layout)
        service_layout.addWidget(self.ai_settings_group)

        self.deepl_settings_group = QGroupBox("DeepL 设置")
        deepl_layout = QVBoxLayout()
        deepl_layout.setSpacing(14)
        deepl_layout.setContentsMargins(20, 20, 20, 20)

        deepl_key_label = QLabel("DeepL API Key:")
        self.deepl_api_key_input = QLineEdit()
        self.deepl_api_key_input.setEchoMode(QLineEdit.Password)
        self.deepl_api_key_input.setPlaceholderText("请输入 DeepL API Key")
        deepl_key_help = QLabel("输入 API Key 后验证身份，程序会自动区分 DeepL Free / Pro。")
        deepl_key_help.setProperty("help", "true")
        deepl_status_row = QHBoxLayout()
        deepl_status_row.setSpacing(10)
        self.deepl_account_badge = QLabel("未验证")
        self.deepl_account_badge.setObjectName("serviceStatusPill")
        self.deepl_verify_button = QPushButton("验证身份")
        self.deepl_verify_button.setFixedHeight(32)
        self.deepl_verify_button.clicked.connect(self._on_verify_deepl_clicked)
        deepl_status_row.addWidget(self.deepl_account_badge)
        deepl_status_row.addWidget(self.deepl_verify_button)
        deepl_status_row.addStretch()
        deepl_layout.addWidget(deepl_key_label)
        deepl_layout.addWidget(self.deepl_api_key_input)
        deepl_layout.addWidget(deepl_key_help)
        deepl_layout.addLayout(deepl_status_row)
        self.deepl_settings_group.setLayout(deepl_layout)
        service_layout.addWidget(self.deepl_settings_group)

        self.achord_engine_updater = AchordEngineUpdater()
        self.achord_engine_group = QGroupBox("Achord 内置引擎")
        achord_layout = QVBoxLayout()
        achord_layout.setSpacing(14)
        achord_layout.setContentsMargins(20, 20, 20, 20)

        self.achord_engine_status = QLabel("正在读取引擎状态...")
        self.achord_engine_status.setObjectName("serviceStatusPill")
        achord_help = QLabel("内置引擎会在本机静默启动，仅应用内部请求；无需登录或填写 Key。")
        achord_help.setProperty("help", "true")
        achord_button_row = QHBoxLayout()
        achord_button_row.setSpacing(10)
        self.achord_engine_check_button = QPushButton("检测更新")
        self.achord_engine_check_button.setFixedHeight(32)
        self.achord_engine_check_button.clicked.connect(self._on_check_achord_engine_clicked)
        self.achord_engine_update_button = QPushButton("更新引擎")
        self.achord_engine_update_button.setFixedHeight(32)
        self.achord_engine_update_button.clicked.connect(self._on_update_achord_engine_clicked)
        achord_button_row.addWidget(self.achord_engine_check_button)
        achord_button_row.addWidget(self.achord_engine_update_button)
        achord_button_row.addStretch()

        achord_layout.addWidget(self.achord_engine_status)
        achord_layout.addWidget(achord_help)
        achord_layout.addLayout(achord_button_row)
        self.achord_engine_group.setLayout(achord_layout)
        service_layout.addWidget(self.achord_engine_group)

        self.translation_note_label = QLabel("注意：Google 翻译无需 API 密钥，但需要确保网络能访问 Google 服务")
        self.translation_note_label.setProperty("help", "true")
        self.translation_note_label.setWordWrap(True)
        service_layout.addWidget(self.translation_note_label)

        service_group.setLayout(service_layout)
        translation_layout.addWidget(service_group)
        translation_layout.addStretch()

        translation_scroll = QScrollArea()
        translation_scroll.setWidgetResizable(True)
        translation_scroll.setObjectName("translationSettingsScroll")
        translation_scroll.setFrameShape(QScrollArea.NoFrame)
        translation_scroll.setWidget(translation_content)
        tabs.addTab(translation_scroll, "翻译设置")

        layout.addWidget(tabs)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("cancelButton")
        cancel_button.setFixedSize(100, 36)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        save_button = QPushButton("保存")
        save_button.setFixedSize(100, 36)
        save_button.clicked.connect(self._save_settings)
        button_layout.addWidget(save_button)
        
        layout.addLayout(button_layout)
        
        # 加载当前设置
        self._load_settings()

        self.vendor_combo.currentTextChanged.connect(self._on_vendor_changed)
        self.translation_api_combo.currentIndexChanged.connect(self._sync_ai_settings_visibility)
        self._current_vendor = self.vendor_combo.currentText()
        self._install_chinese_context_menus()
    
    def _load_settings(self):
        self._load_form_from_config()

    def _install_chinese_context_menus(self):
        for line_edit in self.findChildren(QLineEdit):
            install_chinese_line_edit_menu(line_edit)

    def _load_form_from_config(self):
        """加载当前设置。"""
        api_name = self.parent.config.get("translation.api", "google")
        if api_name == "google":
            api_index = 0
        elif api_name == "deepl":
            api_index = 1
        elif api_name in {"achord_builtin", "deeplx"}:
            api_index = 2
        elif api_name == "openai_compat":
            api_index = 3
        else:
            api_index = 0
        self.translation_api_combo.setCurrentIndex(api_index)

        hotkey = self.parent.config.get("shortcuts.copy_translate", "ctrl+c,c")
        if hasattr(self, "copy_hotkey_input"):
            self.copy_hotkey_input.setText((hotkey or "").strip())

        if hasattr(self, "auto_start_checkbox"):
            actual_auto_start = is_autostart_enabled()
            if actual_auto_start != self.parent.config.get("auto_start", False):
                self.parent.config.set("auto_start", actual_auto_start)
            self.auto_start_checkbox.setChecked(actual_auto_start)
        if hasattr(self, "show_in_dock_checkbox"):
            self.show_in_dock_checkbox.setChecked(self.parent.config.get("show_in_dock", True))

        vendor = self.parent.config.get("openai_compat.vendor", "智谱")
        vendor_index = self.vendor_combo.findText(vendor)
        if vendor_index >= 0:
            self.vendor_combo.setCurrentIndex(vendor_index)

        self._load_vendor_profile(vendor)
        if hasattr(self, "deepl_api_key_input"):
            self.deepl_api_key_input.setText(self.parent.config.get("deepl.api_key", ""))
            self._update_deepl_badge(self.parent.config.get("deepl.account_type", ""))
        self._refresh_achord_engine_status()
        self._sync_ai_settings_visibility()

    def showEvent(self, event):
        super().showEvent(event)
        # 两阶段触发：某些情况下首次 show 时 style polish 尚未完成
        QTimer.singleShot(0, self._ensure_layout_ready)
        QTimer.singleShot(50, self._ensure_layout_ready)

    def _ensure_layout_ready(self):
        try:
            try:
                self.style().unpolish(self)
                self.style().polish(self)
            except Exception:
                pass

            for w in self.findChildren(QWidget):
                try:
                    w.style().unpolish(w)
                    w.style().polish(w)
                except Exception:
                    pass

            l = self.layout()
            if l:
                l.invalidate()
                l.activate()

            QApplication.processEvents()
            self.updateGeometry()
            self.update()
        except Exception:
            pass

    def _save_settings(self):
        self._save_form_to_config()

    def _save_form_to_config(self):
        """保存设置。"""
        try:
            hotkey = ""
            if hasattr(self, "copy_hotkey_input"):
                hotkey = (self.copy_hotkey_input.text() or "").strip().lower().replace(" ", "")

            if hotkey:
                if not self._is_valid_hotkey(hotkey):
                    modifier_label = "Command" if sys.platform == "darwin" else "Ctrl"
                    show_themed_message(
                        self,
                        icon=QMessageBox.Warning,
                        title="快捷键无效",
                        text=f"请输入至少三个键的组合（如 {modifier_label}+Shift+T），也支持 {modifier_label}+C+C。",
                        buttons=QMessageBox.Ok,
                    )
                    return
                self.parent.config.set("shortcuts.copy_translate", hotkey)

            if hasattr(self, "auto_start_checkbox"):
                auto_start = self.auto_start_checkbox.isChecked()
                try:
                    configure_autostart(auto_start)
                    self.parent.config.set("auto_start", auto_start)
                except Exception as e:
                    self.auto_start_checkbox.setChecked(self.parent.config.get("auto_start", False))
                    show_themed_message(
                        self,
                        icon=QMessageBox.Warning,
                        title="开机自启失败",
                        text=str(e),
                        buttons=QMessageBox.Ok,
                    )

            if hasattr(self, "show_in_dock_checkbox"):
                show_in_dock = self.show_in_dock_checkbox.isChecked()
                self.parent.config.set("show_in_dock", show_in_dock)
                apply_macos_dock_visibility(show_in_dock)

            api_names = ["google", "deepl", "achord_builtin", "openai_compat"]
            api_index = self.translation_api_combo.currentIndex()
            api_name = api_names[api_index] if 0 <= api_index < len(api_names) else "google"
            self.parent.config.set("translation.api", api_name)

            if hasattr(self, "deepl_api_key_input"):
                self.parent.config.set("deepl.api_key", self.deepl_api_key_input.text().strip())
                self.parent.config.set(
                    "deepl.account_type",
                    infer_deepl_plan(self.deepl_api_key_input.text().strip()) if self.deepl_api_key_input.text().strip() else "",
                )

            vendor = self.vendor_combo.currentText()
            base_url = self.base_url_input.text().strip()
            inferred_vendor = self._infer_vendor_by_base_url(base_url)
            if inferred_vendor and vendor != "自定义" and inferred_vendor != vendor:
                vendor = inferred_vendor

            self._save_vendor_profile(vendor)

            # 同步写入当前生效配置（保持向后兼容：其他地方仍读取 openai_compat.base_url 等）
            self.parent.config.set("openai_compat.vendor", vendor)
            self.parent.config.set("openai_compat.base_url", base_url)
            self.parent.config.set("openai_compat.model", self.model_input.text().strip())
            self.parent.config.set("openai_compat.api_key", self.api_key_input.text().strip())
            
            self.accept()
        except Exception as e:
            print(f"保存设置时出错: {e}")

    def _on_check_update_clicked(self):
        _update_controller.check_update_with_message(self)

    def _on_show_changelog(self):
        dialog = GengXinRiZhi(self)
        dialog.setModal(True)
        dialog.exec_()

    def _refresh_achord_engine_status(self, extra: str = ""):
        if not hasattr(self, "achord_engine_status"):
            return
        info = self.achord_engine_updater.current_engine_info()
        if info:
            source_map = {
                "cache": "已更新",
                "bundled": "随包内置",
                "development": "开发目录",
            }
            text = f"当前引擎：v{info.version}（{source_map.get(info.source, info.source)}）"
        else:
            text = "当前引擎：缺失"
        if extra:
            text = f"{text} · {extra}"
        self.achord_engine_status.setText(text)

    def _on_check_achord_engine_clicked(self):
        self.achord_engine_check_button.setEnabled(False)
        self.achord_engine_check_button.setText("检测中...")
        self._refresh_achord_engine_status("检测中")

        async def check():
            try:
                latest = await self.achord_engine_updater.check_latest()
                current = self.achord_engine_updater.current_engine_info()
                current_version = current.version if current else "0.0.0"
                if compare_versions(latest.version, current_version) > 0:
                    self._refresh_achord_engine_status(f"发现 v{latest.version}")
                    show_themed_message(
                        self,
                        icon=QMessageBox.Information,
                        title="发现引擎更新",
                        text=f"检测到 Achord 内置引擎 v{latest.version}，可点击“更新引擎”安装。",
                        buttons=QMessageBox.Ok,
                    )
                else:
                    self._refresh_achord_engine_status("已是最新")
                    show_themed_message(
                        self,
                        icon=QMessageBox.Information,
                        title="引擎已是最新",
                        text=f"当前 Achord 内置引擎已是最新版本 v{current_version}。",
                        buttons=QMessageBox.Ok,
                    )
            except Exception as e:
                self._refresh_achord_engine_status("检测失败")
                show_themed_message(
                    self,
                    icon=QMessageBox.Warning,
                    title="检测引擎更新失败",
                    text=str(e),
                    buttons=QMessageBox.Ok,
                )
            finally:
                self.achord_engine_check_button.setEnabled(True)
                self.achord_engine_check_button.setText("检测更新")

        asyncio.get_event_loop().create_task(check())

    def _on_update_achord_engine_clicked(self):
        self.achord_engine_update_button.setEnabled(False)
        self.achord_engine_update_button.setText("更新中...")
        self._refresh_achord_engine_status("下载中")

        def progress(value: int):
            self._refresh_achord_engine_status(f"下载 {value}%")

        async def update():
            try:
                info = await self.achord_engine_updater.download_latest(progress_callback=progress)
                self._refresh_achord_engine_status("更新完成")
                if self.parent.config.get("translation.api", "google") == "achord_builtin":
                    self.parent.reload_translation_api()
                show_themed_message(
                    self,
                    icon=QMessageBox.Information,
                    title="引擎更新完成",
                    text=f"Achord 内置引擎已更新到 v{info.version}。",
                    buttons=QMessageBox.Ok,
                )
            except Exception as e:
                self._refresh_achord_engine_status("更新失败")
                show_themed_message(
                    self,
                    icon=QMessageBox.Warning,
                    title="引擎更新失败",
                    text=str(e),
                    buttons=QMessageBox.Ok,
                )
            finally:
                self.achord_engine_update_button.setEnabled(True)
                self.achord_engine_update_button.setText("更新引擎")

        asyncio.get_event_loop().create_task(update())

    def _update_deepl_badge(self, account_type: str, detail: str = ""):
        account_type = (account_type or "").strip().lower()
        if account_type == "free":
            text = "DeepL Free"
        elif account_type == "pro":
            text = "DeepL Pro"
        else:
            text = "未验证"
        if detail:
            text = f"{text} · {detail}"
        self.deepl_account_badge.setText(text)

    def _on_verify_deepl_clicked(self):
        api_key = self.deepl_api_key_input.text().strip()
        if not api_key:
            show_themed_message(
                self,
                icon=QMessageBox.Warning,
                title="DeepL API Key 缺失",
                text="请先输入 DeepL API Key。",
                buttons=QMessageBox.Ok,
            )
            return

        self.deepl_verify_button.setEnabled(False)
        self.deepl_verify_button.setText("验证中...")
        self._update_deepl_badge(infer_deepl_plan(api_key), "验证中")

        async def verify():
            try:
                result = await verify_deepl_auth(api_key)
                account_type = result["plan"]
                usage = result.get("usage") or {}
                detail = ""
                if isinstance(usage, dict):
                    count = usage.get("character_count")
                    limit = usage.get("character_limit")
                    if count is not None and limit:
                        detail = f"{count}/{limit}"
                self.parent.config.set("deepl.api_key", api_key)
                self.parent.config.set("deepl.account_type", account_type)
                self._update_deepl_badge(account_type, detail)
                show_themed_message(
                    self,
                    icon=QMessageBox.Information,
                    title="DeepL 验证成功",
                    text=f"已识别为 DeepL {'Free' if account_type == 'free' else 'Pro'} 账号。",
                    buttons=QMessageBox.Ok,
                )
            except Exception as e:
                self._update_deepl_badge("")
                show_themed_message(
                    self,
                    icon=QMessageBox.Warning,
                    title="DeepL 验证失败",
                    text=str(e),
                    buttons=QMessageBox.Ok,
                )
            finally:
                self.deepl_verify_button.setEnabled(True)
                self.deepl_verify_button.setText("验证身份")

        asyncio.get_event_loop().create_task(verify())

    def _is_valid_hotkey(self, hotkey: str) -> bool:
        if not hotkey:
            return False
        parts = [part for part in hotkey.replace(" ", "").split(",") if part]
        keys = []
        for part in parts:
            keys.extend([key for key in part.split("+") if key])
        return len(keys) >= 3

    def _on_vendor_changed(self, vendor: str):
        # 先把旧厂家的内容保存到 profiles，避免切换时丢失/串号
        prev_vendor = getattr(self, "_current_vendor", None)
        if prev_vendor and prev_vendor != vendor:
            self._save_vendor_profile(prev_vendor)

        # 优先加载该厂家的历史配置；没有则用预设（model 不强制填）
        if not self._load_vendor_profile(vendor):
            d = VENDOR_DEFAULTS.get(vendor)
            if d:
                self.base_url_input.setText(d["base_url"])
                self.model_input.setText(d["model"])
                self.api_key_input.setText("")

        self._current_vendor = vendor

    def _infer_vendor_by_base_url(self, base_url: str):
        url = (base_url or "").strip().lower()
        if not url:
            return None

        patterns = [
            ("open.bigmodel.cn", "智谱"),
            ("ark.cn-beijing.volces.com", "字节豆包"),
            ("dashscope.aliyuncs.com", "通义千问(Qwen)"),
            ("api.deepseek.com", "DeepSeek"),
            ("api.openai.com", "OpenAI"),
            ("generativelanguage.googleapis.com", "Google Gemini"),
        ]
        for key, vendor in patterns:
            if key in url:
                return vendor
        return None

    def _get_profiles(self):
        profiles = self.parent.config.get("openai_compat.profiles", {})
        return profiles if isinstance(profiles, dict) else {}

    def _load_vendor_profile(self, vendor: str) -> bool:
        profiles = self._get_profiles()
        p = profiles.get(vendor)
        if not isinstance(p, dict):
            return False

        self.base_url_input.setText((p.get("base_url") or "").strip())
        self.model_input.setText((p.get("model") or "").strip())
        self.api_key_input.setText((p.get("api_key") or "").strip())
        return True

    def _save_vendor_profile(self, vendor: str) -> None:
        vendor = (vendor or "").strip()
        if not vendor:
            return

        profiles = self._get_profiles()
        profiles[vendor] = {
            "base_url": self.base_url_input.text().strip(),
            "model": self.model_input.text().strip(),
            "api_key": self.api_key_input.text().strip(),
        }
        self.parent.config.set("openai_compat.profiles", profiles)

    def _notify_translation_settings_changed(self) -> None:
        return

    def _sync_ai_settings_visibility(self):
        index = self.translation_api_combo.currentIndex()
        is_deepl = index == 1
        is_achord_engine = index == 2
        is_ai = index == 3
        if hasattr(self, "deepl_settings_group"):
            self.deepl_settings_group.setVisible(is_deepl)
        if hasattr(self, "achord_engine_group"):
            self.achord_engine_group.setVisible(is_achord_engine)
        self.ai_settings_group.setVisible(is_ai)

        if index == 0:
            self.translation_note_label.setText("Google 翻译无需 API 密钥，但需要确保网络可以访问 Google 服务。")
        elif index == 1:
            self.translation_note_label.setText("DeepL 需要 API Key；程序会自动识别 Free / Pro 并显示身份标识。")
        elif index == 2:
            self.translation_note_label.setText("Achord 内置引擎会在本机静默启动，无需登录；引擎可单独检测并更新。")
        else:
            self.translation_note_label.setText("AI 模式需要填写模型厂家、接口地址、模型名和 API Key。")
