import base64
import os
import sys
import json
import aiohttp
import asyncio
import logging
import re
import subprocess
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass
from PyQt5.QtCore import QObject, pyqtSignal
from src.version import APP_VERSION
from src.gongju.update_delta import (
    DELTA_PACKAGE_TYPE,
    inspect_delta_package,
    is_reparse_point,
    reconstruct_delta_package,
)
from src.gongju.update_trust import (
    extract_signature_from_release_notes,
    infer_package_identity,
    load_manifest_from_dir,
    normalize_platform,
    normalize_version,
    sha256_file,
    strip_signature_markers_from_notes,
    verify_package_authenticity,
)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def should_defer_start_for_pending_update(
    current_version: str,
    *,
    update_restart: bool = False,
    max_age_seconds: float = 600.0,
) -> bool:
    """Block ordinary launches while the external updater owns the install dir."""
    if update_restart:
        return False
    cache_root = os.environ.get("DZFYQ_HOME") or os.path.expanduser("~/.dzfyq")
    pending_path = os.path.join(cache_root, "update_state", "pending_update.json")
    if not os.path.isfile(pending_path):
        return False
    try:
        with open(pending_path, "r", encoding="utf-8") as state_file:
            state = json.load(state_file)
        if not isinstance(state, dict) or not state.get("expected_version"):
            return False
        age = max(0.0, time.time() - os.path.getmtime(pending_path))
        return age <= max(float(max_age_seconds), 1.0)
    except Exception as error:
        logger.warning("读取待应用更新状态失败，按非活动状态处理: %s", error)
        return False


class UpdateSourceError(RuntimeError):
    """所有更新源都不可用时抛出。"""


@dataclass(frozen=True)
class UpdateSource:
    """一个 Release 更新源（GitHub / Gitee 的 releases/latest 接口）。"""

    name: str
    api_url: str
    repo_url: str
    headers: tuple = ()

    def request_headers(self) -> dict:
        return dict(self.headers)


GITHUB_REPO_URL = "https://github.com/Achordchan/dazuo-win"
GITEE_REPO_URL = "https://gitee.com/Achordchan/dazuofanyiguan"

# 1.2.11 起以 GitHub 为主仓库与主更新源；Gitee 长期保留为备用镜像源：
# 旧版本客户端只认 Gitee，且 GitHub 在部分网络下不可达，因此每个版本都需双端发布。
# 顺序即尝试顺序。
DEFAULT_UPDATE_SOURCES = (
    UpdateSource(
        name="GitHub",
        api_url="https://api.github.com/repos/Achordchan/dazuo-win/releases/latest",
        repo_url=GITHUB_REPO_URL,
        headers=(
            ("Accept", "application/vnd.github+json"),
            ("X-GitHub-Api-Version", "2022-11-28"),
            ("User-Agent", f"DaZuoFanYiGuan/{APP_VERSION}"),
        ),
    ),
    UpdateSource(
        name="Gitee",
        api_url="https://gitee.com/api/v5/repos/Achordchan/dazuofanyiguan/releases/latest",
        repo_url=GITEE_REPO_URL,
        headers=(("User-Agent", f"DaZuoFanYiGuan/{APP_VERSION}"),),
    ),
)

# 单个更新源的检查超时。GitHub 在部分网络下可能被阻断，需要尽快切换到下一个源。
UPDATE_SOURCE_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class UpdateAsset:
    name: str
    url: str
    size_bytes: int
    package_type: str
    signature: str
    sha256: str = ""
    base_version: str = ""

    @property
    def suffix(self) -> str:
        return os.path.splitext(self.name)[1] or ".zip"


class Updater(QObject):
    MAX_UPDATE_PACKAGE_BYTES = 400 * 1024 * 1024
    MAX_ZIP_MEMBERS = 20000
    MAX_ZIP_UNCOMPRESSED_BYTES = 800 * 1024 * 1024
    MAX_ZIP_COMPRESSION_RATIO = 100.0
    MAX_SIGNATURE_METADATA_BYTES = 64 * 1024
    MAX_UPDATE_BACKUPS = 2
    # 定义信号
    update_available = pyqtSignal(str, str, bool)  # 版本号, 更新说明, 是否强制更新
    update_progress = pyqtSignal(int)  # 下载进度
    update_error = pyqtSignal(str)  # 错误信息
    update_complete = pyqtSignal(str)  # 下载完成的文件路径

    def __init__(self):
        super().__init__()
        self.current_version = APP_VERSION  # 当前版本号
        self.update_sources: tuple[UpdateSource, ...] = DEFAULT_UPDATE_SOURCES
        self.active_update_source: UpdateSource | None = None
        # 兼容旧调用方/测试：分别暴露 GitHub 与 Gitee 接口地址。
        self.github_api = DEFAULT_UPDATE_SOURCES[0].api_url
        self.gitee_api = DEFAULT_UPDATE_SOURCES[1].api_url
        self.update_url = None
        self.release_notes = None
        self.force_update = False
        self.asset_suffix = None
        self.latest_version = None
        self.release_signature = None
        self._force_update_requested = False
        self.expected_asset_name = None
        self.expected_package_sha256 = None
        self.expected_package_size = None
        self.selected_package_type = "windows_full_update"
        self.selected_base_version = ""
        self._selected_asset = None
        self._fallback_full_asset = None
        self._prepared_update_source = None
        self._download_in_progress = False
        cache_root = os.environ.get("DZFYQ_HOME") or os.path.expanduser("~/.dzfyq")
        self._download_dir = os.path.join(cache_root, "update_cache")
        self._backup_root = os.path.join(cache_root, "update_backup")
        self._state_dir = os.path.join(cache_root, "update_state")
        # Never wipe update_cache while a previous apply is still pending.
        if not os.path.exists(self._pending_update_path()):
            self._cleanup_download_cache()

    @property
    def force_update_requested(self) -> bool:
        """Whether release metadata requests an automatic authenticated update."""
        return bool(self._force_update_requested)

    @property
    def download_in_progress(self) -> bool:
        return bool(self._download_in_progress)

    def _ensure_download_dir(self) -> None:
        os.makedirs(self._download_dir, exist_ok=True)

    def _cleanup_download_cache(self, keep_file: str | None = None) -> None:
        self._ensure_download_dir()
        keep_path = os.path.abspath(keep_file) if keep_file else None
        for name in os.listdir(self._download_dir):
            file_path = os.path.join(self._download_dir, name)
            if keep_path and os.path.abspath(file_path) == keep_path:
                continue
            try:
                if os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                elif os.path.isfile(file_path):
                    os.remove(file_path)
                else:
                    continue
                logger.info(f"已清理旧更新包: {file_path}")
            except OSError as error:
                logger.warning(f"清理旧更新包失败: {file_path}, {error}")

    def _prune_update_backups(self) -> None:
        if not os.path.isdir(self._backup_root):
            return
        backups = []
        try:
            with os.scandir(self._backup_root) as entries:
                for entry in entries:
                    if is_reparse_point(entry.path):
                        logger.warning("跳过重解析点更新备份: %s", entry.path)
                        continue
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    backups.append((entry.stat(follow_symlinks=False).st_mtime, entry.path))
        except OSError as error:
            logger.warning("枚举更新备份失败: %s", error)
            return
        backups.sort(key=lambda item: item[0], reverse=True)
        for _modified_at, path in backups[self.MAX_UPDATE_BACKUPS:]:
            try:
                shutil.rmtree(path)
                logger.info("已清理旧更新备份: %s", path)
            except OSError as error:
                logger.warning("清理旧更新备份失败: %s, %s", path, error)

    def _build_download_path(self, suffix: str) -> str:
        self._ensure_download_dir()
        normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
        filename = f"dazuofanyiguan_update{normalized_suffix}"
        return os.path.join(self._download_dir, filename)

    def _expected_windows_full_update_asset_names(self, version: str) -> set[str]:
        normalized_version = (version or "").strip().lower().lstrip("v")
        if not normalized_version:
            return set()
        return {
            f"dazuofanyiguan_full.for.windows_{normalized_version}.zip",
            f"dazuofanyiguan_full.for.windows_v{normalized_version}.zip",
        }

    def _is_windows_full_update_asset(self, asset_name: str, version: str | None = None) -> bool:
        normalized = os.path.basename(asset_name).lower()
        if version:
            return normalized in self._expected_windows_full_update_asset_names(version)
        return re.fullmatch(
            r"dazuofanyiguan_full\.for\.windows(?:_v?)?\d+(?:\.\d+){1,3}\.zip",
            normalized,
        ) is not None


    def _expected_windows_delta_update_asset_name(
        self,
        base_version: str,
        target_version: str,
    ) -> str:
        base = normalize_version(base_version)
        target = normalize_version(target_version)
        if not base or not target:
            return ""
        return f"dazuofanyiguan_delta.for.windows_{base}_to_{target}.zip"

    @staticmethod
    def _describe_source_status(source: UpdateSource, status: int) -> str:
        if status == 404:
            return (
                f"{source.name} 返回 404。可能是仓库地址错误、仓库被删除、"
                "被设为私有或尚未发布任何 Release。"
            )
        if status == 403:
            return f"{source.name} 返回 403。可能是访问被拒绝、触发频率限制或需要鉴权。"
        if status == 429:
            return f"{source.name} 返回 429。请求过于频繁，请稍后再试。"
        return f"{source.name} 返回 HTTP {status}。"

    async def _fetch_latest_release(self, session) -> dict:
        """按顺序尝试各更新源，返回第一个可用的 Release 数据。"""
        errors = []
        self.active_update_source = None
        for source in self.update_sources:
            try:
                logger.info("正在请求 %s Release API: %s", source.name, source.api_url)
                async with session.get(
                    source.api_url,
                    headers=source.request_headers(),
                    timeout=aiohttp.ClientTimeout(total=UPDATE_SOURCE_TIMEOUT_SECONDS),
                ) as response:
                    if response.status != 200:
                        raise UpdateSourceError(
                            self._describe_source_status(source, response.status)
                        )
                    data = await response.json(content_type=None)
                if not isinstance(data, dict) or not (
                    data.get("tag_name") or data.get("name")
                ):
                    raise UpdateSourceError(f"{source.name} 返回的 Release 数据无效。")
                self.active_update_source = source
                logger.info("使用更新源: %s", source.name)
                return data
            except UpdateSourceError as error:
                errors.append(str(error))
                logger.warning("更新源 %s 不可用: %s", source.name, error)
            except asyncio.TimeoutError:
                errors.append(f"{source.name} 请求超时。")
                logger.warning("更新源 %s 请求超时", source.name)
            except Exception as error:  # 网络错误、JSON 解析错误等，继续尝试下一个源
                errors.append(f"{source.name} 请求失败：{error}")
                logger.warning("更新源 %s 请求失败: %s", source.name, error)
        raise UpdateSourceError(" ".join(errors) or "没有可用的更新源。")

    @staticmethod
    def _release_assets_by_name(assets) -> dict[str, dict]:
        result = {}
        for asset in assets or []:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "").strip()
            if name:
                result[name.lower()] = asset
        return result

    async def _mirror_asset_candidates(
        self,
        session,
        asset_name: str,
        expected_version: str,
    ) -> list[dict]:
        """在其他更新源上查找同名、同版本的资源，供主源下载失败时兜底。

        只做定位，不放松校验：下载后仍按同一份签名/摘要/大小验证，镜像无法替换内容。
        """
        candidates: list[dict] = []
        wanted = str(asset_name or "").strip().lower()
        target = normalize_version(expected_version)
        if not wanted or not target:
            return candidates
        active = self.active_update_source
        for source in self.update_sources:
            if active is not None and source.api_url == active.api_url:
                continue
            try:
                async with session.get(
                    source.api_url,
                    headers=source.request_headers(),
                    timeout=aiohttp.ClientTimeout(total=UPDATE_SOURCE_TIMEOUT_SECONDS),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "镜像源 %s 不可用: %s",
                            source.name,
                            self._describe_source_status(source, response.status),
                        )
                        continue
                    data = await response.json(content_type=None)
            except Exception as error:
                logger.warning("镜像源 %s 请求失败: %s", source.name, error)
                continue
            if not isinstance(data, dict):
                continue
            tag = str(data.get("tag_name") or data.get("name") or "")
            if normalize_version(tag) != target:
                logger.warning(
                    "镜像源 %s 的最新版本 %s 与目标版本 %s 不一致，跳过",
                    source.name,
                    tag,
                    target,
                )
                continue
            asset = self._release_assets_by_name(data.get("assets")).get(wanted)
            url = str((asset or {}).get("browser_download_url") or "").strip()
            if not url:
                logger.warning("镜像源 %s 缺少资源 %s", source.name, asset_name)
                continue
            candidates.append(
                {
                    "source": source.name,
                    "url": url,
                    "size": int((asset or {}).get("size") or 0),
                }
            )
        return candidates

    async def _fetch_small_asset(self, session, url: str, package_name: str) -> bytes:
        # 签名元数据很小，用与 Release API 相同的短超时，避免资源域名被阻断时
        # 长时间等待（会话默认超时可达 5 分钟），以便尽快切换到镜像源。
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=UPDATE_SOURCE_TIMEOUT_SECONDS),
        ) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"下载签名元数据失败：HTTP {response.status}，文件 {package_name}"
                )
            content_length = int(response.headers.get("content-length", 0) or 0)
            if content_length > self.MAX_SIGNATURE_METADATA_BYTES:
                raise RuntimeError(f"签名元数据体积异常：{package_name}")
            chunks = []
            total = 0
            async for chunk in response.content.iter_chunked(8192):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self.MAX_SIGNATURE_METADATA_BYTES:
                    raise RuntimeError(f"签名元数据体积异常：{package_name}")
                chunks.append(chunk)
            return b"".join(chunks)

    async def _read_signature_metadata(
        self,
        session,
        assets_by_name: dict[str, dict],
        package_asset: dict,
        *,
        expected_package_type: str,
        expected_target_version: str,
    ) -> dict | None:
        package_name = str(package_asset.get("name") or "").strip()
        signature_name = f"{package_name}.sig.json"
        signature_asset = assets_by_name.get(signature_name.lower())
        if not signature_asset:
            return None
        signature_url = str(signature_asset.get("browser_download_url") or "").strip()
        if not signature_url:
            raise RuntimeError(f"签名元数据缺少下载地址：{package_name}")
        try:
            raw = await self._fetch_small_asset(session, signature_url, package_name)
        except Exception as error:
            primary_error = error
            if isinstance(error, asyncio.TimeoutError):
                primary_error = RuntimeError(f"下载签名元数据超时：{package_name}")
            # 主源（如 GitHub 资源域名）不可达时，从镜像源取同名签名文件；内容校验不变。
            raw = None
            for candidate in await self._mirror_asset_candidates(
                session, signature_name, expected_target_version
            ):
                try:
                    raw = await self._fetch_small_asset(session, candidate["url"], package_name)
                    logger.warning(
                        "主更新源签名元数据下载失败（%s），已改用 %s 镜像",
                        primary_error,
                        candidate["source"],
                    )
                    break
                except Exception as mirror_error:
                    logger.warning(
                        "镜像源 %s 签名元数据下载失败: %s", candidate["source"], mirror_error
                    )
            if raw is None:
                raise primary_error
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except Exception as error:
            raise RuntimeError(f"签名元数据损坏：{package_name}") from error
        if not isinstance(payload, dict):
            raise RuntimeError(f"签名元数据格式无效：{package_name}")
        if str(payload.get("filename") or "") != package_name:
            raise RuntimeError(f"签名元数据文件名不匹配：{package_name}")
        if normalize_version(payload.get("app_version")) != normalize_version(
            expected_target_version
        ):
            raise RuntimeError(f"签名元数据目标版本不匹配：{package_name}")
        if str(payload.get("package_type") or "") != expected_package_type:
            raise RuntimeError(f"签名元数据包类型不匹配：{package_name}")
        if normalize_platform(payload.get("platform")) != "windows":
            raise RuntimeError(f"签名元数据平台不匹配：{package_name}")
        signature = str(payload.get("signature") or "").strip()
        digest = str(payload.get("sha256") or "").strip().lower()
        try:
            size_bytes = int(payload.get("size_bytes") or 0)
        except (TypeError, ValueError) as error:
            raise RuntimeError(f"签名元数据文件大小无效：{package_name}") from error
        if not signature or not re.fullmatch(r"[A-Za-z0-9+/=]+", signature):
            raise RuntimeError(f"签名元数据缺少有效签名：{package_name}")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"签名元数据 SHA256 无效：{package_name}")
        if size_bytes <= 0:
            raise RuntimeError(f"签名元数据文件大小无效：{package_name}")
        release_size = int(package_asset.get("size") or 0)
        if release_size and release_size != size_bytes:
            raise RuntimeError(f"签名元数据文件大小与 Release 不一致：{package_name}")
        return {
            "signature": signature,
            "sha256": digest,
            "size_bytes": size_bytes,
        }

    @staticmethod
    def _build_update_asset(
        package_asset: dict,
        *,
        package_type: str,
        signature: str,
        signature_metadata: dict | None = None,
        base_version: str = "",
    ) -> UpdateAsset:
        metadata = signature_metadata or {}
        return UpdateAsset(
            name=str(package_asset.get("name") or "").strip(),
            url=str(package_asset.get("browser_download_url") or "").strip(),
            size_bytes=int(metadata.get("size_bytes") or package_asset.get("size") or 0),
            package_type=package_type,
            signature=str(metadata.get("signature") or signature or "").strip(),
            sha256=str(metadata.get("sha256") or "").strip().lower(),
            base_version=normalize_version(base_version),
        )

    def _activate_update_asset(self, asset: UpdateAsset) -> None:
        self._selected_asset = asset
        self.update_url = asset.url
        self.asset_suffix = asset.suffix
        self.release_signature = asset.signature
        self.expected_asset_name = asset.name
        self.expected_package_size = asset.size_bytes or None
        self.expected_package_sha256 = asset.sha256 or None
        self.selected_package_type = asset.package_type
        self.selected_base_version = asset.base_version

    def _sanitize_name(self, value: str | None) -> str:
        safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in (value or ""))
        return safe.strip("._-") or str(int(time.time()))

    def _last_update_result_path(self) -> str:
        os.makedirs(self._state_dir, exist_ok=True)
        return os.path.join(self._state_dir, "last_update_result.json")

    def _pending_update_path(self) -> str:
        os.makedirs(self._state_dir, exist_ok=True)
        return os.path.join(self._state_dir, "pending_update.json")

    def _is_frozen_app(self) -> bool:
        return bool(getattr(sys, "frozen", False) or globals().get("__compiled__"))

    def _is_process_elevated(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _current_process_creation_filetime(self) -> int:
        """Return the Windows creation FILETIME used to disambiguate PID reuse."""
        if sys.platform != "win32":
            return 0
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            get_process_times = kernel32.GetProcessTimes
            get_process_times.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
            ]
            get_process_times.restype = wintypes.BOOL

            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not get_process_times(
                kernel32.GetCurrentProcess(),
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                raise OSError(ctypes.get_last_error(), "GetProcessTimes failed")
            return (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
        except Exception as error:
            raise RuntimeError(
                "\u65e0\u6cd5\u5b89\u5168\u8bc6\u522b\u5f53\u524d\u8fdb\u7a0b\uff0c\u5df2\u7ec8\u6b62\u9759\u9ed8\u66f4\u65b0\u3002"
            ) from error

    def _ensure_silent_update_context(self) -> None:
        if self._is_process_elevated():
            raise RuntimeError(
                "管理员身份下已禁用静默更新。请退出程序后以普通用户身份运行，"
                "再重新检测更新。"
            )

    def _current_install_dir(self) -> str:
        return os.path.dirname(os.path.abspath(sys.executable))

    def _current_exe_name(self) -> str:
        return os.path.basename(sys.executable) or "大佐翻译官.exe"

    def _ensure_target_writable(self, target_dir: str) -> None:
        probe_path = os.path.join(target_dir, f".update_write_test_{os.getpid()}.tmp")
        try:
            with open(probe_path, "w", encoding="utf-8") as probe_file:
                probe_file.write("ok")
        except PermissionError as error:
            raise PermissionError(
                "当前安装目录没有写入权限，无法静默替换更新。"
                "请先用安装包安装到用户目录，之后即可使用静默更新。"
            ) from error
        finally:
            try:
                if os.path.exists(probe_path):
                    os.remove(probe_path)
            except OSError:
                pass

    def _ensure_safe_replace_paths(self, source_dir: str, target_dir: str) -> None:
        source_abs = os.path.abspath(source_dir)
        target_abs = os.path.abspath(target_dir)
        current_exe = os.path.abspath(sys.executable)

        if source_abs == target_abs:
            raise RuntimeError("更新源目录和安装目录相同，已终止更新。")
        try:
            common_path = os.path.commonpath([source_abs, target_abs])
            if common_path in {source_abs, target_abs}:
                raise RuntimeError("更新源目录和安装目录存在嵌套关系，已终止更新。")
        except ValueError:
            # Windows 跨盘安装是正常场景，robocopy 支持跨盘复制；这里只跳过嵌套检查。
            pass
        if os.path.abspath(os.path.dirname(target_abs)) == target_abs:
            raise RuntimeError("安装目录解析异常，已终止更新。")
        if not os.path.isfile(current_exe):
            raise RuntimeError("当前主程序路径不存在，已终止更新。")
        try:
            if os.path.commonpath([target_abs, current_exe]) != target_abs:
                raise RuntimeError("当前主程序不在安装目录内，已终止更新。")
        except ValueError as error:
            raise RuntimeError("当前主程序路径异常，已终止更新。") from error

    def _safe_extract_zip(self, zip_path: str, extract_dir: str) -> None:
        extract_root = os.path.abspath(extract_dir)
        with zipfile.ZipFile(zip_path, "r") as archive:
            members = archive.infolist()
            if len(members) > self.MAX_ZIP_MEMBERS:
                raise RuntimeError(f"更新包文件数过多，已终止更新：{len(members)}")

            total_uncompressed = 0
            for member in members:
                if member.is_dir():
                    continue
                total_uncompressed += int(member.file_size or 0)
                if total_uncompressed > self.MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise RuntimeError("更新包解压后体积过大，已终止更新。")
                compressed = max(int(member.compress_size or 0), 1)
                ratio = float(member.file_size or 0) / float(compressed)
                if ratio > self.MAX_ZIP_COMPRESSION_RATIO and (member.file_size or 0) > 1024 * 1024:
                    raise RuntimeError("更新包压缩比异常，已终止更新。")

                member_target = os.path.abspath(os.path.join(extract_root, member.filename))
                try:
                    if os.path.commonpath([extract_root, member_target]) != extract_root:
                        raise RuntimeError("更新包包含非法路径，已终止更新。")
                except ValueError as error:
                    raise RuntimeError("更新包包含非法路径，已终止更新。") from error

            for member in members:
                archive.extract(member, extract_root)

    def _validate_update_source_dir(self, source_dir: str, exe_name: str) -> tuple[str, str]:
        exe_path = os.path.join(source_dir, exe_name)
        resource_dir = os.path.join(source_dir, "src", "ziyuan")
        icon_path = os.path.join(resource_dir, "logo.ico")
        if not os.path.isfile(exe_path):
            raise RuntimeError("更新包内未找到主程序，请确认上传的是完整运行目录 zip。")
        if not os.path.isdir(resource_dir) or not os.path.isfile(icon_path):
            raise RuntimeError("更新包缺少 src/ziyuan 资源目录，请确认上传的是完整运行目录 zip。")
        return source_dir, exe_name

    def _read_update_manifest_version(self, directory: str) -> str:
        manifest_path = os.path.join(directory, "update_manifest.json")
        if not os.path.isfile(manifest_path):
            return ""
        try:
            with open(manifest_path, "r", encoding="utf-8") as manifest_file:
                manifest = json.load(manifest_file)
        except Exception as error:
            raise RuntimeError("更新包版本清单损坏，已终止更新。") from error
        return str(manifest.get("app_version") or "").strip()

    def _current_update_platform(self) -> str:
        if sys.platform == "darwin":
            return "macos"
        if sys.platform == "win32":
            return "windows"
        return normalize_platform(sys.platform)

    def _package_identity_for_path(self, file_path: str, filename: str = "") -> tuple[str, str]:
        name = filename or self.expected_asset_name or os.path.basename(file_path)
        return infer_package_identity(name)

    def _validate_update_manifest(self, source_dir: str) -> None:
        expected_version = normalize_version(self.latest_version or "")
        if not expected_version:
            return
        manifest = load_manifest_from_dir(source_dir)
        package_version = normalize_version(str(manifest.get("app_version") or ""))
        if not package_version:
            raise RuntimeError("更新包缺少版本清单，已终止更新。")
        if self._compare_versions(package_version, expected_version) != 0:
            raise RuntimeError(
                f"更新包版本不匹配：期望 v{expected_version}，实际 v{package_version}。"
            )
        # Prefer package-level authenticity verification performed before extract.
        # Still require package_type when present.
        package_type = str(manifest.get("package_type") or "").strip()
        if package_type and package_type not in {"windows_full_update"}:
            raise RuntimeError(f"更新包类型不受支持：{package_type}")

    def _find_update_source_dir(self, extract_dir: str, exe_name: str) -> tuple[str, str]:
        candidates = [exe_name, "大佐翻译官.exe"]

        for candidate in candidates:
            if os.path.isfile(os.path.join(extract_dir, candidate)):
                return self._validate_update_source_dir(extract_dir, candidate)

        entries = [
            os.path.join(extract_dir, name)
            for name in os.listdir(extract_dir)
            if os.path.isdir(os.path.join(extract_dir, name))
        ]
        files = [
            name
            for name in os.listdir(extract_dir)
            if os.path.isfile(os.path.join(extract_dir, name))
        ]
        if len(entries) == 1 and not files:
            for candidate in candidates:
                if os.path.isfile(os.path.join(entries[0], candidate)):
                    return self._validate_update_source_dir(entries[0], candidate)

        raise RuntimeError("更新包内未找到主程序，请确认上传的是完整运行目录 zip。")

    def _verify_downloaded_package(self, file_path: str) -> None:
        size = os.path.getsize(file_path)
        if size <= 0:
            raise RuntimeError("更新包为空，已终止更新。")
        if size > self.MAX_UPDATE_PACKAGE_BYTES:
            raise RuntimeError("更新包体积过大，已终止更新。")
        if self.expected_package_size and int(self.expected_package_size) != size:
            raise RuntimeError("更新包大小与发布信息不一致，已终止更新。")

        actual_sha = sha256_file(file_path, max_bytes=self.MAX_UPDATE_PACKAGE_BYTES)
        if self.expected_package_sha256 and actual_sha != str(self.expected_package_sha256).lower():
            raise RuntimeError("更新包校验值与发布信息不一致，已终止更新。")

        signature = (self.release_signature or "").strip()
        if not signature:
            raise RuntimeError("更新包缺少有效签名，已终止更新。")

        expected_filename = self.expected_asset_name or os.path.basename(file_path)
        package_type, platform = self._package_identity_for_path(file_path, expected_filename)
        verify_package_authenticity(
            package_path=file_path,
            expected_version=self.latest_version or "",
            signature_b64=signature,
            expected_filename=expected_filename,
            package_type=package_type,
            platform=platform,
            max_bytes=self.MAX_UPDATE_PACKAGE_BYTES,
        )
        if package_type == DELTA_PACKAGE_TYPE:
            inspect_delta_package(
                file_path,
                expected_base_version=self.selected_base_version or self.current_version,
                expected_target_version=self.latest_version or "",
                verify_payload_hashes=True,
            )
        self.force_update = bool(self._force_update_requested)
        self.expected_package_sha256 = actual_sha
        self.expected_package_size = size

    def _prepare_full_update_source(self, file_path: str) -> tuple[str, str]:
        self._verify_downloaded_package(file_path)
        if not zipfile.is_zipfile(file_path):
            raise RuntimeError("更新包不是有效的 zip 文件。")

        version_name = self._sanitize_name(self.latest_version or self.current_version)
        extract_dir = os.path.join(self._download_dir, f"full_update_{version_name}")
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        os.makedirs(extract_dir, exist_ok=True)

        self._safe_extract_zip(file_path, extract_dir)
        source_dir, exe_name = self._find_update_source_dir(extract_dir, self._current_exe_name())
        self._validate_update_manifest(source_dir)
        return source_dir, exe_name

    def _prepare_delta_update_source(self, file_path: str) -> tuple[str, str]:
        if not self._is_frozen_app():
            raise RuntimeError("开发模式不支持增量静默替换，请使用打包版本验证。")
        self._ensure_silent_update_context()
        self._ensure_download_dir()
        version_name = self._sanitize_name(self.latest_version or self.current_version)
        rebuild_dir = tempfile.mkdtemp(
            prefix=f"delta_rebuilt_{version_name}_",
            dir=self._download_dir,
        )
        try:
            manifest = reconstruct_delta_package(
                file_path,
                install_dir=self._current_install_dir(),
                output_dir=rebuild_dir,
                expected_base_version=self.selected_base_version or self.current_version,
                expected_target_version=self.latest_version or "",
                allowed_output_root=self._download_dir,
            )
        except Exception:
            if not is_reparse_point(rebuild_dir):
                shutil.rmtree(rebuild_dir, ignore_errors=True)
            raise
        source_dir, exe_name = self._find_update_source_dir(
            rebuild_dir,
            self._current_exe_name(),
        )
        self._validate_update_manifest(source_dir)
        self._prepared_update_source = (
            os.path.abspath(file_path),
            source_dir,
            exe_name,
        )
        logger.info(
            "增量更新目录重建完成: v%s -> v%s, %s",
            manifest.base_version,
            manifest.app_version,
            source_dir,
        )
        return source_dir, exe_name

    def _clear_prepared_update_source(self) -> None:
        prepared = self._prepared_update_source
        self._prepared_update_source = None
        if not prepared:
            return
        source_dir = os.path.abspath(prepared[1])
        download_root = os.path.abspath(self._download_dir)
        try:
            if (
                os.path.commonpath([download_root, source_dir]) == download_root
                and not is_reparse_point(source_dir)
            ):
                shutil.rmtree(source_dir, ignore_errors=True)
        except ValueError:
            return

    def _build_apply_script(self) -> str:
        return r'''$SourceDir = [string]$env:DZFYQ_UPDATE_SOURCE_DIR
$TargetDir = [string]$env:DZFYQ_UPDATE_TARGET_DIR
$ExeName = [string]$env:DZFYQ_UPDATE_EXE_NAME
$ProcessId = [int]$env:DZFYQ_UPDATE_PROCESS_ID
$ProcessCreationFileTime = [Int64]$env:DZFYQ_UPDATE_PROCESS_CREATED_FILETIME
$BackupDir = [string]$env:DZFYQ_UPDATE_BACKUP_DIR
$LogPath = [string]$env:DZFYQ_UPDATE_LOG_PATH
$ResultPath = [string]$env:DZFYQ_UPDATE_RESULT_PATH
$PendingPath = [string]$env:DZFYQ_UPDATE_PENDING_PATH
$ExpectedVersion = [string]$env:DZFYQ_UPDATE_EXPECTED_VERSION

$ErrorActionPreference = "Stop"
$backupCompleted = $false

function Write-UpdateLog {
    param([string]$Message)
    $parent = Split-Path -Parent $LogPath
    if ($parent) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
}

function Write-UpdateResult {
    param(
        [string]$Status,
        [string]$Message
    )

    $parent = Split-Path -Parent $ResultPath
    if ($parent) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    $payload = [PSCustomObject]@{
        status = $Status
        message = $Message
        expected_version = $ExpectedVersion
        log_path = $LogPath
        updated_at = (Get-Date).ToString("o")
    }
    $payload | ConvertTo-Json -Compress | Set-Content -LiteralPath $ResultPath -Encoding UTF8
}

function Get-OriginalProcess {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $null
    }
    if ($ProcessCreationFileTime -le 0) {
        return $process
    }
    try {
        $actualCreationFileTime = [Int64]$process.StartTime.ToUniversalTime().ToFileTimeUtc()
    }
    catch {
        throw "Cannot verify process $ProcessId identity: $($_.Exception.Message)"
    }
    if ($actualCreationFileTime -ne $ProcessCreationFileTime) {
        return $null
    }
    return $process
}

function Invoke-RobocopyChecked {
    param(
        [string]$From,
        [string]$To,
        [string]$Phase,
        [switch]$Mirror
    )

    $copyMode = if ($Mirror) { "/MIR" } else { "/E" }
    Write-UpdateLog "$Phase from [$From] to [$To] with $copyMode"
    & robocopy $From $To $copyMode /IS /R:3 /W:1 /NFL /NDL /NJH /NJS /NP
    $code = $LASTEXITCODE
    Write-UpdateLog "$Phase robocopy exit code: $code"
    if ($code -gt 7) {
        throw "$Phase failed with robocopy exit code $code"
    }
}

function Restore-UninstallerFiles {
    param(
        [string]$From,
        [string]$To
    )

    foreach ($pattern in @("unins*.exe", "unins*.dat", "unins*.msg")) {
        Get-ChildItem -LiteralPath $From -Filter $pattern -File -ErrorAction SilentlyContinue |
            ForEach-Object {
                Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $To $_.Name) -Force
                Write-UpdateLog "Preserved uninstaller file: $($_.Name)"
            }
    }
}

function Stop-TargetEngineProcesses {
    Write-UpdateLog "Stopping engine processes under target dir."
    $targetRoot = [System.IO.Path]::GetFullPath($TargetDir).TrimEnd('\') + '\'
    Get-CimInstance Win32_Process -Filter "Name = 'deeplx.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ExecutablePath -and
            [System.IO.Path]::GetFullPath($_.ExecutablePath).StartsWith($targetRoot, [System.StringComparison]::OrdinalIgnoreCase)
        } |
        ForEach-Object {
            Write-UpdateLog "Stopping engine process PID $($_.ProcessId): $($_.ExecutablePath)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

function Get-UpdateManifestVersion {
    param([string]$Directory)

    $manifestPath = Join-Path $Directory "update_manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        return ""
    }
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        return [string]$manifest.app_version
    }
    catch {
        throw "Update manifest is invalid: $($_.Exception.Message)"
    }
}

function Assert-ExpectedVersion {
    param(
        [string]$Directory,
        [string]$Phase
    )

    if ([string]::IsNullOrWhiteSpace($ExpectedVersion)) {
        return
    }
    $actualVersion = Get-UpdateManifestVersion -Directory $Directory
    if ([string]::IsNullOrWhiteSpace($actualVersion)) {
        throw "$Phase version verification failed: update_manifest.json is missing"
    }
    if ($actualVersion -ne $ExpectedVersion) {
        throw "$Phase version verification failed: expected $ExpectedVersion but found $actualVersion"
    }
    Write-UpdateLog "$Phase version verified: $actualVersion"
}

function Start-TargetAppIfStopped {
    param([string]$Reason)

    if ($null -ne (Get-OriginalProcess)) {
        Write-UpdateLog "Skip restart because old process is still running."
        return
    }

    $targetExe = Join-Path $TargetDir $ExeName
    if (Test-Path -LiteralPath $targetExe -PathType Leaf) {
        Start-Process -FilePath $targetExe -WorkingDirectory $TargetDir -ArgumentList "--update-restart"
        Write-UpdateLog "Started target app $Reason."
    }
    else {
        Write-UpdateLog "Cannot restart app; executable not found: $targetExe"
    }
}

try {
    Write-UpdateLog "Update started."
    if (-not (Test-Path -LiteralPath $SourceDir -PathType Container)) {
        throw "SourceDir not found: $SourceDir"
    }
    if (-not (Test-Path -LiteralPath $TargetDir -PathType Container)) {
        throw "TargetDir not found: $TargetDir"
    }

    $newExe = Join-Path $SourceDir $ExeName
    if (-not (Test-Path -LiteralPath $newExe -PathType Leaf)) {
        throw "New executable not found: $newExe"
    }
    Assert-ExpectedVersion -Directory $SourceDir -Phase "source"

    $deadline = (Get-Date).AddSeconds(60)
    $originalProcess = Get-OriginalProcess
    if ($null -eq $originalProcess -and $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
        Write-UpdateLog "Process ID $ProcessId has been reused; the unrelated process will not be stopped."
    }
    while ($null -ne $originalProcess) {
        if ((Get-Date) -gt $deadline) {
            Write-UpdateLog "Timed out waiting for process $ProcessId to exit; forcing termination."
            Stop-Process -InputObject $originalProcess -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 800
            break
        }
        Start-Sleep -Milliseconds 500
        $originalProcess = Get-OriginalProcess
    }
    if ($null -ne (Get-OriginalProcess)) {
        throw "Process $ProcessId is still running after forced termination."
    }
    Stop-TargetEngineProcesses

    if (Test-Path -LiteralPath $BackupDir) {
        Remove-Item -LiteralPath $BackupDir -Recurse -Force
    }
    [System.IO.Directory]::CreateDirectory($BackupDir) | Out-Null

    Invoke-RobocopyChecked -From $TargetDir -To $BackupDir -Phase "backup" -Mirror
    $backupCompleted = $true
    Invoke-RobocopyChecked -From $SourceDir -To $TargetDir -Phase "update" -Mirror
    Restore-UninstallerFiles -From $BackupDir -To $TargetDir

    $targetExe = Join-Path $TargetDir $ExeName
    if (-not (Test-Path -LiteralPath $targetExe -PathType Leaf)) {
        throw "Updated executable not found: $targetExe"
    }
    Assert-ExpectedVersion -Directory $TargetDir -Phase "target"

    Write-UpdateResult -Status "success" -Message "Update completed."
    Start-Process -FilePath $targetExe -WorkingDirectory $TargetDir -ArgumentList "--update-restart"
    Write-UpdateLog "Update completed and app restarted."
    Remove-Item -LiteralPath $PendingPath -Force -ErrorAction SilentlyContinue
    exit 0
}
catch {
    Write-UpdateLog "Update failed: $($_.Exception.Message)"
    $restoreSucceeded = $false
    try {
        if ($backupCompleted -and (Test-Path -LiteralPath $BackupDir -PathType Container)) {
            Invoke-RobocopyChecked -From $BackupDir -To $TargetDir -Phase "restore" -Mirror
            $targetExeAfter = Join-Path $TargetDir $ExeName
            if (-not (Test-Path -LiteralPath $targetExeAfter -PathType Leaf)) {
                throw "Restored executable not found: $targetExeAfter"
            }
            Write-UpdateLog "Restore completed."
            $restoreSucceeded = $true
        }
        else {
            Write-UpdateLog "Backup did not complete; target directory was left unchanged."
            $targetExeAfter = Join-Path $TargetDir $ExeName
            if ((Test-Path -LiteralPath $targetExeAfter -PathType Leaf) -and (Get-OriginalProcess) -eq $null) {
                # Target never modified; safe to restart original.
                $restoreSucceeded = $true
            }
        }
    }
    catch {
        Write-UpdateLog "Restore failed: $($_.Exception.Message)"
        $restoreSucceeded = $false
    }
    if ($restoreSucceeded) {
        Start-TargetAppIfStopped -Reason "after update failure with successful restore"
    }
    else {
        Write-UpdateLog "Skip restart after update failure because restore did not fully succeed."
    }
    Write-UpdateResult -Status "failed" -Message $_.Exception.Message
    Remove-Item -LiteralPath $PendingPath -Force -ErrorAction SilentlyContinue
    exit 1
}
'''

    def _write_apply_script(self, script_path: str) -> None:
        with open(script_path, "w", encoding="utf-8-sig", newline="\r\n") as script_file:
            script_file.write(self._build_apply_script())

    def _write_pending_update_state(self, log_path: str) -> None:
        state = {
            "expected_version": self.latest_version or "",
            "current_version": self.current_version,
            "package_type": self.selected_package_type,
            "base_version": self.selected_base_version,
            "log_path": log_path,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        with open(self._pending_update_path(), "w", encoding="utf-8") as state_file:
            json.dump(state, state_file, ensure_ascii=False, indent=2)

    def _apply_windows_full_update(self, file_path: str) -> None:
        if not self._is_frozen_app():
            raise RuntimeError("开发模式不支持静默替换，请使用打包版本验证。")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"更新包不存在: {file_path}")

        self._ensure_silent_update_context()
        target_dir = self._current_install_dir()
        self._ensure_target_writable(target_dir)

        if self.selected_package_type == DELTA_PACKAGE_TYPE:
            prepared = self._prepared_update_source
            if prepared and os.path.abspath(prepared[0]) == os.path.abspath(file_path):
                source_dir, exe_name = prepared[1], prepared[2]
            else:
                source_dir, exe_name = self._prepare_delta_update_source(file_path)
        else:
            source_dir, exe_name = self._prepare_full_update_source(file_path)
        self._ensure_safe_replace_paths(source_dir, target_dir)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        version_name = self._sanitize_name(self.latest_version or self.current_version)
        os.makedirs(self._backup_root, exist_ok=True)

        backup_dir = os.path.join(self._backup_root, f"{version_name}_{timestamp}")
        os.makedirs(self._state_dir, exist_ok=True)
        log_path = os.path.join(self._state_dir, f"apply_update_{version_name}_{timestamp}.log")
        result_path = self._last_update_result_path()
        pending_path = self._pending_update_path()
        process_creation_filetime = self._current_process_creation_filetime()
        self._write_pending_update_state(log_path)

        env = os.environ.copy()
        env.pop("__COMPAT_LAYER", None)
        env.pop("COMPAT_LAYER", None)
        env.update(
            {
                "DZFYQ_UPDATE_SOURCE_DIR": source_dir,
                "DZFYQ_UPDATE_TARGET_DIR": target_dir,
                "DZFYQ_UPDATE_EXE_NAME": exe_name,
                "DZFYQ_UPDATE_PROCESS_ID": str(os.getpid()),
                "DZFYQ_UPDATE_PROCESS_CREATED_FILETIME": str(process_creation_filetime),
                "DZFYQ_UPDATE_BACKUP_DIR": backup_dir,
                "DZFYQ_UPDATE_LOG_PATH": log_path,
                "DZFYQ_UPDATE_RESULT_PATH": result_path,
                "DZFYQ_UPDATE_PENDING_PATH": pending_path,
                "DZFYQ_UPDATE_EXPECTED_VERSION": str(self.latest_version or ""),
            }
        )

        encoded_script = base64.b64encode(
            self._build_apply_script().encode("utf-16-le")
        ).decode("ascii")
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-EncodedCommand",
            encoded_script,
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.Popen(
                command,
                shell=False,
                env=env,
                cwd=self._download_dir,
                creationflags=creationflags,
            )
        except Exception:
            try:
                os.remove(self._pending_update_path())
            except FileNotFoundError:
                pass
            except OSError as cleanup_error:
                logger.warning("Failed to remove pending update state after launcher failure: %s", cleanup_error)
            raise
        os._exit(0)

    def discard_downloaded_update(self, file_path: str) -> None:
        self._clear_prepared_update_source()
        if not file_path:
            return
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"已删除未安装的更新包: {file_path}")
        except OSError as error:
            logger.warning(f"删除更新包失败: {file_path}, {error}")

    async def check_update(self):
        """检查是否有新版本可用"""
        if self._download_in_progress:
            logger.info("更新包正在下载，跳过重复更新检查。")
            return False
        try:
            self.update_url = None
            self.asset_suffix = None
            self.latest_version = None
            self.force_update = False
            self._force_update_requested = False
            self.release_signature = None
            self.expected_asset_name = None
            self.expected_package_sha256 = None
            self.expected_package_size = None
            self.selected_package_type = "windows_full_update"
            self.selected_base_version = ""
            self._selected_asset = None
            self._fallback_full_asset = None
            self._clear_prepared_update_source()
            logger.info("开始检查更新...")
            async with aiohttp.ClientSession(trust_env=True) as session:
                try:
                    data = await self._fetch_latest_release(session)
                except UpdateSourceError as error:
                    self.update_error.emit(f"检查更新失败：{error}")
                    return False

                tag_name = data.get("tag_name") or data.get("name") or ""
                latest_version = normalize_version(tag_name)
                logger.info(
                    "获取到最新版本: %s, 当前版本: %s",
                    latest_version,
                    self.current_version,
                )
                if self._compare_versions(latest_version, self.current_version) <= 0:
                    logger.info("当前已是最新版本")
                    return False

                self.latest_version = latest_version
                self.release_notes = data.get("body") or "暂无更新说明"
                marker = "update=1"
                wants_force_update = marker in self.release_notes
                current_platform = self._current_update_platform()
                release_note_signature = extract_signature_from_release_notes(
                    self.release_notes,
                    platform=current_platform,
                )
                clean_notes = strip_signature_markers_from_notes(
                    self.release_notes.replace(marker, "").strip()
                )
                assets = data.get("assets") or []

                if sys.platform == "darwin":
                    package_asset = next(
                        (
                            asset
                            for asset in assets
                            if str(asset.get("name") or "").lower().endswith(".dmg")
                        ),
                        None,
                    )
                    if not package_asset or not release_note_signature:
                        raise RuntimeError(
                            "Release 缺少 macOS DMG 或 DZFYQ-SIG-MACOS 签名"
                        )
                    selected = self._build_update_asset(
                        package_asset,
                        package_type="macos_dmg_update",
                        signature=release_note_signature,
                    )
                    self._activate_update_asset(selected)
                elif sys.platform == "win32":
                    assets_by_name = self._release_assets_by_name(assets)
                    full_asset_raw = next(
                        (
                            asset
                            for asset in assets
                            if self._is_windows_full_update_asset(
                                str(asset.get("name") or ""),
                                latest_version,
                            )
                        ),
                        None,
                    )
                    if not full_asset_raw:
                        raise RuntimeError(
                            "未找到 Windows 全量更新包，请上传 "
                            "dazuofanyiguan_full.for.windows_<version>.zip"
                        )

                    full_metadata = None
                    try:
                        full_metadata = await self._read_signature_metadata(
                            session,
                            assets_by_name,
                            full_asset_raw,
                            expected_package_type="windows_full_update",
                            expected_target_version=latest_version,
                        )
                    except Exception as error:
                        if not release_note_signature:
                            raise
                        logger.warning("忽略无效的全量包签名元数据: %s", error)
                    if (
                        full_metadata
                        and release_note_signature
                        and full_metadata["signature"] != release_note_signature
                    ):
                        raise RuntimeError("Release 全量包签名标记与签名文件不一致")
                    full_signature = (
                        (full_metadata or {}).get("signature")
                        or release_note_signature
                    )
                    if not full_signature:
                        raise RuntimeError(
                            "Release 缺少 Windows 全量包签名标记或签名文件"
                        )
                    full_asset = self._build_update_asset(
                        full_asset_raw,
                        package_type="windows_full_update",
                        signature=full_signature,
                        signature_metadata=full_metadata,
                    )
                    if not full_asset.url:
                        raise RuntimeError("Windows 全量更新包缺少下载地址")

                    selected = full_asset
                    delta_name = self._expected_windows_delta_update_asset_name(
                        self.current_version,
                        latest_version,
                    )
                    delta_asset_raw = assets_by_name.get(delta_name.lower())
                    if delta_asset_raw:
                        try:
                            delta_metadata = await self._read_signature_metadata(
                                session,
                                assets_by_name,
                                delta_asset_raw,
                                expected_package_type=DELTA_PACKAGE_TYPE,
                                expected_target_version=latest_version,
                            )
                            if delta_metadata is None:
                                raise RuntimeError("增量包缺少签名文件")
                            delta_asset = self._build_update_asset(
                                delta_asset_raw,
                                package_type=DELTA_PACKAGE_TYPE,
                                signature=delta_metadata["signature"],
                                signature_metadata=delta_metadata,
                                base_version=self.current_version,
                            )
                            full_size = int(full_asset.size_bytes or 0)
                            delta_size = int(delta_asset.size_bytes or 0)
                            if (
                                full_size > 0
                                and delta_size > 0
                                and delta_size * 100 <= full_size * 80
                            ):
                                selected = delta_asset
                                self._fallback_full_asset = full_asset
                                logger.info(
                                    "选择文件级增量更新: %s (%s bytes)，"
                                    "全量包 %s bytes",
                                    delta_asset.name,
                                    delta_size,
                                    full_size,
                                )
                            else:
                                logger.info(
                                    "增量包未达到至少节省 20% 的阈值，使用全量包"
                                )
                        except Exception as error:
                            logger.warning("增量包不可用，使用全量包: %s", error)
                    self._activate_update_asset(selected)
                else:
                    self.update_error.emit("暂不支持该平台自动更新。")
                    return False

                self._force_update_requested = wants_force_update
                self.force_update = False
                logger.info(
                    "更新资源已选择: type=%s name=%s force_requested=%s",
                    self.selected_package_type,
                    self.expected_asset_name,
                    wants_force_update,
                )
                self.update_available.emit(latest_version, clean_notes, self.force_update)
                return True
        except aiohttp.ClientError as error:
            logger.error("网络请求错误: %s", error)
            self.update_error.emit(
                f"网络请求错误：{error}。请检查网络/代理/证书设置。"
            )
            return False
        except Exception as error:
            logger.error("检查更新出错: %s", error)
            self.update_error.emit(f"检查更新失败: {error}")
            return False

    async def _download_asset_to_path(
        self,
        session,
        asset: UpdateAsset,
        temp_path: str,
    ) -> None:
        """下载资源；主源资源域名不可达时改用其他更新源上的同名同版本资源。

        无论从哪个源下载，随后都按同一份签名、SHA256 和大小校验，镜像无法篡改内容。
        """
        try:
            await self._download_url_to_path(session, asset.url, asset, temp_path)
            return
        except Exception as primary_error:
            self._remove_partial_download(temp_path)
            candidates = await self._mirror_asset_candidates(
                session, asset.name, self.latest_version or ""
            )
            if not candidates:
                raise
            logger.warning("主更新源下载失败（%s），尝试镜像源", primary_error)
            for candidate in candidates:
                mirror_size = int(candidate.get("size") or 0)
                if asset.size_bytes and mirror_size and mirror_size != asset.size_bytes:
                    logger.warning(
                        "镜像源 %s 的 %s 大小 %s 与发布信息 %s 不一致，跳过",
                        candidate["source"],
                        asset.name,
                        mirror_size,
                        asset.size_bytes,
                    )
                    continue
                self.update_progress.emit(0)
                try:
                    await self._download_url_to_path(
                        session, candidate["url"], asset, temp_path
                    )
                    logger.info("已从 %s 镜像下载 %s", candidate["source"], asset.name)
                    return
                except Exception as mirror_error:
                    self._remove_partial_download(temp_path)
                    logger.warning(
                        "镜像源 %s 下载失败: %s", candidate["source"], mirror_error
                    )
            raise primary_error

    @staticmethod
    def _remove_partial_download(temp_path: str) -> None:
        try:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError as error:
            logger.warning("清理未完成的下载失败: %s", error)

    async def _download_url_to_path(
        self,
        session,
        url: str,
        asset: UpdateAsset,
        temp_path: str,
    ) -> None:
        async with session.get(url) as response:
            if response.status == 404:
                raise RuntimeError("更新包资源不存在（HTTP 404）")
            if response.status == 403:
                raise RuntimeError("更新包下载被拒绝或触发频率限制（HTTP 403）")
            if response.status != 200:
                raise RuntimeError(f"更新包下载失败：HTTP {response.status}")
            total_size = int(response.headers.get("content-length", 0) or 0)
            if total_size and total_size > self.MAX_UPDATE_PACKAGE_BYTES:
                raise RuntimeError("更新包体积过大，已终止更新。")
            if asset.size_bytes and total_size and asset.size_bytes != total_size:
                raise RuntimeError("更新包大小与发布信息不一致，已终止更新。")
            with open(temp_path, "wb") as file:
                downloaded = 0
                async for chunk in response.content.iter_chunked(8192):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > self.MAX_UPDATE_PACKAGE_BYTES:
                        raise RuntimeError("更新包体积过大，已终止更新。")
                    file.write(chunk)
                    if total_size:
                        self.update_progress.emit(int(downloaded / total_size * 100))

    async def download_update(self):
        """下载并验证更新；增量失败时在退出前自动改用全量包。"""
        if self._download_in_progress:
            logger.info("更新包下载已在进行，忽略重复下载请求。")
            return
        selected = self._selected_asset
        if selected is None and self.update_url:
            selected = UpdateAsset(
                name=self.expected_asset_name or os.path.basename(self.update_url),
                url=self.update_url,
                size_bytes=int(self.expected_package_size or 0),
                package_type=self.selected_package_type,
                signature=self.release_signature or "",
                sha256=self.expected_package_sha256 or "",
                base_version=self.selected_base_version,
            )
        if selected is None or not selected.url:
            self.update_error.emit("没有可用的更新")
            return

        attempts = [selected]
        if (
            selected.package_type == DELTA_PACKAGE_TYPE
            and self._fallback_full_asset is not None
        ):
            attempts.append(self._fallback_full_asset)

        self._download_in_progress = True
        temp_path = ""
        last_error = None
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                for index, asset in enumerate(attempts):
                    self._activate_update_asset(asset)
                    temp_path = self._build_download_path(asset.suffix)
                    self._cleanup_download_cache(keep_file=temp_path)
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    try:
                        await self._download_asset_to_path(session, asset, temp_path)
                        logger.info("更新文件下载完成: %s", temp_path)
                        # 完整校验与增量重建要读写整个安装目录，放到工作线程执行，
                        # 避免长时间阻塞 GUI 事件循环。
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(
                            None, self._verify_downloaded_package, temp_path
                        )
                        if asset.package_type == DELTA_PACKAGE_TYPE:
                            await loop.run_in_executor(
                                None, self._prepare_delta_update_source, temp_path
                            )
                        last_error = None
                        self.update_complete.emit(temp_path)
                        return
                    except Exception as error:
                        last_error = error
                        logger.warning(
                            "更新资源处理失败: type=%s name=%s error=%s",
                            asset.package_type,
                            asset.name,
                            error,
                        )
                        self._clear_prepared_update_source()
                        if temp_path and os.path.exists(temp_path):
                            os.unlink(temp_path)
                        if index + 1 < len(attempts):
                            logger.warning("增量更新失败，自动改用已签名全量包")
                            self.update_progress.emit(0)
                            continue
                        raise
        except Exception as error:
            last_error = error
            logger.error("下载更新出错: %s", error)
            self.update_error.emit(f"下载更新失败：{error}")
        finally:
            self._download_in_progress = False
            if last_error and temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def install_update(self, file_path):
        """安装更新"""
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", file_path])
                return

            if sys.platform == "win32":
                self._apply_windows_full_update(file_path)
                return

            raise RuntimeError("暂不支持该平台自动更新。")
        except Exception as e:
            logger.error(f"安装更新出错: {e}")
            raise

    def _compare_versions(self, version1, version2):
        """比较版本号，返回1表示version1更新，-1表示version2更新，0表示相同"""
        v1_parts = self._version_parts(version1)
        v2_parts = self._version_parts(version2)

        for left, right in zip(v1_parts, v2_parts):
            if left > right:
                return 1
            if left < right:
                return -1
        return 0

    def _version_parts(self, version: str) -> tuple[int, int, int]:
        numbers = [int(part) for part in re.findall(r"\d+", str(version or ""))]
        while len(numbers) < 3:
            numbers.append(0)
        return tuple(numbers[:3])
