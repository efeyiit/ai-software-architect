param()

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'assert-private.ps1') | Out-Null

$keyFile = Join-Path $PSScriptRoot 'state\api-key.txt'
$storedKey = Get-Content -LiteralPath $keyFile -Raw -Encoding ascii
if ($storedKey -cnotmatch '^[0-9a-f]{64}$') {
    throw 'Qdrant API key file is malformed; refusing to start.'
}
Write-Output 'Qdrant API key file is present with a private ACL.'
