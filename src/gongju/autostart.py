import logging
import os
import sys
import json
import plistlib
import subprocess
from typing import List, Optional

logger = logging.getLogger(__name__)


def _get_src_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_project_root() -> str:
    return os.path.dirname(_get_src_dir())


def _is_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False) or globals().get("__compiled__"))


def _get_runtime_base_dir() -> str:
    if _is_packaged_app():
        return os.path.dirname(os.path.abspath(sys.executable))
    return _get_project_root()


def _get_resource_path(relative_path: str) -> str:
    return os.path.join(_get_runtime_base_dir(), relative_path)


def _get_launch_command() -> List[str]:
    if _is_packaged_app():
        return [sys.executable]
    return [sys.executable, "-m", "src.main"]


def _get_working_directory() -> str:
    return _get_runtime_base_dir()


def _get_icon_path() -> str:
    icon_path = _get_resource_path(os.path.join("src", "ziyuan", "logo.ico"))
    return icon_path if os.path.exists(icon_path) else sys.executable


def _normalize_path(path: str) -> str:
    if not path:
        return ""
    return os.path.normcase(os.path.abspath(os.path.expandvars(path or "")))


def _format_windows_arguments(arguments: List[str]) -> str:
    return subprocess.list2cmdline(arguments)


def _normalize_windows_arguments(arguments: str) -> str:
    return " ".join(part.strip('"') for part in (arguments or "").split())


def _powershell_literal(value: str) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _run_powershell(script: str, *, capture_output: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        check=True,
        capture_output=capture_output,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=12,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def configure_autostart(enabled: bool) -> None:
    if sys.platform == "win32":
        _configure_windows_autostart(enabled)
        return
    if sys.platform == "darwin":
        _configure_macos_autostart(enabled)
        return


def get_autostart_state() -> Optional[bool]:
    try:
        if sys.platform == "win32":
            shortcut_path = _get_windows_shortcut_path()
            return os.path.exists(shortcut_path) and _windows_shortcut_matches(shortcut_path)
        if sys.platform == "darwin":
            plist_path = _get_macos_plist_path()
            return os.path.exists(plist_path) and _macos_plist_matches(plist_path)
    except Exception as exc:
        logger.warning("检查开机自启状态失败: %s", exc)
        return None
    return False


def is_autostart_enabled() -> bool:
    return bool(get_autostart_state())


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


def _windows_shortcut_matches(shortcut_path: str) -> bool:
    try:
        shortcut = _read_windows_shortcut(shortcut_path)
    except Exception as exc:
        logger.warning("无法读取开机自启快捷方式，按未启用处理: %s", exc)
        return False

    command = _get_launch_command()

    target = shortcut.get("TargetPath", "")
    expanded_target = os.path.expandvars(target)
    if not target or not os.path.exists(expanded_target):
        return False
    if _normalize_path(target) != _normalize_path(command[0]):
        return False

    expected_arguments = _format_windows_arguments(command[1:])
    if _normalize_windows_arguments(shortcut.get("Arguments", "")) != _normalize_windows_arguments(expected_arguments):
        return False

    working_directory = shortcut.get("WorkingDirectory", "")
    return _normalize_path(working_directory) == _normalize_path(_get_working_directory())


def _read_windows_shortcut(shortcut_path: str) -> dict:
    script = f"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut({_powershell_literal(shortcut_path)})
[PSCustomObject]@{{
  TargetPath = $shortcut.TargetPath
  Arguments = $shortcut.Arguments
  WorkingDirectory = $shortcut.WorkingDirectory
}} | ConvertTo-Json -Compress
"""
    result = _run_powershell(script, capture_output=True)
    return json.loads((result.stdout or "{}").strip())


def _configure_windows_autostart(enabled: bool) -> None:
    startup_dir = _get_windows_startup_dir()
    shortcut_path = _get_windows_shortcut_path()
    if not enabled:
        if os.path.exists(shortcut_path):
            os.remove(shortcut_path)
        return

    os.makedirs(startup_dir, exist_ok=True)
    command = _get_launch_command()
    target = command[0]
    arguments = _format_windows_arguments(command[1:])
    script = f"""
$ErrorActionPreference = 'Stop'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut({_powershell_literal(shortcut_path)})
$shortcut.TargetPath = {_powershell_literal(target)}
$shortcut.Arguments = {_powershell_literal(arguments)}
$shortcut.WorkingDirectory = {_powershell_literal(_get_working_directory())}
$shortcut.IconLocation = {_powershell_literal(_get_icon_path())}
$shortcut.Save()
"""
    try:
        _run_powershell(script)
    except Exception as exc:
        raise RuntimeError(f"设置开机自启失败: {exc}") from exc

    if not os.path.exists(shortcut_path):
        raise RuntimeError("设置开机自启失败：启动快捷方式未生成")


def _get_macos_plist_path() -> str:
    return os.path.expanduser("~/Library/LaunchAgents/com.achord.dazuofanyiguan.plist")


def _macos_plist_matches(plist_path: str) -> bool:
    try:
        with open(plist_path, "rb") as file:
            plist_data = plistlib.load(file)
    except Exception as exc:
        logger.warning("读取 macOS 开机自启 plist 失败: %s", exc)
        return False

    return (
        plist_data.get("ProgramArguments") == _get_launch_command()
        and bool(plist_data.get("RunAtLoad"))
        and plist_data.get("WorkingDirectory") == _get_working_directory()
    )


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
        "WorkingDirectory": _get_working_directory(),
        "RunAtLoad": True,
    }

    with open(plist_path, "wb") as f:
        plistlib.dump(plist_data, f)
