#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="stock-penaek"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

log() {
  printf '[ubuntu-remove] %s\n' "$*"
}

sudo_cmd() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

if command -v systemctl >/dev/null 2>&1; then
  sudo_cmd systemctl disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
  sudo_cmd rm -f "$SERVICE_FILE"
  sudo_cmd systemctl daemon-reload
  log "Removed ${SERVICE_NAME} systemd service."
else
  log "systemctl was not found. Nothing to remove."
fi
