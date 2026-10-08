param(
    [string]$SourceDirectory = (Join-Path $PSScriptRoot '../../deploy/windows'),
    [string]$Image = 'mahjong16:7c16004'
)

$ErrorActionPreference = 'Stop'
$env:DOCKER_CONFIG = 'C:\ProgramData\Qinghe\docker-cli'
$env:DOCKER_HOST = 'npipe:////./pipe/dockerDesktopLinuxEngine'
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
# Load only the actual functions, without running the installer or backing up production.
foreach ($file in @('install-backup.ps1', 'backup-hands.ps1')) {
    $tokens = $null
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $SourceDirectory $file), [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw "Parse failed: $file" }
    foreach ($function in $ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst]
    }, $false)) {
        . ([scriptblock]::Create($function.Extent.Text))
    }
}

$directory = Join-Path 'C:\ProgramData\Qinghe' ('backup-review-' + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory $directory | Out-Null
    $child = Join-Path $directory 'existing.sqlite3'
    Set-Content -LiteralPath $child -Value 'fixture'
    foreach ($path in @($directory, $child)) {
        & icacls.exe $path /grant '*S-1-5-32-545:R' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Fixture ACL failed' }
    }
    Set-PrivateBackupPermissions $directory
    $allowed = @('S-1-5-18', [Security.Principal.WindowsIdentity]::GetCurrent().User.Value)
    foreach ($path in @($directory, $child)) {
        $acl = Get-Acl -LiteralPath $path
        $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
        if (-not $acl.AreAccessRulesProtected -or $rules.Count -ne 2) {
            throw 'Expected protected ACL with exactly two rules'
        }
        foreach ($rule in $rules) {
            if ($rule.IdentityReference.Value -notin $allowed -or
                $rule.AccessControlType -ne 'Allow' -or
                $rule.FileSystemRights -ne 'FullControl') { throw 'Unexpected ACL' }
        }
    }
    # New backup files must inherit the restricted directory permissions.
    $newFile = Join-Path $directory 'new.sqlite3'
    Set-Content -LiteralPath $newFile -Value 'fixture'
    foreach ($rule in (Get-Acl $newFile).GetAccessRules(
        $true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($rule.IdentityReference.Value -notin $allowed) { throw 'Unsafe inherited ACL' }
    }
    Write-Output 'PASS: existing broad directory/file grants removed; new files inherit private ACL'

    $before = @(Invoke-Docker ps -aq --filter 'name=mahjong16-hand-backup-')
    $failed = $false
    try {
        Invoke-BackupHelper $Image timeout --signal=KILL 1 python -c "__import__('time').sleep(30)"
    } catch { $failed = $true }
    if (-not $failed) { throw 'Timed-out helper incorrectly reported success' }
    $after = @(Invoke-Docker ps -aq --filter 'name=mahjong16-hand-backup-')
    if (@($after | Where-Object { $_ -notin $before }).Count) {
        throw 'Timed-out helper was left behind'
    }
    Write-Output 'PASS: helper deadline returns failure and removes container'

    # A killed Docker client cannot run finally; the in-container watchdog must survive it.
    $helper = 'mahjong-backup-client-test-' + [guid]::NewGuid().ToString('N')
    try {
        $arguments = "run --rm --name $helper --network none --read-only --cap-drop ALL " +
            "--security-opt no-new-privileges:true --user 10001:10001 --memory 64m " +
            "--pids-limit 16 $Image timeout --signal=KILL 5 python -c __import__('time').sleep(30)"
        $client = Start-Process -FilePath $docker -ArgumentList $arguments `
            -PassThru -WindowStyle Hidden
        $running = @()
        for ($i = 0; $i -lt 10 -and -not $running.Count; $i++) {
            Start-Sleep -Milliseconds 200
            $running = @(Invoke-Docker ps -q --filter "name=^/$helper`$")
        }
        if (-not $running.Count) { throw 'Watchdog test container did not start' }
        Stop-Process -Id $client.Id -Force
        for ($i = 0; $i -lt 16 -and $running.Count; $i++) {
            Start-Sleep -Milliseconds 500
            $running = @(Invoke-Docker ps -aq --filter "name=^/$helper`$")
        }
        if ($running.Count) { throw 'Helper survived its deadline after client termination' }
        Write-Output 'PASS: forcibly killed client still leaves no helper after its deadline'
    } finally {
        try { & $docker rm -f $helper 2>$null | Out-Null } catch {}
    }
} finally {
    Remove-Item -LiteralPath $directory -Recurse -Force
}
