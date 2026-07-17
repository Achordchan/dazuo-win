import configparser
import json
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gongju.update_trust import verify_package_authenticity  # noqa: E402


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
        engine_exe = root / "engines/deeplx/windows/amd64/deeplx.exe"
        engine_payload = _require_file(root, "engines/deeplx/windows/amd64/deeplx.exe.payload")
        if engine_exe.exists():
            raise RuntimeError("online update package must use deeplx.exe.payload, not deeplx.exe")
        if engine_payload.stat().st_size < 1024:
            raise RuntimeError("engine payload is too small")
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


def verify_adjacent_signature(zip_path: Path, expected_version: str) -> None:
    """Verify package against embedded public key using adjacent *.zip.sig.json.

    This catches private-key / embedded-public-key mismatches that package
    structure checks alone cannot detect.
    """
    sig_path = Path(str(zip_path) + ".sig.json")
    if not sig_path.is_file():
        raise RuntimeError(
            f"signature json missing: {sig_path} "
            "(run tools/sign_windows_update_package.py before verify)"
        )

    try:
        sig = json.loads(sig_path.read_text(encoding="utf-8-sig"))
    except Exception as error:
        raise RuntimeError(f"invalid signature json: {sig_path}: {error}") from error

    signature = str(sig.get("signature") or "").strip()
    if not signature:
        raise RuntimeError(f"signature json missing signature field: {sig_path}")

    expected_name = zip_path.name
    package_size = int(zip_path.stat().st_size)

    sig_version = str(sig.get("app_version") or "").strip().lstrip("vV")
    want_version = str(expected_version or "").strip().lstrip("vV")
    if sig_version and want_version and sig_version != want_version:
        raise RuntimeError(
            f"signature version mismatch: expected {expected_version}, found {sig.get('app_version')}"
        )

    sig_name = str(sig.get("filename") or "").strip()
    if sig_name and sig_name != expected_name:
        raise RuntimeError(
            f"signature filename mismatch: expected {expected_name}, found {sig_name}"
        )

    if sig.get("size_bytes") is not None and int(sig["size_bytes"]) != package_size:
        raise RuntimeError(
            f"signature size mismatch: expected {package_size}, found {sig.get('size_bytes')}"
        )

    platform = str(sig.get("platform") or "windows").strip().lower()
    if platform and platform not in {"windows", "win32", "win"}:
        raise RuntimeError(f"signature platform mismatch: expected windows, found {platform}")

    package_type = str(sig.get("package_type") or "windows_full_update").strip()
    if package_type and package_type != "windows_full_update":
        raise RuntimeError(
            f"signature package_type mismatch: expected windows_full_update, found {package_type}"
        )

    payload = verify_package_authenticity(
        package_path=str(zip_path),
        expected_version=expected_version,
        signature_b64=signature,
        expected_filename=expected_name,
        package_type="windows_full_update",
        platform="windows",
    )

    sig_sha = str(sig.get("sha256") or "").strip().lower()
    actual_sha = str(payload.get("sha256") or "").strip().lower()
    if sig_sha and actual_sha and sig_sha != actual_sha:
        raise RuntimeError(
            f"signature sha256 mismatch: expected {actual_sha}, found {sig_sha}"
        )


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: verify_windows_package.py <zip_path> <expected_version>")
        return 2
    zip_path = Path(sys.argv[1]).resolve()
    expected_version = sys.argv[2]
    verify_package(zip_path, expected_version)
    verify_adjacent_signature(zip_path, expected_version)
    print(f"Verified Windows package: {sys.argv[1]} ({sys.argv[2]})")
    print("Verified update signature against embedded public key")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
