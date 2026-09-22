from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


DELTA_SCHEMA_VERSION = 1
DELTA_PACKAGE_TYPE = "windows_file_delta"
DELTA_PLATFORM = "windows"
DELTA_MANIFEST_NAME = "delta_manifest.json"
DELTA_PAYLOAD_PREFIX = "payload/"
ENGINE_EXE_PATH = "engines/deeplx/windows/amd64/deeplx.exe"
ENGINE_PAYLOAD_PATH = f"{ENGINE_EXE_PATH}.payload"

MAX_DELTA_MEMBERS = 20000
MAX_DELTA_UNCOMPRESSED_BYTES = 800 * 1024 * 1024
MAX_DELTA_COMPRESSION_RATIO = 100.0
MAX_DELTA_MANIFEST_BYTES = 4 * 1024 * 1024

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DeltaPackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileRecord:
    path: str
    size_bytes: int
    sha256: str

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class DeltaManifest:
    schema_version: int
    package_type: str
    platform: str
    base_version: str
    app_version: str
    created_at: str
    payload_files: tuple[FileRecord, ...]
    removed_files: tuple[str, ...]
    target_files: tuple[FileRecord, ...]

    @property
    def payload_map(self) -> dict[str, FileRecord]:
        return {record.path: record for record in self.payload_files}

    @property
    def target_map(self) -> dict[str, FileRecord]:
        return {record.path: record for record in self.target_files}

    def as_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "package_type": self.package_type,
            "platform": self.platform,
            "base_version": self.base_version,
            "app_version": self.app_version,
            "created_at": self.created_at,
            "payload_files": [record.as_dict() for record in self.payload_files],
            "removed_files": list(self.removed_files),
            "target_files": [record.as_dict() for record in self.target_files],
        }


def normalize_version(version: str) -> str:
    return str(version or "").strip().lstrip("vV")


def normalize_relative_path(value: str) -> str:
    raw = str(value or "")
    if not raw or raw != raw.strip():
        raise DeltaPackageError("增量包包含空路径或路径两端空格")
    if chr(92) in raw:
        raise DeltaPackageError(f"增量包路径必须使用正斜杠：{raw}")
    path = PurePosixPath(raw)
    if path.is_absolute() or raw.startswith("/"):
        raise DeltaPackageError(f"增量包包含绝对路径：{raw}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise DeltaPackageError(f"增量包包含非法路径：{raw}")
    normalized = path.as_posix()
    if normalized != raw or normalized.endswith("/"):
        raise DeltaPackageError(f"增量包路径不是规范格式：{raw}")
    reserved = {
        "con", "prn", "aux", "nul",
        "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    }
    for part in path.parts:
        if ":" in part or part.endswith((" ", ".")):
            raise DeltaPackageError(f"增量包包含非法 Windows 路径：{raw}")
        if part.split(".", 1)[0].casefold() in reserved:
            raise DeltaPackageError(f"增量包包含 Windows 保留文件名：{raw}")
    return normalized

def _validate_unique_paths(paths: Iterable[str], label: str) -> tuple[str, ...]:
    normalized_paths = []
    seen = {}
    for value in paths:
        normalized = normalize_relative_path(value)
        folded = normalized.casefold()
        previous = seen.get(folded)
        if previous is not None:
            raise DeltaPackageError(
                f"{label}包含重复或大小写冲突路径：{previous} / {normalized}"
            )
        seen[folded] = normalized
        normalized_paths.append(normalized)
    return tuple(normalized_paths)


def _parse_file_records(value, label: str) -> tuple[FileRecord, ...]:
    if not isinstance(value, list):
        raise DeltaPackageError(f"{label}必须是数组")
    paths = []
    records = []
    for item in value:
        if not isinstance(item, dict):
            raise DeltaPackageError(f"{label}包含无效记录")
        path = normalize_relative_path(item.get("path"))
        try:
            size_bytes = int(item.get("size_bytes"))
        except (TypeError, ValueError) as error:
            raise DeltaPackageError(f"{label}文件大小无效：{path}") from error
        if size_bytes < 0:
            raise DeltaPackageError(f"{label}文件大小不能为负数：{path}")
        digest = str(item.get("sha256") or "").strip().lower()
        if not _SHA256_PATTERN.fullmatch(digest):
            raise DeltaPackageError(f"{label} SHA256 无效：{path}")
        paths.append(path)
        records.append(FileRecord(path=path, size_bytes=size_bytes, sha256=digest))
    _validate_unique_paths(paths, label)
    return tuple(records)


def parse_delta_manifest(
    payload: dict,
    *,
    expected_base_version: str = "",
    expected_target_version: str = "",
) -> DeltaManifest:
    if not isinstance(payload, dict):
        raise DeltaPackageError("增量包清单格式无效")
    try:
        schema_version = int(payload.get("schema_version"))
    except (TypeError, ValueError) as error:
        raise DeltaPackageError("增量包 schema_version 无效") from error
    if schema_version != DELTA_SCHEMA_VERSION:
        raise DeltaPackageError(
            f"不支持的增量包清单版本：{schema_version}"
        )
    package_type = str(payload.get("package_type") or "").strip()
    if package_type != DELTA_PACKAGE_TYPE:
        raise DeltaPackageError(f"增量包类型无效：{package_type}")
    platform = str(payload.get("platform") or "").strip().lower()
    if platform != DELTA_PLATFORM:
        raise DeltaPackageError(f"增量包平台无效：{platform}")

    base_version = normalize_version(payload.get("base_version"))
    app_version = normalize_version(payload.get("app_version"))
    if not base_version or not app_version:
        raise DeltaPackageError("增量包缺少来源版本或目标版本")
    if base_version == app_version:
        raise DeltaPackageError("增量包来源版本和目标版本不能相同")
    if expected_base_version and base_version != normalize_version(expected_base_version):
        raise DeltaPackageError(
            f"增量包来源版本不匹配：期望 v{normalize_version(expected_base_version)}，"
            f"实际 v{base_version}"
        )
    if expected_target_version and app_version != normalize_version(expected_target_version):
        raise DeltaPackageError(
            f"增量包目标版本不匹配：期望 v{normalize_version(expected_target_version)}，"
            f"实际 v{app_version}"
        )

    payload_files = _parse_file_records(payload.get("payload_files"), "payload_files")
    target_files = _parse_file_records(payload.get("target_files"), "target_files")
    removed_raw = payload.get("removed_files")
    if not isinstance(removed_raw, list):
        raise DeltaPackageError("removed_files 必须是数组")
    removed_files = _validate_unique_paths(removed_raw, "removed_files")

    payload_map = {record.path.casefold(): record for record in payload_files}
    target_map = {record.path.casefold(): record for record in target_files}
    for folded, record in payload_map.items():
        target = target_map.get(folded)
        if target is None:
            raise DeltaPackageError(f"变化文件不在目标文件清单中：{record.path}")
        if target != record:
            raise DeltaPackageError(f"变化文件与目标文件记录不一致：{record.path}")
    for path in removed_files:
        if path.casefold() in target_map:
            raise DeltaPackageError(f"删除文件仍存在于目标文件清单：{path}")

    return DeltaManifest(
        schema_version=schema_version,
        package_type=package_type,
        platform=platform,
        base_version=base_version,
        app_version=app_version,
        created_at=str(payload.get("created_at") or "").strip(),
        payload_files=tuple(sorted(payload_files, key=lambda item: item.path.casefold())),
        removed_files=tuple(sorted(removed_files, key=str.casefold)),
        target_files=tuple(sorted(target_files, key=lambda item: item.path.casefold())),
    )


def sha256_stream(handle) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        digest.update(chunk)
    return digest.hexdigest().lower(), size


def sha256_path(path: Path) -> tuple[str, int]:
    with path.open("rb") as handle:
        return sha256_stream(handle)


def _validate_zip_members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    members = archive.infolist()
    if len(members) > MAX_DELTA_MEMBERS:
        raise DeltaPackageError(f"增量包文件数过多：{len(members)}")
    total_uncompressed = 0
    file_members = {}
    folded_names = {}
    for member in members:
        if member.is_dir():
            continue
        mode = (member.external_attr >> 16) & 0xFFFF
        if mode and stat.S_ISLNK(mode):
            raise DeltaPackageError(f"增量包不允许符号链接：{member.filename}")
        normalized = normalize_relative_path(member.filename)
        folded = normalized.casefold()
        if folded in folded_names:
            raise DeltaPackageError(
                f"增量包包含重复或大小写冲突成员："
                f"{folded_names[folded]} / {normalized}"
            )
        folded_names[folded] = normalized
        total_uncompressed += int(member.file_size or 0)
        if total_uncompressed > MAX_DELTA_UNCOMPRESSED_BYTES:
            raise DeltaPackageError("增量包解压后体积过大")
        compressed = max(int(member.compress_size or 0), 1)
        ratio = float(member.file_size or 0) / float(compressed)
        if ratio > MAX_DELTA_COMPRESSION_RATIO and (member.file_size or 0) > 1024 * 1024:
            raise DeltaPackageError(f"增量包压缩比异常：{normalized}")
        file_members[normalized] = member
    return file_members


def inspect_delta_package(
    package_path: str | Path,
    *,
    expected_base_version: str = "",
    expected_target_version: str = "",
    verify_payload_hashes: bool = False,
) -> DeltaManifest:
    path = Path(package_path)
    if not path.is_file() or not zipfile.is_zipfile(path):
        raise DeltaPackageError("增量更新包不是有效 ZIP 文件")
    with zipfile.ZipFile(path, "r") as archive:
        members = _validate_zip_members(archive)
        manifest_info = members.get(DELTA_MANIFEST_NAME)
        if manifest_info is None:
            raise DeltaPackageError(f"增量包缺少 {DELTA_MANIFEST_NAME}")
        if manifest_info.file_size > MAX_DELTA_MANIFEST_BYTES:
            raise DeltaPackageError("增量包清单体积过大")
        try:
            manifest_payload = json.loads(
                archive.read(manifest_info).decode("utf-8")
            )
        except Exception as error:
            raise DeltaPackageError("增量包清单损坏") from error
        manifest = parse_delta_manifest(
            manifest_payload,
            expected_base_version=expected_base_version,
            expected_target_version=expected_target_version,
        )
        expected_members = {DELTA_MANIFEST_NAME}
        for record in manifest.payload_files:
            member_name = f"{DELTA_PAYLOAD_PREFIX}{record.path}"
            expected_members.add(member_name)
            info = members.get(member_name)
            if info is None:
                raise DeltaPackageError(f"增量包缺少变化文件：{record.path}")
            if int(info.file_size) != record.size_bytes:
                raise DeltaPackageError(f"变化文件大小不匹配：{record.path}")
            if verify_payload_hashes:
                with archive.open(info, "r") as handle:
                    digest, size = sha256_stream(handle)
                if size != record.size_bytes or digest != record.sha256:
                    raise DeltaPackageError(f"变化文件校验失败：{record.path}")
        actual_members = set(members)
        extras = sorted(actual_members - expected_members)
        missing = sorted(expected_members - actual_members)
        if extras:
            raise DeltaPackageError(f"增量包包含未声明文件：{extras[0]}")
        if missing:
            raise DeltaPackageError(f"增量包缺少声明文件：{missing[0]}")
        return manifest


def _absolute_path(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def is_reparse_point(path: str | Path) -> bool:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse_flag)


def _ensure_no_reparse_points(path: Path, allowed_root: Path) -> None:
    path = _absolute_path(path)
    allowed_root = _absolute_path(allowed_root)
    try:
        relative = path.relative_to(allowed_root)
    except ValueError as error:
        raise DeltaPackageError(f"增量重建目录越界：{path}") from error

    current = allowed_root
    candidates = [current]
    for part in relative.parts:
        current = current / part
        candidates.append(current)
    for candidate in candidates:
        if os.path.lexists(candidate) and is_reparse_point(candidate):
            raise DeltaPackageError(f"增量重建目录不允许重解析点：{candidate}")


def _safe_destination(root: Path, relative: str, allowed_root: Path) -> Path:
    destination = _absolute_path(root / Path(*PurePosixPath(relative).parts))
    try:
        destination.relative_to(_absolute_path(root))
    except ValueError as error:
        raise DeltaPackageError(f"增量更新目标路径越界：{relative}") from error
    _ensure_no_reparse_points(destination.parent, allowed_root)
    if os.path.lexists(destination) and is_reparse_point(destination):
        raise DeltaPackageError(f"增量更新目标不允许重解析点：{relative}")
    return destination


def _read_installed_version(install_dir: Path) -> str:
    manifest_path = install_dir / "update_manifest.json"
    if not manifest_path.is_file():
        raise DeltaPackageError("当前安装目录缺少 update_manifest.json，无法使用增量更新")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as error:
        raise DeltaPackageError("当前安装目录版本清单损坏") from error
    return normalize_version(payload.get("app_version"))


def _find_matching_source(
    install_dir: Path,
    record: FileRecord,
) -> Path:
    candidates = [record.path]
    if record.path == ENGINE_PAYLOAD_PATH:
        candidates.append(ENGINE_EXE_PATH)
    for relative in candidates:
        candidate = install_dir / Path(*PurePosixPath(relative).parts)
        if not candidate.is_file():
            continue
        digest, size = sha256_path(candidate)
        if size == record.size_bytes and digest == record.sha256:
            return candidate
    raise DeltaPackageError(f"当前安装文件缺失或已被修改：{record.path}")


def reconstruct_delta_package(
    package_path: str | Path,
    *,
    install_dir: str | Path,
    output_dir: str | Path,
    expected_base_version: str,
    expected_target_version: str,
    allowed_output_root: str | Path | None = None,
) -> DeltaManifest:
    package = Path(package_path).resolve()
    install_root = Path(install_dir).resolve()
    output_root = _absolute_path(output_dir)
    allowed_root = _absolute_path(allowed_output_root or output_root.parent)
    if not install_root.is_dir():
        raise DeltaPackageError("当前安装目录不存在")
    try:
        relative_output = output_root.relative_to(allowed_root)
    except ValueError as error:
        raise DeltaPackageError("增量重建目录不在允许的缓存目录内") from error
    if not relative_output.parts:
        raise DeltaPackageError("增量重建目录不能等于缓存根目录")
    if output_root == install_root:
        raise DeltaPackageError("增量重建目录不能与安装目录相同")
    _ensure_no_reparse_points(output_root.parent, allowed_root)
    installed_version = _read_installed_version(install_root)
    if installed_version != normalize_version(expected_base_version):
        raise DeltaPackageError(
            f"当前安装版本不匹配：期望 v{normalize_version(expected_base_version)}，"
            f"实际 v{installed_version or '未知'}"
        )

    manifest = inspect_delta_package(
        package,
        expected_base_version=expected_base_version,
        expected_target_version=expected_target_version,
        verify_payload_hashes=False,
    )
    if os.path.lexists(output_root):
        if is_reparse_point(output_root):
            raise DeltaPackageError("增量重建目录不允许使用重解析点")
        if not output_root.is_dir():
            raise DeltaPackageError("增量重建目标不是目录")
        _ensure_no_reparse_points(output_root, allowed_root)
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    _ensure_no_reparse_points(output_root, allowed_root)

    try:
        payload_map = manifest.payload_map
        with zipfile.ZipFile(package, "r") as archive:
            members = _validate_zip_members(archive)
            for record in manifest.target_files:
                destination = _safe_destination(
                    output_root,
                    record.path,
                    allowed_root,
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                _ensure_no_reparse_points(destination.parent, allowed_root)
                if record.path in payload_map:
                    member = members[f"{DELTA_PAYLOAD_PREFIX}{record.path}"]
                    digest = hashlib.sha256()
                    size = 0
                    with archive.open(member, "r") as source, destination.open("wb") as target:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            size += len(chunk)
                            digest.update(chunk)
                            target.write(chunk)
                    if size != record.size_bytes or digest.hexdigest().lower() != record.sha256:
                        raise DeltaPackageError(f"变化文件校验失败：{record.path}")
                    continue

                source = _find_matching_source(install_root, record)
                shutil.copy2(source, destination)

        actual_paths = []
        for path in output_root.rglob("*"):
            if path.is_file():
                actual_paths.append(path.relative_to(output_root).as_posix())
        expected_paths = [record.path for record in manifest.target_files]
        if {item.casefold() for item in actual_paths} != {
            item.casefold() for item in expected_paths
        }:
            raise DeltaPackageError("增量重建后的文件集合与目标清单不一致")
        return manifest
    except Exception:
        try:
            _ensure_no_reparse_points(output_root, allowed_root)
            shutil.rmtree(output_root, ignore_errors=True)
        except Exception:
            pass
        raise
