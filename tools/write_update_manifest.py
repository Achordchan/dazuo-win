import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: write_update_manifest.py <dist_dir>")
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    from src.version import APP_VERSION

    dist_dir = Path(sys.argv[1]).resolve()
    if not dist_dir.is_dir():
        raise FileNotFoundError(f"dist dir not found: {dist_dir}")

    manifest = {
        "app_version": APP_VERSION,
        "package_type": "windows_full_update",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = dist_dir / "update_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote update manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
