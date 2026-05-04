import logging
import os
import sys
import plistlib
from typing import List

logger = logging.getLogger(__name__)


def _get_src_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_project_root() -> str:
    return os.path.dirname(_get_src_dir())


def _get_resource_path(relative_path: str) -> str:
    if getattr(sys, "frozen", False):
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base_dir = _get_project_root()
    return os.path.join(base_dir, relative_path)


def _get_launch_command() -> List[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "src.main"]


def _get_working_directory() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return _get_project_root()


def _get_icon_path() -> str:
    icon_path = _get_resource_path(os.path.join("src", "ziyuan", "logo.ico"))
    return icon_path if os.path.exists(icon_path) else sys.executable


def configure_autostart(enabled: bool) -> None:
    if sys.platform == "win32":
        _configure_windows_autostart(enabled)
        return
    if sys.platform == "darwin":
        _configure_macos_autostart(enabled)
        return


def is_autostart_enabled() -> bool:
    try:
        if sys.platform == "win32":
            return os.path.exists(_get_windows_shortcut_path())
        if sys.platform == "darwin":
            return os.path.exists(_get_macos_plist_path())
    except Exception as exc:
        logger.warning("检查开机自启状态失败: %s", exc)
    return False


def apply_macos_dock_visibility(show_in_dock: bool) -> None:
    if sys.platform != "darwin":
        return
    try:
        from AppKit import (  # type: ignore
            NSApplication,
            NSApplicationActivationPolicyAccessory,
            NSApplicationActivationPolicyRegular,
        )
    except Exception as exc:
        logger.warning("无法设置 Dock 显示状态: %s", exc)
        return

    try:
        app = NSApplication.sharedApplication()
        policy = (
            NSApplicationActivationPolicyRegular
            if show_in_dock
            else NSApplicationActivationPolicyAccessory
        )
        app.setActivationPolicy_(policy)
    except Exception as exc:
        logger.warning("设置 Dock 显示状态失败: %s", exc)


def _get_windows_startup_dir() -> str:
    appdata = os.getenv("APPDATA", "")
    if not appdata:
        raise RuntimeError("无法获取 Windows 启动目录")
    return os.path.join(
        appdata,
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
    )


def _get_windows_shortcut_path() -> str:
    return os.path.join(_get_windows_startup_dir(), "大佐翻译官.lnk")


def _configure_windows_autostart(enabled: bool) -> None:
    startup_dir = _get_windows_startup_dir()
    shortcut_path = _get_windows_shortcut_path()
    if not enabled:
        if os.path.exists(shortcut_path):
            os.remove(shortcut_path)
        return

    try:
        import win32com.client  # type: ignore
    except Exception as exc:
        raise RuntimeError("缺少 pywin32，无法设置开机自启") from exc

    os.makedirs(startup_dir, exist_ok=True)
    command = _get_launch_command()
    target = command[0]
    arguments = ""
    if len(command) > 1:
        arguments = " ".join(f'"{arg}"' for arg in command[1:])

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.Targetpath = target
    shortcut.Arguments = arguments
    shortcut.WorkingDirectory = _get_working_directory()
    shortcut.IconLocation = _get_icon_path()
    shortcut.save()


def _get_macos_plist_path() -> str:
    return os.path.expanduser("~/Library/LaunchAgents/com.achord.dazuofanyiguan.plist")


def _configure_macos_autostart(enabled: bool) -> None:
    plist_path = _get_macos_plist_path()
    launch_agents_dir = os.path.dirname(plist_path)

    if not enabled:
        if os.path.exists(plist_path):
            os.remove(plist_path)
        return

    os.makedirs(launch_agents_dir, exist_ok=True)
    plist_data = {
        "Label": "com.achord.dazuofanyiguan",
        "ProgramArguments": _get_launch_command(),
        "RunAtLoad": True,
    }

    with open(plist_path, "wb") as f:
        plistlib.dump(plist_data, f)
