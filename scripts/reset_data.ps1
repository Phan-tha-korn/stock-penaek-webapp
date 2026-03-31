Param(
  [switch]$KeepReports
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$paths = @(
  ".trash-backup",
  ".auto-garbage",
  "server\db\app.db",
  "server\db\app.backup.db",
  "storage\media"
)

if (-not $KeepReports) {
  $paths += "reports"
}

foreach ($p in $paths) {
  $full = Join-Path $Root $p
  if (Test-Path $full) {
    Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Deleted: $p"
  }
}

Write-Host "Done."
