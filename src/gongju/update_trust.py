"""Update package authenticity helpers.

Uses Ed25519 signatures over a canonical manifest payload. The public key is
embedded in the application so release metadata alone is not trusted.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Optional

# 32-byte Ed25519 public key, base64.
# Replace with the real release-signing public key before shipping signed updates.
# The all-zero placeholder rejects every signature until configured.
UPDATE_ED25519_PUBLIC_KEY_B64 = "RUYCZIcVqIzgPf56cREkoGvQnYYiujdI/nG7EGiGPWA="

CANONICAL_FIELDS = (
    "app_version",
    "package_type",
    "platform",
    "filename",
    "size_bytes",
    "sha256",
)


def normalize_version(version: str) -> str:
    return str(version or "").strip().lstrip("vV")


def sha256_file(path: str, max_bytes: Optional[int] = None) -> str:
    digest = hashlib.sha256()
    total = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise RuntimeError(f"file exceeds size budget: {total} > {max_bytes}")
            digest.update(chunk)
    return digest.hexdigest().lower()


def build_canonical_payload(manifest: Mapping[str, Any]) -> bytes:
    payload = {key: manifest.get(key, "") for key in CANONICAL_FIELDS}
    payload["app_version"] = normalize_version(str(payload.get("app_version") or ""))
    payload["package_type"] = str(payload.get("package_type") or "windows_full_update")
    payload["platform"] = str(payload.get("platform") or "windows")
    payload["filename"] = str(payload.get("filename") or "")
    payload["size_bytes"] = int(payload.get("size_bytes") or 0)
    payload["sha256"] = str(payload.get("sha256") or "").strip().lower()
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _load_public_key_bytes() -> bytes:
    raw = base64.b64decode(UPDATE_ED25519_PUBLIC_KEY_B64.encode("ascii"))
    if len(raw) != 32:
        raise RuntimeError("invalid embedded update public key")
    if raw == bytes(32):
        raise RuntimeError(
            "更新验签公钥未配置，请先写入有效的 Ed25519 公钥。"
        )
    return raw


def verify_ed25519_signature(message: bytes, signature_b64: str) -> None:
    signature = base64.b64decode(str(signature_b64 or "").strip().encode("ascii"), validate=False)
    if len(signature) != 64:
        raise RuntimeError("更新签名格式无效")

    public_key = _load_public_key_bytes()
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception as error:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "缺少 cryptography 依赖，无法校验更新签名，请安装 cryptography 后重试。"
        ) from error

    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except InvalidSignature as error:
        raise RuntimeError("更新签名校验失败") from error
    except Exception as error:
        raise RuntimeError(f"更新签名校验出错: {error}") from error


def normalize_platform(platform: str) -> str:
    value = str(platform or "").strip().lower()
    if value in {"win", "win32", "windows"}:
        return "windows"
    if value in {"mac", "macos", "darwin", "osx"}:
        return "macos"
    return value


def infer_package_identity(filename: str, *, package_type: str = "", platform: str = "") -> tuple[str, str]:
    """Infer (package_type, platform) from explicit args or package filename."""
    name = str(filename or "").strip().lower()
    explicit_type = str(package_type or "").strip()
    explicit_platform = normalize_platform(platform)

    if not explicit_platform:
        if name.endswith(".dmg") or "for.macos" in name or "for.mac" in name or ".macos." in name:
            explicit_platform = "macos"
        elif name.endswith(".zip") or "for.windows" in name or ".windows." in name:
            explicit_platform = "windows"

    if not explicit_type:
        if re.fullmatch(
            r"dazuofanyiguan_delta\.for\.windows_"
            r"\d+(?:\.\d+){1,3}_to_\d+(?:\.\d+){1,3}\.zip",
            name,
        ):
            explicit_type = "windows_file_delta"
        elif explicit_platform == "macos" or name.endswith(".dmg"):
            explicit_type = "macos_dmg_update"
        else:
            explicit_type = "windows_full_update"

    if not explicit_platform:
        explicit_platform = "macos" if explicit_type.startswith("macos") else "windows"

    return explicit_type, explicit_platform


def extract_signature_from_release_notes(notes: str, platform: str = "") -> str:
    """Extract the signature for a package platform from release notes.

    Supported markers:
    - DZFYQ-SIG-WINDOWS:<b64>
    - DZFYQ-SIG-MACOS:<b64>
    - DZFYQ-SIG:<b64>  (legacy, Windows only)
    - "signature": "<b64>" (legacy, Windows only)
    """
    text = notes or ""
    wanted = normalize_platform(platform)

    platform_patterns = {
        "windows": [
            r"DZFYQ-SIG-WINDOWS:([A-Za-z0-9+/=]+)",
            r"DZFYQ-SIG-WIN:([A-Za-z0-9+/=]+)",
        ],
        "macos": [
            r"DZFYQ-SIG-MACOS:([A-Za-z0-9+/=]+)",
            r"DZFYQ-SIG-MAC:([A-Za-z0-9+/=]+)",
            r"DZFYQ-SIG-DARWIN:([A-Za-z0-9+/=]+)",
        ],
    }

    if wanted in platform_patterns:
        for pattern in platform_patterns[wanted]:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()

    # Legacy single marker is only valid for Windows packages.
    if not wanted or wanted == "windows":
        match = re.search(r"DZFYQ-SIG:([A-Za-z0-9+/=]+)", text)
        if match:
            return match.group(1).strip()
        match = re.search(r'"signature"\s*:\s*"([A-Za-z0-9+/=]+)"', text)
        if match:
            return match.group(1).strip()
    return ""


def strip_signature_markers_from_notes(notes: str) -> str:
    text = notes or ""
    text = re.sub(r"DZFYQ-SIG(?:-[A-Za-z]+)?:[A-Za-z0-9+/=]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r'"signature"\s*:\s*"[A-Za-z0-9+/=]+"', "", text)
    return text.strip()


def load_manifest_from_dir(directory: str) -> dict:
    path = Path(directory) / "update_manifest.json"
    if not path.is_file():
        raise RuntimeError("更新包缺少版本清单 update_manifest.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise RuntimeError("更新包版本清单损坏") from error
    if not isinstance(data, dict):
        raise RuntimeError("更新包版本清单格式无效")
    return data


def verify_package_authenticity(
    *,
    package_path: str,
    expected_version: str,
    signature_b64: str,
    expected_filename: str = "",
    package_type: str = "",
    platform: str = "",
    max_bytes: Optional[int] = None,
) -> dict:
    actual_sha = sha256_file(package_path, max_bytes=max_bytes)
    size_bytes = Path(package_path).stat().st_size
    filename = expected_filename or Path(package_path).name
    resolved_type, resolved_platform = infer_package_identity(
        filename,
        package_type=package_type,
        platform=platform,
    )
    payload = {
        "app_version": normalize_version(expected_version),
        "package_type": resolved_type,
        "platform": resolved_platform,
        "filename": filename,
        "size_bytes": int(size_bytes),
        "sha256": actual_sha,
    }
    if not signature_b64:
        raise RuntimeError("更新包缺少有效签名，已终止更新。")
    verify_ed25519_signature(build_canonical_payload(payload), signature_b64)
    return payload
