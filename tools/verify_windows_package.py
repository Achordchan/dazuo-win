import configparser
import json
import sys
import tempfile
import zipfile
from pathlib import Path


def _version_parts(version: str) -> tuple[int, int, int]:
    parts = []
    for part in str(version or "").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if digits:
            parts.append(int(digits))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _exe_file_version(exe_path: Path) -> tuple[int, int, int]:
    try:
        import win32api  # type: ignore

        info = win32api.GetFileVersionInfo(str(exe_path), "\\")
        ms = int(info["FileVersionMS"])
        ls = int(info["FileVersionLS"])
        return (ms >> 16, ms & 0xFFFF, ls >> 16)
    except Exception as error:
        raise RuntimeError(f"cannot read executable version: {exe_path}: {error}") from error


def _require_file(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.is_file():
        raise RuntimeError(f"missing required package file: {relative}")
    return path


def verify_package(zip_path: Path, expected_version: str) -> None:
    if not zip_path.is_file():
        raise FileNotFoundError(f"package not found: {zip_path}")
    if not zipfile.is_zipfile(zip_path):
        raise RuntimeError(f"not a valid zip package: {zip_path}")

    with tempfile.TemporaryDirectory(prefix="dzfyq_verify_package_") as temp:
        root = Path(temp)
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                target = (root / member.filename).resolve()
                if root.resolve() not in target.parents and target != root.resolve():
                    raise RuntimeError(f"zip contains unsafe path: {member.filename}")
            archive.extractall(root)

        manifest_path = _require_file(root, "update_manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        manifest_version = str(manifest.get("app_version") or "").strip()
        if _version_parts(manifest_version) != _version_parts(expected_version):
            raise RuntimeError(
                f"manifest version mismatch: expected {expected_version}, found {manifest_version}"
            )

        exe_path = _require_file(root, "大佐翻译官.exe")
        exe_version = _exe_file_version(exe_path)
        if exe_version != _version_parts(expected_version):
            raise RuntimeError(
                f"executable version mismatch: expected {expected_version}, found {exe_version}"
            )

        _require_file(root, "src/ziyuan/logo.ico")
        _require_file(root, "PyQt5/qt-plugins/platforms/qwindows.dll")
        _require_file(root, "engines/deeplx/windows/amd64/deeplx.exe")
        _require_file(root, "engines/deeplx/windows/amd64/LICENSE")
        _require_file(root, "engines/deeplx/windows/amd64/manifest.json")

        first_run = _require_file(root, "src/config/first_run.ini")
        parser = configparser.ConfigParser()
        parser.read(first_run, encoding="utf-8")
        packaged_first_run = parser.get("App", "first_run", fallback="")
        packaged_last_version = parser.get("App", "last_version", fallback="")
        if packaged_first_run.strip() != "0" or packaged_last_version.strip() != "0.0.0":
            raise RuntimeError(
                "first_run.ini must be the package template: first_run = 0, last_version = 0.0.0"
            )


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: verify_windows_package.py <zip_path> <expected_version>")
        return 2
    verify_package(Path(sys.argv[1]).resolve(), sys.argv[2])
    print(f"Verified Windows package: {sys.argv[1]} ({sys.argv[2]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
