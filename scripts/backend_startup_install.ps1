Param(
  [string]$ApiHost = "0.0.0.0",
  [int]$ApiPort = 8000,
  [string]$Name = "Stock Penaek Backend"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root "storage\logs"
$LogFile = Join-Path $LogDir "backend.log"
$StartCmd = Join-Path $Root "start-server.cmd"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$startupDir = [Environment]::GetFolderPath("Startup")
$target = Join-Path $startupDir "$Name.cmd"

$cmd = "@echo off`r`ncd /d `"$Root`"`r`necho [%date% %time%] starting backend >> `"$LogFile`"`r`n:loop`r`ncall `"$StartCmd`" -ApiHost `"$ApiHost`" -ApiPort $ApiPort >> `"$LogFile`" 2>>&1`r`necho [%date% %time%] backend exited, restarting in 5s >> `"$LogFile`"`r`ntimeout /t 5 /nobreak >nul`r`ngoto loop`r`n"

Set-Content -Path $target -Value $cmd -Encoding ascii

Write-Host "Installed Startup item: $target"
Write-Host "Log file: $LogFile"
