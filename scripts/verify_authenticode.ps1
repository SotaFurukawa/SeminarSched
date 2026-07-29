[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Path,

    [switch]$RequireSigned,

    [switch]$RequireUnsigned,

    [string]$ExpectedSubject = "SignPath Foundation"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($RequireSigned -and $RequireUnsigned) {
    throw "RequireSigned and RequireUnsigned cannot be used together."
}

$results = @()
$failed = $false

foreach ($candidate in $Path) {
    $resolved = Resolve-Path -LiteralPath $candidate -ErrorAction Stop
    if ((Get-Item -LiteralPath $resolved.Path).PSIsContainer) {
        throw "Authenticode target must be a file: $($resolved.Path)"
    }

    $signature = Get-AuthenticodeSignature -LiteralPath $resolved.Path
    $subject = if ($null -ne $signature.SignerCertificate) {
        $signature.SignerCertificate.Subject
    }
    else {
        $null
    }
    $timestampSubject = if ($null -ne $signature.TimeStamperCertificate) {
        $signature.TimeStamperCertificate.Subject
    }
    else {
        $null
    }

    $valid = $signature.Status -eq [System.Management.Automation.SignatureStatus]::Valid
    $expectedSigner = (
        $null -ne $subject -and
        $subject.IndexOf($ExpectedSubject, [StringComparison]::OrdinalIgnoreCase) -ge 0
    )
    $timestamped = $null -ne $signature.TimeStamperCertificate

    if ($RequireSigned -and (-not $valid -or -not $expectedSigner -or -not $timestamped)) {
        $failed = $true
    }
    if (
        $RequireUnsigned -and
        $signature.Status -ne [System.Management.Automation.SignatureStatus]::NotSigned
    ) {
        $failed = $true
    }

    $results += [PSCustomObject]@{
        Path = $resolved.Path
        Status = $signature.Status.ToString()
        StatusMessage = $signature.StatusMessage
        SignerSubject = $subject
        TimestampSubject = $timestampSubject
        ExpectedSigner = $expectedSigner
        Timestamped = $timestamped
    }
}

$results | ConvertTo-Json -Depth 3

if ($failed) {
    if ($RequireUnsigned) {
        throw "Unsigned-candidate verification failed. An unexpected signature was present."
    }
    throw (
        "Authenticode verification failed. Every required file must have a Valid " +
        "signature from '$ExpectedSubject' and a timestamp."
    )
}
