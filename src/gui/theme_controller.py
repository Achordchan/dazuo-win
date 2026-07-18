import logging
logger = logging.getLogger(__name__)

from PyQt5.QtWidgets import QMenu, QAction

from .dialog_utils import build_menu_stylesheet
from .icon_provider import themed_icon
from .output_widgets import InfoTooltipPopup


def on_theme_change(self):
    """主题切换按钮点击事件处理"""
    try:
        logger.info("打开主题选择菜单")

        theme_menu = QMenu(self)
        theme_menu.setStyleSheet(build_menu_stylesheet(self))

        theme_map = {
            "深色主题": "dark",
            "浅色主题": "light",
            "粉色主题": "pink",
        }

        current_theme = self.config.get("theme", "dark")

        for display_name, theme_name in theme_map.items():
            action = QAction(display_name, self)
            action.triggered.connect(lambda checked, t=theme_name: self._apply_theme(t))
            if theme_name == current_theme:
                action.setIcon(themed_icon("check", current_theme, "primary"))
            theme_menu.addAction(action)

        theme_btn = self.sender()
        if theme_btn:
            pos = theme_btn.mapToGlobal(theme_btn.rect().bottomLeft())
            theme_menu.exec_(pos)
            logger.info(f"主题菜单显示在位置: ({pos.x()}, {pos.y()})")

    except Exception as e:
        logger.error(f"显示主题菜单失败: {e}")
        self.tishi.showMessage("主题切换失败", type="error")


def apply_theme(self, theme_name):
    """应用主题

    Args:
        theme_name: 主题名称
    """
    try:
        logger.info(f"切换到主题: {theme_name}")

        valid_themes = {"dark", "light", "pink"}
        if theme_name not in valid_themes:
            theme_name = "dark"
        current_theme = self.config.get("theme", "dark")
        if current_theme != theme_name:
            self.config.set("theme", theme_name)

        theme_map = {
            "dark": "深色主题",
            "light": "浅色主题",
            "pink": "粉色主题",
        }
        display_name = theme_map.get(theme_name, "深色主题")
        style = self.theme_manager.get_theme_style(display_name)

        self.setStyleSheet(style)
        if self.style() is not None:
            self.style().unpolish(self)
            self.style().polish(self)

        update_button_icons(self, theme_name)

        try:
            if hasattr(self, "source_lang_combo") and hasattr(self.source_lang_combo, "hidePopup"):
                self.source_lang_combo.hidePopup()
            if hasattr(self, "target_lang_combo") and hasattr(self.target_lang_combo, "hidePopup"):
                self.target_lang_combo.hidePopup()
            if hasattr(self, "source_lang_combo") and hasattr(self.source_lang_combo, "refresh_theme"):
                self.source_lang_combo.refresh_theme()
            if hasattr(self, "target_lang_combo") and hasattr(self.target_lang_combo, "refresh_theme"):
                self.target_lang_combo.refresh_theme()
        except Exception:
            pass

        try:
            if hasattr(self, "theme_changed"):
                self.theme_changed.emit()
            if hasattr(self, "centralWidget") and self.centralWidget():
                self.centralWidget().update()
            self.update()
            self.repaint()
        except Exception:
            pass

        logger.info("主题切换完成")

    except Exception as e:
        logger.error(f"应用主题失败: {e}")
        self.tishi.showMessage("主题应用失败", type="error")


def update_button_icons(self, theme_name):
    """更新按钮图标以适应主题

    Args:
        theme_name: 主题名称
    """
    try:
        if hasattr(self, "switch_button"):
            self.switch_button.setIcon(themed_icon("switch", theme_name, "primary"))

        toolbar_icons = (
            ('toolbar_theme_button', 'theme'),
            ('toolbar_mini_button', 'mini_mode'),
            ('toolbar_settings_button', 'settings'),
        )
        for attribute, icon_name in toolbar_icons:
            button = getattr(self, attribute, None)
            if button is not None:
                button.setIcon(themed_icon(icon_name, theme_name, 'secondary'))

        for attribute in ('source_chevron', 'target_chevron'):
            label = getattr(self, attribute, None)
            if label is not None:
                label.setPixmap(themed_icon('chevron_down', theme_name, 'secondary').pixmap(12, 12))

        if hasattr(self, 'service_icon_label'):
            self.service_icon_label.setPixmap(
                themed_icon('translation', theme_name, 'primary').pixmap(15, 15)
            )
        if hasattr(self, 'source_panel_icon'):
            self.source_panel_icon.setPixmap(
                themed_icon('source_text', theme_name, 'secondary').pixmap(15, 15)
            )
        if hasattr(self, 'target_panel_icon'):
            self.target_panel_icon.setPixmap(
                themed_icon('translation', theme_name, 'primary').pixmap(15, 15)
            )
        if hasattr(self, 'clear_source_button'):
            self.clear_source_button.setIcon(themed_icon('clear', theme_name, 'secondary'))
        if hasattr(self, 'copy_translation_button'):
            self.copy_translation_button.setIcon(themed_icon('copy', theme_name, 'secondary'))

        if hasattr(self, 'output_text') and hasattr(self.output_text, 'copy_button'):
            self.output_text.copy_button.setIcon(themed_icon("copy", theme_name))

        if hasattr(self, 'output_text') and hasattr(self.output_text, 'ai_info_button'):
            self.output_text.ai_info_button.setIcon(themed_icon("info", theme_name))
        if hasattr(self, 'ai_status_bar') and hasattr(self.ai_status_bar, 'info_button'):
            self.ai_status_bar.info_button.setIcon(themed_icon("info", theme_name))
        if hasattr(self, 'ai_status_bar') and hasattr(self.ai_status_bar, 'sparkles'):
            self.ai_status_bar.sparkles.setPixmap(
                themed_icon('translation', theme_name, 'primary').pixmap(14, 14)
            )

        if hasattr(self, 'biaotilan') and hasattr(self.biaotilan, 'apply_icons'):
            self.biaotilan.apply_icons(theme_name)
        if hasattr(self, 'biaotilan') and hasattr(self.biaotilan, 'apply_theme'):
            self.biaotilan.apply_theme(theme_name)

        popup = InfoTooltipPopup.get_instance()
        if hasattr(popup, 'close_button'):
            popup.close_button.setIcon(themed_icon("close", theme_name, "danger"))
        if hasattr(popup, 'apply_theme'):
            popup.apply_theme(theme_name)

    except Exception as e:
        logger.error(f"更新按钮图标失败: {e}")
