import re
from pathlib import Path


def _parse_version(version_text: str) -> str:
    match = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", version_text)
    if not match:
        raise ValueError("APP_VERSION not found in src/version.py")
    return match.group(1).strip()


def _version_tuple(version: str) -> str:
    parts = []
    for part in version.split("."):
        digits = re.match(r"\d+", part)
        parts.append(int(digits.group(0)) if digits else 0)
    while len(parts) < 4:
        parts.append(0)
    return ", ".join(str(value) for value in parts[:4])


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    version_file = repo_root / "src" / "version.py"
    version_text = version_file.read_text(encoding="utf-8")
    version = _parse_version(version_text)
    version_tuple = _version_tuple(version)

    version_info_path = repo_root / "file_version_info.txt"
    version_info_text = version_info_path.read_text(encoding="utf-8")
    version_info_text = re.sub(
        r"filevers=\([^)]*\)",
        f"filevers=({version_tuple})",
        version_info_text,
    )
    version_info_text = re.sub(
        r"prodvers=\([^)]*\)",
        f"prodvers=({version_tuple})",
        version_info_text,
    )
    version_info_text = re.sub(
        r"StringStruct\(u'FileVersion', u'[^']*'\)",
        f"StringStruct(u'FileVersion', u'{version}')",
        version_info_text,
    )
    version_info_text = re.sub(
        r"StringStruct\(u'ProductVersion', u'[^']*'\)",
        f"StringStruct(u'ProductVersion', u'{version}')",
        version_info_text,
    )
    version_info_path.write_text(version_info_text, encoding="utf-8")

    version_include_path = repo_root / "version.generated.iss"
    version_include_path.write_text(
        f'#define MyAppVersion "{version}"\n',
        encoding="utf-8",
    )

    print(f"Synced version: {version}")


if __name__ == "__main__":
    main()
