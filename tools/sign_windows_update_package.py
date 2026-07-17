"""Sign a Windows full update zip with the release Ed25519 private key."""

from __future__ import annotations

import argparse
import os
import base64
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.gongju.update_trust import (  # noqa: E402
    build_canonical_payload,
    infer_package_identity,
    normalize_platform,
    normalize_version,
    sha256_file,
)


def load_private_key(path: Path) -> Ed25519PrivateKey:
    data = path.read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("private key is not Ed25519")
    return key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_zip", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--private-key",
        type=Path,
        default=None,
        help="Ed25519 private key PEM path; or set DZFYQ_UPDATE_PRIVATE_KEY",
    )
    parser.add_argument("--out", type=Path, default=None, help="write signature json")
    parser.add_argument("--platform", default="", help="windows or macos; inferred from filename when omitted")
    parser.add_argument("--package-type", default="", help="windows_full_update or macos_dmg_update; inferred when omitted")
    args = parser.parse_args()

    package = args.package_zip.resolve()
    if not package.is_file():
        raise FileNotFoundError(package)

    key_path = args.private_key
    if key_path is None:
        env_key = (os.environ.get("DZFYQ_UPDATE_PRIVATE_KEY") or "").strip()
        if env_key:
            key_path = Path(env_key)
    if key_path is None:
        raise SystemExit(
            "缺少私钥路径。请传 --private-key，或设置环境变量 DZFYQ_UPDATE_PRIVATE_KEY。"
        )
    key_path = key_path.expanduser().resolve()
    if not key_path.is_file():
        raise FileNotFoundError(f"private key not found: {key_path}")

    digest = sha256_file(str(package))
    size = package.stat().st_size
    package_type, platform = infer_package_identity(
        package.name,
        package_type=args.package_type,
        platform=args.platform,
    )
    platform = normalize_platform(platform)
    payload = {
        "app_version": normalize_version(args.version),
        "package_type": package_type,
        "platform": platform,
        "filename": package.name,
        "size_bytes": int(size),
        "sha256": digest,
    }
    message = build_canonical_payload(payload)
    signature = load_private_key(key_path).sign(message)
    signature_b64 = base64.b64encode(signature).decode("ascii")
    platform_marker = {
        "windows": "DZFYQ-SIG-WINDOWS",
        "macos": "DZFYQ-SIG-MACOS",
    }.get(platform, f"DZFYQ-SIG-{platform.upper()}" if platform else "DZFYQ-SIG")
    # Keep legacy DZFYQ-SIG for Windows so older clients keep working.
    markers = [f"{platform_marker}:{signature_b64}"]
    if platform == "windows":
        markers.append(f"DZFYQ-SIG:{signature_b64}")
    result = {
        **payload,
        "signature": signature_b64,
        "release_notes_marker": markers[0],
        "release_notes_markers": markers,
    }
    out = args.out or package.with_suffix(package.suffix + ".sig.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for marker in result.get("release_notes_markers") or [result["release_notes_marker"]]:
        print(marker)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
