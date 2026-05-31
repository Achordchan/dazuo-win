import asyncio
import hashlib
import json
import logging
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional

import aiohttp

from ..version import APP_VERSION

logger = logging.getLogger(__name__)

DEEPLX_REPO_API = "https://api.github.com/repos/OwO-Network/DeepLX/releases/latest"
ENGINE_VENDOR = "DeepLX"
ENGINE_EXE_NAME = "deeplx.exe"


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
                return AchordEngineInfo(
                    version=str(manifest.get("version") or "bundled"),
                    executable_path=executable,
                    source="bundled" if directory == _bundled_engine_dir() else "development",
                    manifest_path=manifest_path if os.path.isfile(manifest_path) else "",
                )

        raise FileNotFoundError("缺少内置引擎文件，请先下载 DeepLX Windows amd64 二进制到 third_party/deeplx/windows/amd64/deeplx.exe")

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
            candidates.append(
                AchordEngineInfo(
                    version=str(manifest.get("version") or name),
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

    @property
    def base_url(self) -> str:
        if not self.port:
            raise RuntimeError("Achord 内置引擎尚未启动")
        return f"http://127.0.0.1:{self.port}"

    async def ensure_started(self) -> None:
        if self.process and self.process.poll() is None and self.port:
            return

        self.stop()
        self.engine_info = AchordEngineLocator.current_engine()
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

    async def download_latest(
        self,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> AchordEngineInfo:
        release = await self.check_latest()
        current = self.current_engine_info()
        if current and compare_versions(release.version, current.version) <= 0:
            if progress_callback:
                progress_callback(100)
            return current

        root = _engine_cache_root()
        os.makedirs(root, exist_ok=True)

        safe_version = release.version or release.tag_name.lstrip("v") or str(int(time.time()))
        staging_dir = os.path.join(root, f"_download_{safe_version}_{int(time.time())}")
        target_dir = os.path.join(root, safe_version)
        os.makedirs(staging_dir, exist_ok=True)
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
                        raise RuntimeError(f"下载引擎失败: HTTP {response.status}")
                    total = int(response.headers.get("content-length") or 0)
                    downloaded = 0
                    with open(temp_exe, "wb") as file:
                        async for chunk in response.content.iter_chunked(1024 * 256):
                            file.write(chunk)
                            downloaded += len(chunk)
                            if total and progress_callback:
                                progress_callback(min(99, int(downloaded / total * 100)))

            if not os.path.isfile(temp_exe) or os.path.getsize(temp_exe) < 1024:
                raise RuntimeError("下载的引擎文件无效")

            digest = _sha256_file(temp_exe)
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
