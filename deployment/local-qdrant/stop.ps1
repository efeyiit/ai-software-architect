param()

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$pidFile = Join-Path $root 'state\qdrant.pid.json'
$expectedExe = Join-Path $root 'runtime\v1.19.1\qdrant.exe'
if (-not (Test-Path -LiteralPath $pidFile)) {
    throw 'No local Qdrant PID record; refusing to stop another process.'
}
$record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
$process = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.pid)" -ErrorAction SilentlyContinue
if (-not $process) {
    Remove-Item -LiteralPath $pidFile
    Write-Output 'Recorded Qdrant process was already stopped.'
    exit 0
}
if ($process.ExecutablePath -ne $expectedExe -or
    $process.CreationDate.ToUniversalTime().Ticks -ne $record.creationDate.ToUniversalTime().Ticks) {
    throw 'Recorded PID does not belong to this local Qdrant instance; refusing to stop it.'
}
Stop-Process -Id $record.pid -Force
$deadline = (Get-Date).AddSeconds(15)
while ((Get-Date) -lt $deadline) {
    if (-not (Get-Process -Id $record.pid -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 200
}
if (Get-Process -Id $record.pid -ErrorAction SilentlyContinue) {
    throw 'Qdrant process did not stop.'
}
Remove-Item -LiteralPath $pidFile
Write-Output "Stopped local Qdrant PID $($record.pid). Data remains in $root\data."
