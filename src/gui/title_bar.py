import os

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QDialog, QVBoxLayout, QFrame
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt, QSize, QUrl
from PyQt5.QtGui import QDesktopServices, QIcon, QPixmap, QPainter, QPainterPath, QColor
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply, QSslSocket

from ..version import APP_VERSION


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent
        self.setWindowTitle("关于")
        self.setFixedSize(560, 500)
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
        info_layout.addWidget(self._build_info_row("src/ziyuan/about-author.svg", "作者：Achord"))
        info_layout.addWidget(self._build_info_row("src/ziyuan/about-phone.svg", "Tel: 13160235855"))
        info_layout.addWidget(
            self._build_info_row("src/ziyuan/about-mail.svg", "Email: <a href='mailto:achordchan@gmail.com'>achordchan@gmail.com</a>")
        )
        info_layout.addWidget(self._build_info_row("src/ziyuan/about-version.svg", f"版本：v{APP_VERSION}"))
        info_layout.addWidget(self._build_info_row("src/ziyuan/about-license.svg", "许可：MIT License"))
        card_layout.addLayout(info_layout)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(12)
        actions_layout.addWidget(self._build_action_button("src/ziyuan/about-link.svg", "项目地址", "https://gitee.com/Achordchan/dazuofanyiguan"))
        actions_layout.addWidget(self._build_action_button("src/ziyuan/about-link.svg", "问题反馈", "https://gitee.com/Achordchan/dazuofanyiguan/issues"))
        card_layout.addLayout(actions_layout)

        layout.addWidget(card)
        self._apply_style()
        self._load_avatar("src/ziyuan/头像.jpg")

    def _build_info_row(self, icon_path: str, text: str):
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        icon_label = QLabel()
        icon_label.setObjectName("aboutIcon")
        icon_label.setPixmap(QIcon(icon_path).pixmap(QSize(16, 16)))
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

    def _build_action_button(self, icon_path: str, text: str, url: str):
        button = QPushButton(text)
        button.setObjectName("aboutLinkButton")
        button.setIcon(QIcon(icon_path))
        button.setIconSize(QSize(14, 14))
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        return button

    def _apply_style(self):
        theme_name = "dark"
        if self._parent and hasattr(self._parent, "config"):
            theme_name = self._parent.config.get("theme", "dark")

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
        
        # 图标和标题
        icon_label = QLabel()
        icon_label.setPixmap(QIcon("src/ziyuan/ai.svg").pixmap(QSize(20, 20)))
        layout.addWidget(icon_label)
        
        # 创建标题和About按钮
        title_label = QLabel("大佐翻译官v1 - 开源AI翻译助手")
        about_btn = QPushButton("About")  # 改为更完整的中文标题
        about_btn.setFixedSize(70, 24)  # 调整宽度以适应新文本
        about_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #2196F3;
                font-size: 12px;
                font-weight: 500;
                padding: 2px 8px;
            }
            QPushButton:hover {
                color: #64B5F6;
                text-decoration: underline;
            }
            QPushButton:pressed {
                color: #1976D2;
            }
            QPushButton[darkMode="true"] {
                color: #90CAF9;
            }
            QPushButton[darkMode="true"]:hover {
                color: #BBDEFB;
            }
            QPushButton[darkMode="true"]:pressed {
                color: #64B5F6;
            }
        """)
        
        def show_about():
            dialog = AboutDialog(self.parent)
            dialog.exec_()
            
        about_btn.clicked.connect(show_about)
        layout.addWidget(title_label)
        layout.addWidget(about_btn)
        title_label.setStyleSheet("")
        layout.addWidget(title_label)
        layout.addStretch()
        
        # 添加工具按钮
        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(QIcon("src/ziyuan/settings.svg"))
        self.settings_btn.setToolTip("设置")
        self.settings_btn.clicked.connect(self.parent._on_settings)
        
        # 将历史记录按钮改为迷你模式按钮
        mini_mode_btn = QPushButton()
        mini_mode_btn.setIcon(QIcon(os.path.join(self.parent.resource_dir, "mini_mode.svg")))
        mini_mode_btn.setToolTip("切换到迷你窗口模式")
        mini_mode_btn.clicked.connect(lambda: self.parent._toggle_mini_mode(True, show_hint=True))
        
        self.theme_btn = QPushButton()
        self.theme_btn.setIcon(QIcon("src/ziyuan/theme.svg"))
        self.theme_btn.setToolTip("切换主题")
        self.theme_btn.clicked.connect(self.parent._on_theme_change)
        
        # 最小化按钮
        min_btn = QPushButton("一")
        min_btn.setFixedSize(32, 32)
        min_btn.setToolTip("最小化")
        min_btn.clicked.connect(self.parent.showMinimized)
        
        # 最大化/还原按钮
        self.max_btn = QPushButton("口")
        self.max_btn.setFixedSize(32, 32)
        self.max_btn.setToolTip("最大化")
        self.max_btn.clicked.connect(self._toggle_maximize)
        
        # 关闭按钮
        close_btn = QPushButton("×")
        close_btn.setFixedSize(32, 32)
        close_btn.setToolTip("关闭")
        close_btn.clicked.connect(self.parent.close)
        
        # 设置工具按钮大小
        for btn in (self.settings_btn, mini_mode_btn, self.theme_btn):
            btn.setFixedSize(28, 28)
            btn.setIconSize(QSize(16, 16))
        
        # 加载有按布局
        layout.addWidget(self.settings_btn)
        layout.addWidget(mini_mode_btn)
        layout.addWidget(self.theme_btn)
        layout.addWidget(min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(close_btn)

        self.apply_icons(self.parent.config.get("theme", "dark") if hasattr(self.parent, "config") else "dark")

    def apply_icons(self, theme_name: str):
        tone = "white" if theme_name == "dark" else "black"
        if theme_name == "pink":
            settings_icon = "src/ziyuan/settings-pink.svg"
            theme_icon = "src/ziyuan/theme-pink.svg"
        else:
            settings_icon = f"src/ziyuan/settings-{tone}.svg"
            theme_icon = f"src/ziyuan/theme-{tone}.svg"

        if hasattr(self, "settings_btn"):
            self.settings_btn.setIcon(QIcon(settings_icon if os.path.exists(settings_icon) else "src/ziyuan/settings.svg"))
        if hasattr(self, "theme_btn"):
            self.theme_btn.setIcon(QIcon(theme_icon if os.path.exists(theme_icon) else "src/ziyuan/theme.svg"))
    
    def _toggle_maximize(self):
        """切换最大化/还原状态"""
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.max_btn.setText("口")
            self.max_btn.setToolTip("最大化")
        else:
            self.parent.showMaximized()
            self.max_btn.setText("❐")
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
