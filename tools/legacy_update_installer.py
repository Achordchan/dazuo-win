import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


APP_NAME = "大佐翻译官"
EXE_NAME = f"{APP_NAME}.exe"


def _message(title: str, text: str, flags: int = 0x40) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, flags)
    except Exception:
        print(f"{title}: {text}")


def _payload_zip() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    payload_dir = base / "payload"
    candidates = sorted(payload_dir.glob("dazuofanyiguan_full.for.windows_*.zip"))
    if not candidates:
        candidates = sorted(base.glob("dazuofanyiguan_full.for.windows_*.zip"))
    if not candidates:
        raise FileNotFoundError("安装器缺少内置全量更新包。")
    return candidates[-1]


def _install_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local_appdata) / "Programs" / APP_NAME


def _startup_menu_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME


def _desktop_dir() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"


def _safe_extract(zip_path: Path, target: Path) -> None:
    root = target.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            destination = (root / member.filename).resolve()
            if root not in destination.parents and destination != root:
                raise RuntimeError("安装包内包含非法路径。")
        archive.extractall(root)


def _validate_source(source_dir: Path) -> str:
    manifest_path = source_dir / "update_manifest.json"
    exe_path = source_dir / EXE_NAME
    icon_path = source_dir / "src" / "ziyuan" / "logo.ico"
    engine_path = source_dir / "engines" / "deeplx" / "windows" / "amd64" / "deeplx.exe"
    if not manifest_path.is_file():
        raise RuntimeError("安装包缺少版本清单。")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    version = str(manifest.get("app_version") or "").strip()
    if not version:
        raise RuntimeError("安装包版本清单无效。")
    for path in (exe_path, icon_path, engine_path):
        if not path.is_file():
            raise RuntimeError(f"安装包缺少必要文件：{path.relative_to(source_dir)}")
    return version


def _stop_running_app(install_dir: Path) -> None:
    subprocess.run(
        ["taskkill.exe", "/IM", EXE_NAME, "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    if install_dir.exists():
        root = str(install_dir.resolve()).rstrip("\\") + "\\"
        script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$root = {_ps_literal(root)}
Get-CimInstance Win32_Process -Filter "Name = 'deeplx.exe'" |
    Where-Object {{
        $_.ExecutablePath -and
        [System.IO.Path]::GetFullPath($_.ExecutablePath).StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)
    }} |
    ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
"""
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    time.sleep(0.5)


def _copy_tree(source: Path, target: Path) -> None:
    if target.exists():
        backup_root = Path.home() / ".dzfyq" / "update_backup"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_dir = backup_root / f"setup_{int(time.time())}"
        shutil.move(str(target), str(backup_dir))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)


def _ps_literal(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _create_shortcut(path: Path, target: Path, working_dir: Path, icon: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    script = f"""
$ErrorActionPreference = 'Stop'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_literal(path)})
$shortcut.TargetPath = {_ps_literal(target)}
$shortcut.Arguments = ''
$shortcut.WorkingDirectory = {_ps_literal(working_dir)}
$shortcut.IconLocation = {_ps_literal(icon)}
$shortcut.Save()
"""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=True,
    )


def main() -> int:
    try:
        zip_path = _payload_zip()
        install_dir = _install_dir()
        with tempfile.TemporaryDirectory(prefix="dazuofanyiguan_setup_") as temp:
            source_dir = Path(temp) / "package"
            source_dir.mkdir(parents=True)
            _safe_extract(zip_path, source_dir)
            version = _validate_source(source_dir)
            _stop_running_app(install_dir)
            _copy_tree(source_dir, install_dir)

        exe_path = install_dir / EXE_NAME
        icon_path = install_dir / "src" / "ziyuan" / "logo.ico"
        _create_shortcut(_startup_menu_dir() / f"{APP_NAME}.lnk", exe_path, install_dir, icon_path)
        _create_shortcut(_desktop_dir() / f"{APP_NAME}.lnk", exe_path, install_dir, icon_path)
        subprocess.Popen([str(exe_path)], cwd=str(install_dir), close_fds=True)
        _message("安装完成", f"{APP_NAME} v{version} 已安装。")
        return 0
    except Exception as error:
        _message("安装失败", str(error), flags=0x10)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
