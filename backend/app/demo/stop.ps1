param([Parameter(Mandatory=$true)][string]$ControlDir)

$ErrorActionPreference = 'Stop'
$backend = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$stateFile = Join-Path $ControlDir 'state.json'
if (-not (Test-Path -LiteralPath $stateFile)) { Write-Output 'Kayitli demo sureci yok.'; exit 0 }
$state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
if (-not $state.run_id -or -not $state.launcher_pid -or -not $state.site_pid -or -not $state.model_pid) {
    throw 'Demo surec kaydi gecersiz.'
}
$launcher = Get-CimInstance Win32_Process -Filter "ProcessId = $($state.launcher_pid)"
$site = Get-CimInstance Win32_Process -Filter "ProcessId = $($state.site_pid)"
$model = Get-CimInstance Win32_Process -Filter "ProcessId = $($state.model_pid)"
if (-not $launcher -or -not $site -or -not $model) { throw 'Kayitli demo sureclerinden biri degismis; otomatik kapatma iptal edildi.' }
if ($site.ParentProcessId -ne $launcher.ProcessId -or $model.ParentProcessId -ne $launcher.ProcessId) {
    throw 'Surec ailesi eslesmiyor; otomatik kapatma iptal edildi.'
}
if ($launcher.CommandLine -notmatch 'app\.demo' -or $site.CommandLine -notmatch 'app\.demo\.server' -or
    $model.CommandLine -notmatch 'local_runtime_server\.py' -or
    -not $site.ExecutablePath.StartsWith($backend, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Demo surec kimligi eslesmiyor; otomatik kapatma iptal edildi.'
}
[IO.File]::WriteAllText((Join-Path $ControlDir 'stop.json'), (@{ run_id = $state.run_id } | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    if (-not (Test-Path -LiteralPath $stateFile)) { Write-Output 'Yerel demo kapatildi.'; exit 0 }
    Start-Sleep -Seconds 1
}
throw 'Kapatma istegi gonderildi ancak surecler zamaninda kapanmadi.'
