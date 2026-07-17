"""Verify an update package signature with the embedded public key."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.gongju.update_trust import (  # noqa: E402
    infer_package_identity,
    verify_package_authenticity,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--signature", required=True, help="base64 Ed25519 signature")
    parser.add_argument("--filename", default="", help="expected asset filename")
    parser.add_argument("--platform", default="")
    parser.add_argument("--package-type", default="")
    parser.add_argument(
        "--print-sha256",
        action="store_true",
        help="print sha256=<hex> after successful verification",
    )
    args = parser.parse_args()

    package = args.package.resolve()
    if not package.is_file():
        raise FileNotFoundError(package)

    filename = args.filename or package.name
    package_type, platform = infer_package_identity(
        filename,
        package_type=args.package_type,
        platform=args.platform,
    )

    # Always verify first. Callers may stream stdout; never print digests before auth.
    payload = verify_package_authenticity(
        package_path=str(package),
        expected_version=args.version,
        signature_b64=args.signature,
        expected_filename=filename,
        package_type=package_type,
        platform=platform,
    )
    print("signature-ok")
    if args.print_sha256:
        print(f"sha256={payload['sha256']}")
    print(
        f"platform={payload['platform']} package_type={payload['package_type']} "
        f"sha256={payload['sha256']} size={payload['size_bytes']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
