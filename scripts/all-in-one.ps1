Param(
  [ValidateSet("install", "start", "test", "full")]
  [string]$Action = "full",
  [string]$ApiHost = "127.0.0.1",
  [int]$ApiPort = 8000,
  [string]$BaseUrl = "",
  [string]$OutputDir = "reports/test-results"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not $BaseUrl) {
  $BaseUrl = "http://$ApiHost`:$ApiPort/api"
}

function Run-Step {
  Param(
    [string]$Name,
    [scriptblock]$Script
  )
  $start = Get-Date
  Write-Host ""
  Write-Host "==== $Name ===="
  Write-Host "Start: $($start.ToString('yyyy-MM-dd HH:mm:ss'))"
  & $Script
  $end = Get-Date
  $dur = [int](($end - $start).TotalMilliseconds)
  Write-Host "End:   $($end.ToString('yyyy-MM-dd HH:mm:ss'))"
  Write-Host "Duration(ms): $dur"
}

function Get-PythonExe {
  $py = Join-Path $Root ".venv\Scripts\python.exe"
  if (Test-Path $py) {
    return $py
  }
  return "python"
}

if ($Action -eq "install") {
  Run-Step -Name "Install Dependencies and Init DB" -Script {
    & "$Root\scripts\install.ps1" -ApiHost $ApiHost -ApiPort $ApiPort
  }
  exit 0
}

if ($Action -eq "start") {
  Run-Step -Name "Start API Server" -Script {
    & "$Root\scripts\start.ps1" -ApiHost $ApiHost -ApiPort $ApiPort
  }
  exit 0
}

if ($Action -eq "test") {
  $py = Get-PythonExe
  Run-Step -Name "Run Full System Test" -Script {
    & $py "$Root\scripts\full_system_test.py" --base-url $BaseUrl --output-dir $OutputDir --auto-start-server
  }
  exit $LASTEXITCODE
}

Run-Step -Name "Install Dependencies and Init DB" -Script {
  & "$Root\scripts\install.ps1" -ApiHost $ApiHost -ApiPort $ApiPort
}

$py = Get-PythonExe
Run-Step -Name "Run Full System Test (Auto Start Server)" -Script {
  & $py "$Root\scripts\full_system_test.py" --base-url $BaseUrl --output-dir $OutputDir --auto-start-server
}

exit $LASTEXITCODE
