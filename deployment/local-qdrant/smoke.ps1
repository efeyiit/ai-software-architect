param()

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$base = 'http://127.0.0.1:6333'
$collection = 'ariadne_smoke_' + [guid]::NewGuid().ToString('N')
$keyFile = Join-Path $root 'state\api-key.txt'
$running = $false
$created = $false

if (Get-NetTCPConnection -LocalPort 6333 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 6333 is already in use; smoke test will not restart an existing service.'
}

function Invoke-QdrantJson {
    param([string]$Method, [string]$Path, [object]$Body)
    $params = @{ Method = $Method; Uri = "$base$Path"; TimeoutSec = 10
                 Headers = @{ 'api-key' = $apiKey } }
    if ($null -ne $Body) {
        $params.ContentType = 'application/json'
        $params.Body = $Body | ConvertTo-Json -Depth 10 -Compress
    }
    Invoke-RestMethod @params
}

function Assert-Unauthorized {
    param([hashtable]$Headers)
    $response = Invoke-WebRequest -Uri "$base/collections" -Headers $Headers `
        -TimeoutSec 10 -SkipHttpErrorCheck
    if ($response.StatusCode -notin @(401, 403)) {
        throw "Qdrant accepted an unauthorized collection request (HTTP $($response.StatusCode))."
    }
}

function Assert-TopPoint {
    $result = Invoke-QdrantJson -Method Post -Path "/collections/$collection/points/query" `
        -Body @{ query = @(1.0, 0.0); limit = 2; with_payload = $true }
    if ($result.status -ne 'ok' -or $result.result.points.Count -lt 1 -or
        $result.result.points[0].id -ne 1 -or
        $result.result.points[0].payload.label -ne 'alpha') {
        throw 'Qdrant query did not return the expected synthetic point.'
    }
}

try {
    & (Join-Path $root 'start.ps1') | Out-Host
    $running = $true
    $apiKey = Get-Content -LiteralPath $keyFile -Raw -Encoding ascii
    if ($apiKey -cnotmatch '^[0-9a-f]{64}$') { throw 'Local API key has an unexpected format.' }
    $wrongKey = '0' * 64
    if ($wrongKey -ceq $apiKey) { $wrongKey = '1' * 64 }
    Assert-Unauthorized -Headers @{}
    Assert-Unauthorized -Headers @{ 'api-key' = $wrongKey }
    $createdResponse = Invoke-QdrantJson -Method Put -Path "/collections/$collection" `
        -Body @{ vectors = @{ size = 2; distance = 'Cosine' } }
    if ($createdResponse.status -ne 'ok') { throw 'Could not create smoke collection.' }
    $created = $true
    $upsert = Invoke-QdrantJson -Method Put -Path "/collections/$collection/points?wait=true" `
        -Body @{ points = @(
            @{ id = 1; vector = @(1.0, 0.0); payload = @{ label = 'alpha' } },
            @{ id = 2; vector = @(0.0, 1.0); payload = @{ label = 'beta' } }
        ) }
    if ($upsert.status -ne 'ok') { throw 'Could not upsert smoke points.' }
    Assert-TopPoint
    & (Join-Path $root 'stop.ps1') | Out-Host
    $running = $false
    & (Join-Path $root 'start.ps1') | Out-Host
    $running = $true
    if ((Get-Content -LiteralPath $keyFile -Raw -Encoding ascii) -cne $apiKey) {
        throw 'Qdrant API key changed during restart.'
    }
    Assert-Unauthorized -Headers @{}
    Assert-Unauthorized -Headers @{ 'api-key' = $wrongKey }
    Assert-TopPoint
    $logs = (Get-Content -LiteralPath (Join-Path $root 'logs\qdrant.stdout.log') -Raw) +
            (Get-Content -LiteralPath (Join-Path $root 'logs\qdrant.stderr.log') -Raw)
    if ($logs.Contains($apiKey)) { throw 'Qdrant log contains its API key.' }
    Write-Output 'Qdrant auth, insert, search, and persistence after restart: PASS'
} finally {
    if ($running -and $created) {
        try {
            Invoke-QdrantJson -Method Delete -Path "/collections/$collection" -Body $null | Out-Null
        } catch {
            Write-Warning "Synthetic collection $collection remains for inspection."
        }
    }
    if ($running) { & (Join-Path $root 'stop.ps1') | Out-Host }
}
