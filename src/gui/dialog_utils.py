from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox, QWidget


@dataclass(frozen=True)
class DialogPalette:
    background: str
    surface: str
    surface_alt: str
    border: str
    text: str
    text_secondary: str
    primary: str
    primary_hover: str
    secondary: str
    secondary_hover: str
    progress_start: str
    progress_end: str


_PALETTES = {
    "dark": DialogPalette(
        background="#1E1E1E",
        surface="#2D2D2D",
        surface_alt="#333333",
        border="#404040",
        text="#F5F7FA",
        text_secondary="#B8C0CC",
        primary="#0A84FF",
        primary_hover="#0071E3",
        secondary="#3A3A3A",
        secondary_hover="#4A4A4A",
        progress_start="#18A058",
        progress_end="#0A84FF",
    ),
    "light": DialogPalette(
        background="#F6F8FB",
        surface="#FFFFFF",
        surface_alt="#E5E7EB",
        border="#D5DAE3",
        text="#1F2A37",
        text_secondary="#6B7280",
        primary="#1F7AE0",
        primary_hover="#1768BD",
        secondary="#E5E7EB",
        secondary_hover="#D1D5DB",
        progress_start="#18A058",
        progress_end="#1F7AE0",
    ),
    "pink": DialogPalette(
        background="#FFF6FA",
        surface="#FFFFFF",
        surface_alt="#F8DCE7",
        border="#F2B8CD",
        text="#52243A",
        text_secondary="#8A5870",
        primary="#E85D93",
        primary_hover="#D94881",
        secondary="#F6DCE7",
        secondary_hover="#F0C7D7",
        progress_start="#FF8FB1",
        progress_end="#E85D93",
    ),
}


def _get_theme_key(widget: Optional[QWidget]) -> str:
    current = widget
    while current is not None:
        config = getattr(current, "config", None)
        if config is not None and hasattr(config, "get"):
            try:
                return config.get("theme", "dark") or "dark"
            except Exception:
                return "dark"
        current = current.parent() if hasattr(current, "parent") else None
    return "dark"


def get_dialog_palette(widget: Optional[QWidget]) -> DialogPalette:
    return _PALETTES.get(_get_theme_key(widget), _PALETTES["dark"])


def get_theme_key(widget: Optional[QWidget]) -> str:
    return _get_theme_key(widget)


def get_palette_by_theme(theme_key: Optional[str]) -> DialogPalette:
    return _PALETTES.get(theme_key or "dark", _PALETTES["dark"])


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def to_rgba(color: str, alpha: float) -> str:
    red, green, blue = _hex_to_rgb(color)
    alpha_value = max(0.0, min(1.0, alpha))
    return f"rgba({red}, {green}, {blue}, {alpha_value:.2f})"


def build_menu_stylesheet(widget: Optional[QWidget]) -> str:
    palette = get_dialog_palette(widget)
    return (
        f"QMenu {{ background-color: {palette.surface}; border: 1px solid {palette.border}; border-radius: 6px; padding: 4px; }}"
        f"QMenu::item {{ padding: 6px 24px; border-radius: 4px; margin: 2px 4px; color: {palette.text}; }}"
        f"QMenu::item:selected {{ background-color: {palette.secondary_hover}; color: {palette.text}; }}"
        f"QMenu::separator {{ height: 1px; background-color: {palette.border}; margin: 4px 0px; }}"
        f"QMenu::item:disabled {{ color: {palette.text_secondary}; }}"
    )


def install_chinese_context_menu(widget: QWidget) -> None:
    widget.setContextMenuPolicy(Qt.CustomContextMenu)

    labels = {
        "Undo": "撤销",
        "Redo": "重做",
        "Cut": "剪切",
        "Copy": "复制",
        "Paste": "粘贴",
        "Delete": "删除",
        "Clear": "清空",
        "Select All": "全选",
        "Copy Link Location": "复制链接地址",
        "Open Link": "打开链接",
        "Save Link": "保存链接",
        "Inspect": "检查",
    }

    def show_menu(pos):
        if not hasattr(widget, "createStandardContextMenu"):
            return
        menu = widget.createStandardContextMenu()
        for action in menu.actions():
            raw_text = action.text()
            if not raw_text:
                continue
            label, separator, shortcut = raw_text.partition("\t")
            normalized = label.replace("&", "").replace("...", "").replace("…", "").strip()
            if normalized in labels:
                action.setText(labels[normalized] + (separator + shortcut if separator else ""))
        menu.setStyleSheet(build_menu_stylesheet(widget))
        menu.exec_(widget.mapToGlobal(pos))

    previous_handler = getattr(widget, "_achord_chinese_context_menu_handler", None)
    if previous_handler is not None:
        try:
            widget.customContextMenuRequested.disconnect(previous_handler)
        except Exception:
            pass
    widget._achord_chinese_context_menu_handler = show_menu
    widget.customContextMenuRequested.connect(show_menu)


def build_icon_button_stylesheet(widget: Optional[QWidget], *, danger: bool = False) -> str:
    palette = get_dialog_palette(widget)
    hover_bg = to_rgba("#E5484D" if danger else palette.text, 0.14 if danger else 0.10)
    pressed_bg = to_rgba("#E5484D" if danger else palette.text, 0.22 if danger else 0.18)
    return (
        "QPushButton { background-color: transparent; border: none; border-radius: 4px; }"
        f"QPushButton:hover {{ background-color: {hover_bg}; }}"
        f"QPushButton:pressed {{ background-color: {pressed_bg}; }}"
    )


def build_link_button_stylesheet(widget: Optional[QWidget]) -> str:
    palette = get_dialog_palette(widget)
    link = palette.primary
    hover = palette.primary_hover
    pressed = palette.progress_end
    return (
        "QPushButton { background: transparent; border: none; font-size: 12px; font-weight: 500; padding: 2px 8px; }"
        f"QPushButton {{ color: {link}; }}"
        f"QPushButton:hover {{ color: {hover}; text-decoration: underline; }}"
        f"QPushButton:pressed {{ color: {pressed}; }}"
    )


def build_dialog_stylesheet(widget: Optional[QWidget]) -> str:
    palette = get_dialog_palette(widget)
    return _build_dialog_stylesheet_from_palette(palette)


def build_dialog_stylesheet_for_theme(theme_key: Optional[str]) -> str:
    return _build_dialog_stylesheet_from_palette(get_palette_by_theme(theme_key))


def _build_dialog_stylesheet_from_palette(palette: DialogPalette) -> str:
    return (
        f"QDialog, QMessageBox {{ background: {palette.background}; color: {palette.text}; }}"
        f"QDialog QLabel#updateTitle, QDialog QLabel#progressTitle, QDialog QLabel#dialogTitle {{ font-size: 18px; font-weight: 600; color: {palette.text}; }}"
        f"QDialog QLabel#updateSubtitle, QDialog QLabel#progressSubtitle, QDialog QLabel#dialogSubtitle {{ font-size: 12px; color: {palette.text_secondary}; }}"
        f"QDialog QLabel#updateSection {{ font-size: 12px; color: {palette.text_secondary}; margin-top: 6px; }}"
        f"QDialog QTextBrowser {{ background: {palette.surface}; border: 1px solid {palette.border}; border-radius: 10px; padding: 10px; color: {palette.text}; }}"
        f"QDialog QProgressBar {{ height: 14px; border: 1px solid {palette.border}; border-radius: 7px; background: {palette.surface_alt}; color: {palette.text}; text-align: center; }}"
        f"QDialog QProgressBar::chunk {{ border-radius: 7px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {palette.progress_start}, stop:1 {palette.progress_end}); }}"
        f"QDialog QPushButton, QMessageBox QPushButton {{ background: {palette.secondary}; color: {palette.text}; border: 1px solid {palette.border}; border-radius: 8px; padding: 6px 16px; min-width: 88px; }}"
        f"QDialog QPushButton:hover, QMessageBox QPushButton:hover {{ background: {palette.secondary_hover}; }}"
        f"QPushButton#updateCancel, QPushButton#secondaryButton {{ background: {palette.secondary}; color: {palette.text}; border: 1px solid {palette.border}; }}"
        f"QPushButton#updateCancel:hover, QPushButton#secondaryButton:hover {{ background: {palette.secondary_hover}; }}"
        f"QPushButton#updateOk, QPushButton#primaryButton {{ background: {palette.primary}; color: #FFFFFF; border: 1px solid {palette.primary}; }}"
        f"QPushButton#updateOk:hover, QPushButton#primaryButton:hover {{ background: {palette.primary_hover}; }}"
        f"QMessageBox QLabel {{ color: {palette.text}; background: transparent; padding: 0; margin: 0; min-width: 0px; }}"
        f"QMessageBox QTextEdit {{ background: {palette.surface}; color: {palette.text}; border: 1px solid {palette.border}; }}"
    )


def apply_dialog_theme(widget: QWidget, owner: Optional[QWidget] = None) -> None:
    widget.setStyleSheet(build_dialog_stylesheet(owner or widget))


def show_themed_message(
    owner: Optional[QWidget],
    *,
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    informative_text: Optional[str] = None,
    buttons: QMessageBox.StandardButtons = QMessageBox.Ok,
    default_button: QMessageBox.StandardButton = QMessageBox.NoButton,
    primary_button: QMessageBox.StandardButton = QMessageBox.Ok,
) -> int:
    box = QMessageBox(owner)
    box.setWindowTitle(title)
    box.setIcon(icon)
    box.setText(text)
    if informative_text:
        box.setInformativeText(informative_text)
    box.setStandardButtons(buttons)
    if default_button != QMessageBox.NoButton:
        box.setDefaultButton(default_button)
    box.setWindowFlags(box.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    for button in box.buttons():
        standard_button = box.standardButton(button)
        button.setObjectName("primaryButton" if standard_button == primary_button else "secondaryButton")

    apply_dialog_theme(box, owner)
    return box.exec_()
