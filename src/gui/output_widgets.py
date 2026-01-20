import html

import pyperclip

from PyQt5.QtWidgets import (
    QTextEdit,
    QPushButton,
    QFrame,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QSize, QPoint, QTimer
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtWidgets import QGraphicsDropShadowEffect

from .common_widgets import FuDongAnNiu


class ShuChuKuang(QTextEdit):
    """带复制按钮和加载效果的输出框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMinimumHeight(270)

        self._is_loading = False

        self._ai_info_model = None
        self._ai_info_duration_ms = None
        self._ai_info_estimated_tokens = None
        
        # 创建复制按钮
        self.copy_button = FuDongAnNiu("src/ziyuan/copy.svg", "复制", self)
        self.copy_button.clicked.connect(self._on_copy)
        self.copy_button.hide()
        self.copy_button.raise_()

        # 创建 AI 信息按钮（仅 AI 翻译完成后显示）
        self.ai_info_button = QPushButton("", self)
        self.ai_info_button.setFixedSize(28, 28)
        self.ai_info_button.setObjectName("floatingIconButton")
        self.ai_info_button.setToolTip("AI 翻译详情")
        self.ai_info_button.setIcon(QIcon("src/ziyuan/info.svg"))
        self.ai_info_button.setIconSize(QSize(16, 16))
        self.ai_info_button.clicked.connect(self._on_ai_info)
        self.ai_info_button.hide()
        self.ai_info_button.raise_()
        
        # 加载动画
        self.loading_dots = ""
        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self._update_loading)
        
        # 设置文本框的内边距
        self.setViewportMargins(0, 0, 0, 0)
        
        # 设置右键菜单样式
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _update_action_buttons_positions(self):
        margin = 8
        gap = 6
        scrollbar = self.verticalScrollBar()
        scrollbar_offset = scrollbar.sizeHint().width() if scrollbar and scrollbar.isVisible() else 0

        copy_pos = QPoint(
            self.width() - self.copy_button.width() - margin - scrollbar_offset,
            self.height() - self.copy_button.height() - margin
        )
        self.copy_button.move(copy_pos)
        self.copy_button.raise_()

        if self.ai_info_button.isVisible():
            info_pos = QPoint(
                copy_pos.x() - self.ai_info_button.width() - gap,
                copy_pos.y()
            )
            self.ai_info_button.move(info_pos)
            self.ai_info_button.raise_()
    
    def _show_context_menu(self, pos):
        """显示自定义右键菜单"""
        menu = self.createStandardContextMenu()
        
        # 清除原有菜单项
        menu.clear()
        
        # 添加自定义菜单项
        actions = {
            "复制": "Ctrl+C",
            None: None,  # 分隔符
            "全选": "Ctrl+A",
            None: None,  # 分隔符
            "🌟 大佐翻译官": None,
            "👤 作者: Achord": None
        }
        
        for text, shortcut in actions.items():
            if text is None:
                menu.addSeparator()
            else:
                action = menu.addAction(text)
                if shortcut:
                    action.setShortcut(shortcut)
                if "大佐翻译官" in text or "作者" in text:
                    action.setEnabled(False)
        
        menu.setStyleSheet("""
            QMenu {
                background-color: #2D2D2D;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 4px;
                color: #FFFFFF;
            }
            QMenu::item:selected {
                background-color: #404040;
            }
            QMenu::separator {
                height: 1px;
                background-color: #404040;
                margin: 4px 0px;
            }
            QMenu::item:disabled {
                color: #808080;
            }
        """)
        
        # 连接菜单项动作
        menu.triggered.connect(lambda action: self._handle_menu_action(action.text()))
        
        menu.exec_(self.mapToGlobal(pos))
    
    def _handle_menu_action(self, action_text):
        """处理菜单项点击事件"""
        action_map = {
            "复制": self.copy,
            "全选": self.selectAll
        }
        
        if action_text in action_map:
            action_map[action_text]()
    
    def _update_loading(self):
        """新加载动画"""
        self.loading_dots = self.loading_dots + "." if len(self.loading_dots) < 3 else ""
        self.setPlainText(f"正在翻译{self.loading_dots}")
    
    def start_loading(self):
        """开始加载动画"""
        self._is_loading = True
        self.copy_button.hide()
        self.copy_button.setEnabled(False)
        self.ai_info_button.hide()
        self.loading_dots = ""
        self.loading_timer.start(500)  # 每500ms更新一次
        self._update_loading()
    
    def stop_loading(self):
        """停止加载动画"""
        self.loading_timer.stop()
        self._is_loading = False
    
    def resizeEvent(self, event):
        """重写大小改变事件，更新复制按钮位置"""
        super().resizeEvent(event)
        self._update_action_buttons_positions()
    
    def _on_copy(self):
        """复制按钮点击事件"""
        text = self.toPlainText()
        if text:
            try:
                pyperclip.copy(text)
                # 获取主窗口对象
                main_window = None
                parent = self.parent()
                while parent is not None:
                    if parent.__class__.__name__ == "ZhuChuangKou":
                        main_window = parent
                        break
                    parent = parent.parent()
                
                if main_window and hasattr(main_window, 'tishi'):
                    main_window.tishi.showMessage("复制成功", type='success')
                else:
                    print("复制成功")
            except Exception as e:
                if main_window and hasattr(main_window, 'tishi'):
                    main_window.tishi.showMessage("复制失败", type='error')
                else:
                    print("复制失败")

    def set_ai_info(self, model, duration_ms, estimated_tokens):
        self._ai_info_model = model
        self._ai_info_duration_ms = duration_ms
        self._ai_info_estimated_tokens = estimated_tokens

        has_info = bool(model) and duration_ms is not None
        if has_info and self.toPlainText().strip():
            tip = f"模型：{model}\n耗时：{duration_ms}ms"
            if estimated_tokens is not None:
                tip += f"\n预估 Token：{estimated_tokens}"
            self.ai_info_button.setToolTip(tip)
            self.ai_info_button.show()
        else:
            self.ai_info_button.hide()
        self._update_action_buttons_positions()

    def clear_ai_info(self):
        self._ai_info_model = None
        self._ai_info_duration_ms = None
        self._ai_info_estimated_tokens = None
        self.ai_info_button.hide()
        self._update_action_buttons_positions()

    def _on_ai_info(self):
        model = self._ai_info_model
        duration_ms = self._ai_info_duration_ms
        estimated_tokens = self._ai_info_estimated_tokens
        if not model or duration_ms is None:
            return

        parts = [f"模型：{model}", f"耗时：{duration_ms}ms"]
        if estimated_tokens is not None:
            parts.append(f"预估 Token：{estimated_tokens}")
        text = "\n".join(parts)

        popup = InfoTooltipPopup.get_instance()
        popup.set_content(title="AI 翻译详情", section_title="完成信息", body=text, icon_path="src/ziyuan/ai.svg")
        popup.toggle_near(self.ai_info_button)
    
    def setPlainText(self, text):
        """重写文本设置方法"""
        super().setPlainText(text)
        # 文本改变时更新按钮状态
        if self._is_loading:
            self.copy_button.hide()
            self.copy_button.setEnabled(False)
        else:
            has_text = bool((text or "").strip())
            if has_text:
                self.copy_button.show()
                self.copy_button.setEnabled(True)
            else:
                self.copy_button.hide()
                self.copy_button.setEnabled(False)

        if not (text or "").strip():
            self.ai_info_button.hide()
        self._update_action_buttons_positions()
    
    def wheelEvent(self, event):
        """重写滚轮事件，确保按钮受滚动影响"""
        super().wheelEvent(event)
        self.copy_button.raise_()  # 确保按钮始终在最上层
        self.ai_info_button.raise_()


class AITranslatingStatusBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("aiStatusBar")
        self.setVisible(False)
        self.setFixedHeight(30)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

        self._model = None
        self._phase = None
        self._estimated_tokens = None
        self._dots = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self.info_button = QPushButton("")
        self.info_button.setFixedSize(18, 18)
        self.info_button.setObjectName("floatingIconButton")
        self.info_button.setIcon(QIcon("src/ziyuan/info.svg"))
        self.info_button.setIconSize(QSize(14, 14))
        self.info_button.clicked.connect(self._show_info)
        self.info_button.setToolTip("AI 翻译详情")
        layout.addWidget(self.info_button)

        self.sparkles = QLabel("✨")
        self.sparkles.setObjectName("aiStatusSparkles")
        layout.addWidget(self.sparkles)

        self.label = QLabel("")
        self.label.setObjectName("aiStatusText")
        self.label.setMinimumWidth(0)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.label, 1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        

    def set_context(self, model: str, phase: str, estimated_tokens):
        self._model = model
        self._phase = phase
        self._estimated_tokens = estimated_tokens
        self._update_label()

    def start(self):
        self._dots = ""
        self.setVisible(True)
        if not self._timer.isActive():
            self._timer.start(550)
        self._update_label()

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
        self.setVisible(False)

    def _tick(self):
        self._dots = self._dots + "。" if len(self._dots) < 3 else ""
        self._update_label()

    def _update_label(self):
        model = (self._model or "").strip() or "模型"
        self._full_text = f"正在调用AI模型-{model}翻译，请稍候{self._dots}"
        self._apply_elided_text()

    def _apply_elided_text(self):
        full_text = getattr(self, "_full_text", "")
        if not full_text:
            self.label.setText("")
            return
        fm = self.label.fontMetrics()
        self.label.setText(fm.elidedText(full_text, Qt.ElideRight, max(0, self.label.width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elided_text()

    def _show_info(self):
        phase = self._phase or "正在等待服务端响应"
        if self._estimated_tokens is None:
            tokens = "Token 数：未知"
        else:
            tokens = f"Token 数：{self._estimated_tokens}"
        popup = InfoTooltipPopup.get_instance()
        popup.set_content(title="AI 翻译详情", section_title="翻译中", body=f"当前状态：{phase}\n{tokens}", icon_path="src/ziyuan/ai.svg")
        popup.toggle_near(self.info_button)


class InfoTooltipPopup(QFrame):
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = InfoTooltipPopup()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame(self)
        self.card.setObjectName("infoCard")
        self.card.setMinimumWidth(240)
        self.card.setMaximumWidth(280)

        self._shadow = QGraphicsDropShadowEffect(self.card)
        self._shadow.setBlurRadius(22)
        self._shadow.setOffset(0, 8)
        self._shadow.setColor(QColor(0, 0, 0, 160))
        self.card.setGraphicsEffect(self._shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 16)
        header.addWidget(self.icon_label)

        self.title_label = QLabel("")
        self.title_label.setObjectName("infoTitle")
        header.addWidget(self.title_label, 1)

        self.close_button = QPushButton("")
        self.close_button.setFixedSize(18, 18)
        self.close_button.setIcon(QIcon("src/ziyuan/close-white.svg"))
        self.close_button.setIconSize(QSize(14, 14))
        self.close_button.setObjectName("infoTooltipCloseButton")
        self.close_button.clicked.connect(self.hide)
        header.addWidget(self.close_button)

        card_layout.addLayout(header)

        self.section_title_label = QLabel("")
        self.section_title_label.setObjectName("infoSectionTitle")
        card_layout.addWidget(self.section_title_label)

        self.body_label = QLabel("")
        self.body_label.setObjectName("infoBody")
        self.body_label.setWordWrap(True)
        self.body_label.setTextFormat(Qt.RichText)
        card_layout.addWidget(self.body_label)

        outer.addWidget(self.card)

    def apply_theme(self, theme_name: str):
        is_dark = theme_name == "dark"
        if hasattr(self, "_shadow") and self._shadow:
            self._shadow.setColor(QColor(0, 0, 0, 160 if is_dark else 80))

        palette = {
            "dark": {
                "card": "rgba(24, 24, 26, 0.98)",
                "border": "rgba(255, 255, 255, 0.18)",
                "title": "rgba(255, 255, 255, 0.96)",
                "body": "rgba(255, 255, 255, 0.88)",
                "section": "rgba(255, 255, 255, 0.72)",
                "close_hover": "rgba(255, 255, 255, 0.10)",
            },
            "light": {
                "card": "rgba(255, 255, 255, 0.98)",
                "border": "rgba(0, 0, 0, 0.12)",
                "title": "rgba(0, 0, 0, 0.90)",
                "body": "rgba(0, 0, 0, 0.78)",
                "section": "rgba(0, 0, 0, 0.56)",
                "close_hover": "rgba(0, 0, 0, 0.06)",
            },
            "pink": {
                "card": "rgba(255, 245, 248, 0.98)",
                "border": "rgba(255, 105, 180, 0.28)",
                "title": "rgba(51, 51, 51, 0.92)",
                "body": "rgba(51, 51, 51, 0.80)",
                "section": "rgba(51, 51, 51, 0.60)",
                "close_hover": "rgba(255, 105, 180, 0.16)",
            },
        }
        c = palette.get(theme_name, palette["dark"])
        self.setStyleSheet(
            """
            QFrame#infoCard {
                background-color: %s;
                border: 1px solid %s;
                border-radius: 14px;
            }
            QLabel#infoTitle {
                color: %s;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#infoBody {
                color: %s;
                font-size: 12px;
            }
            QLabel#infoSectionTitle {
                color: %s;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#infoTooltipCloseButton {
                background: transparent;
                border: none;
            }
            QPushButton#infoTooltipCloseButton:hover {
                background-color: %s;
                border-radius: 8px;
            }
            """
            % (
                c["card"],
                c["border"],
                c["title"],
                c["body"],
                c["section"],
                c["close_hover"],
            )
        )

    def set_content(self, title: str, body: str, icon_path: str = "src/ziyuan/ai.svg", section_title: str = ""):
        self.title_label.setText(title or "")
        self.section_title_label.setText(section_title or "")
        self.section_title_label.setVisible(bool((section_title or "").strip()))

        safe_body = body or ""
        html_lines = []
        for raw_line in safe_body.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            if "：" in line:
                k, v = line.split("：", 1)
                html_lines.append(
                    f"<div style='margin: 2px 0;'>"
                    f"<span style='font-weight: 700;'>{html.escape(k)}：</span>"
                    f"<span>{html.escape(v.strip())}</span>"
                    f"</div>"
                )
            elif ":" in line:
                k, v = line.split(":", 1)
                html_lines.append(
                    f"<div style='margin: 2px 0;'>"
                    f"<span style='font-weight: 700;'>{html.escape(k)}:</span>"
                    f"<span> {html.escape(v.strip())}</span>"
                    f"</div>"
                )
            else:
                html_lines.append(f"<div style='margin: 2px 0;'>{html.escape(line)}</div>")

        self.body_label.setText("".join(html_lines) if html_lines else "")
        self.icon_label.setPixmap(QIcon(icon_path).pixmap(QSize(16, 16)))
        self.adjustSize()

    def toggle_near(self, anchor: QWidget):
        if self.isVisible():
            self.hide()
            return

        if anchor is None:
            return

        self.adjustSize()
        anchor_pos = anchor.mapToGlobal(QPoint(0, 0))
        x = anchor_pos.x() - (self.width() - anchor.width())
        y = anchor_pos.y() - self.height() - 8
        if y < 10:
            y = anchor_pos.y() + anchor.height() + 8
        self.move(QPoint(x, y))
        self.show()
