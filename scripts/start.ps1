Param(
  [string]$ApiHost = "0.0.0.0",
  [int]$ApiPort = 8000
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$envPath = Join-Path $Root ".env"
if (Test-Path $envPath) {
  $lines = Get-Content -Path $envPath -ErrorAction Stop
  foreach ($line in $lines) {
    $s = ($line -as [string]).Trim()
    if (-not $s) { continue }
    if ($s.StartsWith("#")) { continue }
    $idx = $s.IndexOf("=")
    if ($idx -lt 1) { continue }
    $k = $s.Substring(0, $idx).Trim()
    $v = $s.Substring($idx + 1)
    if ($k) { Set-Item -Path ("env:{0}" -f $k) -Value $v }
  }
}

$hostVal = if ($PSBoundParameters.ContainsKey("ApiHost")) { $ApiHost } elseif ($env:ESP_API_HOST) { $env:ESP_API_HOST } else { "0.0.0.0" }
$portVal = if ($PSBoundParameters.ContainsKey("ApiPort")) { $ApiPort } elseif ($env:ESP_API_PORT) { [int]$env:ESP_API_PORT } else { 8000 }

if (-not (Test-Path "dist")) {
  npm run build
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  $py = "python"
}

$env:PYTHONPATH = $Root
& $py -m uvicorn server.main:app --host $hostVal --port $portVal

