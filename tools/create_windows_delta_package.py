from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.gongju.update_delta import (
    DELTA_MANIFEST_NAME,
    DELTA_PACKAGE_TYPE,
    DELTA_PAYLOAD_PREFIX,
    DELTA_PLATFORM,
    DELTA_SCHEMA_VERSION,
    FileRecord,
    DeltaPackageError,
    normalize_relative_path,
    normalize_version,
)


def _hash_zip_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> FileRecord:
    digest = hashlib.sha256()
    size = 0
    with archive.open(info, "r") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return FileRecord(
        path=normalize_relative_path(info.filename),
        size_bytes=size,
        sha256=digest.hexdigest().lower(),
    )


def _load_full_package(
    package_path: Path,
) -> tuple[zipfile.ZipFile, str, dict[str, zipfile.ZipInfo], dict[str, FileRecord]]:
    if not package_path.is_file() or not zipfile.is_zipfile(package_path):
        raise DeltaPackageError(f"不是有效的 Windows 全量 ZIP：{package_path}")
    archive = zipfile.ZipFile(package_path, "r")
    try:
        members = {}
        folded_names = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = normalize_relative_path(info.filename)
            folded = name.casefold()
            if folded in folded_names:
                raise DeltaPackageError(
                    f"全量包包含重复或大小写冲突路径："
                    f"{folded_names[folded]} / {name}"
                )
            folded_names[folded] = name
            members[name] = info
        manifest_info = members.get("update_manifest.json")
        if manifest_info is None:
            raise DeltaPackageError(f"全量包缺少 update_manifest.json：{package_path}")
        try:
            manifest = json.loads(archive.read(manifest_info).decode("utf-8-sig"))
        except Exception as error:
            raise DeltaPackageError(f"全量包版本清单损坏：{package_path}") from error
        version = normalize_version(manifest.get("app_version"))
        if not version:
            raise DeltaPackageError(f"全量包缺少 app_version：{package_path}")
        package_type = str(manifest.get("package_type") or "").strip()
        if package_type and package_type != "windows_full_update":
            raise DeltaPackageError(
                f"全量包类型无效：{package_type or '空'}"
            )
        records = {
            name: _hash_zip_member(archive, info)
            for name, info in members.items()
        }
        return archive, version, members, records
    except Exception:
        archive.close()
        raise


def expected_delta_name(base_version: str, target_version: str) -> str:
    return (
        "dazuofanyiguan_delta.for.windows_"
        f"{normalize_version(base_version)}_to_{normalize_version(target_version)}.zip"
    )


def create_delta_package(
    base_zip: Path,
    target_zip: Path,
    output_zip: Path,
) -> dict:
    base_zip = base_zip.resolve()
    target_zip = target_zip.resolve()
    output_zip = output_zip.resolve()
    base_archive, base_version, _base_members, base_records = _load_full_package(base_zip)
    target_archive, target_version, target_members, target_records = _load_full_package(target_zip)
    try:
        if base_version == target_version:
            raise DeltaPackageError("来源版本和目标版本不能相同")
        expected_name = expected_delta_name(base_version, target_version)
        if output_zip.name != expected_name:
            raise DeltaPackageError(
                f"增量包文件名不正确：期望 {expected_name}，实际 {output_zip.name}"
            )

        changed_paths = sorted(
            path
            for path, record in target_records.items()
            if base_records.get(path) != record
        )
        removed_paths = sorted(set(base_records) - set(target_records), key=str.casefold)
        payload_records = [target_records[path] for path in changed_paths]
        target_file_records = sorted(
            target_records.values(),
            key=lambda item: item.path.casefold(),
        )
        manifest = {
            "schema_version": DELTA_SCHEMA_VERSION,
            "package_type": DELTA_PACKAGE_TYPE,
            "platform": DELTA_PLATFORM,
            "base_version": base_version,
            "app_version": target_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload_files": [record.as_dict() for record in payload_records],
            "removed_files": removed_paths,
            "target_files": [record.as_dict() for record in target_file_records],
        }

        output_zip.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=output_zip.name,
            suffix=".tmp",
            dir=output_zip.parent,
        )
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            with zipfile.ZipFile(
                temp_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
                allowZip64=True,
            ) as output:
                output.writestr(
                    DELTA_MANIFEST_NAME,
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                )
                for path in changed_paths:
                    info = target_members[path]
                    payload_name = f"{DELTA_PAYLOAD_PREFIX}{path}"
                    payload_info = zipfile.ZipInfo(
                        filename=payload_name,
                        date_time=info.date_time,
                    )
                    payload_info.compress_type = zipfile.ZIP_DEFLATED
                    payload_info.external_attr = info.external_attr
                    with target_archive.open(info, "r") as source, output.open(
                        payload_info,
                        "w",
                        force_zip64=True,
                    ) as destination:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            destination.write(chunk)
            os.replace(temp_path, output_zip)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        return manifest
    finally:
        base_archive.close()
        target_archive.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_zip", type=Path)
    parser.add_argument("target_zip", type=Path)
    parser.add_argument("output_zip", type=Path, nargs="?")
    args = parser.parse_args()

    with zipfile.ZipFile(args.base_zip) as archive:
        base_manifest = json.loads(
            archive.read("update_manifest.json").decode("utf-8-sig")
        )
    with zipfile.ZipFile(args.target_zip) as archive:
        target_manifest = json.loads(
            archive.read("update_manifest.json").decode("utf-8-sig")
        )
    base_version = normalize_version(base_manifest.get("app_version"))
    target_version = normalize_version(target_manifest.get("app_version"))
    output = args.output_zip or (
        args.target_zip.resolve().parent
        / expected_delta_name(base_version, target_version)
    )
    manifest = create_delta_package(args.base_zip, args.target_zip, output)
    print(
        f"Created Windows delta package: {output.resolve()} "
        f"({len(manifest['payload_files'])} changed, "
        f"{len(manifest['removed_files'])} removed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
