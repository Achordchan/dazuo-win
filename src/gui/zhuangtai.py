"""状态指示器组件"""
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QSizePolicy
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPainter, QColor, QPen

from .dialog_utils import get_dialog_palette


class _ElidedStatusLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, text, detail=None):
        self._full_text = str(text or "")
        self._detail_text = str(detail or "")
        self._sync_text()

    def _sync_text(self):
        available_width = max(0, self.width())
        displayed_text = self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, available_width)
        self.setText(displayed_text)
        detail = getattr(self, "_detail_text", "")
        if detail and detail != self._full_text:
            self.setToolTip(self._full_text + "\n" + detail)
        else:
            self.setToolTip(self._full_text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_text()


class ZhuangTaiZhiShiQi(QWidget):
    """状态指示器组件"""
    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self._compact = compact
        self.setFixedHeight(24 if compact else 28)
        self.setMinimumWidth(0)
        if compact:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
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
        self.status_label = _ElidedStatusLabel("未连接")
        self.status_label.setObjectName("serviceStatusText")
        layout.addWidget(self.status_label)
        
        # 重试按钮（默认隐藏）
        self.retry_button = QPushButton("重试")
        self.retry_button.setFixedSize(60, 24)
        self._apply_theme_styles()
        self.retry_button.hide()
        layout.addWidget(self.retry_button)
        
        if not compact:
            layout.addStretch()
        
        # 设置默认状态
        self.set_status("connecting", "未连接")

    def _apply_theme_styles(self):
        palette = get_dialog_palette(self)
        self.retry_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {palette.primary};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 14px;
                min-width: 0;
            }}
            QPushButton:hover {{
                background-color: {palette.primary_hover};
            }}
            QPushButton:pressed {{
                background-color: {palette.progress_end};
            }}
            """
        )
    
    def set_status(self, status: str, message: str = None, detail: str = None):
        """设置状态

        Args:
            status: 状态类型 ("normal", "connecting", "error")
            message: 可选的状态消息（显示在状态栏，过长时自动省略）
            detail: 可选的详细说明（仅显示在鼠标悬停提示中）
        """
        palette = get_dialog_palette(self)
        if status == "normal":
            self.status_dot.setStyleSheet("""
                background-color: #4CAF50;
                border-radius: 4px;
            """)
            self.status_label.set_full_text(message or "服务正常", detail)
            self.status_label.setStyleSheet(f"color: {palette.progress_start};")
            self.retry_button.hide()
        elif status == "connecting":
            self.status_dot.setStyleSheet(f"""
                background-color: {palette.text_secondary};
                border-radius: 4px;
            """)
            self.status_label.set_full_text(message or "正在连接...", detail)
            self.status_label.setStyleSheet(f"color: {palette.text_secondary};")
            self.retry_button.hide()
        else:
            self.status_dot.setStyleSheet("""
                background-color: #F44336;
                border-radius: 4px;
            """)
            self.status_label.set_full_text(message or "服务异常", detail)
            self.status_label.setStyleSheet("color: #F44336;")
            self.retry_button.show()
