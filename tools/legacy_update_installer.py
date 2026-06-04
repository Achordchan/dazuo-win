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
APP_ID = "5E76B529-0B3B-4E93-AE4D-DCF0EA7174CE"


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


def _default_install_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local_appdata) / "Programs" / APP_NAME


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def _ps_literal(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _candidate_from_exe_path(value: str) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.startswith('"'):
        end = raw.find('"', 1)
        raw = raw[1:end] if end > 1 else raw.strip('"')
    if "," in raw:
        raw = raw.split(",", 1)[0]
    lower = raw.lower()
    exe_marker = ".exe"
    if exe_marker in lower:
        raw = raw[: lower.index(exe_marker) + len(exe_marker)]
    path = Path(raw.strip().strip('"'))
    if not path:
        return None
    if path.suffix.lower() == ".exe":
        return path.parent
    return path


def _valid_install_dir(path: Path) -> bool:
    try:
        return (path / EXE_NAME).is_file()
    except OSError:
        return False


def _unique_existing_dirs(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    for path in paths:
        if not path or not _valid_install_dir(path):
            continue
        if any(_same_path(path, seen) for seen in unique):
            continue
        unique.append(path)
    return unique


def _registry_install_dirs() -> list[Path]:
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []

    roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    candidates: list[Path] = []
    for hive, base_key in roots:
        try:
            with winreg.OpenKey(hive, base_key) as key:
                count = winreg.QueryInfoKey(key)[0]
                for index in range(count):
                    try:
                        subkey_name = winreg.EnumKey(key, index)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            values = {}
                            for value_name in ("DisplayName", "InstallLocation", "DisplayIcon", "UninstallString"):
                                try:
                                    values[value_name] = winreg.QueryValueEx(subkey, value_name)[0]
                                except OSError:
                                    values[value_name] = ""
                    except OSError:
                        continue

                    display_name = str(values.get("DisplayName") or "")
                    if APP_NAME not in display_name and APP_ID.lower() not in subkey_name.lower():
                        continue

                    install_location = str(values.get("InstallLocation") or "").strip()
                    if install_location:
                        candidates.append(Path(install_location))
                    for value_name in ("DisplayIcon", "UninstallString"):
                        candidate = _candidate_from_exe_path(str(values.get(value_name) or ""))
                        if candidate:
                            candidates.append(candidate)
        except OSError:
            continue
    return candidates


def _running_install_dirs() -> list[Path]:
    if sys.platform != "win32":
        return []
    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Get-CimInstance Win32_Process |
    Where-Object {{ $_.Name -eq {_ps_literal(EXE_NAME)} -and $_.ExecutablePath }} |
    Select-Object -ExpandProperty ExecutablePath |
    ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    data = result.stdout.strip()
    if not data:
        return []
    try:
        paths = json.loads(data)
    except json.JSONDecodeError:
        return []
    if isinstance(paths, str):
        paths = [paths]
    return [Path(path).parent for path in paths if path]


def _shortcut_target(shortcut_path: Path) -> Path | None:
    if sys.platform != "win32" or not shortcut_path.exists():
        return None
    script = f"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_literal(shortcut_path)})
$shortcut.TargetPath
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    target = result.stdout.strip()
    if not target:
        return None
    path = Path(target)
    if path.name.lower() != EXE_NAME.lower():
        return None
    return path.parent


def _shortcut_install_dirs() -> list[Path]:
    public_desktop = os.environ.get("PUBLIC")
    shortcuts = [
        _startup_menu_dir() / f"{APP_NAME}.lnk",
        _desktop_dir() / f"{APP_NAME}.lnk",
    ]
    if public_desktop:
        shortcuts.append(Path(public_desktop) / "Desktop" / f"{APP_NAME}.lnk")
    return [target for shortcut in shortcuts if (target := _shortcut_target(shortcut))]


def _known_install_dirs() -> list[Path]:
    candidates = [
        _default_install_dir(),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / APP_NAME,
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / APP_NAME,
    ]
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{letter}:\\")
        if not root.exists():
            continue
        candidates.append(root / APP_NAME)
        candidates.append(root / "Program Files" / APP_NAME)
    return candidates


def _install_candidates_by_source() -> list[tuple[str, Path]]:
    raw: list[tuple[str, Path]] = []
    for source, getter in (
        ("registry", _registry_install_dirs),
        ("running", _running_install_dirs),
        ("shortcut", _shortcut_install_dirs),
        ("known", _known_install_dirs),
    ):
        for path in getter():
            raw.append((source, path))

    unique: list[tuple[str, Path]] = []
    for source, path in raw:
        if not _valid_install_dir(path):
            continue
        if any(_same_path(path, seen) for _, seen in unique):
            continue
        unique.append((source, path))
    return unique


def _choose_install_dir(candidates: list[tuple[str, Path]]) -> Path:
    if not candidates:
        return _default_install_dir()
    for source, path in candidates:
        if source == "registry":
            return path
    default_dir = _default_install_dir()
    for _, path in candidates:
        if not _same_path(path, default_dir):
            return path
    return candidates[0][1]


def _install_dir() -> Path:
    return _choose_install_dir(_install_candidates_by_source())


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
    engine_payload_path = source_dir / "engines" / "deeplx" / "windows" / "amd64" / "deeplx.exe.payload"
    if not manifest_path.is_file():
        raise RuntimeError("安装包缺少版本清单。")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    version = str(manifest.get("app_version") or "").strip()
    if not version:
        raise RuntimeError("安装包版本清单无效。")
    for path in (exe_path, icon_path):
        if not path.is_file():
            raise RuntimeError(f"安装包缺少必要文件：{path.relative_to(source_dir)}")
    if not engine_path.is_file() and not engine_payload_path.is_file():
        raise RuntimeError("安装包缺少内置翻译引擎文件。")
    return version


def _stop_running_app(install_dirs: list[Path]) -> None:
    subprocess.run(
        ["taskkill.exe", "/IM", EXE_NAME, "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    for install_dir in install_dirs:
        if not install_dir.exists():
            continue
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


def _backup_dir(prefix: str) -> Path:
    backup_root = Path.home() / ".dzfyq" / "update_backup"
    backup_root.mkdir(parents=True, exist_ok=True)
    return backup_root / f"{prefix}_{int(time.time())}"


def _copy_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.move(str(target), str(_backup_dir("setup")))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)


def _backup_duplicate_install_dirs(install_dir: Path, discovered_dirs: list[Path]) -> None:
    duplicates = [
        path
        for path in _unique_existing_dirs(discovered_dirs)
        if not _same_path(path, install_dir)
    ]
    for index, duplicate in enumerate(duplicates, start=1):
        if not duplicate.exists():
            continue
        shutil.move(str(duplicate), str(_backup_dir(f"setup_duplicate_{index}")))


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
        install_candidates = _install_candidates_by_source()
        install_dir = _choose_install_dir(install_candidates)
        discovered_dirs = _unique_existing_dirs([path for _, path in install_candidates] + [install_dir])
        with tempfile.TemporaryDirectory(prefix="dazuofanyiguan_setup_") as temp:
            source_dir = Path(temp) / "package"
            source_dir.mkdir(parents=True)
            _safe_extract(zip_path, source_dir)
            version = _validate_source(source_dir)
            _stop_running_app(discovered_dirs)
            _copy_tree(source_dir, install_dir)
            _backup_duplicate_install_dirs(install_dir, discovered_dirs)

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
