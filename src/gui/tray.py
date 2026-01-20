import logging
logger = logging.getLogger(__name__)

import os

from PyQt5.QtWidgets import QMenu, QSystemTrayIcon, QShortcut
from PyQt5.QtGui import QIcon, QKeySequence


def init_tray(self):
    # 创建系统托盘图标
    self.tray_icon = QSystemTrayIcon(self)
    self.tray_icon.setIcon(QIcon(os.path.join(self.resource_dir, 'logo.svg')))
    self.tray_icon.setToolTip("大佐翻译官")
    
    # 创建托盘菜单
    self.tray_menu = QMenu()
    
    # 添加菜单项
    show_action = self.tray_menu.addAction("显示主窗口")
    show_action.triggered.connect(self.show)
    
    # 添加Mini模式切换
    self.mini_mode_action = self.tray_menu.addAction("Mini模式 (Alt+M)")
    self.mini_mode_action.setCheckable(True)
    self.mini_mode_action.setChecked(self.config.get("mini_mode", False))
    self.mini_mode_action.triggered.connect(lambda checked: self._toggle_mini_mode(checked, show_hint=True))
    
    # 添加显示/隐藏Mini窗口选项
    self.toggle_mini_window_action = self.tray_menu.addAction("显示/隐藏Mini窗口 (Alt+H)")
    self.toggle_mini_window_action.triggered.connect(self._toggle_mini_window)
    self.toggle_mini_window_action.setEnabled(False)  # 默认禁用
    
    # 添加Mini模式快捷键
    self.mini_mode_shortcut = QShortcut(QKeySequence("Alt+M"), self)
    self.mini_mode_shortcut.activated.connect(self._toggle_mini_mode_shortcut)
    
    # 添加显示/隐藏Mini窗口快捷键
    self.toggle_mini_window_shortcut = QShortcut(QKeySequence("Alt+H"), self)
    self.toggle_mini_window_shortcut.activated.connect(self._toggle_mini_window)
    
    # 添加分隔线
    self.tray_menu.addSeparator()
    
    # 添加作者信息（禁用状态）
    app_info = self.tray_menu.addAction("🌟 大佐翻译官")
    app_info.setEnabled(False)
    author_info = self.tray_menu.addAction("👤 作者: Achord")
    author_info.setEnabled(False)
    
    # 添加分隔线
    self.tray_menu.addSeparator()
    
    # 添加退出选项
    quit_action = self.tray_menu.addAction("退出")
    quit_action.triggered.connect(self._quit_app)
    
    # 设置托盘菜单样式
    self.tray_menu.setStyleSheet("""
        QMenu {
            background-color: #2D2D2D;
            border: 1px solid #404040;
            border-radius: 4px;
            padding: 4px;
        }
        QMenu::item {
            padding: 6px 24px;
            border-radius: 4px;
            color: #FFFFFF;
        }
        QMenu::item:selected {
            background-color: #404040;
        }
        QMenu::separator {
            height: 1px;
            background-color: #404040;
            margin: 4px 0px;
        }
        QMenu::item:disabled {
            color: #808080;
        }
    """)
    
    # 设置托盘菜单
    self.tray_icon.setContextMenu(self.tray_menu)
    
    # 连接托盘图标的点击事件
    self.tray_icon.activated.connect(self._on_tray_icon_activated)
    
    # 显示托盘图标
    self.tray_icon.show()
