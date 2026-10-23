param(
    [string]$Container = 'mahjong16-pocket-identity-1',
    [string]$ConfigDirectory = 'C:\ProgramData\Qinghe\pocket-private',
    [string]$BackupDirectory = 'C:\ProgramData\Qinghe\backups',
    [string]$ScriptPath = 'C:\ProgramData\Qinghe\backup-source\pocket-backup.py'
)
$ErrorActionPreference = 'Stop'
$env:DOCKER_CONFIG = 'C:\ProgramData\Qinghe\docker-cli'
$env:DOCKER_HOST = 'npipe:////./pipe/dockerDesktopLinuxEngine'
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
function Invoke-Docker {
    & $docker @args
    if ($LASTEXITCODE -ne 0) { throw "Docker failed: $LASTEXITCODE" }
}
foreach ($path in @($ConfigDirectory, $BackupDirectory, $ScriptPath)) {
    if ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Backup paths must not be links or junctions'
    }
}
$info = (Invoke-Docker inspect $Container | ConvertFrom-Json)[0]
$volumes = @($info.Mounts | Where-Object {
    $_.Type -eq 'volume' -and $_.Destination -eq '/app/data'
})
if ($volumes.Count -ne 1) { throw 'Expected one Pocket ID data volume' }
$image = (Invoke-Docker inspect mahjong16-pocket-web-1 | ConvertFrom-Json)[0].Image
$name = 'identity-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' +
    [guid]::NewGuid().ToString('N') + '.zip'
$helper = 'mahjong16-identity-backup-' + [guid]::NewGuid().ToString('N')
try {
    Invoke-Docker run --rm --name $helper --pull never --network none --read-only `
        --cap-drop ALL --security-opt no-new-privileges:true --user 10001:10001 `
        --memory 256m --cpus 1 --pids-limit 64 `
        --mount "type=volume,src=$($volumes[0].Name),dst=/source,readonly" `
        --mount "type=bind,src=$ConfigDirectory,dst=/private,readonly" `
        --mount "type=bind,src=$BackupDirectory,dst=/backup" `
        --mount "type=bind,src=$ScriptPath,dst=/backup-script.py,readonly" `
        $image timeout --signal=KILL 240 python /backup-script.py `
        --data /source --config /private --output "/backup/$name.partial"
} finally {
    try { & $docker rm -f $helper 2>$null | Out-Null } catch {}
}
[IO.File]::Move((Join-Path $BackupDirectory "$name.partial"),
               (Join-Path $BackupDirectory $name))
Write-Output "Verified identity backup: $BackupDirectory\$name"
# Account archives are small: keep hourly snapshots for 30 days, with a hard cap.
$files = @(Get-ChildItem -LiteralPath $BackupDirectory -File |
    Where-Object { $_.Name -match '^identity-\d{8}-\d{6}-[a-f0-9]{32}\.zip$' } |
    Sort-Object LastWriteTime -Descending)
for ($i = 0; $i -lt $files.Count; $i++) {
    if ($files[$i].Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
    if ($i -ge 744 -or $files[$i].LastWriteTime -lt (Get-Date).AddDays(-30)) {
        Remove-Item -LiteralPath $files[$i].FullName -ErrorAction Stop
    }
}
