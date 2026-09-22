"""Build Release notes for a version: changelog section + update signature markers.

Usage:
    python tools/build_release_notes.py --version 1.2.11 \
        --sig-json output/dazuofanyiguan_full.for.windows_1.2.11.zip.sig.json \
        --output output/release_notes_1.2.11.md [--force-update]

The output matches the body format the updater parses: the changelog section for the
version followed by ``DZFYQ-SIG-WINDOWS:<base64>`` (and the legacy ``DZFYQ-SIG:``) lines.
The same file must be used for both the GitHub and the Gitee Release so that every
client, old or new, sees identical notes and signatures.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = REPO_ROOT / "src" / "ziyuan" / "changelog.md"


def extract_changelog_section(changelog_text: str, version: str) -> str:
    version = version.strip().lstrip("vV")
    pattern = re.compile(
        rf"(^## v{re.escape(version)}\b.*?)(?=^## v|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(changelog_text)
    if not match:
        raise SystemExit(f"changelog section for v{version} not found in {CHANGELOG}")
    return match.group(1).strip()


def signature_markers(sig_json: Path) -> list[str]:
    payload = json.loads(sig_json.read_text(encoding="utf-8-sig"))
    markers = payload.get("release_notes_markers")
    if isinstance(markers, list) and markers:
        return [str(marker) for marker in markers]
    signature = str(payload.get("signature") or "").strip()
    if not signature:
        raise SystemExit(f"signature missing in {sig_json}")
    return [f"DZFYQ-SIG-WINDOWS:{signature}", f"DZFYQ-SIG:{signature}"]


def build_notes(version: str, sig_json: Path, force_update: bool = False) -> str:
    section = extract_changelog_section(CHANGELOG.read_text(encoding="utf-8"), version)
    lines = ["# 更新日志", "", section, ""]
    lines.extend(signature_markers(sig_json))
    if force_update:
        lines.append("update=1")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sig-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force-update", action="store_true", help="append update=1 (forced update)")
    args = parser.parse_args()

    notes = build_notes(args.version, args.sig_json, args.force_update)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(notes, encoding="utf-8")
    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
