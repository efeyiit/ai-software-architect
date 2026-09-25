param()

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($PSScriptRoot)
$userSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$trustedSids = @($userSid, 'S-1-5-18', 'S-1-5-32-544')
$writeRights = [Security.AccessControl.FileSystemRights]::WriteData -bor
    [Security.AccessControl.FileSystemRights]::AppendData -bor
    [Security.AccessControl.FileSystemRights]::WriteExtendedAttributes -bor
    [Security.AccessControl.FileSystemRights]::WriteAttributes -bor
    [Security.AccessControl.FileSystemRights]::Delete -bor
    [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
    [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
    [Security.AccessControl.FileSystemRights]::TakeOwnership
$replaceRights = [Security.AccessControl.FileSystemRights]::Delete -bor
    [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
    [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
    [Security.AccessControl.FileSystemRights]::TakeOwnership -bor
    [Security.AccessControl.FileSystemRights]::WriteAttributes -bor
    [Security.AccessControl.FileSystemRights]::WriteExtendedAttributes

function Get-RuleSid {
    param($Rule)
    try {
        return $Rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
    } catch {
        throw "Cannot identify an ACL principal: $($Rule.IdentityReference.Value)"
    }
}

function Assert-PathAcl {
    param([string]$Path, [bool]$Private, [bool]$Ancestor = $false)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Qdrant path is a reparse point: $Path"
    }
    $acl = Get-Acl -LiteralPath $Path
    if ($Private -and $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $userSid) {
        throw "Qdrant private path is not owned by the current user: $Path"
    }
    foreach ($rule in $acl.Access) {
        if ($rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow) { continue }
        if ($Ancestor -and
            ($rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0) {
            continue
        }
        $sid = Get-RuleSid -Rule $rule
        if ($sid -in $trustedSids) { continue }
        $dangerousRights = if ($Ancestor) { $replaceRights } else { $writeRights }
        if ($Private -or (($rule.FileSystemRights -band $dangerousRights) -ne 0)) {
            throw "Qdrant path has an untrusted ACL entry ($sid): $Path"
        }
    }
}

# A writable ancestor could replace the checked scripts or private directories.
$ancestor = $root
while ($ancestor) {
    Assert-PathAcl -Path $ancestor -Private $false -Ancestor ($ancestor -ne $root)
    $parent = [IO.Directory]::GetParent($ancestor)
    if ($null -eq $parent) { break }
    $ancestor = $parent.FullName
}

$requiredPrivateRoots = @('data', 'logs', 'state')
$privateRoots = $requiredPrivateRoots + @('storage', 'snapshots')
foreach ($name in $privateRoots) {
    $path = Join-Path $root $name
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        if (Test-Path -LiteralPath $path) {
            throw "Qdrant private path is not a directory: $path"
        }
        if ($name -in $requiredPrivateRoots) {
            throw "Qdrant private directory is missing: $path"
        }
        continue
    }
    Assert-PathAcl -Path $path -Private $true
    foreach ($item in Get-ChildItem -LiteralPath $path -Recurse -Force) {
        Assert-PathAcl -Path $item.FullName -Private $true
    }
}

$keyFile = Join-Path $root 'state\api-key.txt'
if (-not (Test-Path -LiteralPath $keyFile -PathType Leaf)) {
    throw 'Qdrant API key file is missing; startup is blocked until private storage is provisioned.'
}
$keyAcl = Get-Acl -LiteralPath $keyFile
if (-not $keyAcl.AreAccessRulesProtected -or @($keyAcl.Access).Count -ne 1 -or
    (Get-RuleSid -Rule $keyAcl.Access[0]) -ne $userSid -or
    $keyAcl.Access[0].AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
    ($keyAcl.Access[0].FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -ne
        [Security.AccessControl.FileSystemRights]::FullControl) {
    throw 'Qdrant API key file is not restricted to the current Windows user.'
}

# Check every code and executable file for writable ACLs too.
foreach ($item in Get-ChildItem -LiteralPath $root -Recurse -Force) {
    $isPrivate = $false
    foreach ($name in $privateRoots) {
        $path = Join-Path $root $name
        if ($item.FullName -eq $path -or
            $item.FullName.StartsWith($path + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            $isPrivate = $true
            break
        }
    }
    if ($isPrivate) { continue }
    Assert-PathAcl -Path $item.FullName -Private $false
}

Write-Output 'Qdrant path and ACL preflight: PASS'
