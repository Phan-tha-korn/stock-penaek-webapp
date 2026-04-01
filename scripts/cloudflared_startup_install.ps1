Param(
  [string]$TunnelName = "penaek-backend",
  [string]$Name = "Cloudflared Tunnel"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root "storage\logs"
$LogFile = Join-Path $LogDir "cloudflared.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$exe = (Get-Command cloudflared -ErrorAction Stop).Source
$exeEsc = $exe.Replace('"', '""')

$startupDir = [Environment]::GetFolderPath("Startup")
$target = Join-Path $startupDir "$Name.cmd"

$cmd = "@echo off`r`ncd /d `"$Root`"`r`necho [%date% %time%] starting cloudflared tunnel $TunnelName >> `"$LogFile`"`r`ntimeout /t 10 /nobreak >nul`r`n:loop`r`n`"$exeEsc`" tunnel run $TunnelName >> `"$LogFile`" 2>>&1`r`necho [%date% %time%] cloudflared exited, restarting in 5s >> `"$LogFile`"`r`ntimeout /t 5 /nobreak >nul`r`ngoto loop`r`n"

Set-Content -Path $target -Value $cmd -Encoding ascii

Write-Host "Installed Startup item: $target"
Write-Host "Log file: $LogFile"
