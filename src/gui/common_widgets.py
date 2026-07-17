import logging
logger = logging.getLogger(__name__)

from PyQt5.QtWidgets import QPushButton, QTextEdit
from PyQt5.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QMimeData

from .dialog_utils import build_menu_stylesheet
from .icon_provider import themed_icon


class FuDongAnNiu(QPushButton):
    """浮动按钮类"""
    def __init__(self, icon_path, tooltip="", parent=None):
        super().__init__(parent)
        self.setIcon(themed_icon("copy"))
        self.setToolTip(tooltip)
        self.setFixedSize(28, 28)
        self.setIconSize(QSize(16, 16))
        self.setObjectName("floatingIconButton")
        
        # 设置无边框和透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 建动画
        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(150)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)


class ShuRuKuang(QTextEdit):
    """带计数的输入框"""
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(300)  # 设置最小高度
        
        # 设置接受纯文本
        self.setAcceptRichText(False)
        
        # 设置右键菜单样式
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    def _show_context_menu(self, pos):
        """显示自定义右键菜单"""
        menu = self.createStandardContextMenu()
        
        # 清除原有菜单项
        menu.clear()
        
        # 添加自定义菜单项
        actions = [
            ('撤销', 'Ctrl+Z'),
            ('重做', 'Ctrl+Y'),
            (None, None),
            ('剪切', 'Ctrl+X'),
            ('复制', 'Ctrl+C'),
            ('粘贴', 'Ctrl+V'),
            ('删除', 'Del'),
            (None, None),
            ('全选', 'Ctrl+A'),
            (None, None),
            ('大佐翻译官', None),
            ('作者: Achord', None),
        ]

        for text, shortcut in actions:
            if text is None:
                menu.addSeparator()
            else:
                action = menu.addAction(text)
                if shortcut:
                    action.setShortcut(shortcut)
                if text in {"大佐翻译官", "作者: Achord"}:
                    action.setEnabled(False)
        
        menu.setStyleSheet(build_menu_stylesheet(self))
        
        # 连接菜单项动作
        menu.triggered.connect(lambda action: self._handle_menu_action(action.text()))
        
        menu.exec_(self.mapToGlobal(pos))
    
    def _handle_menu_action(self, action_text):
        """处理菜单项点击事件"""
        action_map = {
            "撤销": self.undo,
            "重做": self.redo,
            "剪切": self.cut,
            "复制": self.copy,
            "粘贴": self.paste,
            "删除": lambda: self.textCursor().removeSelectedText(),
            "全选": self.selectAll,
        }

        if action_text in action_map:
            action_map[action_text]()
    
    def insertFromMimeData(self, source):
        """重写粘贴处理，只接受纯文本"""
        if source.hasText():
            # 获取纯文本内容
            text = source.text()
            # 插入纯文本
            self.insertPlainText(text)
    
    def canInsertFromMimeData(self, source) -> bool:
        """判断是否可以插入内容"""
        # 只允许纯文本
        return source.hasText()
    
    def createMimeDataFromSelection(self):
        """创建选中内容的 MIME 数据"""
        mime = super().createMimeDataFromSelection()
        if mime:
            # 确保只包含纯文本
            text = mime.text()
            new_mime = QMimeData()
            new_mime.setText(text)
            return new_mime
        return mime
