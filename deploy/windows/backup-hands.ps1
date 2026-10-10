param(
    [string]$Container = 'mahjong16-docker-617094b-web-1',
    [string]$BackupDirectory = 'C:\ProgramData\Qinghe\backups'
)

$ErrorActionPreference = 'Stop'
$env:DOCKER_CONFIG = 'C:\ProgramData\Qinghe\docker-cli'
$env:DOCKER_HOST = 'npipe:////./pipe/dockerDesktopLinuxEngine'
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"

function Invoke-Docker {
    & $docker @args
    if ($LASTEXITCODE -ne 0) { throw "Docker failed: $LASTEXITCODE" }
}

function Invoke-BackupHelper {
    $helper = 'mahjong16-hand-backup-' + [guid]::NewGuid().ToString('N')
    try {
        Invoke-Docker run --rm --name $helper --pull never --network none `
            --read-only --cap-drop ALL --security-opt no-new-privileges:true `
            --user 10001:10001 --memory 256m --cpus 1 --pids-limit 64 @args
    } finally {
        # --rm handles normal exit; remove a running helper after a client-side error.
        try { & $docker rm -f $helper 2>$null | Out-Null } catch {}
    }
}

function Get-ExpiredHandBackup([string]$Directory, [datetime]$Now = (Get-Date)) {
    if ((Get-Item -LiteralPath $Directory).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Backup directory must not be a link or junction'
    }
    $daily = @{}
    foreach ($file in Get-ChildItem -LiteralPath $Directory -File | Sort-Object Name -Descending) {
        if ($file.Name -notmatch '^hands-(\d{8}-\d{6})-[a-f0-9]{32}\.sqlite3$' -or
            ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) { continue }
        $created = [datetime]::MinValue
        if (-not [datetime]::TryParseExact($Matches[1], 'yyyyMMdd-HHmmss',
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::None, [ref]$created)) { continue }
        if ($created -ge $Now.AddHours(-48)) { continue }
        $day = $created.ToString('yyyyMMdd')
        if ($created -ge $Now.AddDays(-30) -and -not $daily.ContainsKey($day)) {
            $daily[$day] = $true
            continue
        }
        $file
    }
}

$info = (Invoke-Docker inspect $Container | ConvertFrom-Json)[0]
$records = @($info.Mounts | Where-Object {
    $_.Type -eq 'volume' -and $_.Destination -eq '/var/lib/mahjong16'
})
if ($records.Count -ne 1) { throw 'Expected exactly one hand-records volume' }
if (-not (Test-Path -LiteralPath $BackupDirectory -PathType Container)) {
    throw 'Create and restrict the backup directory before running this script'
}

$name = 'hands-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' +
    [guid]::NewGuid().ToString('N') + '.sqlite3'
$pending = $name + '.partial'
# The helper gets read-only records and a separate output folder, never the passcode.
$check = "import sqlite3,sys; c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); assert c.execute('PRAGMA integrity_check').fetchone()==('ok',)"
Invoke-BackupHelper `
    --mount "type=volume,src=$($records[0].Name),dst=/var/lib/mahjong16,readonly" `
    --mount "type=bind,src=$BackupDirectory,dst=/backup" `
    $info.Image timeout --signal=KILL 240 python -m app.replay backup "/backup/$pending" `
    --db /var/lib/mahjong16/hands.sqlite3

Invoke-BackupHelper `
    --mount "type=bind,src=$BackupDirectory,dst=/backup,readonly" `
    $info.Image timeout --signal=KILL 240 python -c $check "/backup/$pending"

[IO.File]::Move((Join-Path $BackupDirectory $pending), (Join-Path $BackupDirectory $name))
Write-Output "Verified backup: $BackupDirectory\$name"
# Only prune completed backups after the new snapshot passes integrity verification.
foreach ($file in Get-ExpiredHandBackup $BackupDirectory) {
    Remove-Item -LiteralPath $file.FullName -ErrorAction Stop
    Write-Output "Removed expired backup: $($file.Name)"
}
