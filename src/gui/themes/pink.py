"""
粉色主题样式表
"""

STYLE = """
QWidget {
    color: #333333;
    font-family: "PingFang SC", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 14px;
}

QTextEdit {
    background-color: #FFF0F5;
    border: 1px solid #FFB6C1;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 16px;
    line-height: 1.8;
    color: #333333;
    font-family: "PingFang SC", "Microsoft YaHei", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    letter-spacing: 0.4px;
    selection-background-color: #FF69B4;
    selection-color: #FFFFFF;
}

QTextEdit:focus {
    border: 1px solid #FF69B4;
    background-color: #FFF5F8;
}

QTextEdit[readOnly="true"] {
    font-family: "PingFang SC", "Microsoft YaHei", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    color: #333333;
    font-size: 16px;
    line-height: 1.8;
    letter-spacing: 0.4px;
}

QPushButton {
    background-color: #FF69B4;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 15px;
    font-weight: 500;
    min-width: 80px;
    font-family: "PingFang SC", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    letter-spacing: 0.3px;
}

QPushButton:hover {
    background-color: #FF1493;
}

QPushButton:pressed {
    background-color: #DB7093;
}

QComboBox {
    border: 1px solid #FFB6C1;
    border-radius: 6px;
    padding: 6px 12px;
    min-width: 150px;
    background-color: #FFF0F5;
    color: #333333;
    font-family: "PingFang SC", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 15px;
    letter-spacing: 0.2px;
}

QComboBox:hover {
    border: 1px solid #FF69B4;
    background-color: #FFF5F8;
}

QComboBox:focus {
    border: 1px solid #FF69B4;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox::down-arrow {
    image: url(ziyuan/down-arrow.png);
    width: 12px;
    height: 12px;
}

QComboBox QAbstractItemView {
    background-color: #FFF0F5;
    border: 1px solid #FFB6C1;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: #FF69B4;
    selection-color: #FFFFFF;
    font-family: "PingFang SC", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 15px;
}

QLabel {
    color: #333333;
    font-size: 15px;
    padding: 4px 0;
    font-family: "PingFang SC", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    letter-spacing: 0.2px;
}

QLabel#serviceDisplayPill {
    background-color: rgba(255, 105, 180, 0.10);
    border: 1px solid rgba(255, 105, 180, 0.30);
    border-radius: 14px;
    padding: 6px 12px;
    color: rgba(51, 51, 51, 0.78);
    font-size: 13px;
    font-weight: 600;
}

QFrame#langPill {
    background-color: rgba(255, 105, 180, 0.10);
    border: 1px solid rgba(255, 105, 180, 0.28);
    border-radius: 16px;
}

QLabel#langPillLabel {
    color: rgba(51, 51, 51, 0.65);
    font-size: 14px;
    padding: 0;
}

QLabel#langPillChevron {
    color: rgba(51, 51, 51, 0.55);
    font-size: 14px;
    padding: 0;
}

QComboBox#langComboPill {
    background: transparent;
    border: none;
    color: rgba(51, 51, 51, 0.86);
    font-size: 14px;
    padding: 2px 0;
    min-width: 130px;
}

QComboBox#langComboPill::drop-down {
    border: none;
    width: 0px;
}

QComboBox#langComboPill::down-arrow {
    image: none;
    width: 0px;
    height: 0px;
}

QPushButton#langSwitchButton {
    background-color: rgba(255, 105, 180, 0.12);
    border: 1px solid rgba(255, 105, 180, 0.30);
    border-radius: 10px;
    padding: 0;
}

QPushButton#langSwitchButton:hover:enabled {
    background-color: rgba(255, 105, 180, 0.20);
}

QPushButton#langSwitchButton:pressed:enabled {
    background-color: rgba(255, 105, 180, 0.28);
}

QPushButton#langSwitchButton:disabled {
    background-color: rgba(255, 105, 180, 0.08);
    border-color: rgba(255, 105, 180, 0.18);
}

QFrame#serviceStatusPill {
    background-color: rgba(255, 105, 180, 0.10);
    border: 1px solid rgba(255, 105, 180, 0.28);
    border-radius: 16px;
}

QLabel#serviceStatusLabel {
    color: rgba(51, 51, 51, 0.65);
    font-size: 12px;
    padding: 0;
}

QLabel#serviceSparkle {
    color: #B86AD9;
    font-size: 13px;
    padding: 0;
}

QLabel#serviceNameLabel {
    color: rgba(51, 51, 51, 0.82);
    font-size: 13px;
    font-weight: 600;
    padding: 0;
}

QWidget#serviceStatusDot {
    background-color: #4CAF50;
    border-radius: 4px;
}

QLabel#serviceStatusText {
    color: rgba(76, 175, 80, 0.95);
    font-size: 12px;
    padding: 0;
}

QPushButton#floatingIconButton {
    background-color: rgba(255, 105, 180, 0.16);
    border: 1px solid rgba(255, 105, 180, 0.28);
    border-radius: 4px;
    min-width: 28px;
    padding: 4px;
    color: rgba(51, 51, 51, 0.88);
}

QPushButton#floatingIconButton:hover {
    background-color: rgba(255, 105, 180, 0.22);
}

QPushButton#floatingIconButton:pressed {
    background-color: rgba(255, 105, 180, 0.28);
}

QPushButton#floatingIconButton:disabled {
    background-color: rgba(255, 105, 180, 0.10);
    color: rgba(51, 51, 51, 0.30);
}

QFrame#infoCard {
    background-color: rgba(255, 245, 248, 0.98);
    border: 1px solid rgba(255, 105, 180, 0.28);
    border-radius: 10px;
}

QLabel#infoTitle {
    color: rgba(51, 51, 51, 0.92);
    font-size: 12px;
    font-weight: 700;
}

QLabel#infoBody {
    color: rgba(51, 51, 51, 0.78);
    font-size: 11px;
}

QLabel#infoSectionTitle {
    color: rgba(51, 51, 51, 0.58);
    font-size: 10px;
    font-weight: 700;
}

QPushButton#infoTooltipCloseButton {
    background: transparent;
    border: none;
}

QPushButton#infoTooltipCloseButton:hover {
    background-color: rgba(255, 105, 180, 0.16);
    border-radius: 6px;
}

QFrame#aiStatusBar {
    border-top: 1px solid rgba(255, 105, 180, 0.18);
    background-color: rgba(255, 105, 180, 0.08);
}

QLabel#aiStatusSparkles {
    color: rgba(51, 51, 51, 0.60);
    font-size: 12px;
}

QLabel#aiStatusText {
    color: rgba(51, 51, 51, 0.60);
    font-size: 11px;
    font-weight: 600;
}

QDialog#settingsDialog {
    background-color: #FFF0F5;
    border: 1px solid #FFB6C1;
    border-radius: 8px;
}

QDialog#changelogDialog {
    background-color: #FFF0F5;
    border: 1px solid #FFB6C1;
    border-radius: 8px;
}

QTextBrowser#changelogBrowser {
    background-color: #FFF5F8;
    border: 1px solid #FFB6C1;
    border-radius: 6px;
    padding: 10px;
    color: #333333;
    font-size: 14px;
    line-height: 1.6;
}

QPushButton#changelogOk {
    min-width: 100px;
    height: 36px;
}

QDialog#settingsDialog QTabWidget#settingsTabs::pane {
    border: 1px solid #FFB6C1;
    border-radius: 6px;
    background-color: #FFF0F5;
    margin-top: 8px;
}

QDialog#settingsDialog QTabWidget#settingsTabs QTabBar::tab {
    background-color: #FFF5F8;
    color: rgba(51, 51, 51, 0.78);
    border: 1px solid #FFB6C1;
    border-bottom: none;
    padding: 6px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 6px;
}

QDialog#settingsDialog QTabWidget#settingsTabs QTabBar::tab:selected {
    background-color: #FFF0F5;
    border-color: #FF69B4;
    color: #333333;
}

QDialog#settingsDialog QTabWidget#settingsTabs QTabBar::tab:!selected:hover {
    background-color: #FFE7EF;
}

QDialog#settingsDialog QScrollArea {
    background-color: #FFC5C5;
    border: none;
}

QDialog#settingsDialog QScrollArea::viewport {
    background-color: #FFC5C5;
}

QDialog#settingsDialog QLabel[help="true"] {
    color: rgba(51, 51, 51, 0.65);
    font-size: 11px;
    margin-top: 4px;
    margin-left: 4px;
}

QDialog#settingsDialog QLineEdit {
    background-color: #FFF5F8;
    border: 1px solid #FFB6C1;
    border-radius: 6px;
    padding: 8px 12px;
    color: #333333;
    font-size: 13px;
    min-height: 20px;
}

QDialog#settingsDialog QLineEdit:hover {
    border: 1px solid #FF69B4;
}

QDialog#settingsDialog QLineEdit:focus {
    border: 1px solid #FF69B4;
}

QDialog#settingsDialog QGroupBox {
    border: 1px solid #FFB6C1;
    background-color: #FFF5F8;
    border-radius: 6px;
    margin-top: 20px;
    padding-top: 24px;
    color: #333333;
    font-size: 14px;
    font-weight: bold;
}

QDialog#settingsDialog QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    top: 8px;
    padding: 0 8px;
}

QScrollBar:vertical {
    border: none;
    background-color: #FFF0F5;
    width: 12px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #FFB6C1;
    border-radius: 6px;
    min-height: 20px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #FF69B4;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: none;
}

QFrame[frameShape="4"] {
    color: #FFB6C1;
    margin: 8px 0;
}

QMainWindow {
    background-color: #FFF0F5;
}

QWidget#centralWidget {
    background-color: #FFF0F5;
    border-radius: 8px;
}

/* 标题栏样式 */
BiaoTiLan {
    background-color: #FFF0F5;
}

BiaoTiLan QLabel {
    color: #333333;
}

BiaoTiLan QPushButton {
    background: transparent;
    border: none;
    border-radius: 4px;
    min-width: 28px;
    padding: 4px;
    color: #333333;
}

BiaoTiLan QPushButton:hover {
    background: rgba(255, 105, 180, 0.2);
}

BiaoTiLan QPushButton:pressed {
    background: rgba(255, 105, 180, 0.3);
}

/* 关闭按钮特殊样式 */
QPushButton[toolTip="关闭"] {
    background: transparent;
    border: none;
    color: #666666;
    font-family: "PingFang SC", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 16px;
    padding: 0;
    min-width: 32px;
}

QPushButton[toolTip="关闭"]:hover {
    background: #E81123;
    color: white;
}

QPushButton[toolTip="关闭"]:pressed {
    background: #F1707A;
    color: white;
}
""" 

