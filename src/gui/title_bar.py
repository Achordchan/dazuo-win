import os

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QDialog, QVBoxLayout, QFrame
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt, QSize, QUrl
from PyQt5.QtGui import QDesktopServices, QIcon, QPixmap, QPainter, QPainterPath, QColor
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply, QSslSocket

from .dialog_utils import build_icon_button_stylesheet, build_link_button_stylesheet, get_dialog_palette
from .icon_provider import themed_icon, resource_path
from ..version import APP_VERSION


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent
        self.setWindowTitle("关于")
        self.setFixedSize(560, 530)
        self.setObjectName("aboutDialog")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        card = QFrame()
        card.setObjectName("aboutCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(14)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 40))
        card.setGraphicsEffect(shadow)

        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(88, 88)
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setObjectName("aboutAvatar")
        card_layout.addWidget(self.avatar_label, alignment=Qt.AlignHCenter)

        title_label = QLabel("大佐翻译官")
        title_label.setObjectName("aboutTitle")
        title_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title_label)

        subtitle_label = QLabel(f"版本：v{APP_VERSION}")
        subtitle_label.setObjectName("aboutMeta")
        subtitle_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(subtitle_label)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(10)
        info_layout.addWidget(self._build_info_row("author", "作者：Achord"))
        info_layout.addWidget(self._build_info_row("phone", "Tel: 13160235855"))
        info_layout.addWidget(
            self._build_info_row("mail", "Email: <a href='mailto:achordchan@gmail.com'>achordchan@gmail.com</a>")
        )
        info_layout.addWidget(self._build_info_row("version", f"版本：v{APP_VERSION}"))
        info_layout.addWidget(self._build_info_row("license", "许可：MIT License"))
        info_layout.addWidget(
            self._build_info_row(
                "license",
                "内置引擎：Powered by DeepLX / OwO Network MIT License",
            )
        )
        card_layout.addLayout(info_layout)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(12)
        actions_layout.addWidget(self._build_action_button("link", "项目地址", "https://gitee.com/Achordchan/dazuofanyiguan"))
        actions_layout.addWidget(self._build_action_button("link", "问题反馈", "https://gitee.com/Achordchan/dazuofanyiguan/issues"))
        card_layout.addLayout(actions_layout)

        layout.addWidget(card)
        self._apply_style()
        self._load_avatar(resource_path("头像.jpg"))

    def _build_info_row(self, icon_name: str, text: str):
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        icon_label = QLabel()
        icon_label.setObjectName("aboutIcon")
        icon_label.setPixmap(themed_icon(icon_name, self._theme_name(), "secondary").pixmap(QSize(16, 16)))
        icon_label.setFixedWidth(20)
        text_label = QLabel(text)
        text_label.setObjectName("aboutInfo")
        text_label.setTextFormat(Qt.RichText)
        text_label.setOpenExternalLinks(True)
        text_label.setWordWrap(False)
        row.addWidget(icon_label)
        row.addWidget(text_label)
        row.addStretch()
        return row_widget

    def _build_action_button(self, icon_name: str, text: str, url: str):
        button = QPushButton(text)
        button.setObjectName("aboutLinkButton")
        button.setIcon(themed_icon(icon_name, self._theme_name(), "primary"))
        button.setIconSize(QSize(14, 14))
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        return button

    def _theme_name(self):
        if self._parent and hasattr(self._parent, "config"):
            return self._parent.config.get("theme", "dark")
        return "dark"

    def _apply_style(self):
        theme_name = self._theme_name()

        palette = {
            "dark": {
                "dialog": "#171d25",
                "card": "#202833",
                "avatar": "#2b3543",
                "text": "#f2f6fb",
                "subtext": "#9fb0c4",
                "accent": "#7ab7ff",
            },
            "light": {
                "dialog": "#f6f8fb",
                "card": "#ffffff",
                "avatar": "#e8eef5",
                "text": "#3a3f45",
                "subtext": "#708090",
                "accent": "#1f7ae0",
            },
            "pink": {
                "dialog": "#fff5f8",
                "card": "#fffafb",
                "avatar": "#f7e7ee",
                "text": "#533846",
                "subtext": "#8e7281",
                "accent": "#cc5c8a",
            },
        }
        c = palette.get(theme_name, palette["dark"])
        self.setStyleSheet(
            f"#aboutDialog {{ background: {c['dialog']}; }}"
            f"#aboutCard {{ background: {c['card']}; border-radius: 16px; }}"
            f"#aboutAvatar {{ background: {c['avatar']}; border-radius: 44px; border: 2px solid {c['card']}; }}"
            f"#aboutTitle {{ color: {c['text']}; font-size: 18px; font-weight: 700; }}"
            f"#aboutMeta {{ color: {c['subtext']}; font-size: 12px; margin-bottom: 6px; }}"
            f"#aboutInfo {{ color: {c['text']}; font-size: 13px; }}"
            f"#aboutLinkButton {{ background: {c['card']}; color: {c['accent']}; border: 1px solid {c['accent']}; border-radius: 10px; min-height: 34px; padding: 0 14px; text-align: left; }}"
            f"#aboutLinkButton:hover {{ background: {c['avatar']}; }}"
        )

    def _load_avatar(self, url: str):
        if os.path.exists(url):
            pix = QPixmap(url)
            if not pix.isNull():
                self._set_avatar_pixmap(pix)
                return

        if not QSslSocket.supportsSsl():
            self._set_placeholder_avatar()
            return
        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_avatar_loaded)
        self._nam.get(QNetworkRequest(QUrl(url)))

    def _on_avatar_loaded(self, reply: QNetworkReply):
        if reply.error() == QNetworkReply.NoError:
            pix = QPixmap()
            pix.loadFromData(reply.readAll())
            self._set_avatar_pixmap(pix)
        else:
            self._set_placeholder_avatar()
        reply.deleteLater()

    def _set_placeholder_avatar(self):
        size = self.avatar_label.width()
        result = QPixmap(size, size)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(0, 161, 111))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, size, size)
        painter.setPen(Qt.white)
        font = painter.font()
        font.setPointSize(24)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(result.rect(), Qt.AlignCenter, "A")
        painter.end()
        self.avatar_label.setPixmap(result)

    def _set_avatar_pixmap(self, pixmap: QPixmap):
        size = self.avatar_label.width()
        scaled = pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        result = QPixmap(size, size)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        self.avatar_label.setPixmap(result)


class BiaoTiLan(QWidget):
    """自定义标题栏"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(40)
        
        # 创建布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(4)
        
        # 创建标题和About按钮
        self.title_label = QLabel("大佐翻译官v1 - 开源AI翻译助手")
        self.about_btn = QPushButton("About")
        self.about_btn.setFixedSize(70, 24)
        
        def show_about():
            dialog = AboutDialog(self.parent)
            dialog.exec_()
            
        self.about_btn.clicked.connect(show_about)
        layout.addWidget(self.title_label)
        layout.addWidget(self.about_btn)
        layout.addStretch()
        
        # 添加工具按钮
        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(themed_icon("settings"))
        self.settings_btn.setToolTip("设置")
        self.settings_btn.clicked.connect(self.parent._on_settings)
        
        # 将历史记录按钮改为迷你模式按钮
        self.mini_mode_btn = QPushButton()
        self.mini_mode_btn.setIcon(themed_icon("mini_mode"))
        self.mini_mode_btn.setToolTip("切换到迷你窗口模式")
        self.mini_mode_btn.clicked.connect(lambda: self.parent._toggle_mini_mode(True, show_hint=True))
        
        self.theme_btn = QPushButton()
        self.theme_btn.setIcon(themed_icon("theme"))
        self.theme_btn.setToolTip("切换主题")
        self.theme_btn.clicked.connect(self.parent._on_theme_change)
        
        # 最小化按钮
        self.min_btn = QPushButton()
        self.min_btn.setFixedSize(32, 32)
        self.min_btn.setToolTip("最小化")
        self.min_btn.clicked.connect(self.parent.showMinimized)
        
        # 最大化/还原按钮
        self.max_btn = QPushButton()
        self.max_btn.setFixedSize(32, 32)
        self.max_btn.setToolTip("最大化")
        self.max_btn.clicked.connect(self._toggle_maximize)
        
        # 关闭按钮
        self.close_btn = QPushButton()
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setToolTip("关闭")
        self.close_btn.clicked.connect(self.parent.close)
        
        # 设置工具按钮大小
        for btn in (self.settings_btn, self.mini_mode_btn, self.theme_btn):
            btn.setFixedSize(28, 28)
            btn.setIconSize(QSize(16, 16))
        
        # 加载有按布局
        layout.addWidget(self.settings_btn)
        layout.addWidget(self.mini_mode_btn)
        layout.addWidget(self.theme_btn)
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

        theme_name = self.parent.config.get("theme", "dark") if hasattr(self.parent, "config") else "dark"
        self.apply_icons(theme_name)
        self.apply_theme(theme_name)

    def apply_theme(self, theme_name: str):
        palette = get_dialog_palette(self.parent)
        self.title_label.setStyleSheet(f"color: {palette.text}; font-size: 14px; font-weight: 500;")
        self.about_btn.setStyleSheet(build_link_button_stylesheet(self.parent))

        for btn in (self.settings_btn, self.mini_mode_btn, self.theme_btn, self.min_btn, self.max_btn):
            btn.setStyleSheet(build_icon_button_stylesheet(self.parent))
            btn.setCursor(Qt.PointingHandCursor)

        self.close_btn.setStyleSheet(build_icon_button_stylesheet(self.parent, danger=True))
        self.close_btn.setCursor(Qt.PointingHandCursor)

        self.min_btn.setStyleSheet(build_icon_button_stylesheet(self.parent))
        self.max_btn.setStyleSheet(build_icon_button_stylesheet(self.parent))
        self.close_btn.setStyleSheet(build_icon_button_stylesheet(self.parent, danger=True))

    def apply_icons(self, theme_name: str):
        if hasattr(self, "settings_btn"):
            self.settings_btn.setIcon(themed_icon("settings", theme_name))
        if hasattr(self, "theme_btn"):
            self.theme_btn.setIcon(themed_icon("theme", theme_name))
        if hasattr(self, "mini_mode_btn"):
            self.mini_mode_btn.setIcon(themed_icon("mini_mode", theme_name))
        if hasattr(self, "min_btn"):
            self.min_btn.setIcon(themed_icon("minimize", theme_name, "secondary"))
            self.min_btn.setIconSize(QSize(15, 15))
        if hasattr(self, "max_btn"):
            icon_name = "restore" if self.parent.isMaximized() else "maximize"
            self.max_btn.setIcon(themed_icon(icon_name, theme_name, "secondary"))
            self.max_btn.setIconSize(QSize(14, 14))
        if hasattr(self, "close_btn"):
            self.close_btn.setIcon(themed_icon("close", theme_name, "danger"))
            self.close_btn.setIconSize(QSize(16, 16))
    
    def _toggle_maximize(self):
        """切换最大化/还原状态"""
        if self.parent.isMaximized():
            self.parent.showNormal()
            theme_name = self.parent.config.get("theme", "dark") if hasattr(self.parent, "config") else "dark"
            self.max_btn.setIcon(themed_icon("maximize", theme_name, "secondary"))
            self.max_btn.setToolTip("最大化")
        else:
            self.parent.showMaximized()
            theme_name = self.parent.config.get("theme", "dark") if hasattr(self.parent, "config") else "dark"
            self.max_btn.setIcon(themed_icon("restore", theme_name, "secondary"))
            self.max_btn.setToolTip("还原")
    
    def mousePressEvent(self, event):
        """标按下事件"""
        if event.button() == Qt.LeftButton:
            self.parent._drag_start_pos = event.globalPos() - self.parent.pos()
            self.parent._is_dragging = True
            event.accept()
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if self.parent._is_dragging and event.buttons() == Qt.LeftButton:
            self.parent.move(event.globalPos() - self.parent._drag_start_pos)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        self.parent._is_dragging = False
        if hasattr(self.parent, "_schedule_save_window_geometry"):
            self.parent._schedule_save_window_geometry()
        event.accept()
    
    def mouseDoubleClickEvent(self, event):
        """鼠标双击事件"""
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()
