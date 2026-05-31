param(
    [string]$ExpectedVersion = "",
    [string]$Package = "",
    [string]$OldPackage = "",
    [string]$SetupExe = "",
    [string]$Python = "",
    [switch]$SkipEngineLock
)

$ErrorActionPreference = "Stop"

function Resolve-RepoPath {
    param([string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return (Resolve-Path -LiteralPath $Path).Path
    }
    return (Resolve-Path -LiteralPath (Join-Path $RepoRoot $Path)).Path
}

function Invoke-Check {
    param(
        [string]$Name,
        [scriptblock]$Script
    )
    Write-Host "==> $Name"
    & $Script
    Write-Host "ok: $Name"
}

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if (-not $Python) {
    $Python = Join-Path $RepoRoot ".venv311\Scripts\python.exe"
}
$Python = Resolve-RepoPath $Python

if (-not $ExpectedVersion) {
    $ExpectedVersion = (& $Python -c "from src.version import APP_VERSION; print(APP_VERSION)").Trim()
}
if (-not $Package) {
    $Package = Join-Path $RepoRoot "output\dazuofanyiguan_full.for.windows_$ExpectedVersion.zip"
}
if (-not $OldPackage) {
    $OldPackage = Join-Path $RepoRoot "output\dazuofanyiguan_full.for.windows_1.2.4.zip"
}
if (-not $SetupExe) {
    $SetupExe = Join-Path $RepoRoot "output\dazuofanyiguan_setup.for.windows_$ExpectedVersion.exe"
}

$Package = Resolve-RepoPath $Package
$OldPackage = Resolve-RepoPath $OldPackage
$SetupExe = Resolve-RepoPath $SetupExe
$ArchiveViewer = Join-Path (Split-Path -Parent $Python) "pyi-archive_viewer.exe"

Push-Location $RepoRoot
try {
    Invoke-Check "compileall" {
        & $Python -m compileall -q src tools setup.py
        if ($LASTEXITCODE -ne 0) { throw "compileall failed with code $LASTEXITCODE" }
    }

    Invoke-Check "smoke tests" {
        & $Python tools\smoke_tests.py --package $Package
        if ($LASTEXITCODE -ne 0) { throw "smoke_tests.py failed with code $LASTEXITCODE" }
    }

    Invoke-Check "package verification" {
        & $Python tools\verify_windows_package.py $Package $ExpectedVersion
        if ($LASTEXITCODE -ne 0) { throw "verify_windows_package.py failed with code $LASTEXITCODE" }
    }

    Invoke-Check "setup payload verification" {
        if (-not (Test-Path -LiteralPath $ArchiveViewer -PathType Leaf)) {
            throw "pyi-archive_viewer.exe not found: $ArchiveViewer"
        }
        $payloadName = "dazuofanyiguan_full.for.windows_$ExpectedVersion.zip"
        $archiveText = (& $ArchiveViewer $SetupExe -l 2>&1 | Out-String)
        if (-not ($archiveText.Contains("payload") -and $archiveText.Contains($payloadName))) {
            throw "setup payload missing $payloadName"
        }
    }

    Invoke-Check "1.2.4 to $ExpectedVersion update smoke" {
        powershell -NoProfile -ExecutionPolicy Bypass -File tools\smoke_update_from_1_2_4.ps1 `
            -OldZip $OldPackage `
            -NewZip $Package `
            -ExpectedVersion $ExpectedVersion `
            -Python $Python
        if ($LASTEXITCODE -ne 0) { throw "update smoke failed with code $LASTEXITCODE" }
    }

    if (-not $SkipEngineLock) {
        Invoke-Check "1.2.4 to $ExpectedVersion update smoke with engine lock" {
            powershell -NoProfile -ExecutionPolicy Bypass -File tools\smoke_update_from_1_2_4.ps1 `
                -OldZip $OldPackage `
                -NewZip $Package `
                -ExpectedVersion $ExpectedVersion `
                -Python $Python `
                -WithEngineLock
            if ($LASTEXITCODE -ne 0) { throw "engine-lock update smoke failed with code $LASTEXITCODE" }
        }
    }
}
finally {
    Pop-Location
}
