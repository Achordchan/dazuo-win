"""大佐翻译官主程序。"""

import argparse
import asyncio
import ctypes
import logging
import os
import sys
from typing import Optional

import qasync
from PyQt5.QtCore import QSharedMemory, QTimer
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.gongju.autostart import configure_autostart, is_autostart_enabled
from src.gui.dialog_utils import build_dialog_stylesheet_for_theme
from src.shezhi import Config


def _get_frozen_base_dir():
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS

    exe_dir = os.path.dirname(sys.executable)
    dist_dir = os.path.join(exe_dir, f"{os.path.splitext(os.path.basename(sys.executable))[0]}.dist")
    if os.path.isdir(dist_dir):
        return dist_dir
    return exe_dir


def setup_platform_app_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("achord.bagayalu.translate.1.0")
    except Exception as error:
        print(f"设置应用程序ID失败: {error}")


def setup_qt_plugin_paths() -> None:
    if sys.platform not in {"win32", "darwin"}:
        return
    try:
        import PyQt5

        qt_platform_path = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins", "platforms")
        qt_plugin_path = os.path.dirname(qt_platform_path)
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = qt_platform_path
        os.environ["QT_PLUGIN_PATH"] = qt_plugin_path
        logging.info(f"Qt platform plugin path: {qt_platform_path}")
        logging.info(f"Qt plugin path: {qt_plugin_path}")
    except Exception as error:
        logging.error(f"设置Qt插件路径失败: {error}")


def setup_logging() -> None:
    try:
        if sys.platform == "win32":
            base_log_dir = os.getenv("APPDATA")
        elif sys.platform == "darwin":
            base_log_dir = os.path.expanduser("~/Library/Logs")
        else:
            base_log_dir = os.path.expanduser("~/.cache")

        log_dir = os.path.join(base_log_dir or os.path.expanduser("~"), "大佐翻译官", "logs")
        os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(
            filename=os.path.join(log_dir, "app.log"),
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
    except Exception as error:
        print(f"设置日志失败: {error}")


def _ensure_project_paths() -> None:
    if getattr(sys, "frozen", False):
        project_root = _get_frozen_base_dir()
    else:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    candidate_paths = [
        project_root,
        os.path.join(project_root, "src"),
        os.path.join(project_root, "dazuofanyiguan"),
        os.path.join(project_root, "dazuofanyiguan", "src"),
    ]
    for path in candidate_paths:
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

    if getattr(sys, "frozen", False) and os.path.isdir(project_root):
        try:
            os.chdir(project_root)
        except Exception as error:
            logging.error(f"切换工作目录失败: {error}")


setup_platform_app_identity()
setup_qt_plugin_paths()
setup_logging()
_ensure_project_paths()

from src.gui.zhuchuangkou import ZhuChuangKou


def get_resource_path(relative_path):
    try:
        base_path = _get_frozen_base_dir() if getattr(sys, "frozen", False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.abspath(os.path.join(base_path, relative_path))
    except Exception as error:
        logging.error(f"获取资源路径失败: {error}")
        return None


def check_resources():
    try:
        resource_dir = get_resource_path("src/ziyuan")
        logging.info(f"Resource directory: {resource_dir}")
        if not resource_dir or not os.path.exists(resource_dir):
            logging.error(f"Resource directory not found: {resource_dir}")
            return False

        required_icons = ["logo.ico", "ai.svg", "switch.svg", "source.svg", "target.svg", "copy.svg"]
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
    except Exception as error:
        logging.error(f"检查资源文件失败: {error}")
        return False


def handle_exception(exc_type, exc_value, exc_traceback):
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = handle_exception


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    return parser.parse_args()


def hide_console_if_needed(debug: bool) -> None:
    if debug or sys.platform != "win32":
        return

    kernel32 = ctypes.WinDLL("kernel32")
    user32 = ctypes.WinDLL("user32")
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        user32.ShowWindow(hwnd, 0)


def create_application() -> QApplication:
    app = QApplication(sys.argv)
    app.setApplicationName("大佐翻译官")
    app.setApplicationDisplayName("大佐翻译官")
    app.setOrganizationName("Achord")
    app.setOrganizationDomain("github.com/Achordchan")
    app.setQuitOnLastWindowClosed(False)
    setup_application_fonts(app)
    return app


def setup_application_fonts(app: QApplication) -> None:
    preferred_family = "SimHei" if sys.platform == "win32" else "Heiti SC"
    logging.info(f"使用系统字体: {preferred_family}")

    font = QFont(preferred_family)
    font.setWeight(QFont.Normal)
    font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
    try:
        font.setHintingPreference(QFont.PreferDefaultHinting)
    except Exception:
        pass
    app.setFont(font)


def set_application_icon(app: QApplication) -> None:
    icon_path = get_resource_path("src/ziyuan/logo.ico")
    if not icon_path or not os.path.exists(icon_path):
        icon_path = get_resource_path("src/ziyuan/logo.svg")

    if not icon_path or not os.path.exists(icon_path):
        logging.error(f"Application icon not found at: {icon_path}")
        return

    try:
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)
        logging.info(f"Set application icon from: {icon_path}")

        if sys.platform == "win32":
            def set_taskbar_icon():
                try:
                    import win32gui

                    hwnd = win32gui.GetForegroundWindow()
                    if hwnd:
                        logging.info("Skip taskbar icon WM_SETICON")
                except Exception as error:
                    logging.error(f"设置任务栏图标失败: {error}")

            QTimer.singleShot(100, set_taskbar_icon)
    except Exception as error:
        logging.error(f"设置应用程序图标失败: {error}")


def ensure_svg_support() -> None:
    try:
        from PyQt5.QtSvg import QSvgRenderer  # noqa: F401

        logging.info("SVG support loaded")
    except Exception as error:
        logging.error(f"加载SVG支持失败: {error}")


def create_async_loop(app: QApplication):
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    return loop


def repair_autostart_if_needed() -> None:
    try:
        config = Config()
        if not config.get("auto_start", False):
            return
        if is_autostart_enabled():
            return
        configure_autostart(True)
        logging.info("已修复开机自启入口")
    except Exception as error:
        logging.error(f"修复开机自启入口失败: {error}")


def enforce_single_instance() -> Optional[QSharedMemory]:
    shared_memory = QSharedMemory("DaZaoFanYiGuanSingleInstance")
    if shared_memory.create(1):
        return shared_memory

    stale_segment = QSharedMemory("DaZaoFanYiGuanSingleInstance")
    if stale_segment.attach():
        stale_segment.detach()
        if shared_memory.create(1):
            return shared_memory

    message_box = QMessageBox()
    message_box.setWindowTitle("程序已在运行")
    message_box.setText("大佐翻译官已经在运行中。")
    message_box.setInformativeText("请检查系统托盘或任务栏，或使用任务管理器查看。")
    message_box.setIcon(QMessageBox.Warning)
    message_box.setStandardButtons(QMessageBox.Ok)
    try:
        theme_key = Config().get("theme", "dark")
    except Exception:
        theme_key = "dark"
    message_box.setStyleSheet(build_dialog_stylesheet_for_theme(theme_key))
    message_box.exec_()
    return None


def create_main_window() -> ZhuChuangKou:
    return ZhuChuangKou()


def shutdown_async_resources(window: ZhuChuangKou, loop) -> None:
    try:
        try:
            all_tasks = asyncio.all_tasks(loop)
        except TypeError:
            all_tasks = asyncio.all_tasks()

        pending = [task for task in all_tasks if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        if hasattr(window, "fanyi") and hasattr(window.fanyi, "close_current_api"):
            loop.run_until_complete(window.fanyi.close_current_api())

        loop.run_until_complete(loop.shutdown_asyncgens())
    except Exception as error:
        logging.error(f"关闭翻译会话失败: {error}")


def main():
    args = parse_args()
    try:
        if not check_resources():
            logging.error("资源文件检查失败，程序可能无法正常运行")

        hide_console_if_needed(args.debug)
        app = create_application()
        set_application_icon(app)
        ensure_svg_support()
        loop = create_async_loop(app)

        shared_memory = enforce_single_instance()
        if shared_memory is None:
            return

        repair_autostart_if_needed()
        window = create_main_window()
        app.window = window
        app.shared_memory = shared_memory
        window.show()

        with loop:
            try:
                loop.run_forever()
            finally:
                shutdown_async_resources(window, loop)
    except Exception as error:
        logging.error(f"程序运行出错: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
