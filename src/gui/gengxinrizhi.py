from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton
from PyQt5.QtCore import Qt
import os

from .themes import ThemeManager
from .dialog_utils import install_chinese_context_menu

class GengXinRiZhi(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("更新日志")
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowStaysOnTopHint)
        self.setModal(True)
        self.resize(600, 400)
        self.setObjectName("changelogDialog")
        
        # 创建布局
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # 创建文本浏览器
        self.text_browser = QTextBrowser()
        self.text_browser.setObjectName("changelogBrowser")
        self.text_browser.setOpenExternalLinks(True)
        install_chinese_context_menu(self.text_browser)

        if parent is not None and hasattr(parent, "config"):
            theme_key = parent.config.get("theme", "dark")
            theme_map = {
                "dark": "深色主题",
                "light": "浅色主题",
                "pink": "粉色主题",
            }
            display_name = theme_map.get(theme_key, "深色主题")
            self.setStyleSheet(ThemeManager.get_theme_style(display_name))
        
        # 读��更新日志文件
        changelog_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ziyuan', 'changelog.md')
        if os.path.exists(changelog_path):
            with open(changelog_path, 'r', encoding='utf-8') as f:
                changelog_content = f.read()
            self.text_browser.setMarkdown(changelog_content)
        
        # 创建确定按钮
        self.ok_button = QPushButton("确定")
        self.ok_button.setObjectName("changelogOk")
        self.ok_button.setFixedHeight(36)
        self.ok_button.clicked.connect(self.accept)
        
        # 添加组件到布局
        layout.addWidget(self.text_browser)
        layout.addWidget(self.ok_button, 0, Qt.AlignHCenter)
        
        self.setLayout(layout)
    
    def showEvent(self, event):
        """重写显示事件，确保窗口显示在前面"""
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        
    def closeEvent(self, event):
        """重写关闭事件，确保正确关闭"""
        self.accept()
        event.accept()
