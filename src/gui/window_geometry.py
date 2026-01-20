import logging
logger = logging.getLogger(__name__)

from PyQt5.QtCore import Qt, QPoint, QRect, QEvent
from PyQt5.QtWidgets import QWidget, QApplication


def perform_resize(self, global_pos: QPoint):
    delta = global_pos - self._resize_start_pos
    start = self._resize_start_geometry
    edge = self._resize_edge

    x = start.x()
    y = start.y()
    w = start.width()
    h = start.height()

    if 'right' in edge:
        w = start.width() + delta.x()
    if 'bottom' in edge:
        h = start.height() + delta.y()
    if 'left' in edge:
        x = start.x() + delta.x()
        w = start.width() - delta.x()
    if 'top' in edge:
        y = start.y() + delta.y()
        h = start.height() - delta.y()

    min_w = self.minimumWidth()
    min_h = self.minimumHeight()
    max_w = self.maximumWidth()
    max_h = self.maximumHeight()

    if w < min_w:
        w = min_w
        if 'left' in edge:
            x = start.right() - w + 1
    if h < min_h:
        h = min_h
        if 'top' in edge:
            y = start.bottom() - h + 1

    if max_w > 0 and w > max_w:
        w = max_w
        if 'left' in edge:
            x = start.right() - w + 1
    if max_h > 0 and h > max_h:
        h = max_h
        if 'top' in edge:
            y = start.bottom() - h + 1

    self.setGeometry(x, y, w, h)


def install_resize_event_filters(self, root: QWidget):
    root.setMouseTracking(True)
    root.installEventFilter(self)
    for child in root.findChildren(QWidget):
        child.setMouseTracking(True)
        child.installEventFilter(self)


def event_filter(self, obj, event, super_event_filter):
    t = event.type()
    if self.isMaximized():
        return super_event_filter(obj, event)

    if t == QEvent.MouseMove:
        if hasattr(self, '_resize_edge') and self._resize_edge:
            perform_resize(self, event.globalPos())
            return True

        if isinstance(obj, QWidget):
            pos = obj.mapTo(self, event.pos())
            edge = get_edge(self, pos)
            if edge:
                self.setCursor(get_resize_cursor(edge))
                self._current_edge = edge
                return True

        if getattr(self, '_current_edge', None):
            self._current_edge = None
            self.setCursor(Qt.ArrowCursor)
        return False

    if t == QEvent.MouseButtonPress:
        if event.button() == Qt.LeftButton and isinstance(obj, QWidget):
            pos = obj.mapTo(self, event.pos())
            edge = get_edge(self, pos)
            if edge:
                self._resize_edge = edge
                self._resize_start_pos = event.globalPos()
                self._resize_start_geometry = QRect(self.geometry())
                self._is_dragging = False
                self.setCursor(get_resize_cursor(edge))
                return True
        return super_event_filter(obj, event)

    if t == QEvent.MouseButtonRelease:
        if hasattr(self, '_resize_edge') and self._resize_edge:
            self._resize_edge = None
            self.setCursor(Qt.ArrowCursor)
            schedule_save_window_geometry(self)
            return True
        return super_event_filter(obj, event)

    return super_event_filter(obj, event)


def schedule_save_window_geometry(self):
    if hasattr(self, '_save_geometry_timer'):
        self._save_geometry_timer.start(250)


def save_window_geometry(self):
    if self.isMaximized() or getattr(self, 'is_mini_mode', False):
        return
    g = self.geometry()
    self.config._config.setdefault("window", {})["width"] = g.width()
    self.config._config.setdefault("window", {})["height"] = g.height()
    self.config._config.setdefault("window", {})["x"] = g.x()
    self.config._config.setdefault("window", {})["y"] = g.y()
    self.config.save()


def get_edge(self, pos):
    """获取鼠标位置对应的边缘"""
    margin = 6  # 减小边缘检测范围
    x = pos.x()
    y = pos.y()
    width = self.width()
    height = self.height()

    edges = []
    if x <= margin: edges.append('left')
    if x >= width - margin: edges.append('right')
    if y <= margin: edges.append('top')
    if y >= height - margin: edges.append('bottom')

    if len(edges) == 2:
        s = set(edges)
        if s == {'top', 'left'}:
            return 'top-left'
        if s == {'top', 'right'}:
            return 'top-right'
        if s == {'bottom', 'left'}:
            return 'bottom-left'
        if s == {'bottom', 'right'}:
            return 'bottom-right'
        return '-'.join(edges)
    elif len(edges) == 1:
        return edges[0]
    return None


def get_resize_cursor(edge):
    """获取调整大小时鼠标样式"""
    if not edge:
        return Qt.ArrowCursor

    cursor_map = {
        'left': Qt.SizeHorCursor,
        'right': Qt.SizeHorCursor,
        'top': Qt.SizeVerCursor,
        'bottom': Qt.SizeVerCursor,
        'top-left': Qt.SizeFDiagCursor,
        'bottom-right': Qt.SizeFDiagCursor,
        'top-right': Qt.SizeBDiagCursor,
        'bottom-left': Qt.SizeBDiagCursor,
        'left-top': Qt.SizeFDiagCursor,
        'right-bottom': Qt.SizeFDiagCursor,
        'right-top': Qt.SizeBDiagCursor,
        'left-bottom': Qt.SizeBDiagCursor
    }

    return cursor_map.get(edge, Qt.ArrowCursor)


def load_window_geometry(self):
    """加载窗口位置和大小"""
    try:
        width = self.config.get("window.width", 857)
        height = self.config.get("window.height", 620)

        x = self.config.get("window.x")
        y = self.config.get("window.y")

        self.resize(width, height)

        if x is not None and y is not None:
            screen = QApplication.desktop().screenGeometry()
            if 0 <= x <= screen.width() - width and 0 <= y <= screen.height() - height:
                self.move(x, y)
            else:
                center_window(self)
        else:
            center_window(self)

        logger.info(f"加载窗口位置和大小: {width}x{height} @ ({x}, {y})")

    except Exception as e:
        logger.error(f"加载窗口位置和大小失败: {e}")
        self.resize(857, 620)
        center_window(self)


def center_window(self):
    """将窗口居中显示"""
    try:
        screen = QApplication.desktop().screenGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
        logger.info(f"窗口已居中显示: ({x}, {y})")
    except Exception as e:
        logger.error(f"窗口居中显示失败: {e}")
