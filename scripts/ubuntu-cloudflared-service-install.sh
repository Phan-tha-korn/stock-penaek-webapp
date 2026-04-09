#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="stock-penaek-cloudflared"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TUNNEL_NAME="penaek-backend"
CONFIG_PATH=""
SERVICE_USER_OVERRIDE=""

log() {
  printf '[ubuntu-cloudflared] %s\n' "$*"
}

fail() {
  printf '[ubuntu-cloudflared] %s\n' "$*" >&2
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

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --tunnel-name|--cloudflare-tunnel)
        [ "$#" -ge 2 ] || fail "Missing value for $1"
        TUNNEL_NAME="$2"
        shift 2
        ;;
      --config|--cloudflare-config)
        [ "$#" -ge 2 ] || fail "Missing value for $1"
        CONFIG_PATH="$2"
        shift 2
        ;;
      --service-name)
        [ "$#" -ge 2 ] || fail "Missing value for $1"
        SERVICE_NAME="$2"
        SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
        shift 2
        ;;
      --user)
        [ "$#" -ge 2 ] || fail "Missing value for $1"
        SERVICE_USER_OVERRIDE="$2"
        shift 2
        ;;
      *)
        fail "Unknown argument: $1"
        ;;
    esac
  done
}

resolve_service_user() {
  if [ -n "$SERVICE_USER_OVERRIDE" ]; then
    printf '%s\n' "$SERVICE_USER_OVERRIDE"
    return
  fi
  if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
    printf '%s\n' "$SUDO_USER"
    return
  fi
  id -un
}

resolve_config_path() {
  local service_home="$1"
  if [ -n "$CONFIG_PATH" ]; then
    printf '%s\n' "$CONFIG_PATH"
    return
  fi
  printf '%s\n' "${service_home}/.cloudflared/config.yml"
}

write_service_file() {
  local service_user="$1"
  local service_group="$2"
  local service_home="$3"
  local tunnel_name="$4"
  local config_path="$5"
  local tmp_file
  tmp_file="$(mktemp)"

  cat >"$tmp_file" <<EOF
[Unit]
Description=Stock Penaek Cloudflare Tunnel
After=network-online.target stock-penaek.service
Wants=network-online.target

[Service]
Type=simple
User=${service_user}
Group=${service_group}
WorkingDirectory=${service_home}
Environment="HOME=${service_home}"
ExecStart=/usr/bin/env cloudflared --config ${config_path} tunnel run ${tunnel_name}
Restart=always
RestartSec=5
TimeoutStopSec=20
KillSignal=SIGINT
StandardOutput=null
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  sudo_cmd install -m 0644 "$tmp_file" "$SERVICE_FILE"
  rm -f "$tmp_file"
}

main() {
  parse_args "$@"

  command_exists systemctl || fail "systemctl was not found. This script expects Ubuntu with systemd."
  command_exists cloudflared || fail "cloudflared was not found. Install cloudflared and configure the named tunnel first."
  [ -n "$TUNNEL_NAME" ] || fail "Tunnel name is required."

  local service_user
  service_user="$(resolve_service_user)"
  local service_group
  service_group="$(id -gn "$service_user")"
  local service_home
  service_home="$(getent passwd "$service_user" | cut -d: -f6)"
  [ -n "$service_home" ] || fail "Could not resolve home directory for ${service_user}"

  local config_path
  config_path="$(resolve_config_path "$service_home")"
  [ -f "$config_path" ] || fail "Cloudflared config was not found at ${config_path}"

  log "Writing systemd service to ${SERVICE_FILE}"
  write_service_file "$service_user" "$service_group" "$service_home" "$TUNNEL_NAME" "$config_path"

  log "Reloading systemd and enabling ${SERVICE_NAME}"
  sudo_cmd systemctl daemon-reload
  sudo_cmd systemctl enable --now "$SERVICE_NAME"

  if ! sudo_cmd systemctl is-active --quiet "$SERVICE_NAME"; then
    sudo_cmd systemctl status "$SERVICE_NAME" --no-pager || true
    fail "Cloudflared service failed to start."
  fi

  log "Cloudflared autorun is ready."
  log "Service: sudo systemctl status ${SERVICE_NAME}"
  log "Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
}

main "$@"
