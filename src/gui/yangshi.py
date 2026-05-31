"""
应用程序样式表 - 深色主题
"""

MAIN_STYLE = """
QWidget {
    font-family: "SimHei";
}

QMainWindow {
    background: transparent;
}

QWidget#centralWidget {
    background: #2D2D2D;
    border: 1px solid #404040;
    border-radius: 8px;
}

QPushButton {
    background-color: #0A84FF;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    min-width: 80px;
}

QPushButton:hover {
    background-color: #409EFF;
}

QPushButton:pressed {
    background-color: #0D76E3;
}

QComboBox {
    background-color: #363636;
    color: white;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 4px 8px;
    min-width: 100px;
}

QComboBox::drop-down {
    border: none;
}

QComboBox::down-arrow {
    image: url(src/ziyuan/down.svg);
    width: 12px;
    height: 12px;
}

QComboBox QAbstractItemView {
    background-color: #363636;
    color: white;
    selection-background-color: #0A84FF;
    selection-color: white;
    border: 1px solid #404040;
}

QTextEdit {
    background-color: #363636;
    color: white;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 8px;
    selection-background-color: #0A84FF;
    selection-color: white;
}

QLabel {
    color: white;
}

/* 标题栏按钮样式 */
BiaoTiLan QPushButton {
    background: transparent;
    min-width: 32px;
    padding: 4px;
}

BiaoTiLan QPushButton:hover {
    background: rgba(255, 255, 255, 0.1);
}

BiaoTiLan QPushButton:pressed {
    background: rgba(255, 255, 255, 0.2);
}
""" 

