import sys

from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QVBoxLayout,
    QLineEdit,
    QListView,
    QApplication,
    QGraphicsDropShadowEffect,
    QStyledItemDelegate,
    QAbstractItemView,
    QStyle,
)
from PyQt5.QtCore import Qt, QPoint, QSize, QRectF, QStringListModel
from PyQt5.QtGui import QPainter, QPainterPath, QColor, QPen, QPalette


_LANG_PINYIN = {
    "简体中文": ("jiantizhongwen", "jtzw"),
    "繁体中文": ("fantizhongwen", "ftzw"),
    "英语": ("yingyu", "yy"),
    "日语": ("riyu", "ry"),
    "韩语": ("hanyu", "hy"),
    "法语": ("fayu", "fy"),
    "德语": ("deyu", "dy"),
    "西班牙语": ("xibanyayu", "xbyy"),
    "俄语": ("eyu", "ey"),
    "意大利语": ("yidaliyu", "ydly"),
    "葡萄牙语": ("putaoyayu", "ptyy"),
    "越南语": ("yuenanyu", "yny"),
    "泰语": ("taiyu", "ty"),
    "阿拉伯语": ("alaboyu", "alby"),
    "自动检测": ("zidongjiance", "zdjc"),
}


def _norm_query(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "")


def _lang_keys(display_text: str):
    base = (display_text or "").split(" (")[0]
    keys = [base, base.lower()]
    if base in _LANG_PINYIN:
        full, abbr = _LANG_PINYIN[base]
        keys.append(full)
        keys.append(abbr)
        if base == "自动检测":
            keys.append("auto")
    return keys


class _ComboPopup(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self._colors = None
        self._shadow_margin = 1 if sys.platform == "win32" else 4
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

    def set_colors(self, colors: dict):
        self._colors = colors
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        colors = self._colors or {}
        bg = colors.get("popup_bg", QColor(255, 255, 255))
        border = colors.get("popup_border", QColor(0, 0, 0, 30))

        m = float(getattr(self, "_shadow_margin", 4))
        r = QRectF(self.rect()).adjusted(m, m, -m, -m)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        painter.fillPath(path, bg)

        pen = QPen(border)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)


class _ComboPopupItemDelegate(QStyledItemDelegate):
    def __init__(self, colors: dict, parent=None):
        super().__init__(parent)
        self._colors = colors or {}

    def set_colors(self, colors: dict):
        self._colors = colors or {}

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        text = str(index.data(Qt.DisplayRole) or "")
        rect = QRectF(option.rect).adjusted(8, 2, -8, -2)

        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        bg = None
        if selected:
            bg = self._colors.get("item_selected")
        elif hovered:
            bg = self._colors.get("item_hover")

        if bg is not None:
            path = QPainterPath()
            path.addRoundedRect(rect, 8, 8)
            painter.fillPath(path, bg)

        text_color = self._colors.get("text")
        if selected:
            text_color = self._colors.get("text_selected", text_color)
        if text_color is not None:
            painter.setPen(QPen(text_color))

        fm = painter.fontMetrics()
        max_w = max(0, int(rect.width() - 10))
        elided = fm.elidedText(text, Qt.ElideRight, max_w)
        painter.drawText(rect.adjusted(10, 0, -10, 0), Qt.AlignVCenter | Qt.AlignLeft, elided)

        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(30, size.height()))


class SearchableComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_items = []

        font = self.font()
        try:
            font.setPointSize(14)
        except Exception:
            pass
        self.setFont(font)

        self._popup = _ComboPopup(None)
        popup_layout = QVBoxLayout(self._popup)
        popup_layout.setContentsMargins(8, 8, 8, 8)
        popup_layout.setSpacing(6)

        self._search_edit = QLineEdit(self._popup)
        self._search_edit.setPlaceholderText("搜索：中文 / 拼音 / 缩写")
        self._search_edit.setFont(font)
        self._search_edit.setFixedHeight(30)
        popup_layout.addWidget(self._search_edit)

        self._list_view = QListView(self._popup)
        self._list_view.setFont(font)
        self._list_view.setMouseTracking(True)
        self._list_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list_view.setAttribute(Qt.WA_TranslucentBackground, True)
        self._list_view.setAutoFillBackground(False)
        popup_layout.addWidget(self._list_view)

        self._model = QStringListModel(self._popup)
        self._list_view.setModel(self._model)

        try:
            self._list_view.viewport().setAttribute(Qt.WA_TranslucentBackground, True)
            self._list_view.viewport().setAutoFillBackground(False)
        except Exception:
            pass

        self._delegate = _ComboPopupItemDelegate({}, self._list_view)
        self._list_view.setItemDelegate(self._delegate)

        if sys.platform != "win32":
            shadow = QGraphicsDropShadowEffect(self._popup)
            shadow.setBlurRadius(26)
            shadow.setOffset(0, 10)
            shadow.setColor(QColor(0, 0, 0, 120))
            self._popup.setGraphicsEffect(shadow)

        self._search_edit.textChanged.connect(self._on_search_text_changed)
        self._search_edit.returnPressed.connect(self._accept_first_match)
        self._list_view.clicked.connect(self._on_item_clicked)

    def refresh_theme(self):
        colors = self._calc_popup_colors()
        self._popup.set_colors(colors)
        self._delegate.set_colors(colors)
        self._apply_popup_styles(colors)
        if self._popup.isVisible():
            self._popup.update()
            self._list_view.viewport().update()

    def set_items(self, items):
        self.clear()
        self.addItems(list(items))
        self._all_items = list(items)
        self._model.setStringList(self._all_items)

    def setItemText(self, index, text):
        super().setItemText(index, text)
        if 0 <= index < len(self._all_items):
            self._all_items[index] = text
            self._model.setStringList(self._all_items)

    def showPopup(self):
        self._all_items = [self.itemText(i) for i in range(self.count())]
        self._model.setStringList(self._all_items)

        self.refresh_theme()

        self._search_edit.blockSignals(True)
        self._search_edit.setText("")
        self._search_edit.blockSignals(False)

        anchor = self.parentWidget() or self
        pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
        width = anchor.width()

        row_h = self._list_view.sizeHintForRow(0)
        if row_h <= 0:
            row_h = 28
        visible_rows = min(9, max(4, len(self._all_items)))
        list_h = row_h * visible_rows + 6
        popup_h = self._search_edit.sizeHint().height() + 8 + list_h + 16

        self._popup.setFixedSize(width, popup_h)
        self._popup.move(pos)
        self._popup.show()
        self._search_edit.setFocus()

    def hidePopup(self):
        popup = getattr(self, "_popup", None)
        if popup is not None and popup.isVisible():
            popup.hide()

    def closeEvent(self, event):
        popup = getattr(self, "_popup", None)
        if popup is not None:
            popup.hide()
            popup.deleteLater()
            self._popup = None
        super().closeEvent(event)

    def _accept_first_match(self):
        if self._model.rowCount() <= 0:
            return
        first_text = self._model.data(self._model.index(0, 0), Qt.DisplayRole)
        if first_text:
            self._select_text(str(first_text))

    def _on_item_clicked(self, index):
        text = self._model.data(index, Qt.DisplayRole)
        if text:
            self._select_text(str(text))

    def _select_text(self, text: str):
        original_index = -1
        for i in range(self.count()):
            if self.itemText(i) == text:
                original_index = i
                break

        if original_index >= 0:
            self.setCurrentIndex(original_index)
        self.hidePopup()

    def _on_search_text_changed(self, text):
        q = _norm_query(text)
        if not q:
            self._model.setStringList(self._all_items)
            return

        matches = []
        for item in self._all_items:
            keys = _lang_keys(item)
            for k in keys:
                if q in _norm_query(k):
                    matches.append(item)
                    break

        self._model.setStringList(matches)

    def _calc_popup_colors(self):
        theme = None
        p = self
        while p is not None:
            p = p.parent()
            if p is None:
                break
            if hasattr(p, "config"):
                try:
                    theme = p.config.get("theme", "dark")
                except Exception:
                    theme = None
                break

        if theme == "dark":
            return {
                "popup_bg": QColor(34, 34, 34, 245),
                "popup_border": QColor(255, 255, 255, 30),
                "text": QColor(255, 255, 255, 230),
                "text_selected": QColor(255, 255, 255, 245),
                "item_hover": QColor(255, 255, 255, 18),
                "item_selected": QColor(10, 132, 255, 160),
                "input_bg": QColor(255, 255, 255, 18),
                "input_border": QColor(255, 255, 255, 28),
                "placeholder": QColor(255, 255, 255, 120),
                "scroll_handle": QColor(255, 255, 255, 70),
                "scroll_handle_hover": QColor(255, 255, 255, 110),
            }

        if theme == "pink":
            return {
                "popup_bg": QColor(255, 240, 245, 250),
                "popup_border": QColor(255, 182, 193, 120),
                "text": QColor(51, 51, 51, 235),
                "text_selected": QColor(51, 51, 51, 245),
                "item_hover": QColor(255, 105, 180, 20),
                "item_selected": QColor(255, 105, 180, 55),
                "input_bg": QColor(255, 245, 248, 255),
                "input_border": QColor(255, 182, 193, 170),
                "placeholder": QColor(51, 51, 51, 120),
                "scroll_handle": QColor(255, 105, 180, 90),
                "scroll_handle_hover": QColor(255, 105, 180, 140),
            }

        if theme == "light":
            return {
                "popup_bg": QColor(255, 255, 255, 250),
                "popup_border": QColor(0, 0, 0, 26),
                "text": QColor(0, 0, 0, 220),
                "text_selected": QColor(0, 0, 0, 235),
                "item_hover": QColor(0, 0, 0, 10),
                "item_selected": QColor(10, 132, 255, 46),
                "input_bg": QColor(0, 0, 0, 6),
                "input_border": QColor(0, 0, 0, 24),
                "placeholder": QColor(0, 0, 0, 110),
                "scroll_handle": QColor(0, 0, 0, 55),
                "scroll_handle_hover": QColor(0, 0, 0, 90),
            }

        window = QApplication.palette().color(QPalette.Window)
        is_dark = window.lightness() < 128
        if is_dark:
            return {
                "popup_bg": QColor(34, 34, 34, 245),
                "popup_border": QColor(255, 255, 255, 30),
                "text": QColor(255, 255, 255, 230),
                "text_selected": QColor(255, 255, 255, 245),
                "item_hover": QColor(255, 255, 255, 18),
                "item_selected": QColor(10, 132, 255, 160),
                "input_bg": QColor(255, 255, 255, 18),
                "input_border": QColor(255, 255, 255, 28),
                "placeholder": QColor(255, 255, 255, 120),
                "scroll_handle": QColor(255, 255, 255, 70),
                "scroll_handle_hover": QColor(255, 255, 255, 110),
            }

        return {
            "popup_bg": QColor(255, 255, 255, 250),
            "popup_border": QColor(0, 0, 0, 26),
            "text": QColor(0, 0, 0, 220),
            "text_selected": QColor(0, 0, 0, 235),
            "item_hover": QColor(0, 0, 0, 10),
            "item_selected": QColor(10, 132, 255, 46),
            "input_bg": QColor(0, 0, 0, 6),
            "input_border": QColor(0, 0, 0, 24),
            "placeholder": QColor(0, 0, 0, 110),
            "scroll_handle": QColor(0, 0, 0, 55),
            "scroll_handle_hover": QColor(0, 0, 0, 90),
        }

    def _apply_popup_styles(self, colors: dict):
        def _rgba(c: QColor):
            return f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha()})"

        try:
            pal = self._search_edit.palette()
            if colors.get("text") is not None:
                pal.setColor(QPalette.Text, colors.get("text"))
            if colors.get("placeholder") is not None:
                pal.setColor(QPalette.PlaceholderText, colors.get("placeholder"))
            self._search_edit.setPalette(pal)
        except Exception:
            pass

        self._search_edit.setStyleSheet(
            "QLineEdit {"
            f"background-color: {_rgba(colors.get('input_bg'))};"
            f"border: 1px solid {_rgba(colors.get('input_border'))};"
            "border-radius: 9px;"
            "padding: 4px 10px;"
            f"color: {_rgba(colors.get('text'))};"
            "}"
            "QLineEdit:focus {"
            "border: 1px solid rgba(10, 132, 255, 200);"
            "}"
        )

        self._list_view.setStyleSheet(
            "QListView {"
            "background: transparent;"
            "border: none;"
            "outline: none;"
            "}"
            "QListView::viewport {"
            "background: transparent;"
            "}"
            "QListView::item {"
            "background: transparent;"
            "}"
            "QScrollBar:vertical {"
            "background: transparent;"
            "width: 10px;"
            "margin: 2px 2px 2px 0px;"
            "}"
            "QScrollBar::handle:vertical {"
            f"background: {_rgba(colors.get('scroll_handle'))};"
            "border-radius: 5px;"
            "min-height: 24px;"
            "}"
            "QScrollBar::handle:vertical:hover {"
            f"background: {_rgba(colors.get('scroll_handle_hover'))};"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "height: 0px;"
            "background: transparent;"
            "}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            "background: transparent;"
            "}"
        )

        try:
            self._list_view.viewport().setAutoFillBackground(False)
        except Exception:
            pass
