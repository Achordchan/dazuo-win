"""
大佐翻译官主程序
"""
import os
import sys
import site
import logging
import ctypes
import argparse
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QSharedMemory

def get_resource_path(relative_path):
    """获取资源文件的绝对路径"""
    try:
        # PyInstaller创建临时文件夹,将路径存储在_MEIPASS
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            # 获取脚本所在的目录
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        return os.path.abspath(os.path.join(base_path, relative_path))
    except Exception as e:
        logging.error(f"获取资源路径失败: {e}")
        return None

# 必须在创建任何窗口之前设置应用程序ID
if sys.platform == 'win32':
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("achord.bagayalu.translate.1.0")
    except Exception as e:
        print(f"设置应用程序ID失败: {e}")

# 设置 Qt 插件路径
if sys.platform == 'win32' or sys.platform == 'darwin':
    try:
        import PyQt5
        qt_platform_path = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins', 'platforms')
        qt_plugin_path = os.path.dirname(qt_platform_path)
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = qt_platform_path
        os.environ['QT_PLUGIN_PATH'] = qt_plugin_path
        logging.info(f"Qt platform plugin path: {qt_platform_path}")
        logging.info(f"Qt plugin path: {qt_plugin_path}")
    except Exception as e:
        logging.error(f"设置Qt插件路径失败: {e}")

# 设置日志
try:
    if sys.platform == 'win32':
        base_log_dir = os.getenv('APPDATA')
    elif sys.platform == 'darwin':
        base_log_dir = os.path.expanduser('~/Library/Logs')
    else:
        base_log_dir = os.path.expanduser('~/.cache')

    log_dir = os.path.join(base_log_dir or os.path.expanduser('~'), '大佐翻译官', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(log_dir, 'app.log'),
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
except Exception as e:
    print(f"设置日志失败: {e}")

def check_resources():
    """检查资源文件"""
    try:
        resource_dir = get_resource_path('src/ziyuan')
        logging.info(f"Resource directory: {resource_dir}")
        
        if not resource_dir or not os.path.exists(resource_dir):
            logging.error(f"Resource directory not found: {resource_dir}")
            return False
        
        # 检查必要的图标文件
        required_icons = ['logo.ico', 'ai.svg', 'switch.svg', 'source.svg', 'target.svg', 'copy.svg']
        missing_icons = []
        
        for icon in required_icons:
            icon_path = os.path.join(resource_dir, icon)
            if os.path.exists(icon_path):
                logging.info(f"Found icon: {icon}")
            else:
                logging.error(f"Missing icon: {icon}")
                missing_icons.append(icon)
        
        if missing_icons:
            logging.error(f"Missing required icons: {', '.join(missing_icons)}")
            return False
            
        return True
    except Exception as e:
        logging.error(f"检查资源文件失败: {e}")
        return False

# 将项目根目录添加到Python路径
if getattr(sys, 'frozen', False):
    project_root = sys._MEIPASS
else:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

candidate_paths = [
    project_root,
    os.path.join(project_root, 'src'),
    os.path.join(project_root, 'dazuofanyiguan'),
    os.path.join(project_root, 'dazuofanyiguan', 'src'),
]
for path in candidate_paths:
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

if getattr(sys, 'frozen', False) and os.path.isdir(project_root):
    try:
        os.chdir(project_root)
    except Exception as e:
        logging.error(f"切换工作目录失败: {e}")

import asyncio
import qasync
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from src.gui.zhuchuangkou import ZhuChuangKou

def handle_exception(exc_type, exc_value, exc_traceback):
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

# 设置未捕获异常的处理器
sys.excepthook = handle_exception

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    return parser.parse_args()

def main():
    """主程序入口"""
    try:
        # 检查资源文件
        if not check_resources():
            logging.error("资源文件检查失败，程序可能无法正常运行")
            # 继续运行，但记录错误
        
        # 首先隐藏控制台
        if not args.debug and sys.platform == 'win32':
            kernel32 = ctypes.WinDLL('kernel32')
            user32 = ctypes.WinDLL('user32')
            hwnd = kernel32.GetConsoleWindow()
            if hwnd:
                user32.ShowWindow(hwnd, 0)  # SW_HIDE = 0

        # 创建应用程序
        app = QApplication(sys.argv)
        
        # 设置应用程序信息
        app.setApplicationName("大佐翻译官")
        app.setApplicationDisplayName("大佐翻译官")
        app.setOrganizationName("Achord")
        app.setOrganizationDomain("github.com/Achordchan")
        
        # 获取图标路径
        icon_path = get_resource_path('src/ziyuan/logo.ico')
        if not icon_path or not os.path.exists(icon_path):
            icon_path = get_resource_path('src/ziyuan/logo.svg')
        
        if icon_path and os.path.exists(icon_path):
            try:
                app_icon = QIcon(icon_path)
                app.setWindowIcon(app_icon)
                logging.info(f"Set application icon from: {icon_path}")
                
                # 确保在 Windows 上设置任务栏图标
                if sys.platform == 'win32':
                    try:
                        import win32gui
                        import win32con
                        
                        def set_taskbar_icon():
                            try:
                                hwnd = win32gui.GetForegroundWindow()
                                if hwnd:
                                    logging.info("Skip taskbar icon WM_SETICON")
                            except Exception as e:
                                logging.error(f"设置任务栏图标失败: {e}")
                        
                        # 使用 QTimer 延迟设置图标
                        from PyQt5.QtCore import QTimer
                        QTimer.singleShot(100, set_taskbar_icon)
                    except Exception as e:
                        logging.error(f"初始化任务栏图标失败: {e}")
            except Exception as e:
                logging.error(f"设置应用程序图标失败: {e}")
        else:
            logging.error(f"Application icon not found at: {icon_path}")
        
        # 确保加载 SVG 支持
        try:
            from PyQt5.QtSvg import QSvgRenderer
            logging.info("SVG support loaded")
        except Exception as e:
            logging.error(f"加载SVG支持失败: {e}")
        
        # 防止应用程序过早退出
        app.setQuitOnLastWindowClosed(False)
        
        # 创建事件循环
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        
        # 创建共享内存对象用于检查是否已有实例运行
        shared_memory = QSharedMemory('DaZaoFanYiGuanSingleInstance')
        
        # 尝试创建共享内存
        if not shared_memory.create(1):
            # 如果创建失败，说明已经有一个实例在运行
            QMessageBox.warning(
                None,
                "程序已在运行",
                "大佐翻译官已经在运行中。\n\n请检查系统托盘或任务栏，或使用任务管理器查看。",
                QMessageBox.Ok
            )
            return
        
        # 创建主窗口
        window = ZhuChuangKou()
        # 保持窗口引用
        app.window = window
        
        # 显示窗口
        window.show()
        
        # 运行事件循环
        with loop:
            try:
                loop.run_forever()
            finally:
                try:
                    if hasattr(window, "fanyi") and hasattr(window.fanyi, "close_current_api"):
                        loop.run_until_complete(window.fanyi.close_current_api())
                except Exception as e:
                    logging.error(f"关闭翻译会话失败: {e}")
            
    except Exception as e:
        logging.error(f"程序运行出错: {e}")
        sys.exit(1)

if __name__ == "__main__":
    args = parse_args()
    main() 