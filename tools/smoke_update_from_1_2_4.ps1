param(
    [string]$OldZip = "",
    [string]$NewZip = "",
    [string]$ExpectedVersion = "1.2.5",
    [string]$Python = "",
    [int]$TimeoutSeconds = 180,
    [switch]$WithEngineLock,
    [switch]$KeepTemp
)

$ErrorActionPreference = "Stop"

function Resolve-RepoPath {
    param([string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return (Resolve-Path -LiteralPath $Path).Path
    }
    return (Resolve-Path -LiteralPath (Join-Path $RepoRoot $Path)).Path
}

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), 0)
    $listener.Start()
    try {
        return $listener.LocalEndpoint.Port
    }
    finally {
        $listener.Stop()
    }
}

function Stop-ProcessesUnderDirectory {
    param([string]$Directory)
    $root = [System.IO.Path]::GetFullPath($Directory).TrimEnd("\") + "\"
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ExecutablePath -and
            [System.IO.Path]::GetFullPath($_.ExecutablePath).StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if (-not $OldZip) {
    $OldZip = Join-Path $RepoRoot "output\dazuofanyiguan_full.for.windows_1.2.4.zip"
}
if (-not $NewZip) {
    $NewZip = Join-Path $RepoRoot "output\dazuofanyiguan_full.for.windows_$ExpectedVersion.zip"
}
if (-not $Python) {
    $Python = Join-Path $RepoRoot ".venv311\Scripts\python.exe"
}

$OldZip = Resolve-RepoPath $OldZip
$NewZip = Resolve-RepoPath $NewZip
$Python = Resolve-RepoPath $Python

$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("dzfyq_update_124_to_125_" + [System.Guid]::NewGuid().ToString("N"))
$TargetDir = Join-Path $TempRoot "install"
$ProfileDir = Join-Path $TempRoot "profile"
$WorkDir = Join-Path $TempRoot "work"
$success = $false
$oldUserProfile = $env:USERPROFILE
$oldHome = $env:HOME
$oldAppData = $env:APPDATA
$oldLocalAppData = $env:LOCALAPPDATA
$oldRepoRoot = $env:DZFYQ_REPO_ROOT
$oldTargetExe = $env:DZFYQ_TARGET_EXE
$oldNewZip = $env:DZFYQ_NEW_ZIP
$oldExpectedVersion = $env:DZFYQ_EXPECTED_VERSION

try {
    New-Item -ItemType Directory -Force -Path $TargetDir, $ProfileDir, $WorkDir | Out-Null
    Expand-Archive -LiteralPath $OldZip -DestinationPath $TargetDir -Force

    $targetExe = Get-ChildItem -LiteralPath $TargetDir -Filter "*.exe" -File |
        Where-Object { $_.Name -ne "deeplx.exe" } |
        Select-Object -First 1
    if (-not $targetExe) {
        throw "Old package main executable not found."
    }

    $engineExe = Join-Path $TargetDir "engines\deeplx\windows\amd64\deeplx.exe"
    $engineProcess = $null
    if ($WithEngineLock -and (Test-Path -LiteralPath $engineExe -PathType Leaf)) {
        $port = Get-FreePort
        $engineProcess = Start-Process -FilePath $engineExe -ArgumentList @("-p", "$port", "-token", "smoke-token") -WorkingDirectory (Split-Path -Parent $engineExe) -WindowStyle Hidden -PassThru
        Start-Sleep -Milliseconds 800
    }

    $oldUpdatePath = Join-Path $WorkDir "update_v1_2_4.py"
    git -C $RepoRoot show "v1.2.4:src/gongju/update.py" | Set-Content -LiteralPath $oldUpdatePath -Encoding UTF8
    if (-not (Test-Path -LiteralPath $oldUpdatePath -PathType Leaf)) {
        throw "Could not materialize v1.2.4 update.py."
    }

    $helperPath = Join-Path $WorkDir "run_old_updater.py"
    @'
import importlib.util
import os
import sys

repo_root = os.environ["DZFYQ_REPO_ROOT"]
sys.path.insert(0, repo_root)
sys.frozen = True
sys.executable = os.environ["DZFYQ_TARGET_EXE"]

spec = importlib.util.spec_from_file_location("update_v1_2_4", os.environ["DZFYQ_OLD_UPDATE"])
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

updater = module.Updater()
updater.latest_version = os.environ.get("DZFYQ_EXPECTED_VERSION", "1.2.5")
updater.install_update(os.environ["DZFYQ_NEW_ZIP"])
'@ | Set-Content -LiteralPath $helperPath -Encoding UTF8

    $env:USERPROFILE = $ProfileDir
    $env:HOME = $ProfileDir
    $env:APPDATA = Join-Path $ProfileDir "AppData\Roaming"
    $env:LOCALAPPDATA = Join-Path $ProfileDir "AppData\Local"
    $env:DZFYQ_REPO_ROOT = $RepoRoot
    $env:DZFYQ_TARGET_EXE = $targetExe.FullName
    $env:DZFYQ_NEW_ZIP = $NewZip
    $env:DZFYQ_OLD_UPDATE = $oldUpdatePath
    $env:DZFYQ_EXPECTED_VERSION = $ExpectedVersion
    New-Item -ItemType Directory -Force -Path $env:APPDATA, $env:LOCALAPPDATA | Out-Null

    & $Python $helperPath
    if ($LASTEXITCODE -ne 0) {
        throw "v1.2.4 updater helper exited with code $LASTEXITCODE."
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $logRoot = Join-Path $ProfileDir ".dzfyq\update_cache"
    $completed = $false
    while ((Get-Date) -lt $deadline) {
        $latestLog = Get-ChildItem -LiteralPath $logRoot -Filter "apply_update_*.log" -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($latestLog) {
            $logText = Get-Content -LiteralPath $latestLog.FullName -Raw -Encoding UTF8
            if ($logText -match "Update failed") {
                throw "v1.2.4 updater failed. Log: $($latestLog.FullName)`n$logText"
            }
            if ($logText -match "Update completed") {
                $completed = $true
                break
            }
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $completed) {
        throw "Timed out waiting for v1.2.4 updater completion. Temp: $TempRoot"
    }

    $manifestPath = Join-Path $TargetDir "update_manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Updated install missing update_manifest.json."
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$manifest.app_version -ne $ExpectedVersion) {
        throw "Updated manifest version mismatch: expected $ExpectedVersion, found $($manifest.app_version)."
    }

    $verifyPath = Join-Path $WorkDir "verify_exe_version.py"
    @'
import sys
from pathlib import Path
import win32api

exe = Path(sys.argv[1])
expected = tuple(int(part) for part in sys.argv[2].split(".")[:3])
info = win32api.GetFileVersionInfo(str(exe), "\\")
actual = (int(info["FileVersionMS"]) >> 16, int(info["FileVersionMS"]) & 0xFFFF, int(info["FileVersionLS"]) >> 16)
if actual != expected:
    raise SystemExit(f"exe version mismatch: expected {expected}, found {actual}")
print("exe version ok:", ".".join(str(part) for part in actual))
'@ | Set-Content -LiteralPath $verifyPath -Encoding UTF8
    & $Python $verifyPath $targetExe.FullName $ExpectedVersion
    if ($LASTEXITCODE -ne 0) {
        throw "Updated executable version verification failed."
    }

    Stop-ProcessesUnderDirectory -Directory $TargetDir
    if ($engineProcess -and -not $engineProcess.HasExited) {
        Stop-Process -Id $engineProcess.Id -Force -ErrorAction SilentlyContinue
    }
    $success = $true
    $lockMode = if ($WithEngineLock) { "with engine lock" } else { "without engine lock" }
    Write-Host "1.2.4 -> $ExpectedVersion update smoke passed ($lockMode)."
}
finally {
    $env:USERPROFILE = $oldUserProfile
    $env:HOME = $oldHome
    $env:APPDATA = $oldAppData
    $env:LOCALAPPDATA = $oldLocalAppData
    $env:DZFYQ_REPO_ROOT = $oldRepoRoot
    $env:DZFYQ_TARGET_EXE = $oldTargetExe
    $env:DZFYQ_NEW_ZIP = $oldNewZip
    $env:DZFYQ_EXPECTED_VERSION = $oldExpectedVersion
    Remove-Item Env:\DZFYQ_OLD_UPDATE -ErrorAction SilentlyContinue

    if (Test-Path -LiteralPath $TargetDir) {
        Stop-ProcessesUnderDirectory -Directory $TargetDir
    }
    if ($success -and -not $KeepTemp -and (Test-Path -LiteralPath $TempRoot)) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    elseif (-not $success) {
        Write-Host "Smoke temp kept for inspection: $TempRoot"
    }
}
