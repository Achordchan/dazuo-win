from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon

class BiaoTiLan(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        
        # 创建水平布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)
        
        # 添加图标
        icon_label = QLabel()
        icon_label.setPixmap(QIcon("src/ziyuan/logo.svg").pixmap(QSize(20, 20)))
        layout.addWidget(icon_label)
        
        # 添加标题
        title_label = QLabel("大佐翻译官")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        layout.addWidget(title_label)
        
        layout.addStretch()
        
        # 添加历史记录按钮
        history_button = QPushButton()
        history_button.setIcon(QIcon("src/ziyuan/history.svg"))
        history_button.setToolTip("历史记录")
        history_button.setFixedSize(28, 28)
        history_button.setIconSize(QSize(16, 16))
        history_button.clicked.connect(self.parent._on_history)
        history_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        layout.addWidget(history_button)
        
        # 添加设置按钮
        settings_button = QPushButton()
        settings_button.setIcon(QIcon("src/ziyuan/settings.svg"))
        settings_button.setToolTip("设置")
        settings_button.setFixedSize(28, 28)
        settings_button.setIconSize(QSize(16, 16))
        settings_button.clicked.connect(self.parent._on_settings)
        settings_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        layout.addWidget(settings_button)
        
        # 添加最小化按钮
        min_button = QPushButton()
        min_button.setIcon(QIcon("src/ziyuan/minimize.svg"))
        min_button.setToolTip("最小化")
        min_button.setFixedSize(28, 28)
        min_button.setIconSize(QSize(16, 16))
        min_button.clicked.connect(self.parent.showMinimized)
        min_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        layout.addWidget(min_button)
        
        # 添加关闭按钮
        close_button = QPushButton()
        close_button.setIcon(QIcon("src/ziyuan/close.svg"))
        close_button.setToolTip("关闭")
        close_button.setFixedSize(28, 28)
        close_button.setIconSize(QSize(16, 16))
        close_button.clicked.connect(self.parent.close)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(255, 0, 0, 0.2);
            }
        """)
        layout.addWidget(close_button)
        
        # 添加主题切换按钮
        theme_button = QPushButton()
        theme_button.setIcon(QIcon("src/ziyuan/theme.svg"))
        theme_button.setToolTip("切换主题")
        theme_button.setFixedSize(28, 28)
        theme_button.setIconSize(QSize(16, 16))
        theme_button.clicked.connect(self.parent._on_theme_change)
        theme_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        layout.addWidget(theme_button)
        
        # 设置鼠标跟踪
        self.setMouseTracking(True)