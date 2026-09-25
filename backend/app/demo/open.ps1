param([Parameter(Mandatory=$true)][string]$ControlDir)

$ErrorActionPreference = 'Stop'
$url = 'http://127.0.0.1:8765/demo'
$metaUrl = 'http://127.0.0.1:8765/demo/meta'
$backend = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Backend Python bulunamadi: $python" }

function Get-DemoMeta {
    try {
        $meta = Invoke-RestMethod -Uri $metaUrl -TimeoutSec 2
        if ($meta.mode -eq 'local_demo' -and $meta.data_origin -eq 'bundled_synthetic') { return $meta }
    } catch { }
    return $null
}

if (Get-DemoMeta) { Start-Process $url; exit 0 }
foreach ($port in 8765,8766) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -in @('127.0.0.1','0.0.0.0','::1','::') } | Select-Object -First 1
    if ($listener) { throw "127.0.0.1:$port dolu (PID $($listener.OwningProcess))." }
}

New-Item -ItemType Directory -Path $ControlDir -Force | Out-Null
$env:ARIADNE_DEMO_CONTROL_DIR = (Resolve-Path -LiteralPath $ControlDir).Path
$launcher = Start-Process -FilePath $python -ArgumentList @('-m','app.demo') -WorkingDirectory $backend `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $ControlDir 'demo.log') `
    -RedirectStandardError (Join-Path $ControlDir 'demo-errors.log')
for ($attempt = 0; $attempt -lt 240; $attempt++) {
    if (Get-DemoMeta) { Start-Process $url; exit 0 }
    if ($launcher.HasExited) { throw "Demo baslatilamadi. Log: $(Join-Path $ControlDir 'demo-errors.log')" }
    Start-Sleep -Seconds 1
}
throw "Demo zamaninda acilmadi. Log: $(Join-Path $ControlDir 'demo-errors.log')"
