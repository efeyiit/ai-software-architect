param([Parameter(Mandatory=$true)][string]$ControlDir)

$ErrorActionPreference = 'Stop'
$target = [IO.Path]::GetFullPath($ControlDir)
$userSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$trusted = @($userSid, 'S-1-5-18', 'S-1-5-32-544')
$writeRights = [Security.AccessControl.FileSystemRights]::WriteData -bor
    [Security.AccessControl.FileSystemRights]::AppendData -bor
    [Security.AccessControl.FileSystemRights]::WriteExtendedAttributes -bor
    [Security.AccessControl.FileSystemRights]::WriteAttributes -bor
    [Security.AccessControl.FileSystemRights]::Delete -bor
    [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
    [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
    [Security.AccessControl.FileSystemRights]::TakeOwnership

function Get-RuleSid($Rule) {
    try { return $Rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value }
    catch { throw "Kontrol klasoru ACL kimligi okunamadi: $($Rule.IdentityReference.Value)" }
}

function Assert-Access([string]$Path, [bool]$Private) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Kontrol yolu yeniden yonlendirme iceriyor: $Path"
    }
    $acl = Get-Acl -LiteralPath $Path
    $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($owner -notin $trusted) {
        throw "Kontrol yolu guvenilir sahiplikte degil: $Path"
    }
    if ($Private -and $owner -ne $userSid) {
        throw "Kontrol yolu mevcut Windows kullanicisina ait degil: $Path"
    }
    if ($Private -and $Path -eq $target -and -not $acl.AreAccessRulesProtected) {
        throw "Kontrol klasoru ust dizinden izin devraliyor: $Path"
    }
    foreach ($rule in $acl.Access) {
        if ($rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow) { continue }
        $sid = Get-RuleSid $rule
        if ($sid -in $trusted) { continue }
        if ($Private -or (($rule.FileSystemRights -band $writeRights) -ne 0)) {
            throw "Kontrol yolunda guvenilmeyen izin var ($sid): $Path"
        }
    }
}

if (-not (Test-Path -LiteralPath $target -PathType Container)) {
    throw "Korumali kontrol klasoru bulunamadi: $target"
}
$current = $target
while ($current) {
    Assert-Access $current ($current -eq $target)
    $parent = [IO.Directory]::GetParent($current)
    if ($null -eq $parent) { break }
    $current = $parent.FullName
}
foreach ($name in @('state.json','stop.json','launcher.log','launcher-errors.log',
                     'model.log','site.log','worker.log','qdrant-owned.txt')) {
    $path = Join-Path $target $name
    if (Test-Path -LiteralPath $path) { Assert-Access $path $true }
}
Write-Output 'Control directory ACL preflight: PASS'
