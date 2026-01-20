from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                           QLineEdit, QPushButton, QComboBox, QWidget, QGroupBox,
                           QTabWidget, QMessageBox, QScrollArea, QCheckBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QApplication
from .themes import ThemeManager
from .gengxinrizhi import GengXinRiZhi
from . import update_controller as _update_controller
from ..shezhi import Config
from ..gongju.autostart import configure_autostart, apply_macos_dock_visibility
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
        self.translation_api_combo.addItems(["Achord自研模型（推荐）", "Google（需科学上网）", "AI（通用接口）"])
        service_help = QLabel("在这里选择翻译引擎")
        service_help.setProperty("help", "true")
        service_container.addWidget(service_label)
        service_container.addWidget(self.translation_api_combo)
        service_container.addWidget(service_help)
        service_layout.addLayout(service_container)

        service_group.setLayout(service_layout)
        translation_layout.addWidget(service_group)
        translation_layout.addStretch()

        translation_scroll = QScrollArea()
        translation_scroll.setWidgetResizable(True)
        translation_scroll.setObjectName("translationSettingsScroll")
        translation_scroll.setFrameShape(QScrollArea.NoFrame)
        translation_scroll.setWidget(translation_content)
        tabs.addTab(translation_scroll, "翻译设置")

        # 模型设置
        model_tab = QWidget()
        model_layout = QVBoxLayout(model_tab)
        model_layout.setSpacing(16)

        model_scroll = QScrollArea()
        model_scroll.setWidgetResizable(True)
        model_scroll.setObjectName("modelSettingsScroll")
        model_scroll.setFrameShape(QScrollArea.NoFrame)

        model_content = QWidget()
        model_content.setObjectName("settingsTabContent")
        model_content_layout = QVBoxLayout(model_content)
        model_content_layout.setSpacing(24)

        api_group = QGroupBox("模型配置")
        api_layout = QVBoxLayout()
        api_layout.setSpacing(22)
        api_layout.setContentsMargins(20, 24, 20, 24)

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
        api_layout.addLayout(vendor_container)

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
        api_layout.addLayout(url_container)

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
        api_layout.addLayout(model_container)

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
        api_layout.addLayout(key_container)
        
        api_group.setLayout(api_layout)
        model_content_layout.addWidget(api_group)
        
        # 添加说明文本
        note_label = QLabel("注意：Google 翻译无需 API 密钥，但需要确保网络能访问 Google 服务")
        note_label.setProperty("help", "true")
        note_label.setWordWrap(True)
        model_content_layout.addWidget(note_label)
        model_content_layout.addStretch()

        model_scroll.setWidget(model_content)
        model_layout.addWidget(model_scroll)
        tabs.addTab(model_tab, "模型设置")

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
        self._current_vendor = self.vendor_combo.currentText()
    
    def _load_settings(self):
        """加载当前设置"""
        api_name = self.parent.config.get("translation.api", "google")
        if api_name == "openai_compat":
            api_index = 1
        elif api_name == "achord":
            api_index = 2
        else:
            api_index = 0
        self.translation_api_combo.setCurrentIndex(api_index)

        hotkey = self.parent.config.get("shortcuts.copy_translate", "ctrl+c,c")
        if hasattr(self, "copy_hotkey_input"):
            self.copy_hotkey_input.setText((hotkey or "").strip())

        if hasattr(self, "auto_start_checkbox"):
            self.auto_start_checkbox.setChecked(self.parent.config.get("auto_start", False))
        if hasattr(self, "show_in_dock_checkbox"):
            self.show_in_dock_checkbox.setChecked(self.parent.config.get("show_in_dock", True))

        vendor = self.parent.config.get("openai_compat.vendor", "智谱")
        vendor_index = self.vendor_combo.findText(vendor)
        if vendor_index >= 0:
            self.vendor_combo.setCurrentIndex(vendor_index)

        self._load_vendor_profile(vendor)

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
        """保存设置"""
        try:
            hotkey = ""
            if hasattr(self, "copy_hotkey_input"):
                hotkey = (self.copy_hotkey_input.text() or "").strip().lower().replace(" ", "")

            if hotkey:
                if not self._is_valid_hotkey(hotkey):
                    modifier_label = "Command" if sys.platform == "darwin" else "Ctrl"
                    QMessageBox.warning(
                        self,
                        "快捷键无效",
                        f"请输入至少三个键的组合（如 {modifier_label}+Shift+T），也支持 {modifier_label}+C+C。",
                    )
                    return
                self.parent.config.set("shortcuts.copy_translate", hotkey)

            if hasattr(self, "auto_start_checkbox"):
                auto_start = self.auto_start_checkbox.isChecked()
                self.parent.config.set("auto_start", auto_start)
                try:
                    configure_autostart(auto_start)
                except Exception as e:
                    QMessageBox.warning(self, "开机自启失败", str(e))

            if hasattr(self, "show_in_dock_checkbox"):
                show_in_dock = self.show_in_dock_checkbox.isChecked()
                self.parent.config.set("show_in_dock", show_in_dock)
                apply_macos_dock_visibility(show_in_dock)

            if self.translation_api_combo.currentIndex() == 1:
                api_name = "openai_compat"
            elif self.translation_api_combo.currentIndex() == 2:
                api_name = "achord"
            else:
                api_name = "google"
            self.parent.config.set("translation.api", api_name)

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
            
            # 保存后重新初始化翻译 API
            if hasattr(self.parent, '_init_translation_api'):
                loop = asyncio.get_event_loop()
                loop.create_task(self.parent._init_translation_api())
            
            self.accept()
        except Exception as e:
            print(f"保存设置时出错: {e}")

    def _on_check_update_clicked(self):
        _update_controller.check_update_with_message(self)

    def _on_show_changelog(self):
        dialog = GengXinRiZhi(self)
        dialog.setModal(True)
        dialog.exec_()

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

        defaults = {
            "智谱": {
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                "model": "glm-4-flash",
            },
            "OpenAI": {
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
            },
            "DeepSeek": {
                "base_url": "https://api.deepseek.com",
                "model": "",
            },
            "通义千问(Qwen)": {
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "",
            },
            "字节豆包": {
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "model": "",
            },
            "Google Gemini": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "model": "",
            },
            "自定义": {
                "base_url": "",
                "model": "",
            },
        }

        # 优先加载该厂家的历史配置；没有则用预设（model 不强制填）
        if not self._load_vendor_profile(vendor):
            d = defaults.get(vendor)
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