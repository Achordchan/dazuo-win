"""
深色主题样式表
"""

STYLE = """
QWidget {
    color: #FFFFFF;
    font-family: "SimHei";
    font-size: 14px;
}

QTextEdit {
    background-color: #2D2D2D;
    border: 1px solid #404040;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 16px;
    color: #FFFFFF;
    font-family: "SimHei";
    selection-background-color: #0A84FF;
    selection-color: #FFFFFF;
}

QTextEdit:focus {
    border: 1px solid #0A84FF;
    background-color: #333333;
}

QTextEdit[readOnly="true"] {
    font-family: "SimHei";
    color: #E8E8E8;
    font-size: 16px;
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
    border: 1px solid #404040;
    border-radius: 6px;
    padding: 6px 12px;
    min-width: 150px;
    background-color: #2D2D2D;
    color: #FFFFFF;
    font-family: "SimHei";
    font-size: 15px;
}

QComboBox:hover {
    border: 1px solid #505050;
    background-color: #333333;
}

QComboBox:focus {
    border: 1px solid #0A84FF;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #2D2D2D;
    border: 1px solid #404040;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: #0A84FF;
    selection-color: #FFFFFF;
    font-family: "SimHei";
    font-size: 15px;
}

QLabel {
    color: #FFFFFF;
    font-size: 15px;
    padding: 4px 0;
    font-family: "SimHei";
}

QLabel#serviceDisplayPill {
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 14px;
    padding: 6px 12px;
    color: rgba(255, 255, 255, 0.88);
    font-size: 15px;
    font-weight: 600;
}

QFrame#langPill {
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 16px;
}

QLabel#langPillLabel {
    color: rgba(255, 255, 255, 0.70);
    font-size: 16px;
    padding: 0;
}

QLabel#langPillChevron {
    color: rgba(255, 255, 255, 0.55);
    font-size: 16px;
    padding: 0;
}

QComboBox#langComboPill {
    background: transparent;
    border: none;
    color: rgba(255, 255, 255, 0.92);
    font-size: 16px;
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
    background-color: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 10px;
    padding: 0;
}

QPushButton#langSwitchButton:hover:enabled {
    background-color: rgba(255, 255, 255, 0.14);
}

QPushButton#langSwitchButton:pressed:enabled {
    background-color: rgba(255, 255, 255, 0.20);
}

QPushButton#langSwitchButton:disabled {
    background-color: rgba(255, 255, 255, 0.04);
    border-color: rgba(255, 255, 255, 0.08);
}

QFrame#serviceStatusPill {
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 16px;
}

QLabel#serviceStatusLabel {
    color: rgba(255, 255, 255, 0.70);
    font-size: 14px;
    padding: 0;
}

QLabel#serviceSparkle {
    color: #B388FF;
    font-size: 15px;
    padding: 0;
}

QLabel#serviceNameLabel {
    color: rgba(255, 255, 255, 0.90);
    font-size: 15px;
    font-weight: 600;
    padding: 0;
}

QWidget#serviceStatusDot {
    background-color: #4CAF50;
    border-radius: 4px;
}

QLabel#serviceStatusText {
    color: rgba(76, 175, 80, 0.95);
    font-size: 14px;
    padding: 0;
}

QPushButton#floatingIconButton {
    background-color: rgba(45, 45, 45, 0.60);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 4px;
    min-width: 28px;
    padding: 4px;
    color: rgba(255, 255, 255, 0.92);
}

QPushButton#floatingIconButton:hover {
    background-color: rgba(60, 60, 60, 0.80);
}

QPushButton#floatingIconButton:pressed {
    background-color: rgba(70, 70, 70, 0.90);
}

QPushButton#floatingIconButton:disabled {
    background-color: rgba(45, 45, 45, 0.30);
    color: rgba(255, 255, 255, 0.30);
}

QFrame#infoCard {
    background-color: rgba(24, 24, 26, 0.98);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 14px;
}

QLabel#infoTitle {
    color: rgba(255, 255, 255, 0.96);
    font-size: 14px;
    font-weight: 700;
}

QLabel#infoBody {
    color: rgba(255, 255, 255, 0.88);
    font-size: 13px;
}

QLabel#infoSectionTitle {
    color: rgba(255, 255, 255, 0.70);
    font-size: 12px;
    font-weight: 700;
}

QPushButton#infoTooltipCloseButton {
    background: transparent;
    border: none;
}

QPushButton#infoTooltipCloseButton:hover {
    background-color: rgba(255, 255, 255, 0.08);
    border-radius: 8px;
}

QFrame#aiStatusBar {
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    background-color: rgba(0, 0, 0, 0.12);
}

QLabel#aiStatusSparkles {
    color: rgba(255, 255, 255, 0.70);
    font-size: 14px;
}

QLabel#aiStatusText {
    color: rgba(255, 255, 255, 0.70);
    font-size: 13px;
    font-weight: 600;
}

QDialog#settingsDialog {
    background-color: #1E1E1E;
    border: 1px solid #404040;
    border-radius: 8px;
}

QDialog#changelogDialog {
    background-color: #1E1E1E;
    border: 1px solid #404040;
    border-radius: 8px;
}

QTextBrowser#changelogBrowser {
    background-color: #2D2D2D;
    border: 1px solid #404040;
    border-radius: 6px;
    padding: 10px;
    color: #FFFFFF;
    font-size: 14px;
}

QPushButton#changelogOk {
    min-width: 100px;
    height: 36px;
}

QDialog#settingsDialog QTabWidget#settingsTabs::pane {
    border: 1px solid #404040;
    border-radius: 6px;
    background-color: #1E1E1E;
    margin-top: 8px;
}

QDialog#settingsDialog QTabWidget#settingsTabs QTabBar::tab {
    background-color: #2D2D2D;
    color: rgba(255, 255, 255, 0.85);
    border: 1px solid #404040;
    border-bottom: none;
    padding: 8px 18px;
    min-height: 24px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 6px;
    font-size: 16px;
}

QDialog#settingsDialog QTabWidget#settingsTabs QTabBar::tab:selected {
    background-color: #1E1E1E;
    border-color: #0A84FF;
    color: #FFFFFF;
}

QDialog#settingsDialog QTabWidget#settingsTabs QTabBar::tab:!selected:hover {
    background-color: #333333;
}

QDialog#settingsDialog QScrollArea {
    background-color: #1E1E1E;
    border: none;
}

QDialog#settingsDialog QScrollArea::viewport {
    background-color: #1E1E1E;
}

QDialog#settingsDialog QWidget#settingsTabContent {
    background-color: #1E1E1E;
}

QDialog#settingsDialog QScrollArea#baseSettingsScroll,
QDialog#settingsDialog QScrollArea#translationSettingsScroll,
QDialog#settingsDialog QScrollArea#modelSettingsScroll {
    background-color: #1E1E1E;
}

QDialog#settingsDialog QLabel {
    font-size: 17px;
}

QDialog#settingsDialog QPushButton,
QDialog#settingsDialog QComboBox,
QDialog#settingsDialog QCheckBox {
    font-size: 17px;
}

QDialog#settingsDialog QLabel[help="true"] {
    color: rgba(255, 255, 255, 0.55);
    font-size: 13px;
    margin-top: 4px;
    margin-left: 4px;
}

QDialog#settingsDialog QLineEdit {
    background-color: #2D2D2D;
    border: 1px solid #404040;
    border-radius: 6px;
    padding: 8px 12px;
    color: #FFFFFF;
    font-size: 15px;
    min-height: 20px;
}

QDialog#settingsDialog QLineEdit:hover {
    border: 1px solid #505050;
}

QDialog#settingsDialog QLineEdit:focus {
    border: 1px solid #0A84FF;
}

QDialog#settingsDialog QGroupBox {
    border: 1px solid #404040;
    background-color: #2D2D2D;
    border-radius: 6px;
    margin-top: 20px;
    padding-top: 24px;
    color: #FFFFFF;
    font-size: 16px;
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
    background-color: #2D2D2D;
    width: 12px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #505050;
    border-radius: 6px;
    min-height: 20px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #606060;
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
    color: #404040;
    margin: 8px 0;
}

QMainWindow {
    background-color: #1E1E1E;
}

QWidget#centralWidget {
    background-color: #1E1E1E;
    border-radius: 8px;
}

/* 标题栏样式 */
BiaoTiLan {
    background-color: #1E1E1E;
}

BiaoTiLan QLabel {
    color: #FFFFFF;
}

BiaoTiLan QPushButton {
    background: transparent;
    border: none;
    border-radius: 4px;
    min-width: 28px;
    padding: 4px;
    color: #FFFFFF;
}

BiaoTiLan QPushButton:hover {
    background: rgba(255, 255, 255, 0.1);
}

BiaoTiLan QPushButton:pressed {
    background: rgba(255, 255, 255, 0.2);
}

/* 关闭按钮特殊样式 */
QPushButton[toolTip="关闭"] {
    background: transparent;
    border: none;
    color: #CCCCCC;
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

