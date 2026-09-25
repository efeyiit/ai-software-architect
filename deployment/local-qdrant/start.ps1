param([int]$StartupTimeoutSeconds = 60)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$exe = Join-Path $root 'runtime\v1.19.1\qdrant.exe'
$data = Join-Path $root 'data\storage'
$snapshots = Join-Path $root 'data\snapshots'
$logs = Join-Path $root 'logs'
$state = Join-Path $root 'state'
$pidFile = Join-Path $state 'qdrant.pid.json'
$keyFile = Join-Path $state 'api-key.txt'
$url = 'http://127.0.0.1:6333'

& (Join-Path $root 'assert-private.ps1') | Out-Null
if (-not (Test-Path -LiteralPath $exe)) {
    throw 'Qdrant binary missing. Run deployment/local-qdrant/install.ps1 first.'
}
& (Join-Path $root 'verify.ps1') -ExecutablePath $exe | Out-Null
& (Join-Path $root 'ensure-key.ps1') | Out-Null
$apiKey = Get-Content -LiteralPath $keyFile -Raw -Encoding ascii

if (Test-Path -LiteralPath $pidFile) {
    $record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    $recordedProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.pid)" -ErrorAction SilentlyContinue
    if ($recordedProcess -and $recordedProcess.ExecutablePath -eq $exe -and
        $recordedProcess.CreationDate.ToUniversalTime().Ticks -eq $record.creationDate.ToUniversalTime().Ticks) {
        $recordedListener = Get-NetTCPConnection -OwningProcess $record.pid -LocalPort 6333 -State Listen -ErrorAction SilentlyContinue
        if (-not $recordedListener) {
            throw 'Recorded Qdrant process is running without port 6333; refusing a second instance on the same data.'
        }
    } elseif ($recordedProcess) {
        throw 'Recorded PID belongs to another process; inspect state/qdrant.pid.json before starting.'
    } else {
        Remove-Item -LiteralPath $pidFile
    }
}

$listener = Get-NetTCPConnection -LocalPort 6333 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    if (-not (Test-Path -LiteralPath $pidFile)) {
        throw 'Port 6333 is already in use by a service this script did not start.'
    }
    $record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    $owned = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.pid)" -ErrorAction SilentlyContinue
    if (-not $owned -or $owned.ExecutablePath -ne $exe -or
        $owned.CreationDate.ToUniversalTime().Ticks -ne $record.creationDate.ToUniversalTime().Ticks) {
        throw 'Port 6333 is in use, but the recorded process is not this local Qdrant instance.'
    }
    $bindings = Get-NetTCPConnection -OwningProcess $record.pid -State Listen -ErrorAction SilentlyContinue
    if (@($bindings | Where-Object { $_.LocalAddress -ne '127.0.0.1' -or $_.LocalPort -ne 6333 }).Count -gt 0) {
        throw 'Recorded Qdrant process has a listener outside 127.0.0.1:6333.'
    }
    & (Join-Path $root 'ready.ps1')
    exit 0
}

New-Item -ItemType Directory -Force -Path $data, $snapshots, $logs, $state | Out-Null
$stdout = Join-Path $logs 'qdrant.stdout.log'
$stderr = Join-Path $logs 'qdrant.stderr.log'
$process = Start-Process -FilePath $exe -ArgumentList '--disable-telemetry' -WorkingDirectory $root `
    -Environment @{ QDRANT__SERVICE__API_KEY = $apiKey } `
    -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$owned = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)"
@{ pid = $process.Id; executable = $exe; creationDate = $owned.CreationDate.ToString('o') } |
    ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8

$ready = $false
try {
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($process.HasExited) {
            throw "Qdrant exited during startup. See $stderr"
        }
        try {
            $response = Invoke-WebRequest -Uri "$url/readyz" -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $bindings = Get-NetTCPConnection -OwningProcess $process.Id -State Listen -ErrorAction SilentlyContinue
                if (@($bindings | Where-Object { $_.LocalAddress -ne '127.0.0.1' -or $_.LocalPort -ne 6333 }).Count -gt 0) {
                    throw 'Qdrant opened a listener outside 127.0.0.1:6333'
                }
                $ready = $true
                Write-Output "Qdrant ready: $url (PID $($process.Id))"
                exit 0
            }
        } catch {
            if ($_.Exception.Message -like '*outside 127.0.0.1*') { throw }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Qdrant did not become ready in $StartupTimeoutSeconds seconds. See $stderr"
} finally {
    if (-not $ready) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
    }
}
