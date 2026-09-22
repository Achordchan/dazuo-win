from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.gongju.update_delta import (  # noqa: E402
    DELTA_PACKAGE_TYPE,
    inspect_delta_package,
    normalize_version,
)
from src.gongju.update_trust import verify_package_authenticity  # noqa: E402


def verify_adjacent_signature(package: Path, target_version: str) -> dict:
    signature_path = Path(str(package) + ".sig.json")
    if not signature_path.is_file():
        raise FileNotFoundError(f"missing delta signature file: {signature_path}")
    payload = json.loads(signature_path.read_text(encoding="utf-8-sig"))
    if str(payload.get("filename") or "") != package.name:
        raise RuntimeError("delta signature filename mismatch")
    if str(payload.get("package_type") or "") != DELTA_PACKAGE_TYPE:
        raise RuntimeError("delta signature package_type mismatch")
    if normalize_version(payload.get("app_version")) != normalize_version(
        target_version
    ):
        raise RuntimeError("delta signature app_version mismatch")
    if str(payload.get("platform") or "").strip().lower() != "windows":
        raise RuntimeError("delta signature platform mismatch")
    signature = str(payload.get("signature") or "").strip()
    verified = verify_package_authenticity(
        package_path=str(package),
        expected_version=target_version,
        signature_b64=signature,
        expected_filename=package.name,
        package_type=DELTA_PACKAGE_TYPE,
        platform="windows",
    )
    if str(payload.get("sha256") or "").lower() != verified["sha256"]:
        raise RuntimeError("delta signature sha256 mismatch")
    if int(payload.get("size_bytes") or 0) != verified["size_bytes"]:
        raise RuntimeError("delta signature size mismatch")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_zip", type=Path)
    parser.add_argument("--base-version", default="")
    parser.add_argument("--target-version", default="")
    parser.add_argument("--skip-signature", action="store_true")
    args = parser.parse_args()

    package = args.package_zip.resolve()
    manifest = inspect_delta_package(
        package,
        expected_base_version=args.base_version,
        expected_target_version=args.target_version,
        verify_payload_hashes=True,
    )
    if not args.skip_signature:
        verify_adjacent_signature(package, manifest.app_version)
    print(
        "delta-package-ok "
        f"base={manifest.base_version} target={manifest.app_version} "
        f"changed={len(manifest.payload_files)} "
        f"removed={len(manifest.removed_files)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
