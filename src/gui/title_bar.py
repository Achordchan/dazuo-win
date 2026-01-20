import os

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QDialog, QVBoxLayout, QFrame
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt, QSize, QUrl
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QPainterPath, QColor
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply, QSslSocket


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于")
        self.setFixedSize(520, 420)
        self.setObjectName("aboutDialog")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        card = QFrame()
        card.setObjectName("aboutCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(12)

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

        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)
        info_layout.addLayout(self._build_info_row("👤", "作者：Achord"))
        info_layout.addLayout(self._build_info_row("📞", "Tel: 13160235855"))
        info_layout.addLayout(
            self._build_info_row("✉️", "Email: <a href='mailto:achordchan@gmail.com'>achordchan@gmail.com</a>")
        )
        info_layout.addLayout(self._build_info_row("🏷️", "版本：v1.1.0"))
        info_layout.addLayout(self._build_info_row("📄", "许可：MIT License"))
        card_layout.addLayout(info_layout)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(16)
        actions_layout.addLayout(self._build_action_item("🌐", "项目地址", "#"))
        actions_layout.addLayout(self._build_action_item("🛡️", "隐私条款", "#"))
        actions_layout.addLayout(self._build_action_item("📄", "开源协议", "#"))
        actions_layout.addLayout(self._build_action_item("💚", "赞助我", "#"))
        card_layout.addLayout(actions_layout)

        layout.addWidget(card)
        self._apply_style()
        self._load_avatar("src/ziyuan/头像.jpg")

    def _build_info_row(self, icon: str, text: str):
        row = QHBoxLayout()
        row.setSpacing(8)
        icon_label = QLabel(icon)
        icon_label.setObjectName("aboutIcon")
        text_label = QLabel(text)
        text_label.setObjectName("aboutInfo")
        text_label.setTextFormat(Qt.RichText)
        text_label.setOpenExternalLinks(True)
        row.addStretch()
        row.addWidget(icon_label)
        row.addWidget(text_label)
        row.addStretch()
        return row

    def _build_action_item(self, icon: str, text: str, url: str):
        row = QHBoxLayout()
        row.setSpacing(6)
        icon_label = QLabel(icon)
        icon_label.setObjectName("aboutActionIcon")
        link_label = QLabel(f"<a href='{url}'>{text}</a>")
        link_label.setObjectName("aboutAction")
        link_label.setTextFormat(Qt.RichText)
        link_label.setOpenExternalLinks(True)
        row.addStretch()
        row.addWidget(icon_label)
        row.addWidget(link_label)
        row.addStretch()
        return row

    def _apply_style(self):
        self.setStyleSheet(
            "#aboutDialog { background: #f6f8fb; }"
            "#aboutCard { background: #ffffff; border-radius: 16px; }"
            "#aboutAvatar { background: #e8eef5; border-radius: 44px; border: 2px solid #ffffff; }"
            "#aboutIcon { color: #00a16f; font-size: 16px; }"
            "#aboutInfo { color: #3a3f45; font-size: 13px; }"
            "#aboutActionIcon { color: #00a16f; font-size: 14px; }"
            "#aboutAction { color: #1f7ae0; font-size: 12px; }"
            "#aboutAction a { text-decoration: none; }"
            "#aboutAction a:hover { text-decoration: underline; }"
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
        settings_btn = QPushButton()
        settings_btn.setIcon(QIcon("src/ziyuan/settings.svg"))
        settings_btn.setToolTip("设置")
        settings_btn.clicked.connect(self.parent._on_settings)
        
        # 将历史记录按钮改为迷你模式按钮
        mini_mode_btn = QPushButton()
        mini_mode_btn.setIcon(QIcon(os.path.join(self.parent.resource_dir, "mini_mode.svg")))
        mini_mode_btn.setToolTip("切换到迷你窗口模式")
        mini_mode_btn.clicked.connect(lambda: self.parent._toggle_mini_mode(True, show_hint=True))
        
        theme_btn = QPushButton()
        theme_btn.setIcon(QIcon("src/ziyuan/theme.svg"))
        theme_btn.setToolTip("切换主题")
        theme_btn.clicked.connect(self.parent._on_theme_change)
        
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
        for btn in (settings_btn, mini_mode_btn, theme_btn):
            btn.setFixedSize(28, 28)
            btn.setIconSize(QSize(16, 16))
        
        # 加载有按布局
        layout.addWidget(settings_btn)
        layout.addWidget(mini_mode_btn)
        layout.addWidget(theme_btn)
        layout.addWidget(min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(close_btn)
    
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
