$ErrorActionPreference = 'Stop'

$template = Join-Path $PSScriptRoot '.env.example'
$target = Join-Path $PSScriptRoot '.env.local'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$guard = Join-Path $PSScriptRoot 'assert-local-acl.ps1'
if (Test-Path -LiteralPath $target) {
    throw '.env.local already exists. It was not overwritten.'
}
foreach ($path in @($repoRoot, $PSScriptRoot, $PSCommandPath, $guard, $template)) {
    & $guard -LiteralPath $path
}
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$fernetKey = [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')
$content = [IO.File]::ReadAllText($template)
$content = $content.Replace('REPLACE_WITH_LOCALLY_GENERATED_FERNET_KEY', $fernetKey)
[IO.File]::WriteAllText($target, $content, [Text.UTF8Encoding]::new($false))
try {
    & $guard -LiteralPath $target
} catch {
    Remove-Item -LiteralPath $target -Force
    throw
}
Write-Host 'Created ignored .env.local with a local encryption key.'
Write-Host 'Fill the GitHub OAuth Client ID/Secret placeholders locally.'
