param(
    [string]$ExecutablePath = (Join-Path $PSScriptRoot 'runtime\v1.19.1\qdrant.exe')
)

$ErrorActionPreference = 'Stop'
# SHA-256 of qdrant.exe inside the pinned, verified v1.19.1 Windows release ZIP.
$expectedSha256 = 'b5354e3c8f9d13d92294f38d4988d4ddedc04acaa2ce51f0a2d65b30e2d4cd69'
if (-not (Test-Path -LiteralPath $ExecutablePath -PathType Leaf)) {
    throw 'Qdrant executable is missing.'
}
$actualSha256 = (Get-FileHash -LiteralPath $ExecutablePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualSha256 -ne $expectedSha256) {
    throw 'Qdrant executable SHA-256 mismatch; refusing to run it.'
}
Write-Output 'Qdrant executable SHA-256 verified.'
