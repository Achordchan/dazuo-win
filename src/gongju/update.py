import os
import sys
import json
import aiohttp
import asyncio
import logging
import re
import subprocess
import shutil
import time
import zipfile
from PyQt5.QtCore import QObject, pyqtSignal
from src.version import APP_VERSION

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Updater(QObject):
    # 定义信号
    update_available = pyqtSignal(str, str, bool)  # 版本号, 更新说明, 是否强制更新
    update_progress = pyqtSignal(int)  # 下载进度
    update_error = pyqtSignal(str)  # 错误信息
    update_complete = pyqtSignal(str)  # 下载完成的文件路径

    def __init__(self):
        super().__init__()
        self.current_version = APP_VERSION  # 当前版本号
        self.gitee_api = "https://gitee.com/api/v5/repos/Achordchan/dazuofanyiguan/releases/latest"
        self.update_url = None
        self.release_notes = None
        self.force_update = False
        self.asset_suffix = None
        self.latest_version = None
        self._download_dir = os.path.join(os.path.expanduser("~/.dzfyq"), "update_cache")
        self._backup_root = os.path.join(os.path.expanduser("~/.dzfyq"), "update_backup")
        self._state_dir = os.path.join(os.path.expanduser("~/.dzfyq"), "update_state")
        self._cleanup_download_cache()

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
            for member in archive.infolist():
                member_target = os.path.abspath(os.path.join(extract_root, member.filename))
                try:
                    if os.path.commonpath([extract_root, member_target]) != extract_root:
                        raise RuntimeError("更新包包含非法路径，已终止更新。")
                except ValueError as error:
                    raise RuntimeError("更新包包含非法路径，已终止更新。") from error
            archive.extractall(extract_root)

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

    def _validate_update_manifest(self, source_dir: str) -> None:
        expected_version = (self.latest_version or "").strip()
        if not expected_version:
            return
        package_version = self._read_update_manifest_version(source_dir)
        if not package_version:
            raise RuntimeError("更新包缺少版本清单，已终止更新。")
        if self._compare_versions(package_version, expected_version) != 0:
            raise RuntimeError(
                f"更新包版本不匹配：期望 v{expected_version}，实际 v{package_version}。"
            )

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

    def _prepare_full_update_source(self, file_path: str) -> tuple[str, str]:
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

    def _write_apply_script(self, script_path: str) -> None:
        script = r'''param(
    [Parameter(Mandatory=$true)][string]$SourceDir,
    [Parameter(Mandatory=$true)][string]$TargetDir,
    [Parameter(Mandatory=$true)][string]$ExeName,
    [Parameter(Mandatory=$true)][int]$ProcessId,
    [Parameter(Mandatory=$true)][string]$BackupDir,
    [Parameter(Mandatory=$true)][string]$LogPath,
    [Parameter(Mandatory=$true)][string]$ResultPath,
    [Parameter(Mandatory=$true)][string]$PendingPath,
    [string]$ExpectedVersion = ""
)

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

function Invoke-RobocopyChecked {
    param(
        [string]$From,
        [string]$To,
        [string]$Phase,
        [switch]$Mirror
    )

    $copyMode = if ($Mirror) { "/MIR" } else { "/E" }
    Write-UpdateLog "$Phase from [$From] to [$To] with $copyMode"
    & robocopy $From $To $copyMode /R:3 /W:1 /NFL /NDL /NJH /NJS /NP
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

    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        Write-UpdateLog "Skip restart because old process is still running."
        return
    }

    $targetExe = Join-Path $TargetDir $ExeName
    if (Test-Path -LiteralPath $targetExe -PathType Leaf) {
        Start-Process -FilePath $targetExe -WorkingDirectory $TargetDir
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
    while (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        if ((Get-Date) -gt $deadline) {
            Write-UpdateLog "Timed out waiting for process $ProcessId to exit; forcing termination."
            Stop-Process -Id $ProcessId -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 800
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
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

    Start-Process -FilePath $targetExe -WorkingDirectory $TargetDir
    Write-UpdateLog "Update completed and app restarted."
    Write-UpdateResult -Status "success" -Message "Update completed."
    Remove-Item -LiteralPath $PendingPath -Force -ErrorAction SilentlyContinue
    exit 0
}
catch {
    Write-UpdateLog "Update failed: $($_.Exception.Message)"
    try {
        if ($backupCompleted -and (Test-Path -LiteralPath $BackupDir -PathType Container)) {
            Invoke-RobocopyChecked -From $BackupDir -To $TargetDir -Phase "restore" -Mirror
            Write-UpdateLog "Restore completed."
        }
        else {
            Write-UpdateLog "Backup did not complete; target directory was left unchanged."
        }
    }
    catch {
        Write-UpdateLog "Restore failed: $($_.Exception.Message)"
    }
    Start-TargetAppIfStopped -Reason "after update failure"
    Write-UpdateResult -Status "failed" -Message $_.Exception.Message
    Remove-Item -LiteralPath $PendingPath -Force -ErrorAction SilentlyContinue
    exit 1
}
'''
        with open(script_path, "w", encoding="utf-8-sig", newline="\r\n") as script_file:
            script_file.write(script)

    def _write_pending_update_state(self, log_path: str) -> None:
        state = {
            "expected_version": self.latest_version or "",
            "current_version": self.current_version,
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

        target_dir = os.path.dirname(os.path.abspath(sys.executable))
        self._ensure_target_writable(target_dir)

        source_dir, exe_name = self._prepare_full_update_source(file_path)
        self._ensure_safe_replace_paths(source_dir, target_dir)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        version_name = self._sanitize_name(self.latest_version or self.current_version)
        os.makedirs(self._backup_root, exist_ok=True)

        backup_dir = os.path.join(self._backup_root, f"{version_name}_{timestamp}")
        script_path = os.path.join(self._download_dir, f"apply_update_{version_name}_{timestamp}.ps1")
        os.makedirs(self._state_dir, exist_ok=True)
        log_path = os.path.join(self._state_dir, f"apply_update_{version_name}_{timestamp}.log")
        self._write_apply_script(script_path)
        self._write_pending_update_state(log_path)

        env = os.environ.copy()
        env.pop("__COMPAT_LAYER", None)
        env.pop("COMPAT_LAYER", None)

        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            script_path,
            "-SourceDir",
            source_dir,
            "-TargetDir",
            target_dir,
            "-ExeName",
            exe_name,
            "-ProcessId",
            str(os.getpid()),
            "-BackupDir",
            backup_dir,
            "-LogPath",
            log_path,
            "-ResultPath",
            self._last_update_result_path(),
            "-PendingPath",
            self._pending_update_path(),
            "-ExpectedVersion",
            str(self.latest_version or ""),
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            command,
            shell=False,
            env=env,
            cwd=self._download_dir,
            creationflags=creationflags,
        )
        os._exit(0)

    def discard_downloaded_update(self, file_path: str) -> None:
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
        try:
            self.update_url = None
            self.asset_suffix = None
            self.latest_version = None
            logger.info("开始检查更新...")
            async with aiohttp.ClientSession() as session:
                logger.info(f"正在请求 Gitee API: {self.gitee_api}")
                async with session.get(self.gitee_api) as response:
                    if response.status == 404:
                        logger.error("仓库不存在或无法访问")
                        self.update_error.emit(
                            "检查更新失败：Gitee 返回 404。可能是仓库地址错误、仓库被删除或被设为私有。"
                        )
                        return False
                    if response.status == 403:
                        logger.error("访问被拒绝或频率限制")
                        self.update_error.emit(
                            "检查更新失败：Gitee 返回 403。可能是访问被拒绝、触发频率限制或需要鉴权。"
                        )
                        return False
                    if response.status != 200:
                        logger.error(f"Gitee API 请求失败: HTTP {response.status}")
                        self.update_error.emit(
                            f"检查更新失败：Gitee 返回 HTTP {response.status}。"
                        )
                        return False
                    
                    data = await response.json()
                    tag_name = data.get('tag_name') or data.get('name') or ""
                    latest_version = tag_name.lstrip('v')
                    logger.info(f"获取到最新版本: {latest_version}, 当前版本: {self.current_version}")
                    
                    # 比较版本号
                    if self._compare_versions(latest_version, self.current_version) > 0:
                        logger.info(f"发现新版本: {latest_version}")
                        self.latest_version = latest_version
                        
                        # 获取更新信息
                        self.release_notes = data.get('body') or "暂无更新说明"
                        logger.info(f"更新说明: {self.release_notes}")
                        
                        # 检查是否强制更新
                        marker = "update=1"
                        self.force_update = marker in self.release_notes
                        # 移除强制更新标记
                        clean_notes = self.release_notes.replace(marker, "").strip()
                        logger.info(f"是否强制更新: {self.force_update}")
                        
                        # 获取下载链接
                        platform_suffixes = []
                        if sys.platform == "darwin":
                            platform_suffixes = [".dmg"]
                        elif sys.platform == "win32":
                            platform_suffixes = [".zip"]
                        else:
                            self.update_error.emit("暂不支持该平台自动更新。")
                            return False

                        for asset in data.get('assets', []):
                            asset_name = (asset.get('name') or "").lower()
                            logger.info(f"检查资源: {asset_name}")
                            if sys.platform == "win32":
                                asset_matched = self._is_windows_full_update_asset(asset_name, latest_version)
                            else:
                                asset_matched = any(asset_name.endswith(suffix) for suffix in platform_suffixes)
                            if asset_matched:
                                self.update_url = asset.get('browser_download_url')
                                self.asset_suffix = os.path.splitext(asset_name)[1]
                                if self.update_url:
                                    logger.info(f"找到更新包下载链接: {self.update_url}")
                                    break
                        
                        if self.update_url:
                            logger.info("发送更新可用信号")
                            self.update_available.emit(latest_version, clean_notes, self.force_update)
                            return True
                        suffix_text = "/".join(platform_suffixes)
                        if sys.platform == "win32":
                            self.update_error.emit(
                                "未找到 Windows 全量更新包，请在 Gitee Release 中上传 "
                                "dazuofanyiguan_full.for.windows_<version>.zip"
                            )
                        else:
                            self.update_error.emit(f"未找到安装包资源，请在 Gitee Release 中上传 {suffix_text} 文件")
                        return False
                    else:
                        logger.info("当前已是最新版本")
            
            return False
        except aiohttp.ClientError as e:
            logger.error(f"网络请求错误: {e}")
            self.update_error.emit(f"网络请求错误：{str(e)}。请检查网络/代理/证书设置。")
            return False
        except Exception as e:
            logger.error(f"检查更新出错: {e}")
            self.update_error.emit(f"检查更新失败: {str(e)}")
            return False

    async def download_update(self):
        """下载更新文件"""
        if not self.update_url:
            self.update_error.emit("没有可用的更新")
            return

        temp_path = ""
        try:
            suffix = self.asset_suffix or (".dmg" if sys.platform == "darwin" else ".zip")
            temp_path = self._build_download_path(suffix)
            self._cleanup_download_cache(keep_file=temp_path)
            if os.path.exists(temp_path):
                os.remove(temp_path)

            async with aiohttp.ClientSession() as session:
                async with session.get(self.update_url) as response:
                    if response.status == 404:
                        self.update_error.emit("下载失败：更新包资源不存在（HTTP 404）。")
                        return
                    if response.status == 403:
                        self.update_error.emit("下载失败：下载被拒绝或频率限制（HTTP 403）。")
                        return
                    if response.status != 200:
                        self.update_error.emit(f"下载失败：HTTP {response.status}。")
                        return

                    # 获取文件大小
                    total_size = int(response.headers.get('content-length', 0))
                    
                    # 下载文件
                    with open(temp_path, 'wb') as f:
                        downloaded = 0
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            # 更新进度
                            if total_size:
                                progress = int((downloaded / total_size) * 100)
                                self.update_progress.emit(progress)

            logger.info(f"更新文件下载完成: {temp_path}")
            self.update_complete.emit(temp_path)
            
        except Exception as e:
            logger.error(f"下载更新出错: {e}")
            self.update_error.emit(f"下载更新失败：{str(e)}")
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def install_update(self, file_path):
        """安装更新"""
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", file_path])
                return

            if sys.platform == "win32":
                self._apply_windows_full_update(file_path)
                return

            self.update_error.emit("暂不支持该平台自动更新。")
        except Exception as e:
            logger.error(f"安装更新出错: {e}")
            self.update_error.emit(f"安装更新失败: {str(e)}")

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
