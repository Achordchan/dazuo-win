import asyncio
import atexit
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
import socket
import subprocess
import sys
import time
import weakref
from dataclasses import dataclass
from typing import Callable, Optional

import aiohttp

from ..version import APP_VERSION

logger = logging.getLogger(__name__)

DEEPLX_REPO_API = "https://api.github.com/repos/OwO-Network/DeepLX/releases/latest"
ENGINE_VENDOR = "DeepLX"
ENGINE_EXE_NAME = "deeplx.exe"
ENGINE_PAYLOAD_NAME = f"{ENGINE_EXE_NAME}.payload"

# Independent trust root for DeepLX binaries.
# Bundled third_party manifest sha256 is always trusted; online downloads must
# match either the bundled digest for the same version or a release allowlist.
TRUSTED_ENGINE_DIGESTS: dict[str, str] = {}


def _load_bundled_trust_root() -> dict[str, str]:
    trusted: dict[str, str] = {}
    for directory in (_bundled_engine_dir(), _dev_engine_dir()):
        manifest_path = os.path.join(directory, "manifest.json")
        manifest = _read_manifest(manifest_path)
        version = str(manifest.get("version") or "").strip().lstrip("v")
        digest = str(manifest.get("sha256") or "").strip().lower()
        if version and digest:
            trusted[version] = digest
    allowlist_paths = {
        os.path.normpath(
            os.path.join(directory, "..", "..", "trusted_releases.json")
        )
        for directory in (_bundled_engine_dir(), _dev_engine_dir())
    }
    for allowlist_path in allowlist_paths:
        try:
            with open(allowlist_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            releases = data.get("releases") if isinstance(data, dict) else None
            if isinstance(releases, dict):
                for version, digest in releases.items():
                    version = str(version or "").strip().lstrip("v")
                    digest = str(digest or "").strip().lower()
                    if version and re.fullmatch(r"[0-9a-f]{64}", digest):
                        trusted[version] = digest
        except FileNotFoundError:
            continue
        except Exception as error:
            logger.warning(
                "Failed to load DeepLX trust allowlist %s: %s",
                allowlist_path,
                error,
            )
    return trusted


def _expected_engine_digest(version: str) -> str:
    global TRUSTED_ENGINE_DIGESTS
    if not TRUSTED_ENGINE_DIGESTS:
        TRUSTED_ENGINE_DIGESTS = _load_bundled_trust_root()
    return TRUSTED_ENGINE_DIGESTS.get(str(version or "").strip().lstrip("v"), "")


def _assert_trusted_engine(path: str, version: str, expected_digest: str = "") -> str:
    digest = _sha256_file(path).lower()
    trusted = (expected_digest or _expected_engine_digest(version) or "").lower()
    if not trusted:
        raise RuntimeError(
            f"DeepLX {version} 尚未通过当前客户端安全校验，请等待客户端更新后再安装。"
        )
    if digest != trusted:
        raise RuntimeError("DeepLX 文件摘要与可信清单不一致，已拒绝执行。")
    if os.path.getsize(path) > 80 * 1024 * 1024:
        raise RuntimeError("DeepLX 文件体积过大，已拒绝执行。")
    return digest

_ENGINE_DOWNLOAD_LOCK = asyncio.Lock()

_ENGINE_MANAGERS: "weakref.WeakSet[AchordEngineManager]" = weakref.WeakSet()


def _stop_all_engine_managers() -> None:
    for manager in list(_ENGINE_MANAGERS):
        try:
            manager.stop()
        except Exception as error:
            logger.warning("退出时关闭 Achord 内置引擎失败: %s", error)


atexit.register(_stop_all_engine_managers)


@dataclass(frozen=True)
class AchordEngineInfo:
    version: str
    executable_path: str
    source: str
    manifest_path: str = ""


@dataclass(frozen=True)
class AchordEngineRelease:
    version: str
    tag_name: str
    asset_name: str
    download_url: str
    published_at: str
    release_url: str


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _runtime_base_dir() -> str:
    if getattr(sys, "frozen", False) or globals().get("__compiled__"):
        candidates = []
        for raw_path in (sys.executable, sys.argv[0]):
            if raw_path:
                base = os.path.dirname(os.path.abspath(raw_path))
                candidates.extend(
                    [
                        base,
                        os.path.join(base, "main.dist"),
                        os.path.join(base, f"{os.path.splitext(os.path.basename(raw_path))[0]}.dist"),
                    ]
                )
        candidates.extend([os.getcwd(), os.path.join(os.getcwd(), "main.dist")])
        for candidate in candidates:
            if os.path.isdir(os.path.join(candidate, "engines")) or os.path.isdir(os.path.join(candidate, "src", "ziyuan")):
                return os.path.abspath(candidate)
        return os.path.dirname(os.path.abspath(sys.executable))
    return _project_root()


def _engine_cache_root() -> str:
    return os.path.join(os.path.expanduser("~"), ".dzfyq", "engines", "deeplx")


def _bundled_engine_dir() -> str:
    return os.path.join(_runtime_base_dir(), "engines", "deeplx", "windows", "amd64")


def _dev_engine_dir() -> str:
    return os.path.join(_project_root(), "third_party", "deeplx", "windows", "amd64")


def _version_parts(version: str) -> tuple[int, int, int]:
    parts = []
    for part in (version or "").lstrip("v").split("."):
        number = "".join(ch for ch in part if ch.isdigit())
        if number:
            parts.append(int(number))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def compare_versions(left: str, right: str) -> int:
    left_parts = _version_parts(left)
    right_parts = _version_parts(right)
    if left_parts > right_parts:
        return 1
    if left_parts < right_parts:
        return -1
    return 0


def _read_manifest(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _asset_name_for_current_platform() -> str:
    if sys.platform != "win32":
        raise RuntimeError("Achord 内置引擎当前仅支持 Windows 自动管理。")
    return "deeplx_windows_amd64.exe"


class AchordEngineLocator:
    @staticmethod
    def current_engine() -> AchordEngineInfo:
        cached = AchordEngineLocator._latest_cached_engine()
        if cached:
            return cached

        for directory in (_bundled_engine_dir(), _dev_engine_dir()):
            executable = os.path.join(directory, ENGINE_EXE_NAME)
            if os.path.isfile(executable):
                manifest_path = os.path.join(directory, "manifest.json")
                manifest = _read_manifest(manifest_path)
                payload_path = os.path.join(directory, ENGINE_PAYLOAD_NAME)
                expected_sha = str(manifest.get("sha256") or "").strip().lower()
                version = str(manifest.get("version") or "bundled")
                allowlist_sha = _expected_engine_digest(version)
                if expected_sha:
                    try:
                        actual = _sha256_file(executable).lower()
                        if actual != expected_sha:
                            materialized = AchordEngineLocator._materialize_payload_engine(directory)
                            if materialized:
                                return materialized
                        if allowlist_sha and actual != allowlist_sha:
                            logger.warning("Bundled engine digest is not in allowlist for %s", version)
                    except Exception as error:
                        logger.warning("Failed to validate bundled engine hash: %s", error)
                return AchordEngineInfo(
                    version=str(manifest.get("version") or "bundled"),
                    executable_path=executable,
                    source="bundled" if directory == _bundled_engine_dir() else "development",
                    manifest_path=manifest_path if os.path.isfile(manifest_path) else "",
                )
            materialized = AchordEngineLocator._materialize_payload_engine(directory)
            if materialized:
                return materialized

        raise FileNotFoundError("缺少内置引擎文件，请先下载 DeepLX Windows amd64 二进制到 third_party/deeplx/windows/amd64/deeplx.exe")

    @staticmethod
    def _materialize_payload_engine(directory: str) -> Optional[AchordEngineInfo]:
        payload_path = os.path.join(directory, ENGINE_PAYLOAD_NAME)
        if not os.path.isfile(payload_path):
            return None

        manifest_path = os.path.join(directory, "manifest.json")
        manifest = _read_manifest(manifest_path)
        version = str(manifest.get("version") or f"bundled-{APP_VERSION}")
        target_dir = os.path.join(_engine_cache_root(), version)
        target_exe = os.path.join(target_dir, ENGINE_EXE_NAME)
        target_manifest = os.path.join(target_dir, "manifest.json")

        if os.path.isfile(target_exe):
            return AchordEngineInfo(
                version=version,
                executable_path=target_exe,
                source="payload_cache",
                manifest_path=target_manifest if os.path.isfile(target_manifest) else "",
            )

        staging_dir = os.path.join(_engine_cache_root(), f"_payload_{version}_{int(time.time())}")
        try:
            os.makedirs(staging_dir, exist_ok=True)
            staging_exe = os.path.join(staging_dir, ENGINE_EXE_NAME)
            shutil.copy2(payload_path, staging_exe)
            if not os.path.isfile(staging_exe) or os.path.getsize(staging_exe) < 1024:
                raise RuntimeError("invalid bundled engine payload")
            expected = str(manifest.get("sha256") or "").strip().lower()
            actual = _sha256_file(staging_exe).lower()
            if expected and actual != expected:
                raise RuntimeError("bundled engine payload hash mismatch")
            allowlist = _expected_engine_digest(version)
            if allowlist and actual != allowlist:
                raise RuntimeError("bundled engine payload not in trust allowlist")

            payload_manifest = dict(manifest)
            payload_manifest.update(
                {
                    "name": payload_manifest.get("name") or ENGINE_VENDOR,
                    "version": version,
                    "sha256": str(manifest.get("sha256") or _sha256_file(staging_exe)).strip().lower(),
                    "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "source": "bundled_payload",
                }
            )
            with open(os.path.join(staging_dir, "manifest.json"), "w", encoding="utf-8") as file:
                json.dump(payload_manifest, file, ensure_ascii=False, indent=2)
                file.write("\n")

            license_path = os.path.join(directory, "LICENSE")
            if os.path.isfile(license_path):
                shutil.copy2(license_path, os.path.join(staging_dir, "LICENSE"))

            os.makedirs(_engine_cache_root(), exist_ok=True)
            if os.path.isdir(target_dir):
                shutil.rmtree(target_dir)
            os.replace(staging_dir, target_dir)
            return AchordEngineInfo(
                version=version,
                executable_path=target_exe,
                source="payload_cache",
                manifest_path=target_manifest,
            )
        except Exception as error:
            shutil.rmtree(staging_dir, ignore_errors=True)
            logger.warning("Failed to materialize bundled engine payload: %s", error)
            return None

    @staticmethod
    def _latest_cached_engine() -> Optional[AchordEngineInfo]:
        root = _engine_cache_root()
        if not os.path.isdir(root):
            return None

        candidates: list[AchordEngineInfo] = []
        for name in os.listdir(root):
            directory = os.path.join(root, name)
            executable = os.path.join(directory, ENGINE_EXE_NAME)
            manifest_path = os.path.join(directory, "manifest.json")
            if not os.path.isdir(directory) or not os.path.isfile(executable):
                continue
            manifest = _read_manifest(manifest_path)
            version = str(manifest.get("version") or name).strip().lstrip("v")
            # Only independent allowlist digests are trusted for cache selection.
            # Never promote a cache entry solely because its own manifest claims a high version/hash.
            allowlist = _expected_engine_digest(version)
            if not allowlist:
                logger.warning("Skip cache engine not in trust allowlist: %s", executable)
                continue
            try:
                actual = _assert_trusted_engine(executable, version, expected_digest=allowlist)
            except Exception as error:
                logger.warning("Skip untrusted cached engine %s: %s", executable, error)
                continue
            candidates.append(
                AchordEngineInfo(
                    version=version,
                    executable_path=executable,
                    source="cache",
                    manifest_path=manifest_path if os.path.isfile(manifest_path) else "",
                )
            )

        if not candidates:
            return None
        return max(candidates, key=lambda item: _version_parts(item.version))


class AchordEngineManager:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.port: Optional[int] = None
        self.token: str = ""
        self.engine_info: Optional[AchordEngineInfo] = None
        self._start_lock = asyncio.Lock()
        _ENGINE_MANAGERS.add(self)

    @property
    def base_url(self) -> str:
        if not self.port:
            raise RuntimeError("Achord 内置引擎尚未启动")
        return f"http://127.0.0.1:{self.port}"

    async def ensure_started(self) -> None:
        async with self._start_lock:
            if self.process and self.process.poll() is None and self.port:
                return

            self.stop()
            self.engine_info = AchordEngineLocator.current_engine()
            _assert_trusted_engine(self.engine_info.executable_path, self.engine_info.version)
            self.port = _find_free_loopback_port()
            self.token = secrets.token_urlsafe(32)

            command = [
                self.engine_info.executable_path,
                "-p",
                str(self.port),
                "-token",
                self.token,
            ]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                self.process = subprocess.Popen(
                    command,
                    cwd=os.path.dirname(self.engine_info.executable_path),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    shell=False,
                    creationflags=creationflags,
                )
            except Exception as error:
                self.stop()
                raise RuntimeError(f"内置引擎启动失败: {error}") from error

            try:
                await self._wait_until_listening()
            except Exception as error:
                self.stop()
                raise RuntimeError(f"内置引擎启动失败: {error}") from error

    async def _wait_until_listening(self) -> None:
        if not self.port:
            raise RuntimeError("引擎端口未分配")

        deadline = time.monotonic() + 8
        last_error: Optional[Exception] = None
        while time.monotonic() < deadline:
            if self.process and self.process.poll() is not None:
                raise RuntimeError("引擎进程已退出")
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                return
            except Exception as error:
                last_error = error
                await asyncio.sleep(0.15)
        raise TimeoutError(f"等待引擎监听超时: {last_error}")

    def stop(self) -> None:
        process = self.process
        self.process = None
        self.port = None
        self.token = ""
        if not process or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=3)
            except Exception as error:
                logger.warning("关闭 Achord 内置引擎失败: %s", error)


class AchordEngineUpdater:
    def __init__(self):
        self.release_api = DEEPLX_REPO_API
        self._timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)

    def current_engine_info(self) -> Optional[AchordEngineInfo]:
        try:
            return AchordEngineLocator.current_engine()
        except Exception:
            return None

    def approved_digest(self, release_or_version) -> str:
        version = getattr(release_or_version, "version", release_or_version)
        return _expected_engine_digest(str(version or ""))

    def is_release_approved(self, release: AchordEngineRelease) -> bool:
        return bool(self.approved_digest(release))

    async def check_latest(self) -> AchordEngineRelease:
        asset_name = _asset_name_for_current_platform()
        async with aiohttp.ClientSession(
            headers={"User-Agent": f"DaZuoFanYiGuan/{APP_VERSION}"},
            timeout=self._timeout,
            trust_env=True,
        ) as session:
            async with session.get(self.release_api) as response:
                if response.status != 200:
                    raise RuntimeError(f"检查引擎更新失败: GitHub HTTP {response.status}")
                data = await response.json(content_type=None)

        tag_name = str(data.get("tag_name") or data.get("name") or "").strip()
        version = tag_name.lstrip("v")
        for asset in data.get("assets") or []:
            if (asset.get("name") or "") == asset_name and asset.get("browser_download_url"):
                return AchordEngineRelease(
                    version=version,
                    tag_name=tag_name,
                    asset_name=asset_name,
                    download_url=asset["browser_download_url"],
                    published_at=str(data.get("published_at") or ""),
                    release_url=str(data.get("html_url") or ""),
                )
        raise RuntimeError(f"最新版本未提供 {asset_name}")

    @property
    def download_in_progress(self) -> bool:
        return _ENGINE_DOWNLOAD_LOCK.locked()

    async def download_latest(
        self,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> AchordEngineInfo:
        if _ENGINE_DOWNLOAD_LOCK.locked():
            raise RuntimeError("DeepLX 更新正在进行，请勿重复操作。")
        async with _ENGINE_DOWNLOAD_LOCK:
            return await self._download_latest_locked(progress_callback)


    async def _download_latest_locked(
        self,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> AchordEngineInfo:
        release = await self.check_latest()
        current = self.current_engine_info()
        # Only skip download when the currently selected engine is already trusted
        # and not older than the remote release. Unknown high-version cache must not
        # block recovery of a bundled/allowlisted engine.
        if current and compare_versions(release.version, current.version) <= 0:
            try:
                _assert_trusted_engine(current.executable_path, current.version)
                if progress_callback:
                    progress_callback(100)
                return current
            except Exception as error:
                logger.warning(
                    "Current engine cannot be reused for download skip (%s); continue downloading %s",
                    error,
                    release.version,
                )

        expected_digest = self.approved_digest(release)
        if not expected_digest:
            raise RuntimeError(
                f"DeepLX {release.version} 尚未通过当前客户端安全校验，请等待客户端更新后再安装。"
            )

        root = _engine_cache_root()
        os.makedirs(root, exist_ok=True)

        safe_version = release.version or release.tag_name.lstrip("v") or str(int(time.time()))
        staging_dir = tempfile.mkdtemp(prefix=f"_download_{safe_version}_", dir=root)
        target_dir = os.path.join(root, safe_version)
        temp_exe = os.path.join(staging_dir, ENGINE_EXE_NAME)
        manifest_path = os.path.join(staging_dir, "manifest.json")

        try:
            async with aiohttp.ClientSession(
                headers={"User-Agent": f"DaZuoFanYiGuan/{APP_VERSION}"},
                timeout=self._timeout,
                trust_env=True,
            ) as session:
                async with session.get(release.download_url) as response:
                    if response.status != 200:
                        raise RuntimeError(f"引擎下载失败: HTTP {response.status}")
                    total = int(response.headers.get("content-length") or 0)
                    max_bytes = 80 * 1024 * 1024
                    if total and total > max_bytes:
                        raise RuntimeError("DeepLX 下载体积过大")
                    downloaded = 0
                    with open(temp_exe, "wb") as file:
                        async for chunk in response.content.iter_chunked(1024 * 256):
                            if not chunk:
                                continue
                            downloaded += len(chunk)
                            if downloaded > max_bytes:
                                raise RuntimeError("DeepLX 下载体积过大")
                            file.write(chunk)
                            if total and progress_callback:
                                progress_callback(min(99, int(downloaded / total * 100)))

            if not os.path.isfile(temp_exe) or os.path.getsize(temp_exe) < 1024:
                raise RuntimeError("下载的引擎文件无效")

            digest = _assert_trusted_engine(temp_exe, safe_version, expected_digest=expected_digest)
            manifest = {
                "name": ENGINE_VENDOR,
                "version": safe_version,
                "asset_name": release.asset_name,
                "sha256": digest,
                "download_url": release.download_url,
                "release_url": release.release_url,
                "published_at": release.published_at,
                "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "license": "MIT",
                "copyright": "Copyright (c) 2022 OwO Network Limited",
            }
            with open(manifest_path, "w", encoding="utf-8") as file:
                json.dump(manifest, file, ensure_ascii=False, indent=2)
                file.write("\n")

            if os.path.isdir(target_dir):
                shutil.rmtree(target_dir)
            os.replace(staging_dir, target_dir)
            if progress_callback:
                progress_callback(100)
            return AchordEngineInfo(
                version=safe_version,
                executable_path=os.path.join(target_dir, ENGINE_EXE_NAME),
                source="cache",
                manifest_path=os.path.join(target_dir, "manifest.json"),
            )
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
