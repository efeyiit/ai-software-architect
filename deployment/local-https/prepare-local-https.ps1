param([switch]$ExistingListener)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$config = Join-Path $PSScriptRoot '.env.local'
$certDir = Join-Path $PSScriptRoot 'certs'
$caPath = Join-Path $certDir 'local-ca.pem'
$certPath = Join-Path $certDir 'localhost.pem'
$keyPath = Join-Path $certDir 'localhost.key'
$receiptPath = Join-Path $certDir 'ca-provenance.json'
$guard = Join-Path $PSScriptRoot 'assert-local-acl.ps1'
$generator = Join-Path $PSScriptRoot 'generate_cert.py'

foreach ($path in @($repoRoot, $PSScriptRoot, $PSCommandPath, $guard, $generator)) {
    & $guard -LiteralPath $path
}

if (-not (Test-Path -LiteralPath $config)) {
    throw 'Missing ignored .env.local. Run new-local-config.ps1 and fill its placeholders.'
}
& $guard -LiteralPath $config
& $guard -LiteralPath $certDir -RequireProtected
if (-not (Test-Path -LiteralPath $receiptPath)) {
    throw 'Existing local CA has no verified secure-generation receipt. Do not trust it.'
}
foreach ($path in @($caPath, $certPath, $keyPath, (Join-Path $certDir 'local-ca.key'), $receiptPath)) {
    & $guard -LiteralPath $path
}
$ca = [Security.Cryptography.X509Certificates.X509Certificate2]::new($caPath)
try {
    if ((Get-Item -LiteralPath $receiptPath).Length -gt 1024) {
        throw 'Oversized receipt'
    }
    $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    $fields = @($receipt.PSObject.Properties.Name)
    if ($fields.Count -ne 2 -or 'format' -notin $fields -or 'ca_sha256' -notin $fields -or
        $receipt.format -cne 'ariadne-local-ca-v1' -or
        $receipt.ca_sha256 -cne $ca.GetCertHashString([Security.Cryptography.HashAlgorithmName]::SHA256)) {
        throw 'Receipt mismatch'
    }
} catch {
    throw 'Local CA provenance does not match the certificate. Do not trust it.'
}
$allowed = @(
    'ARIADNE_DATABASE_URL', 'ARIADNE_GITHUB_CLIENT_ID',
    'ARIADNE_GITHUB_CLIENT_SECRET', 'ARIADNE_GITHUB_REDIRECT_URI',
    'ARIADNE_OAUTH_FERNET_KEYS'
)
$values = @{}
foreach ($line in [IO.File]::ReadAllLines($config)) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
    if ($trimmed -notmatch '^([A-Z][A-Z0-9_]*)=(.*)$') {
        throw 'Invalid .env.local line. Use NAME=value without quotes or shell commands.'
    }
    $name = $Matches[1]
    $value = $Matches[2]
    if ($name -notin $allowed -or $values.ContainsKey($name)) {
        throw "Unknown or duplicate .env.local setting: $name"
    }
    $values[$name] = $value
}
$launcherDatabaseUrl = [Environment]::GetEnvironmentVariable('ARIADNE_DATABASE_URL', 'Process')
if ($launcherDatabaseUrl -and -not $launcherDatabaseUrl.Contains('REPLACE_WITH_')) {
    $values['ARIADNE_DATABASE_URL'] = $launcherDatabaseUrl
}
$required = @(
    'ARIADNE_DATABASE_URL', 'ARIADNE_GITHUB_CLIENT_ID',
    'ARIADNE_GITHUB_CLIENT_SECRET', 'ARIADNE_GITHUB_REDIRECT_URI',
    'ARIADNE_OAUTH_FERNET_KEYS'
)
foreach ($name in $required) {
    if (-not $values.ContainsKey($name) -or -not $values[$name] -or
        $values[$name].Contains('REPLACE_WITH_')) {
        throw "Fill $name in the ignored .env.local before starting."
    }
}
if ($values['ARIADNE_GITHUB_REDIRECT_URI'] -cne 'https://localhost:8443/auth/github/callback') {
    throw 'ARIADNE_GITHUB_REDIRECT_URI must match the registered https://localhost:8443/auth/github/callback exactly.'
}
foreach ($name in $values.Keys) {
    if ($values[$name].Contains('REPLACE_WITH_')) { throw "Fill $name in .env.local before starting." }
}
foreach ($path in @($caPath, $certPath, $keyPath)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw 'Missing local TLS files. Run generate_cert.py first.'
    }
}
$trusted = Get-ChildItem Cert:\CurrentUser\Root |
    Where-Object { $_.Thumbprint -eq $ca.Thumbprint } |
    Select-Object -First 1
if (-not $trusted) {
    throw 'Local CA is not in CurrentUser Trusted Root. Review and manually trust certs/local-ca.pem; the launcher never changes the trust store.'
}
$leaf = [Security.Cryptography.X509Certificates.X509Certificate2]::new($certPath)
if ($leaf.NotBefore -gt (Get-Date) -or $leaf.NotAfter -le (Get-Date)) {
    throw 'The localhost TLS certificate is outside its validity period.'
}
if (-not $ExistingListener) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 8443)
    try { $listener.Start() } catch { throw 'Port 8443 on 127.0.0.1 is already in use.' } finally { $listener.Stop() }
}

foreach ($name in $values.Keys) {
    [Environment]::SetEnvironmentVariable($name, $values[$name], 'Process')
}
foreach ($name in @('ARIADNE_QDRANT_URL', 'ARIADNE_LOCAL_RUNTIME_TOKEN')) {
    if (-not $values.ContainsKey($name)) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
}
$AriadneLocalTlsCertPath = $certPath
$AriadneLocalTlsKeyPath = $keyPath
