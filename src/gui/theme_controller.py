import logging
logger = logging.getLogger(__name__)

import os

from PyQt5.QtWidgets import QMenu, QAction
from PyQt5.QtGui import QIcon

from .output_widgets import InfoTooltipPopup


def on_theme_change(self):
    """主题切换按钮点击事件处理"""
    try:
        logger.info("打开主题选择菜单")

        theme_menu = QMenu(self)
        theme_menu.setStyleSheet(
            """
                QMenu {
                    background-color: #2D2D2D;
                    border: 1px solid #404040;
                    border-radius: 6px;
                    padding: 4px;
                }
                QMenu::item {
                    padding: 8px 24px;
                    border-radius: 4px;
                    margin: 2px 4px;
                    color: #FFFFFF;
                }
                QMenu::item:selected {
                    background-color: #0A84FF;
                }
            """
        )

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
                action.setIcon(QIcon("src/ziyuan/theme.svg"))
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

        theme_map = {
            "dark": "深色主题",
            "light": "浅色主题",
            "pink": "粉色主题",
        }
        display_name = theme_map.get(theme_name, "深色主题")
        style = self.theme_manager.get_theme_style(display_name)

        self.setStyleSheet(style)

        update_button_icons(self, theme_name)

        self.config.set("theme", theme_name)

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
        switch_icon = f"src/ziyuan/switch-{theme_name}.svg"
        if os.path.exists(switch_icon):
            self.switch_button.setIcon(QIcon(switch_icon))
            logger.info(f"更新切换按钮图标: {switch_icon}")

        is_dark = theme_name == "dark"
        copy_icon = "src/ziyuan/copy-white.svg" if is_dark else "src/ziyuan/copy-black.svg"
        info_icon = "src/ziyuan/info.svg" if is_dark else "src/ziyuan/info-black.svg"
        close_icon = "src/ziyuan/close-white.svg" if is_dark else "src/ziyuan/close-black.svg"

        if hasattr(self, 'output_text') and hasattr(self.output_text, 'copy_button') and os.path.exists(copy_icon):
            self.output_text.copy_button.setIcon(QIcon(copy_icon))

        if os.path.exists(info_icon):
            if hasattr(self, 'output_text') and hasattr(self.output_text, 'ai_info_button'):
                self.output_text.ai_info_button.setIcon(QIcon(info_icon))
            if hasattr(self, 'ai_status_bar') and hasattr(self.ai_status_bar, 'info_button'):
                self.ai_status_bar.info_button.setIcon(QIcon(info_icon))

        if hasattr(self, 'biaotilan') and hasattr(self.biaotilan, 'apply_icons'):
            self.biaotilan.apply_icons(theme_name)

        popup = InfoTooltipPopup.get_instance()
        if hasattr(popup, 'close_button') and os.path.exists(close_icon):
            popup.close_button.setIcon(QIcon(close_icon))
        if hasattr(popup, 'apply_theme'):
            popup.apply_theme(theme_name)

    except Exception as e:
        logger.error(f"更新按钮图标失败: {e}")
