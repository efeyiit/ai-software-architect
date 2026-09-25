param([Parameter(Mandatory=$true)][string]$ControlDir)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$backend = Join-Path $repo 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$qdrant = Join-Path $repo 'deployment\local-qdrant'
$tls = Join-Path $repo 'deployment\local-https'
$url = 'https://localhost:8443/'
$stateFile = Join-Path $ControlDir 'state.json'
$guard = Join-Path $tls 'assert-local-acl.ps1'
$controlGuard = Join-Path $PSScriptRoot 'assert-control.ps1'
foreach ($path in @($repo, $PSScriptRoot, $PSCommandPath, $guard, $controlGuard)) {
    & $guard -LiteralPath $path
}
& $controlGuard -ControlDir $ControlDir | Out-Null
$env:ARIADNE_DATABASE_URL = 'postgresql://ariadne@127.0.0.1:55440/ariadne'

function Test-ProductReady {
    try {
        $health = Invoke-RestMethod -Uri 'https://localhost:8443/health' -TimeoutSec 3
        if ($health.status -ne 'ok') { return $false }
        try { Invoke-WebRequest -Uri 'https://localhost:8443/auth/me' -TimeoutSec 3 | Out-Null; return $false }
        catch { return ([int]$_.Exception.Response.StatusCode -eq 401) }
    } catch { return $false }
}

if (Test-Path -LiteralPath $stateFile) {
    $record = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $launcher = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.launcher_pid)" -ErrorAction SilentlyContinue
    if ($launcher -and $launcher.CommandLine -match 'app\.api\.local_launcher') {
        $site = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.site_pid)" -ErrorAction SilentlyContinue
        $model = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.model_pid)" -ErrorAction SilentlyContinue
        $worker = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.worker_pid)" -ErrorAction SilentlyContinue
        $siteListener = Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalAddress -eq '127.0.0.1' } | Select-Object -First 1
        $modelListener = Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalAddress -eq '127.0.0.1' } | Select-Object -First 1
        if (-not $site -or -not $model -or -not $worker -or
            $site.ParentProcessId -ne $launcher.ProcessId -or
            $model.ParentProcessId -ne $launcher.ProcessId -or
            $worker.ParentProcessId -ne $launcher.ProcessId -or
            $site.CommandLine -notmatch 'app\.main:app' -or
            $model.CommandLine -notmatch 'local_runtime_server\.py' -or
            $worker.CommandLine -notmatch 'app\.api\.worker' -or
            $siteListener.OwningProcess -ne $site.ProcessId -or
            $modelListener.OwningProcess -ne $model.ProcessId) {
            throw 'Kayitli Ariadne servis surecleri/portlari eslesmiyor; mevcut servis sahiplenilmeyecek.'
        }
        if (Test-ProductReady) {
            . (Join-Path $tls 'prepare-local-https.ps1') -ExistingListener
            & (Join-Path $qdrant 'assert-private.ps1') | Out-Null
            & (Join-Path $qdrant 'ready.ps1') | Out-Null
            Start-Process $url
            exit 0
        }
        throw 'Kayitli Ariadne sureci var ancak servis hazir degil. Loglari inceleyin.'
    }
    Remove-Item -LiteralPath $stateFile
}
if (Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue) {
    throw '8443 portunda baska bir servis var; Ariadne onu sahiplenmeyecek.'
}
if (-not (Test-Path -LiteralPath $python)) { throw "Backend Python eksik: $python" }
# Missing or blocked PostgreSQL remains a clear startup error.
. (Join-Path $tls 'prepare-local-https.ps1')

$qdrantWasRunning = [bool](Get-NetTCPConnection -LocalPort 6333 -State Listen -ErrorAction SilentlyContinue)
try {
    & (Join-Path $qdrant 'install.ps1')
    & (Join-Path $qdrant 'start.ps1')
    & (Join-Path $qdrant 'ready.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Qdrant hazir degil.' }
    $env:ARIADNE_LOCAL_CONTROL_DIR = (Resolve-Path -LiteralPath $ControlDir).Path
    $env:ARIADNE_LOCAL_TLS_CERT = $AriadneLocalTlsCertPath
    $env:ARIADNE_LOCAL_TLS_KEY = $AriadneLocalTlsKeyPath
    $env:ARIADNE_LOCAL_TLS_CA = Join-Path $tls 'certs\local-ca.pem'
    $env:ARIADNE_QDRANT_API_KEY_FILE = Join-Path $qdrant 'state\api-key.txt'
    $process = Start-Process -FilePath $python -ArgumentList @('-m','app.api.local_launcher') `
        -WorkingDirectory $backend -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $ControlDir 'launcher.log') `
        -RedirectStandardError (Join-Path $ControlDir 'launcher-errors.log')
    for ($attempt = 0; $attempt -lt 480; $attempt++) {
        if ((Test-Path -LiteralPath $stateFile) -and (Test-ProductReady)) {
            if (-not $qdrantWasRunning) {
                Set-Content -LiteralPath (Join-Path $ControlDir 'qdrant-owned.txt') -Value 'started-by-local-app' -Encoding ascii
            }
            Start-Process $url
            exit 0
        }
        if ($process.HasExited) {
            throw "Ariadne baslatilamadi. Log: $(Join-Path $ControlDir 'launcher-errors.log')"
        }
        Start-Sleep -Seconds 1
    }
    throw "Ariadne hazir olmadi. Log: $(Join-Path $ControlDir 'launcher-errors.log')"
} catch {
    if (-not $qdrantWasRunning) {
        try { & (Join-Path $qdrant 'stop.ps1') } catch { }
    }
    throw
}
