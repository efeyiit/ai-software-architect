param(
    [Parameter(Mandatory = $true)][string]$LiteralPath,
    [switch]$RequireProtected
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $LiteralPath)) {
    throw 'Local security ACL check failed: required path is missing.'
}

function Get-AriadneSid([System.Security.Principal.IdentityReference]$Identity) {
    if ($Identity -is [System.Security.Principal.SecurityIdentifier]) {
        return $Identity.Value
    }
    return $Identity.Translate([System.Security.Principal.SecurityIdentifier]).Value
}

try {
    $currentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $acl = Get-Acl -LiteralPath $LiteralPath
    $ownerSid = Get-AriadneSid ($acl.GetOwner([System.Security.Principal.NTAccount]))
    if ($ownerSid -ne $currentSid) {
        throw 'owner differs from current Windows user'
    }
    if ($RequireProtected -and -not $acl.AreAccessRulesProtected) {
        throw 'ACL inherits permissions from its parent'
    }
    foreach ($rule in $acl.Access) {
        if ($rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) {
            continue
        }
        $ruleSid = Get-AriadneSid $rule.IdentityReference
        if ($ruleSid -notin @($currentSid, 'S-1-5-18')) {
            throw 'another account or group has access'
        }
    }
} catch {
    throw 'Local security ACL check failed. Protect the repository and local secret files for this Windows user before starting.'
}
