param([string]$SourceDirectory = $PSScriptRoot)

$ErrorActionPreference = 'Stop'

function Set-PrivateBackupPermissions([string]$Directory) {
    $rootItem = Get-Item -LiteralPath $Directory -Force
    if ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Backup directory must not be a link or junction'
    }
    $items = @($rootItem) + @(Get-ChildItem -LiteralPath $Directory -Recurse -Force)
    if (@($items | Where-Object {
        $_.Attributes -band [IO.FileAttributes]::ReparsePoint
    }).Count) { throw 'Backup directory contains a link or junction' }
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $system = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    foreach ($item in $items) {
        if ($item.PSIsContainer) {
            $acl = [Security.AccessControl.DirectorySecurity]::new()
            $inherit = [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
        } else {
            $acl = [Security.AccessControl.FileSecurity]::new()
            $inherit = [Security.AccessControl.InheritanceFlags]::None
        }
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($sid in @($user, $system)) {
            $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
                $sid, 'FullControl', $inherit, 'None', 'Allow'))
        }
        Set-Acl -LiteralPath $item.FullName -AclObject $acl
    }
}

$root = 'C:\ProgramData\Qinghe'
$backups = Join-Path $root 'backups'
$account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
New-Item -ItemType Directory -Force $backups | Out-Null
Set-PrivateBackupPermissions $backups
Copy-Item -LiteralPath (Join-Path $SourceDirectory 'backup-hands.ps1') `
    -Destination (Join-Path $root 'backup-hands.ps1') -Force

$body = @'
$ErrorActionPreference = 'Stop'
try {
    & ([scriptblock]::Create([IO.File]::ReadAllText('C:\ProgramData\Qinghe\backup-hands.ps1'))) *>&1 |
        Out-File -Encoding utf8 'C:\ProgramData\Qinghe\backup-last-run.log'
    exit 0
} catch {
    $_ | Out-File -Append -Encoding utf8 'C:\ProgramData\Qinghe\backup-last-run.log'
    exit 1
}
'@
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($body))
$action = New-ScheduledTaskAction `
    -Execute "$env:windir\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -Argument "-NoProfile -NonInteractive -EncodedCommand $encoded"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddHours(1) `
    -RepetitionInterval (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'Mahjong16-HandBackup' -Action $action `
    -Trigger $trigger -Principal $principal -Settings $settings -Force `
    -Description 'Hourly private SQLite backup; requires the user logged in and Docker running.' |
    Out-Null
Start-ScheduledTask -TaskName 'Mahjong16-HandBackup'
