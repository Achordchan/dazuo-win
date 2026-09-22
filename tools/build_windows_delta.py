from __future__ import annotations

import argparse
import os
import subprocess
import sys
import zipfile
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.gongju.update_delta import normalize_version  # noqa: E402
from tools.create_windows_delta_package import (  # noqa: E402
    create_delta_package,
    expected_delta_name,
)


def _package_version(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        payload = json.loads(
            archive.read("update_manifest.json").decode("utf-8-sig")
        )
    version = normalize_version(payload.get("app_version"))
    if not version:
        raise RuntimeError(f"package missing app_version: {path}")
    return version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_zip", type=Path)
    parser.add_argument("target_zip", type=Path)
    parser.add_argument(
        "--private-key",
        type=Path,
        default=None,
        help="Ed25519 private key PEM path; or set DZFYQ_UPDATE_PRIVATE_KEY",
    )
    args = parser.parse_args()

    base_zip = args.base_zip.resolve()
    target_zip = args.target_zip.resolve()
    base_version = _package_version(base_zip)
    target_version = _package_version(target_zip)
    output = target_zip.parent / expected_delta_name(base_version, target_version)
    create_delta_package(base_zip, target_zip, output)

    key_path = args.private_key
    if key_path is None:
        raw = (os.environ.get("DZFYQ_UPDATE_PRIVATE_KEY") or "").strip()
        if raw:
            key_path = Path(raw)
    if key_path is None:
        raise RuntimeError("缺少增量更新签名私钥路径")

    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "sign_windows_update_package.py"),
            str(output),
            "--version",
            target_version,
            "--package-type",
            "windows_file_delta",
            "--platform",
            "windows",
            "--private-key",
            str(key_path),
        ],
        check=True,
        cwd=REPO_ROOT,
    )
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "verify_windows_delta_package.py"),
            str(output),
            "--base-version",
            base_version,
            "--target-version",
            target_version,
        ],
        check=True,
        cwd=REPO_ROOT,
    )
    print(f"Windows delta package ready: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
