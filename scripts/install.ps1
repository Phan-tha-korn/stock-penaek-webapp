Param(
  [string]$ApiHost = "0.0.0.0",
  [int]$ApiPort = 8000
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Require-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Missing dependency: $name"
  }
}

function Assert-LastExitCode {
  Param(
    [string]$Step
  )
  if ($LASTEXITCODE -ne 0) {
    throw "$Step failed with exit code $LASTEXITCODE"
  }
}

function New-SecureToken {
  Param(
    [int]$Bytes = 48
  )
  $buf = New-Object byte[] $Bytes
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $rng.GetBytes($buf)
  $rng.Dispose()

  $b64 = [Convert]::ToBase64String($buf)
  return $b64.TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Read-DotEnv {
  Param(
    [string]$Path
  )
  $map = @{}
  if (-not (Test-Path $Path)) {
    return $map
  }

  $lines = Get-Content -Path $Path -ErrorAction Stop
  foreach ($line in $lines) {
    $s = ($line -as [string]).Trim()
    if (-not $s) { continue }
    if ($s.StartsWith("#")) { continue }
    $idx = $s.IndexOf("=")
    if ($idx -lt 1) { continue }
    $k = $s.Substring(0, $idx).Trim()
    $v = $s.Substring($idx + 1)
    if ($k) { $map[$k] = $v }
  }
  return $map
}

function Write-DotEnv {
  Param(
    [string]$Path,
    [hashtable]$Values
  )
  $keys = $Values.Keys | Sort-Object
  $out = New-Object System.Collections.Generic.List[string]
  foreach ($k in $keys) {
    $out.Add("$k=$($Values[$k])")
  }
  Set-Content -Path $Path -Value $out -Encoding utf8
}

function Normalize-RequirementsFile {
  Param(
    [string]$Path
  )
  if (-not (Test-Path $Path)) { return }
  $bytes = [System.IO.File]::ReadAllBytes($Path)
  $hasNull = $false
  foreach ($b in $bytes) {
    if ($b -eq 0) {
      $hasNull = $true
      break
    }
  }
  if (-not $hasNull) { return }
  $text = [System.Text.Encoding]::Unicode.GetString($bytes)
  [System.IO.File]::WriteAllText($Path, $text, [System.Text.UTF8Encoding]::new($false))
  Write-Host "Normalized requirements encoding to UTF-8: $Path"
}

Require-Command "node"
Require-Command "npm"
Require-Command "python"

$envPath = Join-Path $Root ".env"
$envMap = Read-DotEnv -Path $envPath

if (-not $envMap.ContainsKey("ESP_ENV")) { $envMap["ESP_ENV"] = "development" }
if (-not $envMap.ContainsKey("ESP_DATABASE_URL")) { $envMap["ESP_DATABASE_URL"] = "" }
if (-not $envMap.ContainsKey("ESP_REDIS_URL")) { $envMap["ESP_REDIS_URL"] = "" }
if (-not $envMap.ContainsKey("ESP_API_HOST")) { $envMap["ESP_API_HOST"] = $ApiHost }
if (-not $envMap.ContainsKey("ESP_API_PORT")) { $envMap["ESP_API_PORT"] = "$ApiPort" }
if (-not $envMap.ContainsKey("ESP_WEB_URL")) { $envMap["ESP_WEB_URL"] = "http://localhost:$ApiPort/" }

if (-not $envMap.ContainsKey("ESP_JWT_SECRET") -or -not $envMap["ESP_JWT_SECRET"] -or $envMap["ESP_JWT_SECRET"] -eq "CHANGE_ME") {
  $envMap["ESP_JWT_SECRET"] = New-SecureToken -Bytes 48
}
if (-not $envMap.ContainsKey("ESP_LOGIN_SECRET_PHRASE") -or $envMap["ESP_LOGIN_SECRET_PHRASE"] -eq "CHANGE_ME") {
  $envMap["ESP_LOGIN_SECRET_PHRASE"] = New-SecureToken -Bytes 16
}

Write-DotEnv -Path $envPath -Values $envMap

npm install
Assert-LastExitCode "npm install"

if (-not (Test-Path ".venv")) {
  python -m venv .venv
  Assert-LastExitCode "python -m venv .venv"
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
Assert-LastExitCode "pip install --upgrade pip"
Normalize-RequirementsFile -Path (Join-Path $Root "server\requirements.txt")
& $py -m pip install -r "server\requirements.txt"
Assert-LastExitCode "pip install -r server\\requirements.txt"

$env:PYTHONPATH = $Root
$initCode = @(
  "import asyncio",
  "from server.db.init_db import create_all, seed_if_empty",
  "from server.db.database import SessionLocal",
  "async def main():",
  "    await create_all()",
  "    async with SessionLocal() as db:",
  "        await seed_if_empty(db)",
  "asyncio.run(main())",
  "print('DB initialized.')"
) -join "`n"
& $py -c $initCode
Assert-LastExitCode "database init"

Write-Host "Done."
Write-Host "Start: .\scripts\start.ps1 -ApiHost `"$ApiHost`" -ApiPort $ApiPort"

