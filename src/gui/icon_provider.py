import logging
import os

from PyQt5.QtGui import QIcon

from .dialog_utils import get_palette_by_theme

logger = logging.getLogger(__name__)

try:
    import qtawesome.iconic_font as _qta_iconic_font

    _qta_iconic_font.IconicFont._install_fonts = lambda self, fonts_directory, system_wide=False: fonts_directory

    import qtawesome as qta
except Exception as error:  # pragma: no cover - fallback for environments without qtawesome
    qta = None
    logger.warning("QtAwesome is unavailable, falling back to SVG icons: %s", error)


ICON_MAP = {
    "app": "fa6s.language",
    "about": "fa6s.circle-info",
    "author": "fa6s.user",
    "phone": "fa6s.phone",
    "mail": "fa6s.envelope",
    "version": "fa6s.code-branch",
    "license": "fa6s.scale-balanced",
    "link": "fa6s.arrow-up-right-from-square",
    "settings": "fa6s.gear",
    "theme": "fa6s.palette",
    "mini_mode": "fa6s.window-restore",
    "copy": "fa6s.copy",
    "info": "fa6s.circle-info",
    "close": "fa6s.xmark",
    "minimize": "fa6s.minus",
    "maximize": "fa6s.expand",
    "restore": "fa6s.compress",
    "switch": "fa6s.arrow-right-arrow-left",
    "check": "fa6s.check",
}

FALLBACK_SVG = {
    "app": "ai.svg",
    "about": "info.svg",
    "author": "about-author.svg",
    "phone": "about-phone.svg",
    "mail": "about-mail.svg",
    "version": "about-version.svg",
    "license": "about-license.svg",
    "link": "about-link.svg",
    "settings": "settings.svg",
    "theme": "theme.svg",
    "mini_mode": "mini_mode.svg",
    "copy": "copy.svg",
    "info": "info.svg",
    "close": "close.svg",
    "minimize": "close.svg",
    "maximize": "restore.svg",
    "restore": "restore.svg",
    "switch": "switch.svg",
}


def color_for_theme(theme_name: str, role: str = "text") -> str:
    palette = get_palette_by_theme(theme_name)
    if role == "secondary":
        return palette.text_secondary
    if role == "primary":
        return palette.primary
    if role == "danger":
        return "#E5484D"
    return palette.text


def themed_icon(name: str, theme_name: str = "dark", role: str = "text", fallback_dir: str = "src/ziyuan") -> QIcon:
    if qta is not None:
        try:
            return qta.icon(ICON_MAP[name], color=color_for_theme(theme_name, role))
        except Exception as error:
            logger.warning("Failed to create QtAwesome icon '%s': %s", name, error)

    fallback_name = FALLBACK_SVG.get(name)
    if fallback_name:
        fallback_path = os.path.join(fallback_dir, fallback_name)
        if os.path.exists(fallback_path):
            return QIcon(fallback_path)
    return QIcon()
