from __future__ import annotations

from PyQt5.QtWidgets import QTextEdit


MIN_TEXT_FONT_SIZE = 12
MAX_TEXT_FONT_SIZE = 28
DEFAULT_TEXT_FONT_SIZE = 18
_FONT_STYLE_START = "/* achord-display-font-size:start */"
_FONT_STYLE_END = "/* achord-display-font-size:end */"


def clamp_text_font_size(value, default: int = DEFAULT_TEXT_FONT_SIZE) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = default
    return max(MIN_TEXT_FONT_SIZE, min(MAX_TEXT_FONT_SIZE, size))


def apply_text_edit_font_size(widget: QTextEdit, size: int) -> None:
    font_size = clamp_text_font_size(size)
    font = widget.font()
    font.setPixelSize(font_size)
    widget.setFont(font)
    widget.document().setDefaultFont(font)
    widget.setStyleSheet(_with_text_edit_font_size(widget.styleSheet(), font_size))


def _with_text_edit_font_size(stylesheet: str, font_size: int) -> str:
    base = _remove_text_edit_font_size(stylesheet or "").strip()
    override = (
        f"{_FONT_STYLE_START}\n"
        f"QTextEdit {{ font-size: {font_size}px; }}\n"
        f"QTextEdit[readOnly=\"true\"] {{ font-size: {font_size}px; }}\n"
        f"{_FONT_STYLE_END}"
    )
    return f"{base}\n\n{override}".strip() if base else override


def _remove_text_edit_font_size(stylesheet: str) -> str:
    start = stylesheet.find(_FONT_STYLE_START)
    end = stylesheet.find(_FONT_STYLE_END)
    if start == -1 or end == -1 or end < start:
        return stylesheet
    return stylesheet[:start] + stylesheet[end + len(_FONT_STYLE_END):]
