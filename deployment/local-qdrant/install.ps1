param()

$ErrorActionPreference = 'Stop'
$version = 'v1.19.1'
$asset = 'qdrant-x86_64-pc-windows-msvc.zip'
$expectedSha256 = '9b6f69bd85f6abed4bc13f943099f55c6ffd55f5dd90388635320d8fbb569eb0'
$url = "https://github.com/qdrant/qdrant/releases/download/$version/$asset"
$runtime = Join-Path $PSScriptRoot 'runtime'
$archive = Join-Path $runtime "$version-$asset"
$install = Join-Path $runtime $version
$exe = Join-Path $install 'qdrant.exe'

New-Item -ItemType Directory -Force -Path $runtime | Out-Null
if (-not (Test-Path -LiteralPath $archive)) {
    Invoke-WebRequest -Uri $url -OutFile $archive
}
$actualSha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualSha256 -ne $expectedSha256) {
    throw "Qdrant archive SHA-256 mismatch; expected $expectedSha256, got $actualSha256"
}
if (-not (Test-Path -LiteralPath $exe)) {
    if (Test-Path -LiteralPath $install) {
        throw "Incomplete Qdrant directory at $install; inspect it before retrying"
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $install
}
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Verified archive did not provide qdrant.exe at $exe"
}
& (Join-Path $PSScriptRoot 'verify.ps1') -ExecutablePath $exe | Out-Null
Write-Output "Qdrant $version installed from verified official release: $exe"
