[CmdletBinding()]
param(
    [string]$Version = "6.7.3",
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $Destination) {
    $Destination = Join-Path $repoRoot "build\inno-setup"
}
$Destination = [IO.Path]::GetFullPath($Destination)
$workspacePrefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
    [IO.Path]::DirectorySeparatorChar
if (-not $Destination.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to install Inno Setup outside the workspace: $Destination"
}

$downloadDirectory = Join-Path $repoRoot "build\inno-download"
New-Item -ItemType Directory -Force -Path $downloadDirectory | Out-Null
$installer = Join-Path $downloadDirectory "innosetup-$Version.exe"
$tagVersion = $Version.Replace(".", "_")
$uri = "https://github.com/jrsoftware/issrc/releases/download/is-$tagVersion/innosetup-$Version.exe"

Invoke-WebRequest -Uri $uri -OutFile $installer
$signature = Get-AuthenticodeSignature -LiteralPath $installer
if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
    throw "Inno Setup Authenticode signature is not valid: $($signature.Status)"
}
if ($signature.SignerCertificate.Subject -notmatch "Pyrsys B\.V\.") {
    throw "Unexpected Inno Setup signer: $($signature.SignerCertificate.Subject)"
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$destinationArgument = '/DIR="' + $Destination + '"'
$process = Start-Process -FilePath $installer -Wait -PassThru -ArgumentList @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/SP-",
    "/PORTABLE=1",
    "/CURRENTUSER",
    $destinationArgument
)
if ($process.ExitCode -ne 0) {
    throw "Inno Setup installation failed with exit code $($process.ExitCode)."
}
$iscc = Join-Path $Destination "ISCC.exe"
if (-not (Test-Path -LiteralPath $iscc -PathType Leaf)) {
    throw "ISCC.exe was not installed: $iscc"
}
Write-Host $iscc
