from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout, QApplication, QSizePolicy, QLabel
from PyQt5.QtCore import Qt, QPoint, QSize, pyqtSignal, QTimer, QRectF, QEvent
from PyQt5.QtGui import QIcon, QPainter, QColor, QCursor, QPen, QPainterPath, QTextCursor
import logging
from ..shezhi import Config
import asyncio
import os
import pyperclip
import sys

logger = logging.getLogger(__name__)

class MiniChuangKou(QWidget):
    # 添加文本变化信号
    text_changed = pyqtSignal()
    
    # 定义主题映射
    THEME_MAP = {
        "dark": "深色主题",
        "light": "浅色主题",
        "pink": "粉色主题"
    }
    
    # 定义主题样式
    THEMES = {
        "深色主题": {
            "background_color": "#2D2D2D",
            "text_color": "#FFFFFF",
            "border_color": "#404040",
            "hover_border_color": "#505050",
            "focus_border_color": "#0A84FF",
            "scrollbar_background": "#2D2D2D",
            "scrollbar_handle": "#404040",
            "scrollbar_handle_hover": "#505050",
            "button_background": "#2D2D2D",
            "button_border": "#404040",
            "button_hover": "#404040",
            "button_hover_border": "#505050",
            "button_pressed": "#505050"
        },
        "浅色主题": {
            "background_color": "#FFFFFF",
            "text_color": "#000000",
            "border_color": "#E0E0E0",
            "hover_border_color": "#BDBDBD",
            "focus_border_color": "#2196F3",
            "scrollbar_background": "#F5F5F5",
            "scrollbar_handle": "#BDBDBD",
            "scrollbar_handle_hover": "#9E9E9E",
            "button_background": "#FFFFFF",
            "button_border": "#E0E0E0",
            "button_hover": "#F5F5F5",
            "button_hover_border": "#BDBDBD",
            "button_pressed": "#EEEEEE"
        },
        "粉色主题": {
            "background_color": "#FFF0F5",
            "text_color": "#FF1493",
            "border_color": "#FFB6C1",
            "hover_border_color": "#FF69B4",
            "focus_border_color": "#FF1493",
            "scrollbar_background": "#FFF0F5",
            "scrollbar_handle": "#FFB6C1",
            "scrollbar_handle_hover": "#FF69B4",
            "button_background": "#FFF0F5",
            "button_border": "#FFB6C1",
            "button_hover": "#FFE4E1",
            "button_hover_border": "#FF69B4",
            "button_pressed": "#FFB6C1"
        }
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent  # 保存父窗口引用
        
        # 初始化主题变量
        self.current_theme = self.THEMES.get("浅色主题", {})  # 确保有默认主题
        
        # 设置窗口标志
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 初始化变量
        self._drag_pos = None
        self._showing = False
        self._closing = False
        self.config = Config()
        
        # 创建翻译计时器
        self._translate_timer = QTimer(self)
        self._translate_timer.setSingleShot(True)
        self._translate_timer.timeout.connect(self._emit_text_changed)
        
        # 初始化UI
        self._update_current_theme()  # 先更新主题，再初始化UI
        self._init_ui()
        
        # 安装事件过滤器
        self.installEventFilter(self)
        
        # 连接主窗口的主题变化信号
        if self._parent and hasattr(self._parent, 'theme_changed'):
            self._parent.theme_changed.connect(self._on_theme_changed)
        
        # 应用当前主题
        self._apply_theme()
        
        # 设置窗口初始大小 - 但不使用固定大小，允许后续自适应
        size = self.config.get("mini_window_size", {"width": 300, "height": 150})
        self.resize(size["width"], size["height"])
        
        # 设置窗口透明度为85%
        self.setWindowOpacity(0.85)
    
    def _init_ui(self):
        """初始化UI"""
        try:
            # 获取当前主题
            theme = self._get_theme_colors()
            
            # 使用简单明了的布局
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(1, 1, 1, 1)  # 最小边距
            main_layout.setSpacing(1)  # 最小间距
            
            # 创建顶部工具栏 - 优化高度和布局
            title_bar = QWidget()
            title_bar.setFixedHeight(18)  # 略微调整高度
            title_layout = QHBoxLayout(title_bar)
            title_layout.setContentsMargins(3, 0, 3, 0)  # 减少垂直内边距
            title_layout.setSpacing(2)  # 减少元素间距
            
            # 添加简单标签 - 调整样式
            self.title_label = QLabel("大佐翻译官")
            self.title_label.setStyleSheet(f"""
                color: {theme.get('text_color', '#ad921f')}; 
                font-size: 9px;  /* 减小字体 */
                font-weight: bold;
            """)
            title_layout.addWidget(self.title_label)
            
            # 添加弹性空间
            title_layout.addStretch()
            
            # 添加恢复按钮 - 调整为更简洁的样式
            self.restore_btn = QPushButton("▢")  # 使用更小的方框符号
            self.restore_btn.setToolTip("切换到主窗口")
            self.restore_btn.setFixedSize(18, 18)  # 减小按钮尺寸
            self.restore_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {theme.get('text_color', '#FFFFFF')};
                    background-color: transparent;  /* 透明背景 */
                    border: none;  /* 移除边框 */
                    font-size: 9px;  /* 减小字体 */
                    font-weight: bold;
                    padding: 0px;
                    margin: 0px;
                }}
                QPushButton:hover {{
                    color: {theme.get('focus_border_color', '#0A84FF')};  /* 悬停时变色 */
                }}
            """)
            self.restore_btn.clicked.connect(self._switch_to_main)
            title_layout.addWidget(self.restore_btn)
            
            # 添加标题栏到主布局
            main_layout.addWidget(title_bar)
            
            # 创建简单的文本显示区域 - 使用QLabel替代QTextEdit以确保简单显示
            self.output_text = QLabel("翻译结果将显示在这里...")
            self.output_text.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.output_text.setWordWrap(True)
            self.output_text.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            self.output_text.setStyleSheet(f"""
                QLabel {{
                    color: {theme.get('text_color', '#FFFFFF')};
                    background-color: {theme.get('text_background', '#2D2D2D')};
                    padding: 5px;
                    font-size: 12px;
                    border: 1px solid {theme.get('border_color', '#404040')};
                    border-radius: 2px;
                }}
            """)
            self.output_text.setMinimumHeight(30)
            
            # 添加文本区域到主布局
            main_layout.addWidget(self.output_text)
            
            # 设置窗口整体样式
            self.setStyleSheet(f"""
                MiniChuangKou {{
                    background-color: {theme.get('background_color', '#2D2D2D')};
                    border: 1px solid {theme.get('border_color', '#404040')};
                    border-radius: 3px;
                }}
            """)
            
            logger.info("成功初始化Mini窗口UI")
        except Exception as e:
            logger.error(f"初始化Mini窗口UI失败: {e}")
    
    def _update_current_theme(self):
        """更新当前主题"""
        if not self._parent:
            return
            
        try:
            # 重新加载配置
            self.config.load()
            
            # 获取最新的主题设置
            theme_name = self.config.get("theme", "light")
            display_name = self.THEME_MAP.get(theme_name, "浅色主题")
            self.current_theme = self.THEMES.get(display_name, self.THEMES["浅色主题"])
            
            # 根据主题背景色选择图标颜色
            background_color = self.current_theme["background_color"].lower()
            # 深色背景使用白色图标，其他使用黑色图标
            if background_color == "#2d2d2d":
                icon_suffix = "-white"
            else:
                icon_suffix = "-black"
            
            # 该按钮当前使用文本显示，不依赖 maximize-*.svg，避免无意义的缺失告警
            if hasattr(self, "restore_btn") and self.restore_btn:
                self.restore_btn.setText("-")
            
            logger.info(f"Mini窗口更新主题: {theme_name}, 显示名称: {display_name}, 背景色: {background_color}, 图标后缀: {icon_suffix}")
            
        except Exception as e:
            logger.error(f"更新Mini窗口主题失败: {e}")
    
    def _apply_theme(self):
        """应用主题样式"""
        if not self._parent:
            return
            
        # 确保主题是最新的
        self._update_current_theme()
        theme = self.current_theme
            
        # output_text 当前是 QLabel
        text_style = f"""
            QLabel {{
                background-color: {theme["background_color"]};
                color: {theme["text_color"]};
                border: 1px solid {theme["border_color"]};
                border-radius: 3px;
                padding: 5px;
                font-size: 12px;
                font-family: "SimHei", "Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑";
            }}
        """
        self.output_text.setStyleSheet(text_style)
        
        # 设置窗口样式
        self.setStyleSheet(f"""
            MiniChuangKou {{
                background-color: {theme["background_color"]};
                border: 1px solid {theme["border_color"]};
                border-radius: 4px;
            }}
        """)

    def update_opacity(self, opacity: float):
        try:
            self.setWindowOpacity(float(opacity))
        except Exception:
            pass
    
    def start_loading(self):
        """开始加载动画"""
        try:
            # 确保先清空旧文本
            self.output_text.clear()  # 清空任何现有内容
            
            # 使用setText而不是setPlainText
            self.output_text.setText("正在翻译...")
            
            # 显示加载状态
            self._loading = True
            
            logger.info("开始加载动画")
        except Exception as e:
            logger.error(f"开始加载动画失败: {e}")
    
    def stop_loading(self):
        """停止加载动画"""
        try:
            # 停止加载状态
            self._loading = False
            
            logger.info("停止加载动画")
        except Exception as e:
            logger.error(f"停止加载动画失败: {e}")
    
    def _adjust_window_size(self):
        """根据内容自动调整窗口大小"""
        try:
            # 获取文本内容
            text = self.output_text.toPlainText()
            line_count = len(text.split('\n'))
            
            if line_count <= 1:
                # 单行文本使用简单固定尺寸
                self.resize(300, 60)  # 固定宽高，确保可见
                return
            
            # 以下是多行文本的处理逻辑
            # 获取文本文档尺寸
            doc = self.output_text.document()
            doc_height = doc.size().height()
            doc_width = doc.idealWidth()
            
            # 计算所需的额外空间
            toolbar_height = 20  # 顶部工具栏高度
            vertical_padding = 30  # 垂直方向的内边距
            horizontal_padding = 30  # 水平方向的内边距
            
            # 计算理想的窗口高度和宽度
            ideal_height = doc_height + vertical_padding
            ideal_width = max(250, doc_width + horizontal_padding)
            
            # 确保尺寸在合理范围内
            min_height = 70  # 最小高度
            max_height = 300  # 最大高度
            min_width = 250  # 最小宽度
            max_width = 450  # 最大宽度
            
            # 计算最终尺寸
            final_height = max(min_height, min(ideal_height, max_height))
            final_width = max(min_width, min(ideal_width, max_width))
            
            # 保存当前大小以便下次使用
            self.config.set("mini_window_size", {"width": int(final_width), "height": int(final_height)})
            self.config.save()
            
            # 应用新尺寸
            self.resize(int(final_width), int(final_height))
            
            logger.info(f"调整窗口大小: {int(final_width)}x{int(final_height)}, 行数: {line_count}")
        except Exception as e:
            logger.error(f"调整窗口大小失败: {e}")
    
    def _copy_result(self):
        """复制翻译结果到剪贴板"""
        result = self.output_text.toPlainText()
        if result and result != "正在翻译...":
            pyperclip.copy(result)
            if self._parent:
                self._parent.tishi.showMessage("翻译结果已复制到剪贴板")
    
    def _switch_to_main(self):
        """切换到主窗口"""
        if self._parent:
            self._parent.show()
            self._parent.activateWindow()
            self.hide()
    
    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            # 确保窗口获得焦点
            self.activateWindow()
            self.setFocus(Qt.MouseFocusReason)
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """处理鼠标移动事件"""
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件"""
        if event.button() == Qt.LeftButton:
            self._drag_pos = None
            # 保存窗口位置
            pos = self.pos()
            self.config.set("mini_window_position", {
                "x": pos.x(),
                "y": pos.y()
            })
            self.config.save()
            event.accept()
    
    def paintEvent(self, event):
        """绘制窗口背景"""
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # 创建圆角矩形路径
            path = QPainterPath()
            rect = QRectF(self.rect())
            path.addRoundedRect(rect, 24, 24)
            
            # 使用当前主题的颜色
            if self.current_theme:
                background_color = QColor(self.current_theme["background_color"])
                border_color = QColor(self.current_theme["border_color"])
            else:
                background_color = QColor(45, 45, 45)
                border_color = QColor(64, 64, 64)
            
            # 设置背景颜色
            painter.fillPath(path, background_color)
            
            # 绘制边框
            pen = QPen(border_color)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawPath(path)
            
            painter.end()
            
        except Exception as e:
            logger.error(f"绘制窗口背景失败: {e}")
    
    def resizeEvent(self, event):
        """处理窗口大小改变事件"""
        super().resizeEvent(event)
        # 更新窗口大小时重新应用圆角
        self.update()
    
    def show_at_cursor(self):
        """在鼠标位置显示窗口"""
        try:
            # 确保没有正在关闭
            if self._closing:
                return
            
            # 获取鼠标当前位置
            cursor_pos = QCursor.pos()
            
            # 使用固定尺寸
            self.resize(300, 60)
            
            # 始终重置内容
            self.output_text.clear()
            
            # 计算窗口位置，确保在屏幕内
            screen = QApplication.primaryScreen()
            screen_rect = screen.availableGeometry()
            
            # 窗口尺寸
            window_size = self.size()
            
            # 计算显示坐标 (偏移以避免鼠标遮挡)
            x = min(cursor_pos.x() + 10, screen_rect.right() - window_size.width())
            y = min(cursor_pos.y() + 10, screen_rect.bottom() - window_size.height())
            
            # 如果窗口会超出屏幕左边或上边，则调整
            if x < screen_rect.left():
                x = screen_rect.left()
            if y < screen_rect.top():
                y = screen_rect.top()
            
            # 设置窗口位置
            self.move(x, y)
            
            # 显示窗口并激活
            self.show()
            self.raise_()
            self.activateWindow()
            self._showing = True
            
            logger.info(f"在坐标({x}, {y})显示Mini窗口")
        except Exception as e:
            logger.error(f"显示Mini窗口失败: {e}")
    
    def _update_theme_and_position(self):
        """异步更新主题和位置"""
        try:
            # 重新加载配置并更新主题
            self.config.load()
            self._update_current_theme()
            self._apply_theme()
            
            # 获取鼠标位置
            cursor_pos = QCursor.pos()
            screen = QApplication.screenAt(cursor_pos)
            if not screen:
                screen = QApplication.primaryScreen()
            
            screen_geometry = screen.geometry()
            
            # 计算窗口位置，确保窗口完全在屏幕内
            x = min(cursor_pos.x(), screen_geometry.right() - self.width())
            y = min(cursor_pos.y(), screen_geometry.bottom() - self.height())
            
            # 如果窗口超出屏幕左边或上边，调整位置
            x = max(screen_geometry.left(), x)
            y = max(screen_geometry.top(), y)
            
            # 移动窗口到计算出的位置
            self.move(x, y)
            
            # 清除所有控件的焦点
            for child in self.findChildren(QWidget):
                child.clearFocus()
            
            # 显示窗口并立即激活
            self.show()
            self.raise_()
            self.activateWindow()
            self.setFocus(Qt.MouseFocusReason)
            
            # 完成显示过程
            QTimer.singleShot(100, lambda: setattr(self, '_showing', False))
            
            logger.info(f"Mini窗口显示在鼠标位置: ({x}, {y})")
            
        except Exception as e:
            logger.error(f"更新Mini窗口主题和位置失败: {e}")
            self._showing = False
    
    def _activate_window(self):
        """激活窗口并设置焦点"""
        try:
            if not self._showing:
                return
                
            self.activateWindow()
            self.setFocus(Qt.MouseFocusReason)
            
            # 完成显示过程
            self._showing = False
            
        except Exception as e:
            logger.error(f"激活Mini窗口失败: {e}")
            self._showing = False
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        try:
            # 保存窗口位置
            pos = self.pos()
            self.config.set("mini_window_position", {
                "x": pos.x(),
                "y": pos.y()
            })
            self.config.save()
            
            # 停止所有定时器
            self._translate_timer.stop()
            
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"关闭Mini窗口失败: {e}")
            event.accept()
    
    def width(self):
        return self._width
    
    def height(self):
        return self._height 
    
    def _on_theme_changed(self):
        """响应主题变化"""
        try:
            logger.info("接收到主题变化信号")
            # 重新加载配置
            self.config.load()
            self._update_current_theme()
            self._apply_theme()
            logger.info("完成主题更新")
        except Exception as e:
            logger.error(f"响应主题变化失败: {e}")
    
    def enterEvent(self, event):
        """鼠标进入窗口事件"""
        # 移除button_widget相关代码，避免错误
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """鼠标离开窗口事件"""
        # 移除button_widget相关代码，避免错误
        super().leaveEvent(event)
    
    def focusOutEvent(self, event):
        """处理窗口失去焦点事件"""
        # 如果窗口正在显示过程中，不处理关闭事件
        if self._showing:
            super().focusOutEvent(event)
            return
            
        # 如果正在关闭，不处理事件
        if self._closing:
            super().focusOutEvent(event)
            return
            
        cursor_pos = QCursor.pos()
        window_rect = self.geometry()
        
        # 检查是否点击了窗口的子控件
        child_widget = self.childAt(self.mapFromGlobal(cursor_pos))
        
        # 如果鼠标在窗口外且不是点击了子控件，则关闭窗口
        if not window_rect.contains(cursor_pos) and not child_widget:
            self._closing = True
            QTimer.singleShot(0, self._close_window)
        
        super().focusOutEvent(event)
    
    def eventFilter(self, obj, event):
        """事件过滤器，统一处理窗口关闭逻辑"""
        # 处理全局鼠标事件
        if event.type() == QEvent.MouseButtonPress:
            if self.isVisible() and not self._showing:
                cursor_pos = QCursor.pos()
                window_rect = self.geometry()
                
                # 如果点击位置在窗口外，关闭窗口
                if not window_rect.contains(cursor_pos):
                    # 检查是否点击了窗口的子控件
                    child_widget = self.childAt(self.mapFromGlobal(cursor_pos))
                    if not child_widget:
                        self._closing = True
                        self._close_window()
                        return True
        
        if obj is self:
            if event.type() == QEvent.Show:
                # 窗口显示时立即激活并获得焦点
                QTimer.singleShot(0, lambda: (self.activateWindow(), self.setFocus(Qt.MouseFocusReason)))
                return False
                
            if event.type() == QEvent.WindowDeactivate:
                if self._closing or self._showing:
                    return False
                    
                cursor_pos = QCursor.pos()
                window_rect = self.geometry()
                
                # 检查是否点击了窗口的子控件
                child_widget = self.childAt(self.mapFromGlobal(cursor_pos))
                
                # 如果鼠标在窗口外且不是点击了子控件，则关闭窗口
                if not window_rect.contains(cursor_pos) and not child_widget:
                    self._closing = True
                    self._close_window()
                    return True
                    
        return super().eventFilter(obj, event)
    
    def _close_window(self):
        """统一的窗口关闭处理"""
        try:
            if not self._closing:
                return
                
            # 保存窗口位置
            pos = self.pos()
            self.config.set("mini_window_position", {
                "x": pos.x(),
                "y": pos.y()
            })
            self.config.save()
            
            # 停止所有定时器（添加安全检查）
            if hasattr(self, '_translate_timer') and self._translate_timer:
                self._translate_timer.stop()
            
            # 隐藏窗口
            self.hide()
            
            # 重置标志
            self._closing = False
            self._showing = False
            
        except Exception as e:
            logger.error(f"关闭Mini窗口失败: {e}")
            self.hide()
            self._closing = False
            self._showing = False
    
    def set_text_to_translate(self, text):
        """设置要翻译的文本并开始翻译过程"""
        if not text or not text.strip():
            return
        
        # 开始加载动画
        self.start_loading()
        
        # 获取源语言和目标语言
        source_lang = "自动检测"  # Mini窗口默认使用自动检测
        target_lang = self._parent.target_lang_combo.currentText() if self._parent else "中文"
        
        # 开始翻译
        loop = asyncio.get_event_loop()
        loop.create_task(self.translate_text(text, source_lang, target_lang))

    async def translate_text(self, text, source_lang, target_lang):
        """执行翻译过程"""
        try:
            # 使用父窗口的翻译功能
            if self._parent and hasattr(self._parent, 'fanyi'):
                result = await self._parent.fanyi.fanyi(text, source_lang, target_lang)
                # 确保结果是字符串
                if isinstance(result, tuple):
                    result = str(result[0]) if result else ""
                self.update_translation(result)
            else:
                self.update_translation("翻译失败：无法获取翻译服务")
        except Exception as e:
            logger.error(f"翻译出错: {str(e)}")
            self.update_translation(f"翻译出错：{str(e)}")
        finally:
            self.stop_loading()

    def update_translation(self, text):
        """更新翻译结果"""
        try:
            # 对于QLabel，直接设置文本
            self.output_text.setText(text)
            
            # 自动调整窗口大小以显示全部内容
            self._adjust_window_size_for_text(text)
            
            logger.info(f"更新翻译结果: {text[:20]}...")
        except Exception as e:
            logger.error(f"更新翻译结果失败: {e}")
            self.output_text.setText(f"翻译错误: {str(e)}")

    def _adjust_window_size_for_text(self, text):
        """根据文本内容自动调整窗口大小"""
        try:
            if not text:
                # 空文本使用默认尺寸
                self.resize(300, 60)
                return
            
            # 计算所需高度
            font_metrics = self.output_text.fontMetrics()
            text_width = self.output_text.width() - 20  # 减去边距
            
            # 计算文本在给定宽度下需要多少行
            text_lines = []
            for line in text.split('\n'):
                # 处理长行自动换行
                while font_metrics.horizontalAdvance(line) > text_width:
                    # 找到适合当前宽度的截断点
                    i = len(line)
                    while i > 0 and font_metrics.horizontalAdvance(line[:i]) > text_width:
                        i -= 1
                    
                    if i == 0:  # 单个字符宽度超过文本框宽度
                        i = 1
                    
                    text_lines.append(line[:i])
                    line = line[i:]
                
                if line:  # 添加剩余的行
                    text_lines.append(line)
            
            # 计算所需高度 (行数 * 行高 + 额外空间)
            line_count = len(text_lines)
            line_height = font_metrics.lineSpacing()
            
            # 考虑标题栏高度增加后的额外空间需求
            title_bar_height = 20  # 与上面设置的标题栏高度保持一致
            content_height = line_count * line_height + 20 + title_bar_height  # 添加一些额外空间
            
            # 限制最大高度，避免窗口过大
            max_height = 400
            content_height = min(content_height, max_height)
            
            # 调整窗口大小
            self.resize(300, max(60, content_height))
            logger.info(f"调整窗口大小为: 300x{content_height}, 文本行数: {line_count}")
        except Exception as e:
            logger.error(f"调整窗口大小失败: {e}")
            # 出错时使用默认大小
            self.resize(300, 60)

    def _get_theme_colors(self):
        """获取当前主题颜色"""
        # 获取当前主题
        if hasattr(self, 'current_theme') and self.current_theme:
            return {
                "text_background": self.current_theme["background_color"],
                "text_color": self.current_theme["text_color"],
                "border_color": self.current_theme["border_color"],
                "selection_background": self.current_theme["focus_border_color"],
                "selection_color": "#FFFFFF",
                "button_background": self.current_theme["button_background"],
                "button_border": self.current_theme["button_border"],
                "button_hover": self.current_theme["button_hover"],
                "button_hover_border": self.current_theme["button_hover_border"],
                "button_pressed": self.current_theme["button_pressed"],
                # 添加滚动条相关颜色
                "scrollbar_background": self.current_theme.get("scrollbar_background", self.current_theme["background_color"]),
                "scrollbar_handle": self.current_theme.get("scrollbar_handle", self.current_theme["border_color"]),
                "scrollbar_handle_hover": self.current_theme.get("scrollbar_handle_hover", self.current_theme["hover_border_color"])
            }
        
        # 默认使用深色主题
        theme = self.THEMES.get("深色主题", {})
        return {
            "text_background": theme.get("background_color", "#2D2D2D"),
            "text_color": theme.get("text_color", "#FFFFFF"),
            "border_color": theme.get("border_color", "#404040"),
            "selection_background": theme.get("focus_border_color", "#0A84FF"),
            "selection_color": "#FFFFFF",
            "button_background": theme.get("button_background", "#2D2D2D"),
            "button_border": theme.get("button_border", "#404040"),
            "button_hover": theme.get("button_hover", "#404040"),
            "button_hover_border": theme.get("button_hover_border", "#505050"),
            "button_pressed": theme.get("button_pressed", "#505050"),
            # 添加滚动条相关颜色
            "scrollbar_background": theme.get("scrollbar_background", "#2D2D2D"),
            "scrollbar_handle": theme.get("scrollbar_handle", "#404040"),
            "scrollbar_handle_hover": theme.get("scrollbar_handle_hover", "#505050")
        }

    def _resource_path(self, relative_path):
        """获取资源文件路径"""
        if hasattr(self, "_resource_dir"):
            return os.path.join(self._resource_dir, relative_path)
        
        # 获取资源路径
        if getattr(sys, 'frozen', False):
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        self._resource_dir = os.path.join(base_dir, 'src', 'ziyuan')
        return os.path.join(self._resource_dir, relative_path)

    def _emit_text_changed(self):
        """发出文本变化信号"""
        self.text_changed.emit() 

