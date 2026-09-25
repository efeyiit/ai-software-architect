param([int]$TimeoutSeconds = 3)

$ErrorActionPreference = 'Stop'
try {
    $response = Invoke-WebRequest -Uri 'http://127.0.0.1:6333/readyz' -TimeoutSec $TimeoutSeconds
    if ($response.StatusCode -ne 200) { throw "HTTP $($response.StatusCode)" }
    Write-Output 'Qdrant ready at http://127.0.0.1:6333'
} catch {
    Write-Error 'Qdrant is not ready at http://127.0.0.1:6333/readyz'
    exit 1
}
