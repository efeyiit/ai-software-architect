param([Parameter(Mandatory=$true)][string]$ControlDir)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$controlGuard = Join-Path $PSScriptRoot 'assert-control.ps1'
$aclGuard = Join-Path $repo 'deployment\local-https\assert-local-acl.ps1'
foreach ($path in @($repo, $PSScriptRoot, $PSCommandPath, $controlGuard, $aclGuard)) {
    & $aclGuard -LiteralPath $path
}
& $controlGuard -ControlDir $ControlDir | Out-Null
$stateFile = Join-Path $ControlDir 'state.json'
if (-not (Test-Path -LiteralPath $stateFile)) { Write-Output 'Kayitli Ariadne uygulamasi yok.'; exit 0 }
$record = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
if (-not $record.run_id -or -not $record.launcher_pid -or -not $record.model_pid -or
    -not $record.site_pid -or -not $record.worker_pid) { throw 'Surec kaydi gecersiz.' }
$launcher = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.launcher_pid)"
$model = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.model_pid)"
$site = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.site_pid)"
$worker = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.worker_pid)"
if (-not $launcher -or -not $model -or -not $site -or -not $worker -or
    $model.ParentProcessId -ne $launcher.ProcessId -or
    $site.ParentProcessId -ne $launcher.ProcessId -or
    $worker.ParentProcessId -ne $launcher.ProcessId -or
    $launcher.CommandLine -notmatch 'app\.api\.local_launcher' -or
    $model.CommandLine -notmatch 'local_runtime_server\.py' -or
    $site.CommandLine -notmatch 'app\.main:app' -or
    $worker.CommandLine -notmatch 'app\.api\.worker') {
    throw 'Surec kimligi eslesmiyor; yabanci surec kapatilmayacak.'
}
[IO.File]::WriteAllText((Join-Path $ControlDir 'stop.json'),
    (@{ run_id = $record.run_id } | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
for ($attempt = 0; $attempt -lt 25; $attempt++) {
    if (-not (Test-Path -LiteralPath $stateFile)) { break }
    Start-Sleep -Seconds 1
}
if (Test-Path -LiteralPath $stateFile) { throw 'Ariadne child surecleri zamaninda kapanmadi.' }
$ownedQdrant = Join-Path $ControlDir 'qdrant-owned.txt'
if (Test-Path -LiteralPath $ownedQdrant) {
    & (Join-Path $repo 'deployment\local-qdrant\stop.ps1')
    Remove-Item -LiteralPath $ownedQdrant
}
Write-Output 'Ariadne uygulamasi kapatildi.'
