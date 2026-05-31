"""
浅色主题样式表
"""

STYLE = """
QWidget {
    color: #000000;
    font-family: "SimHei";
    font-size: 14px;
}

QTextEdit {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 16px;
    line-height: 1.8;
    color: #000000;
    font-family: "SimHei";
    selection-background-color: #0A84FF;
    selection-color: #FFFFFF;
}

QTextEdit:focus {
    border: 1px solid #0A84FF;
    background-color: #FFFFFF;
}

QTextEdit[readOnly="true"] {
    font-family: "SimHei";
    color: #333333;
    font-size: 16px;
    line-height: 1.8;
}

QPushButton {
    background-color: #0A84FF;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 15px;
    font-weight: 500;
    min-width: 80px;
    font-family: "SimHei";
}

QPushButton:hover {
    background-color: #0071E3;
}

QPushButton:pressed {
    background-color: #0062C4;
}

QComboBox {
    border: 1px solid #E0E0E0;
    border-radius: 6px;
    padding: 6px 12px;
    min-width: 150px;
    background-color: #FFFFFF;
    color: #000000;
    font-family: "SimHei";
    font-size: 15px;
}

QComboBox:hover {
    border: 1px solid #D0D0D0;
    background-color: #F8F8F8;
}

QComboBox:focus {
    border: 1px solid #0A84FF;
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
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: #0A84FF;
    selection-color: #FFFFFF;
    font-family: "SimHei";
    font-size: 15px;
}

QLabel {
    color: #000000;
    font-size: 15px;
    padding: 4px 0;
    font-family: "SimHei";
}

QLabel#serviceDisplayPill {
    background-color: rgba(0, 0, 0, 0.04);
    border: 1px solid rgba(0, 0, 0, 0.10);
    border-radius: 14px;
    padding: 6px 12px;
    color: rgba(0, 0, 0, 0.78);
    font-size: 13px;
    font-weight: 600;
}

QFrame#langPill {
    background-color: rgba(0, 0, 0, 0.04);
    border: 1px solid rgba(0, 0, 0, 0.10);
    border-radius: 16px;
}

QLabel#langPillLabel {
    color: rgba(0, 0, 0, 0.60);
    font-size: 14px;
    padding: 0;
}

QLabel#langPillChevron {
    color: rgba(0, 0, 0, 0.45);
    font-size: 14px;
    padding: 0;
}

QComboBox#langComboPill {
    background: transparent;
    border: none;
    color: rgba(0, 0, 0, 0.82);
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
    background-color: rgba(0, 0, 0, 0.04);
    border: 1px solid rgba(0, 0, 0, 0.10);
    border-radius: 10px;
    padding: 0;
}

QPushButton#langSwitchButton:hover:enabled {
    background-color: rgba(0, 0, 0, 0.08);
}

QPushButton#langSwitchButton:pressed:enabled {
    background-color: rgba(0, 0, 0, 0.12);
}

QPushButton#langSwitchButton:disabled {
    background-color: rgba(0, 0, 0, 0.02);
    border-color: rgba(0, 0, 0, 0.06);
}

QFrame#serviceStatusPill {
    background-color: rgba(0, 0, 0, 0.04);
    border: 1px solid rgba(0, 0, 0, 0.10);
    border-radius: 16px;
}

QLabel#serviceStatusLabel {
    color: rgba(0, 0, 0, 0.60);
    font-size: 12px;
    padding: 0;
}

QLabel#serviceSparkle {
    color: #8E6BE8;
    font-size: 13px;
    padding: 0;
}

QLabel#serviceNameLabel {
    color: rgba(0, 0, 0, 0.80);
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
    background-color: rgba(0, 0, 0, 0.06);
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 4px;
    min-width: 28px;
    padding: 4px;
    color: rgba(0, 0, 0, 0.80);
}

QPushButton#floatingIconButton:hover {
    background-color: rgba(0, 0, 0, 0.10);
}

QPushButton#floatingIconButton:pressed {
    background-color: rgba(0, 0, 0, 0.14);
}

QPushButton#floatingIconButton:disabled {
    background-color: rgba(0, 0, 0, 0.04);
    color: rgba(0, 0, 0, 0.25);
}

QFrame#infoCard {
    background-color: rgba(255, 255, 255, 0.98);
    border: 1px solid rgba(0, 0, 0, 0.10);
    border-radius: 10px;
}

QLabel#infoTitle {
    color: rgba(0, 0, 0, 0.86);
    font-size: 12px;
    font-weight: 700;
}

QLabel#infoBody {
    color: rgba(0, 0, 0, 0.74);
    font-size: 11px;
}

QLabel#infoSectionTitle {
    color: rgba(0, 0, 0, 0.50);
    font-size: 10px;
    font-weight: 700;
}

QPushButton#infoTooltipCloseButton {
    background: transparent;
    border: none;
}

QPushButton#infoTooltipCloseButton:hover {
    background-color: rgba(0, 0, 0, 0.06);
    border-radius: 6px;
}

QFrame#aiStatusBar {
    border-top: 1px solid rgba(0, 0, 0, 0.08);
    background-color: rgba(0, 0, 0, 0.04);
}

QLabel#aiStatusSparkles {
    color: rgba(0, 0, 0, 0.55);
    font-size: 12px;
}

QLabel#aiStatusText {
    color: rgba(0, 0, 0, 0.55);
    font-size: 11px;
    font-weight: 600;
}

QDialog#settingsDialog {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 8px;
}

QDialog#changelogDialog {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 8px;
}

QTextBrowser#changelogBrowser {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 6px;
    padding: 10px;
    color: #000000;
    font-size: 14px;
    line-height: 1.6;
}

QPushButton#changelogOk {
    min-width: 100px;
    height: 36px;
}

QDialog#settingsDialog QTabWidget#settingsTabs::pane {
    border: 1px solid #E0E0E0;
    border-radius: 6px;
    background-color: #FFFFFF;
    margin-top: 8px;
}

QDialog#settingsDialog QTabWidget#settingsTabs QTabBar::tab {
    background-color: #F5F5F5;
    color: rgba(0, 0, 0, 0.75);
    border: 1px solid #E0E0E0;
    border-bottom: none;
    padding: 6px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 6px;
}

QDialog#settingsDialog QTabWidget#settingsTabs QTabBar::tab:selected {
    background-color: #FFFFFF;
    border-color: #0A84FF;
    color: #000000;
}

QDialog#settingsDialog QTabWidget#settingsTabs QTabBar::tab:!selected:hover {
    background-color: #F0F0F0;
}

QDialog#settingsDialog QScrollArea {
    background-color: #FFFFFF;
    border: none;
}

QDialog#settingsDialog QScrollArea::viewport {
    background-color: #FFFFFF;
}

QDialog#settingsDialog QLabel[help="true"] {
    color: rgba(0, 0, 0, 0.55);
    font-size: 11px;
    margin-top: 4px;
    margin-left: 4px;
}

QDialog#settingsDialog QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 6px;
    padding: 8px 12px;
    color: #000000;
    font-size: 13px;
    min-height: 20px;
}

QDialog#settingsDialog QLineEdit:hover {
    border: 1px solid #D0D0D0;
}

QDialog#settingsDialog QLineEdit:focus {
    border: 1px solid #0A84FF;
}

QDialog#settingsDialog QGroupBox {
    border: 1px solid #E0E0E0;
    background-color: #FFFFFF;
    border-radius: 6px;
    margin-top: 20px;
    padding-top: 24px;
    color: #000000;
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
    background-color: #F5F5F5;
    width: 12px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #C0C0C0;
    border-radius: 6px;
    min-height: 20px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #A0A0A0;
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
    color: #E0E0E0;
    margin: 8px 0;
}

QMainWindow {
    background-color: #F5F5F5;
}

QWidget#centralWidget {
    background-color: #F5F5F5;
    border-radius: 8px;
}

/* 标题栏样式 */
BiaoTiLan {
    background-color: #F5F5F5;
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
    background: rgba(0, 0, 0, 0.1);
}

BiaoTiLan QPushButton:pressed {
    background: rgba(0, 0, 0, 0.2);
}

/* 关闭按钮特殊样式 */
QPushButton[toolTip="关闭"] {
    background: transparent;
    border: none;
    color: #666666;
    font-family: "SimHei";
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

