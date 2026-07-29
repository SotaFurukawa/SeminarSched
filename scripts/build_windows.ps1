[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pyproject = Join-Path $repoRoot "pyproject.toml"

if ($repoRoot -match "[^\x00-\x7F]") {
    throw @"
Windows release builds require an ASCII-only workspace path because MSVC/Nuitka can
corrupt non-ASCII linker paths. Copy or clone this repository to an ASCII-only
workspace (for example C:\build\summer-scheduler), create the release virtual
environment there, and retry:

  Set-Location C:\build\summer-scheduler
  py -3.12 -m venv .venv-release
  .\.venv-release\Scripts\python.exe -m pip install -r packaging\requirements-release.txt
  .\.venv-release\Scripts\python.exe -m pip install --no-deps .
  .\scripts\build_windows.ps1 -Python .\.venv-release\Scripts\python.exe

This restriction applies only to the build workspace. The packaged application
continues to support Japanese user-data and installation paths.
"@
}

function Get-WorkspacePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $fullPath = [IO.Path]::GetFullPath($Path)
    $prefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
        [IO.Path]::DirectorySeparatorChar
    if (-not $fullPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside the workspace: $fullPath"
    }
    return $fullPath
}

function Reset-BuildDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)
    $fullPath = Get-WorkspacePath $Path
    if (Test-Path -LiteralPath $fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
    New-Item -ItemType Directory -Path $fullPath | Out-Null
    return $fullPath
}

Push-Location $repoRoot
try {
    if (Test-Path -LiteralPath $Python -PathType Leaf) {
        $pythonExecutable = (Resolve-Path -LiteralPath $Python).Path
    }
    else {
        $pythonExecutable = (Get-Command $Python -ErrorAction Stop).Source
    }
    $repositoryRealPath = (
        & $Python -c "import os, sys; print(os.path.realpath(sys.argv[1]))" $repoRoot
    ).Trim()
    $pythonRealPath = (
        & $Python -c "import os, sys; print(os.path.realpath(sys.argv[1]))" $pythonExecutable
    ).Trim()
    foreach ($physicalPath in @($repositoryRealPath, $pythonRealPath)) {
        if ($physicalPath -match "[^\x00-\x7F]") {
            throw @"
The repository and release Python must both have ASCII-only physical paths.
subst, junctions, and symbolic links are not sufficient because Nuitka/MSVC
resolve their targets. Copy or clone the source to an ASCII-only workspace,
create a new .venv-release there, and retry.

Resolved non-ASCII path: $physicalPath
"@
        }
    }
    $pythonVersion = (& $Python -c "import platform; print(platform.python_version())").Trim()
    $pythonMinor = (& $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    $pythonBits = (& $Python -c "import struct; print(struct.calcsize('P') * 8)").Trim()
    if ($pythonMinor -ne "3.12" -or $pythonBits -ne "64") {
        throw "Windows x64 Python 3.12 is required (found: $pythonVersion / ${pythonBits}bit)."
    }

    if (-not $Version) {
        $Version = (& $Python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
    }
    & $Python scripts/package_release.py validate-version --pyproject $pyproject --expected $Version
    if ($LASTEXITCODE -ne 0) {
        throw "Application version validation failed."
    }
    & $Python scripts/verify_release_environment.py `
        --requirements (Join-Path $repoRoot "packaging\requirements-release.txt") `
        --pyproject $pyproject
    if ($LASTEXITCODE -ne 0) {
        throw "Release environment validation failed."
    }
    if ($Version -notmatch "^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)") {
        throw "Version cannot be converted to a Windows file version: $Version"
    }
    $fileVersion = "$($Matches[1]).$($Matches[2]).$($Matches[3]).0"

    $pythonDirectory = Split-Path -Parent $pythonExecutable
    $env:PATH = $pythonDirectory + [IO.Path]::PathSeparator + $env:PATH
    $deployCommand = Join-Path $pythonDirectory "pyside6-deploy.exe"
    if (-not (Test-Path -LiteralPath $deployCommand)) {
        $resolvedDeploy = Get-Command "pyside6-deploy" -ErrorAction Stop
        $deployCommand = $resolvedDeploy.Source
    }
    & $Python -c "import importlib.metadata as m; assert m.version('Nuitka') == '4.0'"
    if ($LASTEXITCODE -ne 0) {
        throw "Nuitka 4.0 is required. Install packaging/requirements-release.txt."
    }

    $buildRoot = Get-WorkspacePath (Join-Path $repoRoot "build")
    New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
    $deployRoot = Reset-BuildDirectory (Join-Path $buildRoot "deploy")
    $portableParent = Reset-BuildDirectory (Join-Path $buildRoot "portable")
    $transientSpec = Get-WorkspacePath (Join-Path $buildRoot "pysidedeploy.spec")
    Copy-Item -LiteralPath (Join-Path $repoRoot "packaging\pysidedeploy.spec") -Destination $transientSpec
    $specText = Get-Content -Raw -Encoding UTF8 -LiteralPath $transientSpec
    $specText = $specText.Replace("@FILE_VERSION@", $fileVersion)
    # PySide6 6.11 reads this INI through the active Windows code page.
    # The template is deliberately ASCII-only, so avoid a UTF-8 BOM here.
    Set-Content -Encoding ASCII -LiteralPath $transientSpec -Value $specText

    Write-Host "pyside6-deploy standalone build: version=$Version python=$pythonVersion"
    & $deployCommand -c $transientSpec -f
    if ($LASTEXITCODE -ne 0) {
        throw "pyside6-deploy failed with exit code $LASTEXITCODE."
    }

    $deployedDirectory = Join-Path $deployRoot "SummerCourseScheduler.dist"
    if (-not (Test-Path -LiteralPath $deployedDirectory -PathType Container)) {
        throw "Standalone output directory is missing: $deployedDirectory"
    }
    $generatedExecutable = Join-Path $deployedDirectory "__main__.exe"
    if (-not (Test-Path -LiteralPath $generatedExecutable -PathType Leaf)) {
        throw "Standalone executable is missing: $generatedExecutable"
    }

    # PySide6 6.11 may bundle the unused Qt.labs.assetdownloader development
    # directory, including .obj/.lib intermediates. It is not imported by this
    # application and must not enter a release artifact.
    $assetDownloaderDirectory = Get-WorkspacePath (
        Join-Path $deployedDirectory "PySide6\qml\Qt\labs\assetdownloader"
    )
    if (Test-Path -LiteralPath $assetDownloaderDirectory -PathType Container) {
        Remove-Item -LiteralPath $assetDownloaderDirectory -Recurse -Force
    }

    # Alembic discovers env.py and revision scripts from the filesystem at
    # runtime. Nuitka compiles Python modules but does not retain these source
    # files as data, so copy only the migration runtime sources explicitly.
    $migrationSource = Join-Path $repoRoot (
        "src\summer_scheduler\infrastructure\db\alembic"
    )
    $migrationTarget = Get-WorkspacePath (
        Join-Path $deployedDirectory (
            "summer_scheduler\infrastructure\db\alembic"
        )
    )
    New-Item -ItemType Directory -Force -Path $migrationTarget | Out-Null
    foreach ($migrationFile in @("env.py", "script.py.mako")) {
        $sourceFile = Join-Path $migrationSource $migrationFile
        if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
            throw "Required Alembic runtime file is missing: $sourceFile"
        }
        Copy-Item -LiteralPath $sourceFile -Destination (
            Join-Path $migrationTarget $migrationFile
        )
    }
    $revisionSource = Join-Path $migrationSource "versions"
    $revisionFiles = @(
        Get-ChildItem -LiteralPath $revisionSource -Filter "*.py" -File
    )
    if ($revisionFiles.Count -eq 0) {
        throw "Alembic revision sources are missing: $revisionSource"
    }
    $revisionTarget = Join-Path $migrationTarget "versions"
    New-Item -ItemType Directory -Force -Path $revisionTarget | Out-Null
    foreach ($revisionFile in $revisionFiles) {
        Copy-Item -LiteralPath $revisionFile.FullName -Destination (
            Join-Path $revisionTarget $revisionFile.Name
        )
    }

    Rename-Item -LiteralPath $generatedExecutable -NewName "SummerCourseScheduler.exe"

    $portableRoot = Join-Path $portableParent "SummerCourseScheduler"
    New-Item -ItemType Directory -Path $portableRoot | Out-Null
    Copy-Item -Path (Join-Path $deployedDirectory "*") -Destination $portableRoot -Recurse
    Copy-Item -LiteralPath (Join-Path $repoRoot "packaging\portable_README.txt") `
        -Destination (Join-Path $portableRoot "README.txt")
    Copy-Item -LiteralPath (Join-Path $repoRoot "THIRD_PARTY_NOTICES.md") `
        -Destination (Join-Path $portableRoot "THIRD_PARTY_NOTICES.md")
    Copy-Item -LiteralPath (Join-Path $repoRoot "PRIVACY.md") `
        -Destination (Join-Path $portableRoot "PRIVACY.md")
    Copy-Item -LiteralPath (Join-Path $repoRoot "docs\code_signing_policy.md") `
        -Destination (Join-Path $portableRoot "CODE_SIGNING_POLICY.md")
    $projectLicense = Join-Path $repoRoot "LICENSE"
    if (Test-Path -LiteralPath $projectLicense -PathType Leaf) {
        Copy-Item -LiteralPath $projectLicense -Destination (Join-Path $portableRoot "LICENSE")
    }
    & $Python scripts/collect_licenses.py --output (Join-Path $portableRoot "licenses")
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency license collection failed."
    }

    & $Python scripts/package_release.py validate-distribution --source $portableRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Standalone distribution validation failed."
    }

    $distRoot = Get-WorkspacePath (Join-Path $repoRoot "dist")
    New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
    $portableZip = Join-Path $distRoot "SummerCourseScheduler-Portable-$Version.zip"
    & $Python scripts/package_release.py archive --source $portableRoot --output $portableZip
    if ($LASTEXITCODE -ne 0) {
        throw "Portable ZIP creation failed."
    }

    Write-Host "Portable directory: $portableRoot"
    Write-Host "Portable ZIP: $portableZip"
}
finally {
    Pop-Location
}
