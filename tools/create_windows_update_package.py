import argparse
import os
import tempfile
import zipfile
from pathlib import Path


ENGINE_EXE = Path("engines/deeplx/windows/amd64/deeplx.exe")
ENGINE_PAYLOAD = Path("engines/deeplx/windows/amd64/deeplx.exe.payload")


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def create_package(source_dir: Path, output_zip: Path) -> None:
    source_dir = source_dir.resolve()
    output_zip = output_zip.resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"source directory not found: {source_dir}")

    engine_exe_path = source_dir / ENGINE_EXE
    if not engine_exe_path.is_file():
        raise FileNotFoundError(f"bundled engine missing before packaging: {ENGINE_EXE}")

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=output_zip.name, suffix=".tmp", dir=output_zip.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in _iter_files(source_dir):
                relative = path.relative_to(source_dir)
                archive_name = ENGINE_PAYLOAD if relative == ENGINE_EXE else relative
                archive.write(path, archive_name.as_posix())
        os.replace(temp_path, output_zip)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_zip", type=Path)
    args = parser.parse_args()
    create_package(args.source_dir, args.output_zip)
    print(f"Created Windows update package: {args.output_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
