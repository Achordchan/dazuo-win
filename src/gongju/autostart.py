import logging
import os
import sys
import plistlib
from typing import List

logger = logging.getLogger(__name__)


def _get_src_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_main_script() -> str:
    return os.path.join(_get_src_dir(), "main.py")


def _get_launch_command() -> List[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, _get_main_script()]


def configure_autostart(enabled: bool) -> None:
    if sys.platform == "win32":
        _configure_windows_autostart(enabled)
        return
    if sys.platform == "darwin":
        _configure_macos_autostart(enabled)
        return


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


def _configure_windows_autostart(enabled: bool) -> None:
    startup_dir = os.path.join(
        os.getenv("APPDATA", ""),
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
    )
    if not startup_dir:
        raise RuntimeError("无法获取 Windows 启动目录")

    shortcut_path = os.path.join(startup_dir, "大佐翻译官.lnk")
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
    shortcut.WorkingDirectory = os.path.dirname(target)
    shortcut.IconLocation = target
    shortcut.save()


def _configure_macos_autostart(enabled: bool) -> None:
    launch_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
    plist_path = os.path.join(launch_agents_dir, "com.achord.dazuofanyiguan.plist")

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
