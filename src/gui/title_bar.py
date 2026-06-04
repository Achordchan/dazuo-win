import os

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QDialog, QVBoxLayout, QFrame
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt, QSize, QUrl
from PyQt5.QtGui import QDesktopServices, QIcon, QPixmap, QPainter, QPainterPath, QColor
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply, QSslSocket

from .dialog_utils import build_icon_button_stylesheet, build_link_button_stylesheet, get_dialog_palette, to_rgba
from .icon_provider import themed_icon, resource_path
from . import window_geometry as _window_geometry
from ..version import APP_VERSION


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent
        self.setWindowTitle("关于")
        self.setFixedSize(620, 680)
        self.setObjectName("aboutDialog")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("aboutCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(16)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 90 if self._theme_name() == "dark" else 34))
        card.setGraphicsEffect(shadow)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(16)

        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(76, 76)
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setObjectName("aboutAvatar")
        header.addWidget(self.avatar_label, alignment=Qt.AlignTop)

        header_text = QVBoxLayout()
        header_text.setContentsMargins(0, 2, 0, 0)
        header_text.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        title_label = QLabel("大佐翻译官")
        title_label.setObjectName("aboutTitle")
        title_row.addWidget(title_label)
        version_badge = QLabel(f"v{APP_VERSION}")
        version_badge.setObjectName("aboutVersionBadge")
        title_row.addWidget(version_badge)
        title_row.addStretch()
        header_text.addLayout(title_row)

        subtitle_label = QLabel("开源 AI 翻译助手")
        subtitle_label.setObjectName("aboutSubtitle")
        header_text.addWidget(subtitle_label)

        summary_label = QLabel("提供多翻译服务接入、快捷呼出和内置翻译引擎能力。")
        summary_label.setObjectName("aboutSummary")
        summary_label.setWordWrap(True)
        header_text.addWidget(summary_label)
        header.addLayout(header_text, 1)
        card_layout.addLayout(header)

        divider = QFrame()
        divider.setObjectName("aboutDivider")
        divider.setFrameShape(QFrame.HLine)
        card_layout.addWidget(divider)

        project_section = self._build_section(
            "项目信息",
            [
                ("author", "作者", "Achord"),
                ("version", "当前版本", f"v{APP_VERSION}"),
                ("license", "软件许可", "MIT License"),
            ],
        )
        card_layout.addWidget(project_section)

        contact_section = self._build_section(
            "联系与反馈",
            [
                ("phone", "电话", "13160235855"),
                ("mail", "邮箱", "<a href='mailto:achordchan@gmail.com'>achordchan@gmail.com</a>"),
            ],
        )
        card_layout.addWidget(contact_section)

        engine_section = self._build_section(
            "第三方组件",
            [
                ("license", "内置引擎", "Powered by DeepLX / OwO Network"),
                ("license", "许可声明", "MIT License，Copyright (c) 2022 OwO Network Limited"),
            ],
        )
        card_layout.addWidget(engine_section)

        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 2, 0, 0)
        actions_layout.setSpacing(10)
        actions_layout.addWidget(self._build_action_button("link", "项目地址", "https://gitee.com/Achordchan/dazuofanyiguan"))
        actions_layout.addWidget(self._build_action_button("link", "问题反馈", "https://gitee.com/Achordchan/dazuofanyiguan/issues"))
        actions_layout.addStretch()
        close_button = QPushButton("关闭")
        close_button.setObjectName("aboutCloseButton")
        close_button.setCursor(Qt.PointingHandCursor)
        close_button.clicked.connect(self.accept)
        actions_layout.addWidget(close_button)
        card_layout.addLayout(actions_layout)

        layout.addWidget(card)
        self._apply_style()
        self._disable_context_menus()
        self._load_avatar(resource_path("头像.jpg"))

    def _build_section(self, title: str, rows: list[tuple[str, str, str]]):
        section = QFrame()
        section.setObjectName("aboutSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)
        title_label = QLabel(title)
        title_label.setObjectName("aboutSectionTitle")
        layout.addWidget(title_label)
        for icon_name, label, value in rows:
            layout.addWidget(self._build_info_row(icon_name, label, value))
        return section

    def _build_info_row(self, icon_name: str, label: str, value: str):
        row_widget = QWidget()
        row_widget.setMinimumHeight(26)
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(9)
        icon_label = QLabel()
        icon_label.setObjectName("aboutIcon")
        icon_label.setPixmap(themed_icon(icon_name, self._theme_name(), "secondary").pixmap(QSize(16, 16)))
        icon_label.setFixedSize(20, 20)
        row.addWidget(icon_label, alignment=Qt.AlignTop)

        label_widget = QLabel(label)
        label_widget.setObjectName("aboutInfoLabel")
        label_widget.setFixedWidth(76)
        label_widget.setMinimumHeight(22)
        row.addWidget(label_widget, alignment=Qt.AlignTop)

        if "<a " in value and "style=" not in value:
            value = value.replace(
                "<a ",
                f"<a style='color:{get_dialog_palette(self._parent).primary}; text-decoration:none;' ",
                1,
            )
        text_label = QLabel(value)
        text_label.setObjectName("aboutInfoValue")
        text_label.setTextFormat(Qt.RichText)
        text_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        text_label.setOpenExternalLinks(True)
        text_label.setWordWrap(True)
        text_label.setMinimumHeight(22)
        row.addWidget(text_label, 1, alignment=Qt.AlignTop)
        return row_widget

    def _build_action_button(self, icon_name: str, text: str, url: str):
        button = QPushButton(text)
        button.setObjectName("aboutLinkButton")
        button.setIcon(themed_icon(icon_name, self._theme_name(), "primary"))
        button.setIconSize(QSize(14, 14))
        button.setMinimumWidth(108)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        return button

    def _theme_name(self):
        if self._parent and hasattr(self._parent, "config"):
            return self._parent.config.get("theme", "dark")
        return "dark"

    def _disable_context_menus(self):
        self.setContextMenuPolicy(Qt.NoContextMenu)
        for child in self.findChildren(QWidget):
            child.setContextMenuPolicy(Qt.NoContextMenu)

    def _apply_style(self):
        theme_name = self._theme_name()
        palette = get_dialog_palette(self._parent)
        soft_primary = to_rgba(palette.primary, 0.14 if theme_name != "dark" else 0.18)
        soft_border = to_rgba(palette.primary, 0.20 if theme_name != "dark" else 0.28)
        muted_surface = palette.surface_alt if theme_name == "dark" else palette.background
        link_hover = palette.secondary_hover
        self.setStyleSheet(
            f"#aboutDialog {{ background: {palette.background}; }}"
            f"#aboutCard {{ background: {palette.surface}; border: 1px solid {palette.border}; border-radius: 16px; }}"
            f"#aboutAvatar {{ background: {soft_primary}; border-radius: 38px; border: 1px solid {soft_border}; }}"
            f"#aboutTitle {{ color: {palette.text}; font-size: 24px; font-weight: 700; padding: 0; }}"
            f"#aboutVersionBadge {{ background: {soft_primary}; color: {palette.primary}; border: 1px solid {soft_border}; border-radius: 10px; padding: 2px 9px; font-size: 14px; font-weight: 700; }}"
            f"#aboutSubtitle {{ color: {palette.text}; font-size: 15px; font-weight: 600; padding: 0; }}"
            f"#aboutSummary {{ color: {palette.text_secondary}; font-size: 14px; padding: 0; }}"
            f"#aboutDivider {{ color: {palette.border}; background: {palette.border}; max-height: 1px; border: none; }}"
            f"#aboutSection {{ background: {muted_surface}; border: 1px solid {palette.border}; border-radius: 12px; }}"
            f"#aboutSectionTitle {{ color: {palette.text_secondary}; font-size: 14px; font-weight: 700; padding: 0; }}"
            f"#aboutInfoLabel {{ color: {palette.text_secondary}; font-size: 14px; padding: 0; }}"
            f"#aboutInfoValue {{ color: {palette.text}; font-size: 15px; padding: 0; }}"
            f"#aboutInfoValue a {{ color: {palette.primary}; text-decoration: none; }}"
            f"#aboutLinkButton {{ background: transparent; color: {palette.primary}; border: 1px solid {soft_border}; border-radius: 9px; min-height: 32px; padding: 0 12px; text-align: left; font-size: 14px; font-weight: 600; }}"
            f"#aboutLinkButton:hover {{ background: {link_hover}; }}"
            f"#aboutCloseButton {{ background: {palette.primary}; color: #FFFFFF; border: 1px solid {palette.primary}; border-radius: 9px; min-width: 76px; min-height: 32px; padding: 0 16px; font-size: 14px; font-weight: 600; }}"
            f"#aboutCloseButton:hover {{ background: {palette.primary_hover}; border-color: {palette.primary_hover}; }}"
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
        self.title_label.setStyleSheet(f"color: {palette.text}; font-size: 16px; font-weight: 500;")
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
            _window_geometry.begin_move(self.parent)
            self.parent._is_dragging = True
            event.accept()
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if self.parent._is_dragging and event.buttons() == Qt.LeftButton:
            position = event.globalPos() - self.parent._drag_start_pos
            self.parent.move(_window_geometry.constrain_move_position(self.parent, position))
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        self.parent._is_dragging = False
        _window_geometry.end_move(self.parent)
        if hasattr(self.parent, "_schedule_save_window_geometry"):
            self.parent._schedule_save_window_geometry()
        event.accept()
    
    def mouseDoubleClickEvent(self, event):
        """鼠标双击事件"""
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()
