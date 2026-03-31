Param(
  [string]$ApiHost = "0.0.0.0",
  [int]$ApiPort = 8000,
  [string]$TaskName = "Stock Penaek Backend",
  [switch]$RunHighest
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$StartScript = Join-Path $Root "scripts\start.ps1"
$LogDir = Join-Path $Root "storage\logs"
$LogFile = Join-Path $LogDir "backend.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$cmd = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -ApiHost `"$ApiHost`" -ApiPort $ApiPort *>> `"$LogFile`""

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $cmd"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$runLevel = "Limited"
if ($RunHighest) { $runLevel = "Highest" }
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel $runLevel

try {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
} catch {}

try {
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
} catch {
  if (-not $RunHighest -and (($_.Exception.Message -like "*Access is denied*") -or (($_ | Out-String) -like "*0x80070005*"))) {
    Write-Host "Access denied. Try running as Administrator, or re-run with -RunHighest from an elevated terminal."
  }
  throw
}

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Backend command: $cmd"
Write-Host "Log file: $LogFile"
