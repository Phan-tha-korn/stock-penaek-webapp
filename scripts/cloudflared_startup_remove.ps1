Param(
  [string]$Name = "Cloudflared Tunnel"
)

$ErrorActionPreference = "Stop"

$startupDir = [Environment]::GetFolderPath("Startup")
$target = Join-Path $startupDir "$Name.cmd"

if (Test-Path $target) {
  Remove-Item -LiteralPath $target -Force
  Write-Host "Removed Startup item: $target"
} else {
  Write-Host "Startup item not found: $target"
}

