Param(
  [string]$ApiHost = "0.0.0.0",
  [int]$ApiPort = 8000,
  [string]$Name = "Stock Penaek Backend"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$StartScript = Join-Path $Root "scripts\start.ps1"
$LogDir = Join-Path $Root "storage\logs"
$LogFile = Join-Path $LogDir "backend.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$startupDir = [Environment]::GetFolderPath("Startup")
$target = Join-Path $startupDir "$Name.cmd"

$cmd = "@echo off`r`ncd /d `"$Root`"`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -ApiHost `"$ApiHost`" -ApiPort $ApiPort *>> `"$LogFile`"`r`n"

Set-Content -Path $target -Value $cmd -Encoding ascii

Write-Host "Installed Startup item: $target"
Write-Host "Log file: $LogFile"

