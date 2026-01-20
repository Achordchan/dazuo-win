"""状态指示器组件"""
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPainter, QColor, QPen

class ZhuangTaiZhiShiQi(QWidget):
    """状态指示器组件"""
    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self._compact = compact
        self.setFixedHeight(24 if compact else 28)
        
        # 创建布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6 if compact else 8)
        
        # 状态指示圆点
        self.status_dot = QWidget()
        self.status_dot.setObjectName("serviceStatusDot")
        self.status_dot.setFixedSize(8, 8)
        layout.addWidget(self.status_dot)
        
        # 状态文本
        self.status_label = QLabel("服务正常")
        self.status_label.setObjectName("serviceStatusText")
        layout.addWidget(self.status_label)
        
        # 重试按钮（默认隐藏）
        self.retry_button = QPushButton("重试")
        self.retry_button.setFixedSize(60, 24)
        self.retry_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.retry_button.hide()
        layout.addWidget(self.retry_button)
        
        if not compact:
            layout.addStretch()
        
        # 设置默认状态
        self.set_status("normal")
    
    def set_status(self, status: str, message: str = None):
        """设置状态
        
        Args:
            status: 状态类型 ("normal", "error")
            message: 可选的状态消息
        """
        if status == "normal":
            self.status_dot.setStyleSheet("""
                background-color: #4CAF50;
                border-radius: 4px;
            """)
            self.status_label.setText(message or "服务正常")
            self.status_label.setStyleSheet("color: #4CAF50;")
            self.retry_button.hide()
        else:
            self.status_dot.setStyleSheet("""
                background-color: #F44336;
                border-radius: 4px;
            """)
            self.status_label.setText(message or "服务异常")
            self.status_label.setStyleSheet("color: #F44336;")
            self.retry_button.show()