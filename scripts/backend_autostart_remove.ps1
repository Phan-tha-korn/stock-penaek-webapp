Param(
  [string]$TaskName = "Stock Penaek Backend"
)

$ErrorActionPreference = "Stop"

try {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop | Out-Null
  Write-Host "Removed scheduled task: $TaskName"
} catch {
  Write-Host "Task not found: $TaskName"
}

