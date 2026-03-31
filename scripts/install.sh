#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

require_cmd() {
  local c="$1"
  if ! command -v "$c" >/dev/null 2>&1; then
    echo "Missing dependency: $c"
    return 1
  fi
  return 0
}

ensure_node() {
  if require_cmd node && require_cmd npm; then
    return 0
  fi
  if command -v winget >/dev/null 2>&1; then
    winget install -e --id OpenJS.NodeJS.LTS || true
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y nodejs npm
  fi
  require_cmd node && require_cmd npm
}

ensure_python() {
  if require_cmd python && python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"; then
    return 0
  fi
  if command -v winget >/dev/null 2>&1; then
    winget install -e --id Python.Python.3.12 || true
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip
  fi
  require_cmd python
  python -c "import sys; assert sys.version_info >= (3,10)"
}

ensure_git() {
  if require_cmd git; then
    return 0
  fi
  if command -v winget >/dev/null 2>&1; then
    winget install -e --id Git.Git || true
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y git
  fi
  require_cmd git
}

check_files() {
  local missing=0
  for f in "package.json" "server/main.py" "server/requirements.txt" "config.json"; do
    if [ ! -f "$ROOT_DIR/$f" ]; then
      echo "Missing required file: $f"
      missing=1
    fi
  done
  if [ "$missing" -ne 0 ]; then
    exit 1
  fi
}

generate_env_template() {
  if [ ! -f "$ROOT_DIR/.env" ]; then
    cat >"$ROOT_DIR/.env" <<'ENV'
ESP_ENV=development
ESP_DATABASE_URL=
ESP_REDIS_URL=
ESP_API_PORT=8000
ESP_WEB_URL=http://localhost:8000/
ENV
  fi
}

generate_secrets() {
  python - <<'PY'
import json, secrets, pathlib
root = pathlib.Path(__file__).resolve().parents[1]
path = root / "config.json"
cfg = json.loads(path.read_text(encoding="utf-8"))
if not cfg.get("jwt_secret") or cfg.get("jwt_secret") == "CHANGE_ME_IN_INSTALLER":
  cfg["jwt_secret"] = secrets.token_urlsafe(48)
if not cfg.get("login_secret_phrase") or cfg.get("login_secret_phrase") == "CHANGE_ME_IN_INSTALLER":
  cfg["login_secret_phrase"] = secrets.token_urlsafe(16)
path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Updated config.json secrets.")
PY
}

install_deps() {
  echo "Installing npm dependencies..."
  npm install

  echo "Setting up Python venv..."
  if [ ! -d ".venv" ]; then
    python -m venv .venv
  fi
  if [ -f ".venv/bin/activate" ]; then
    source ".venv/bin/activate"
  fi
  python -m pip install --upgrade pip
  python -m pip install -r server/requirements.txt
}

init_db() {
  echo "Initializing database + seed demo data..."
  PYTHONPATH="$ROOT_DIR" python - <<'PY'
import asyncio
from server.db.init_db import create_all
from server.db.database import SessionLocal
from server.db.init_db import seed_if_empty
async def main():
  await create_all()
  async with SessionLocal() as db:
    await seed_if_empty(db)
asyncio.run(main())
PY
}

health_check() {
  echo "Running health check..."
  python - <<'PY'
import sys, urllib.request
try:
  urllib.request.urlopen("http://localhost:8000/api/health", timeout=3).read()
  print("OK")
  sys.exit(0)
except Exception as e:
  print("FAILED:", e)
  sys.exit(1)
PY
}

ensure_git
ensure_python
ensure_node
check_files
generate_env_template
generate_secrets
install_deps
init_db

echo "Launching production server..."
bash "$ROOT_DIR/scripts/start.sh" &
sleep 2
health_check || true
echo "Dashboard URL: http://localhost:8000/"
if command -v npx >/dev/null 2>&1; then
  npx qrcode-terminal "http://localhost:8000/" || true
fi

