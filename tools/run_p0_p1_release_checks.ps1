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

    Invoke-Check "package signature artifact" {
        $sigPath = "$Package.sig.json"
        if (-not (Test-Path -LiteralPath $sigPath -PathType Leaf)) {
            throw "signature json missing: $sigPath (run tools/sign_windows_update_package.py)"
        }
        $sig = Get-Content -LiteralPath $sigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $sig.signature) {
            throw "signature json missing signature field: $sigPath"
        }
        if (-not [string]$sig.release_notes_marker) {
            throw "signature json missing release notes marker: $sigPath"
        }
        $marker = [string]$sig.release_notes_marker
        if (-not (
            $marker.StartsWith("DZFYQ-SIG:") -or
            $marker.StartsWith("DZFYQ-SIG-WINDOWS:") -or
            $marker.StartsWith("DZFYQ-SIG-WIN:")
        )) {
            throw "signature json missing Windows DZFYQ-SIG release notes marker: $sigPath"
        }

        $packageItem = Get-Item -LiteralPath $Package
        $expectedName = $packageItem.Name
        $expectedSize = [int64]$packageItem.Length

        # Fully consume verifier output before inspecting it. Do not pipe to
        # Select-Object -First, which can stop the Python process early.
        $verifyOut = & $Python tools\verify_update_signature.py `
            $Package `
            --version $ExpectedVersion `
            --signature ([string]$sig.signature) `
            --filename $expectedName `
            --platform windows `
            --package-type windows_full_update `
            --print-sha256
        $verifyExit = $LASTEXITCODE
        $verifyText = (($verifyOut | ForEach-Object { "$_" }) -join "`n")
        if ($verifyExit -ne 0) {
            throw "embedded public-key signature verification failed for $Package (exit=$verifyExit)"
        }
        if ($verifyText -notmatch "signature-ok") {
            throw "embedded public-key signature verification did not confirm success"
        }
        $actualSha = $null
        foreach ($line in ($verifyText -split "`n")) {
            $trim = $line.Trim()
            if ($trim -match '^sha256=([A-Fa-f0-9]{64})$') {
                $actualSha = $Matches[1].ToLowerInvariant()
                break
            }
            if ($trim -match '^[A-Fa-f0-9]{64}$') {
                $actualSha = $trim.ToLowerInvariant()
                break
            }
        }
        if (-not $actualSha -or $actualSha.Length -ne 64) {
            throw "failed to read package sha256 from signature verifier output"
        }

        $sigVersion = ([string]$sig.app_version).TrimStart("vV")
        $wantVersion = $ExpectedVersion.TrimStart("vV")
        if ($sigVersion -ne $wantVersion) {
            throw "signature version mismatch: expected $ExpectedVersion, found $($sig.app_version)"
        }
        if ([string]$sig.filename -and [string]$sig.filename -ne $expectedName) {
            throw "signature filename mismatch: expected $expectedName, found $($sig.filename)"
        }
        if ($null -ne $sig.size_bytes -and [int64]$sig.size_bytes -ne $expectedSize) {
            throw "signature size mismatch: expected $expectedSize, found $($sig.size_bytes)"
        }
        if ([string]$sig.platform -and ([string]$sig.platform).ToLowerInvariant() -notin @("windows", "win32", "win")) {
            throw "signature platform mismatch: expected windows, found $($sig.platform)"
        }
        if ([string]$sig.package_type -and [string]$sig.package_type -ne "windows_full_update") {
            throw "signature package_type mismatch: expected windows_full_update, found $($sig.package_type)"
        }
        $sigSha = ([string]$sig.sha256).Trim().ToLowerInvariant()
        if ($sigSha -and $sigSha -ne $actualSha) {
            throw "signature sha256 mismatch: expected $actualSha, found $sigSha"
        }
    }

    Invoke-Check "setup installer verification" {
        if (-not (Test-Path -LiteralPath $SetupExe -PathType Leaf)) {
            throw "setup exe not found: $SetupExe"
        }
        $item = Get-Item -LiteralPath $SetupExe
        if ($item.Length -lt 1MB) {
            throw "setup exe too small: $($item.Length) bytes"
        }
        # Inno Setup installers are PE files, not PyInstaller archives.
        $bytes = [System.IO.File]::ReadAllBytes($SetupExe)
        $ascii = [System.Text.Encoding]::ASCII.GetString($bytes[0..([Math]::Min($bytes.Length-1, 4MB))])
        if (-not ($ascii.Contains("Inno Setup") -or $ascii.Contains("InnoSetup"))) {
            throw "setup exe does not look like an Inno Setup installer"
        }
        if (-not $ascii.Contains($ExpectedVersion) -and -not $ascii.Contains("v$ExpectedVersion")) {
            Write-Warning "setup exe did not embed plain version string $ExpectedVersion (may still be valid)"
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
