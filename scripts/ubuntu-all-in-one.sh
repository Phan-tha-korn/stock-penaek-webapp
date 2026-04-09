#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="stock-penaek"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

log() {
  printf '[ubuntu-all-in-one] %s\n' "$*"
}

fail() {
  printf '[ubuntu-all-in-one] %s\n' "$*" >&2
  exit 1
}

sudo_cmd() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

read_env_value() {
  local key="$1"
  local fallback="$2"
  local env_file="$ROOT_DIR/.env"
  if [ ! -f "$env_file" ]; then
    printf '%s\n' "$fallback"
    return
  fi

  local line
  line="$(grep -E "^${key}=" "$env_file" | tail -n 1 || true)"
  if [ -z "$line" ]; then
    printf '%s\n' "$fallback"
    return
  fi
  printf '%s\n' "${line#*=}" | tr -d '\r'
}

resolve_service_user() {
  if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
    printf '%s\n' "$SUDO_USER"
    return
  fi
  id -un
}

write_service_file() {
  local service_user="$1"
  local service_group="$2"
  local service_home="$3"
  local api_port="$4"
  local tmp_file
  tmp_file="$(mktemp)"

  cat >"$tmp_file" <<EOF
[Unit]
Description=Stock Penaek FastAPI service
After=network.target

[Service]
Type=simple
User=${service_user}
Group=${service_group}
WorkingDirectory=${ROOT_DIR}
Environment="HOME=${service_home}"
Environment="PYTHONUNBUFFERED=1"
Environment="PYTHONPATH=${ROOT_DIR}"
Environment="ESP_ENV=production"
ExecStart=/usr/bin/env bash ./scripts/start.sh --host 0.0.0.0 --port ${api_port}
Restart=always
RestartSec=5
TimeoutStopSec=20
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
EOF

  sudo_cmd install -m 0644 "$tmp_file" "$SERVICE_FILE"
  rm -f "$tmp_file"
}

wait_for_health() {
  local api_port="$1"
  local attempts=30
  local url="http://127.0.0.1:${api_port}/api/health"

  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

main() {
  command_exists systemctl || fail "systemctl was not found. This script expects Ubuntu with systemd."
  command_exists curl || true

  bash "$ROOT_DIR/scripts/install.sh"

  local service_user
  service_user="$(resolve_service_user)"
  local service_group
  service_group="$(id -gn "$service_user")"
  local service_home
  service_home="$(getent passwd "$service_user" | cut -d: -f6)"
  local api_port
  api_port="$(read_env_value "ESP_API_PORT" "8000")"

  log "Writing systemd service to ${SERVICE_FILE}"
  write_service_file "$service_user" "$service_group" "$service_home" "$api_port"

  log "Reloading systemd and enabling ${SERVICE_NAME}"
  sudo_cmd systemctl daemon-reload
  sudo_cmd systemctl enable --now "$SERVICE_NAME"

  log "Waiting for API health check"
  if ! wait_for_health "$api_port"; then
    sudo_cmd systemctl status "$SERVICE_NAME" --no-pager || true
    fail "Service started but health check did not become ready in time."
  fi

  log "Ubuntu autorun setup completed."
  log "App URL: http://127.0.0.1:${api_port}/"
  log "Status: sudo systemctl status ${SERVICE_NAME}"
  log "Logs:   sudo journalctl -u ${SERVICE_NAME} -f"
  log "Remove: bash ./scripts/ubuntu-service-remove.sh"
}

main "$@"
