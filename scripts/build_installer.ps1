[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Version = "",
    [string]$Iscc = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Push-Location $repoRoot
try {
    if (-not $Version) {
        $Version = (& $Python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
    }
    & $Python scripts/package_release.py validate-version --pyproject pyproject.toml --expected $Version
    if ($LASTEXITCODE -ne 0) {
        throw "Application version validation failed."
    }
    if ($Version -notmatch "^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)") {
        throw "Version cannot be converted to a Windows file version: $Version"
    }
    $fileVersion = "$($Matches[1]).$($Matches[2]).$($Matches[3]).0"

    if (-not $Iscc) {
        $candidates = @(
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"),
            (Join-Path $repoRoot "build\inno-setup\ISCC.exe")
        )
        $Iscc = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
    }
    if (-not $Iscc -or -not (Test-Path -LiteralPath $Iscc -PathType Leaf)) {
        throw "ISCC.exe is missing. Install Inno Setup 6.7.3 or pass -Iscc."
    }

    $sourceDirectory = [IO.Path]::GetFullPath(
        (Join-Path $repoRoot "build\portable\SummerCourseScheduler")
    )
    if (-not (Test-Path -LiteralPath (Join-Path $sourceDirectory "SummerCourseScheduler.exe"))) {
        throw "Run scripts/build_windows.ps1 first."
    }
    & $Python scripts/package_release.py validate-distribution --source $sourceDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Installer source distribution validation failed."
    }
    $outputDirectory = [IO.Path]::GetFullPath((Join-Path $repoRoot "dist"))
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

    & $Iscc `
        "/DMyAppVersion=$Version" `
        "/DMyAppFileVersion=$fileVersion" `
        "/DSourceDirectory=$sourceDirectory" `
        "/DOutputDirectory=$outputDirectory" `
        "installer\SummerCourseScheduler.iss"
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
    }

    $installer = Join-Path $outputDirectory "SummerCourseScheduler-Setup-$Version.exe"
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
        throw "Installer output is missing: $installer"
    }
    Write-Host "Installer: $installer"
}
finally {
    Pop-Location
}
