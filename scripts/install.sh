#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APT_UPDATED=0

log() {
  printf '[install] %s\n' "$*"
}

fail() {
  printf '[install] %s\n' "$*" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

sudo_cmd() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

apt_update_once() {
  if [ "$APT_UPDATED" -eq 0 ]; then
    sudo_cmd apt-get update -y
    APT_UPDATED=1
  fi
}

install_apt_packages() {
  apt_update_once
  sudo_cmd apt-get install -y "$@"
}

require_file() {
  local path="$1"
  [ -f "$ROOT_DIR/$path" ] || fail "Missing required file: $path"
}

node_is_recent() {
  if ! command_exists node || ! command_exists npm; then
    return 1
  fi
  local major
  major="$(node -p "process.versions.node.split('.')[0]" 2>/dev/null || echo 0)"
  [ "${major:-0}" -ge 18 ]
}

python_is_recent() {
  command_exists python3 && python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
}

run_nodesource_setup() {
  if [ "$(id -u)" -eq 0 ]; then
    bash -
  else
    sudo -E bash -
  fi
}

ensure_base_packages() {
  if ! command_exists apt-get; then
    fail "This Linux installer currently targets Ubuntu/Debian systems with apt-get."
  fi
  install_apt_packages ca-certificates curl git python3 python3-venv python3-pip
}

ensure_python() {
  if python_is_recent; then
    return
  fi
  ensure_base_packages
  python_is_recent || fail "Python 3.10+ is required."
}

ensure_node() {
  if node_is_recent; then
    return
  fi
  ensure_base_packages
  install_apt_packages gnupg
  curl -fsSL https://deb.nodesource.com/setup_20.x | run_nodesource_setup
  install_apt_packages nodejs
  node_is_recent || fail "Node.js 18+ installation failed."
}

resolve_python() {
  if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    printf '%s\n' "$ROOT_DIR/.venv/bin/python"
    return
  fi
  if command_exists python3; then
    printf '%s\n' "python3"
    return
  fi
  printf '%s\n' "python"
}

ensure_env_file() {
  ROOT_DIR="$ROOT_DIR" python3 - <<'PY'
from pathlib import Path
import os

root = Path(os.environ["ROOT_DIR"])
path = root / ".env"
defaults = {
    "ESP_ENV": "production",
    "ESP_API_HOST": "0.0.0.0",
    "ESP_API_PORT": "8000",
    "ESP_DATABASE_URL": "",
    "ESP_REDIS_URL": "",
    "ESP_WEB_URL": "http://127.0.0.1:8000/",
}

existing: dict[str, str] = {}
if path.exists():
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        existing[key.strip()] = value.strip()

for key, value in defaults.items():
    existing.setdefault(key, value)

ordered_keys = list(defaults.keys()) + sorted(k for k in existing if k not in defaults)
lines = [f"{key}={existing[key]}" for key in ordered_keys]
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

ensure_config_secrets() {
  ROOT_DIR="$ROOT_DIR" python3 - <<'PY'
import json
import os
import secrets
from pathlib import Path

path = Path(os.environ["ROOT_DIR"]) / "config.json"
cfg = json.loads(path.read_text(encoding="utf-8"))

if not cfg.get("jwt_secret") or cfg.get("jwt_secret") == "CHANGE_ME_IN_INSTALLER":
    cfg["jwt_secret"] = secrets.token_urlsafe(48)

if cfg.get("login_secret_phrase") == "CHANGE_ME_IN_INSTALLER":
    cfg["login_secret_phrase"] = ""

path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

install_dependencies() {
  local python_bin
  python_bin="$(resolve_python)"

  log "Installing frontend dependencies"
  npm install --no-fund --no-audit

  log "Creating Python virtual environment"
  if [ ! -d "$ROOT_DIR/.venv" ]; then
    python3 -m venv "$ROOT_DIR/.venv"
  fi
  python_bin="$(resolve_python)"

  log "Installing backend dependencies"
  "$python_bin" -m pip install --upgrade pip
  "$python_bin" -m pip install -r "$ROOT_DIR/server/requirements.txt"

  log "Building frontend"
  npm run build
}

init_db() {
  local python_bin
  python_bin="$(resolve_python)"

  log "Initializing database and seed data"
  PYTHONPATH="$ROOT_DIR" "$python_bin" - <<'PY'
import asyncio

from server.db.database import SessionLocal
from server.db.init_db import create_all, seed_if_empty
from server.services.attachments import ensure_attachment_type_classifications
from server.services.branches import bootstrap_branch_foundations
from server.services.suppliers import bootstrap_supplier_foundations


async def main() -> None:
    await create_all()
    async with SessionLocal() as db:
        await seed_if_empty(db)
        await bootstrap_branch_foundations(db)
        await ensure_attachment_type_classifications(db)
        await bootstrap_supplier_foundations(db)
        await db.commit()


asyncio.run(main())
PY
}

main() {
  require_file "package.json"
  require_file "server/main.py"
  require_file "server/requirements.txt"
  require_file "config.json"

  ensure_python
  ensure_node
  ensure_env_file
  ensure_config_secrets
  install_dependencies
  init_db

  log "Install completed successfully."
  log "Manual start command: bash ./scripts/start.sh"
}

main "$@"
