import logging
logger = logging.getLogger(__name__)

from PyQt5.QtCore import Qt, QPoint, QRect, QEvent
from PyQt5.QtWidgets import QWidget, QApplication


DEFAULT_WINDOW_WIDTH = 857
DEFAULT_WINDOW_HEIGHT = 620
MIN_VISIBLE_WIDTH = 96
MIN_VISIBLE_HEIGHT = 64
MAX_TOP_OVERFLOW = 0


def _as_int(value, default=None):
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value, minimum, maximum):
    if maximum < minimum:
        return minimum
    return max(minimum, min(value, maximum))


def _window_screen(window):
    try:
        handle = window.windowHandle()
        if handle:
            screen = handle.screen()
            if screen:
                return screen
    except Exception:
        pass

    try:
        screen = window.screen()
        if screen:
            return screen
    except Exception:
        pass

    return None


def _screen_for_rect(rect: QRect):
    if rect is None or not rect.isValid():
        return None

    try:
        screen = QApplication.screenAt(rect.center())
        if screen:
            return screen
    except Exception:
        pass

    best_screen = None
    best_area = 0
    try:
        for screen in QApplication.screens():
            available = screen.availableGeometry()
            intersection = available.intersected(rect)
            if not intersection.isValid():
                continue
            area = intersection.width() * intersection.height()
            if area > best_area:
                best_screen = screen
                best_area = area
    except Exception:
        pass
    return best_screen


def _available_geometries():
    geometries = []
    try:
        for screen in QApplication.screens():
            available = screen.availableGeometry()
            if available.width() > 0 and available.height() > 0:
                geometries.append(QRect(available))
    except Exception:
        pass
    if geometries:
        return geometries

    try:
        screen = QApplication.primaryScreen()
    except Exception:
        screen = None
    if screen is not None:
        try:
            available = screen.availableGeometry()
            if available.width() > 0 and available.height() > 0:
                geometries.append(QRect(available))
        except Exception:
            pass
    return geometries


def _available_geometry(window=None, rect=None, prefer_rect: bool = False):
    screen = None
    if prefer_rect:
        screen = _screen_for_rect(rect)
    if screen is None and window is not None:
        screen = _window_screen(window)
    if screen is None and rect is not None:
        screen = _screen_for_rect(rect)
    if screen is None:
        try:
            screen = QApplication.primaryScreen()
        except Exception:
            screen = None
    if screen is not None:
        try:
            available = screen.availableGeometry()
            if available.width() > 0 and available.height() > 0:
                return available
        except Exception:
            pass
    return QRect(0, 0, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)


def _ensure_effective_minimum_size(window, available: QRect):
    desired = getattr(window, "_window_geometry_desired_minimum_size", None)
    if desired is None:
        desired = (max(1, window.minimumWidth()), max(1, window.minimumHeight()))
        try:
            window._window_geometry_desired_minimum_size = desired
        except Exception:
            pass

    min_w = min(max(1, desired[0]), max(1, available.width()))
    min_h = min(max(1, desired[1]), max(1, available.height()))
    try:
        if window.minimumWidth() != min_w or window.minimumHeight() != min_h:
            window.setMinimumSize(min_w, min_h)
    except Exception:
        pass
    return min_w, min_h


def _limit_window_size(window, rect: QRect, available: QRect):
    min_w, min_h = _ensure_effective_minimum_size(window, available)
    width = _clamp(_as_int(rect.width(), DEFAULT_WINDOW_WIDTH), min_w, max(1, available.width()))
    height = _clamp(_as_int(rect.height(), DEFAULT_WINDOW_HEIGHT), min_h, max(1, available.height()))
    return width, height


def _repair_window_position(rect: QRect, available: QRect):
    width = max(1, rect.width())
    height = max(1, rect.height())
    visible_w = min(MIN_VISIBLE_WIDTH, width, max(1, available.width()))
    visible_h = min(MIN_VISIBLE_HEIGHT, height, max(1, available.height()))

    min_x = available.x() + visible_w - width
    max_x = available.right() - visible_w + 1
    min_y_for_visible_area = available.y() + visible_h - height
    min_y_for_title = available.y() - min(MAX_TOP_OVERFLOW, max(0, height - 1))
    min_y = max(min_y_for_visible_area, min_y_for_title)
    max_y = available.bottom() - visible_h + 1

    x = _clamp(_as_int(rect.x(), available.x()), min_x, max_x)
    y = _clamp(_as_int(rect.y(), available.y()), min_y, max_y)
    return x, y


def _is_recoverable_geometry(rect: QRect):
    if rect is None or not rect.isValid():
        return False

    available_geometries = _available_geometries()
    if not available_geometries:
        available_geometries = [QRect(0, 0, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)]

    width = max(1, rect.width())
    height = max(1, rect.height())
    for available in available_geometries:
        if rect.y() < available.y():
            continue
        intersection = available.intersected(rect)
        if not intersection.isValid():
            continue
        required_w = min(MIN_VISIBLE_WIDTH, width, max(1, available.width()))
        required_h = min(MIN_VISIBLE_HEIGHT, height, max(1, available.height()))
        if intersection.width() >= required_w and intersection.height() >= required_h:
            return True
    return False


def limit_window_size_preserving_position(window, rect: QRect, prefer_rect_screen: bool = False):
    available = _available_geometry(window, rect, prefer_rect=prefer_rect_screen)
    width, height = _limit_window_size(window, rect, available)
    return QRect(_as_int(rect.x(), available.x()), _as_int(rect.y(), available.y()), width, height)


def clamp_window_geometry(window, rect: QRect, prefer_rect_screen: bool = False, repair_position: bool = True):
    geometry = limit_window_size_preserving_position(window, rect, prefer_rect_screen=prefer_rect_screen)
    if repair_position and not _is_recoverable_geometry(geometry):
        available = _available_geometry(window, geometry, prefer_rect=True)
        x, y = _repair_window_position(geometry, available)
        geometry = QRect(x, y, geometry.width(), geometry.height())
    return geometry


def _centered_geometry(window, width: int, height: int):
    available = _available_geometry(window)
    min_w, min_h = _ensure_effective_minimum_size(window, available)
    width = _clamp(width, min_w, max(1, available.width()))
    height = _clamp(height, min_h, max(1, available.height()))
    x = available.x() + (available.width() - width) // 2
    y = available.y() + (available.height() - height) // 2
    return QRect(x, y, width, height)


def _write_window_geometry(self, rect: QRect):
    window_config = self.config._config.setdefault("window", {})
    values = {
        "width": rect.width(),
        "height": rect.height(),
        "x": rect.x(),
        "y": rect.y(),
    }
    changed = any(window_config.get(key) != value for key, value in values.items())
    window_config.update(values)
    if changed:
        self.config.save()
    return changed


def _resize_limits(self):
    available = getattr(self, "_resize_available_geometry", None)
    minimum = getattr(self, "_resize_minimum_size", None)
    if available is None or not available.isValid() or minimum is None:
        available = _available_geometry(self)
        minimum = _ensure_effective_minimum_size(self, available)

    min_w, min_h = minimum
    max_w = self.maximumWidth()
    max_h = self.maximumHeight()
    available_w = max(1, available.width())
    available_h = max(1, available.height())

    if max_w <= 0 or max_w > available_w:
        max_w = available_w
    if max_h <= 0 or max_h > available_h:
        max_h = available_h
    max_w = max(min_w, max_w)
    max_h = max(min_h, max_h)
    return min_w, min_h, max_w, max_h


def _best_available_for_rect(rect: QRect, available_geometries: list[QRect]):
    if not available_geometries:
        return QRect(0, 0, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
    best_available = available_geometries[0]
    best_area = -1
    for available in available_geometries:
        intersection = available.intersected(rect)
        area = intersection.width() * intersection.height() if intersection.isValid() else 0
        if area > best_area:
            best_available = available
            best_area = area
    return best_available


def begin_move(self):
    geometries = _available_geometries()
    if not geometries:
        geometries = [_available_geometry(self)]
    self._move_available_geometries = [QRect(geometry) for geometry in geometries]


def constrain_move_position(self, position: QPoint):
    geometries = getattr(self, "_move_available_geometries", None)
    if not geometries:
        geometries = _available_geometries() or [_available_geometry(self)]
    rect = QRect(position.x(), position.y(), max(1, self.width()), max(1, self.height()))
    available = _best_available_for_rect(rect, geometries)
    if position.y() < available.y():
        return QPoint(position.x(), available.y())
    return position


def end_move(self):
    self._move_available_geometries = None


def begin_resize(self, edge, global_pos: QPoint):
    available = _available_geometry(self)
    self._resize_edge = edge
    self._resize_start_pos = global_pos
    self._resize_start_geometry = QRect(self.geometry())
    self._resize_available_geometry = QRect(available)
    self._resize_minimum_size = _ensure_effective_minimum_size(self, available)
    self._is_dragging = False


def end_resize(self):
    self._resize_edge = None
    self._resize_available_geometry = None
    self._resize_minimum_size = None


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

    min_w, min_h, max_w, max_h = _resize_limits(self)

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
                begin_resize(self, edge, event.globalPos())
                self.setCursor(get_resize_cursor(edge))
                return True
        return super_event_filter(obj, event)

    if t == QEvent.MouseButtonRelease:
        if hasattr(self, '_resize_edge') and self._resize_edge:
            end_resize(self)
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
    g = clamp_window_geometry(self, self.geometry(), prefer_rect_screen=True)
    if g != self.geometry():
        self.setGeometry(g)
    _write_window_geometry(self, g)


def protect_window_size(self):
    if self.isMaximized() or getattr(self, 'is_mini_mode', False):
        return
    if getattr(self, '_window_geometry_size_protecting', False):
        return
    g = limit_window_size_preserving_position(self, self.geometry(), prefer_rect_screen=True)
    if g == self.geometry():
        return
    try:
        self._window_geometry_size_protecting = True
    except Exception:
        pass
    try:
        self.setGeometry(g)
    finally:
        try:
            self._window_geometry_size_protecting = False
        except Exception:
            pass


def get_edge(self, pos):
    """Return the resize edge under the mouse position."""
    margin = 6
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
    """Return the cursor for a resize edge."""
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
    """Load saved window geometry and repair invalid values."""
    try:
        width = _as_int(self.config.get("window.width", DEFAULT_WINDOW_WIDTH), DEFAULT_WINDOW_WIDTH)
        height = _as_int(self.config.get("window.height", DEFAULT_WINDOW_HEIGHT), DEFAULT_WINDOW_HEIGHT)

        x = _as_int(self.config.get("window.x"))
        y = _as_int(self.config.get("window.y"))

        if x is not None and y is not None:
            geometry = clamp_window_geometry(self, QRect(x, y, width, height), prefer_rect_screen=True)
        else:
            geometry = _centered_geometry(self, width, height)

        self.setGeometry(geometry)
        _write_window_geometry(self, geometry)

        logger.info(f"Loaded window geometry {geometry.width()}x{geometry.height()} @ ({geometry.x()}, {geometry.y()})")

    except Exception as e:
        logger.error(f"Failed to load window geometry: {e}")
        geometry = _centered_geometry(self, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setGeometry(geometry)
        _write_window_geometry(self, geometry)


def center_window(self):
    """Center the window inside the current available screen area."""
    try:
        geometry = _centered_geometry(self, self.width(), self.height())
        self.setGeometry(geometry)
        logger.info(f"Window centered at ({geometry.x()}, {geometry.y()})")
    except Exception as e:
        logger.error(f"Failed to center window: {e}")
