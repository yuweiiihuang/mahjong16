param([string]$Source = (Join-Path $PSScriptRoot '../../deploy/windows/backup-hands.ps1'))

$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    $Source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Backup script failed to parse' }
$function = $ast.Find({ param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Get-ExpiredHandBackup'
}, $false)
. ([scriptblock]::Create($function.Extent.Text))
$directory = Join-Path ([IO.Path]::GetTempPath()) ('backup-retention-' + [guid]::NewGuid())
try {
    New-Item -ItemType Directory $directory | Out-Null
    $now = [datetime]'2026-10-11T12:00:00'
    $keep = @('20261011-110000', '20261009-120000', '20261008-230000',
        '20261007-180000', '20260911-120000', '20261012-120000')
    $expire = @('20261008-090000', '20261007-080000', '20260911-115959',
        '20260910-230000')
    foreach ($stamp in $keep + $expire) {
        Set-Content (Join-Path $directory ("hands-$stamp-" + ('a' * 32) + '.sqlite3')) 'fixture'
    }
    foreach ($name in @('other.sqlite3', 'hands-invalid.sqlite3',
        ('hands-20261301-120000-' + ('a' * 32) + '.sqlite3'),
        ('hands-20260901-120000-' + ('a' * 32) + '.sqlite3.partial'))) {
        Set-Content (Join-Path $directory $name) 'fixture'
    }
    $removed = @(Get-ExpiredHandBackup $directory $now)
    if ($removed.Count -ne $expire.Count) { throw 'Unexpected expired backup count' }
    foreach ($stamp in $expire) {
        if ("hands-$stamp-$('a' * 32).sqlite3" -notin $removed.Name) {
            throw "Missing expired backup: $stamp"
        }
    }
    foreach ($file in $removed) { Remove-Item -LiteralPath $file.FullName }
    if (@(Get-ExpiredHandBackup $directory $now).Count) { throw 'Cleanup is not idempotent' }
    Write-Output 'PASS: 48-hour copies, daily copies, 30-day boundary and unrelated files'
} finally {
    Remove-Item -LiteralPath $directory -Recurse -Force
}
