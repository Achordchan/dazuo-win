from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QRectF
from PyQt5.QtGui import QPainter, QPainterPath, QColor

class TiShiKuang(QLabel):
    """自定义提示框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        
        # 设置样式
        self.setStyleSheet("""
            QLabel {
                color: white;
                padding: 10px 20px;
                border-radius: 4px;
                background: rgba(0, 0, 0, 0.7);
            }
        """)
        
        # 默认隐藏
        self.hide()
        
        # 创建定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.hide)
        
        # 创建动画
        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(300)
    
    def showMessage(self, message: str, duration: int = 2000, type: str = "info"):
        """显示提示消息
        
        Args:
            message: 提示消息
            duration: 显示时长(毫秒)
            type: 消息类型 (info/success/warning/error)
        """
        # 设置消息
        self.setText(message)
        
        # 调整大小
        self.adjustSize()
        
        # 计算位置
        parent_rect = self.parent.rect()
        x = (parent_rect.width() - self.width()) // 2
        y = parent_rect.height() - self.height() - 20
        
        # 设置动画
        start_pos = QPoint(x, parent_rect.height())
        end_pos = QPoint(x, y)
        
        self.animation.setStartValue(start_pos)
        self.animation.setEndValue(end_pos)
        
        # 根据类型设置样式
        colors = {
            "info": "#2D2D2D",
            "success": "#28a745",
            "warning": "#ffc107",
            "error": "#dc3545"
        }
        color = colors.get(type, colors["info"])
        
        self.setStyleSheet(f"""
            QLabel {{
                color: white;
                padding: 10px 20px;
                border-radius: 4px;
                background: {color};
            }}
        """)
        
        # 显示提示
        self.show()
        self.animation.start()
        
        # 设置定时器
        self.timer.start(duration)
    
    def paintEvent(self, event):
        """重写绘制事件，实现圆角效果"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 创建圆角路径
        path = QPainterPath()
        rect = QRectF(self.rect())  # 将 QRect 转换为 QRectF
        path.addRoundedRect(rect, 4, 4)
        
        # 设置遮罩
        painter.setClipPath(path)
        
        # 调用父类绘制
        super().paintEvent(event) 