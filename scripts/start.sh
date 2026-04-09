#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

API_HOST_OVERRIDE=""
API_PORT_OVERRIDE=""
SKIP_BUILD=0

log() {
  printf '[start] %s\n' "$*"
}

fail() {
  printf '[start] %s\n' "$*" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

load_env_file() {
  local env_path="$1"
  [ -f "$env_path" ] || return 0

  while IFS= read -r raw_line || [ -n "$raw_line" ]; do
    local line="$raw_line"
    line="${line%$'\r'}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -z "$line" ] && continue
    case "$line" in
      \#*) continue ;;
    esac
    if [[ "$line" != *=* ]]; then
      continue
    fi
    local key="${line%%=*}"
    local value="${line#*=}"
    key="${key//[[:space:]]/}"
    [ -z "$key" ] && continue
    if [ -z "${!key+x}" ]; then
      export "$key=$value"
    fi
  done < "$env_path"
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
  if command_exists python; then
    printf '%s\n' "python"
    return
  fi
  fail "Python was not found. Run bash ./scripts/install.sh first."
}

build_frontend_if_needed() {
  if [ "$SKIP_BUILD" -eq 1 ]; then
    return
  fi
  if [ ! -f "$ROOT_DIR/dist/index.html" ]; then
    command_exists npm || fail "npm was not found. Run bash ./scripts/install.sh first."
    log "Building frontend because dist/index.html is missing"
    npm run build
  fi
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --host)
        [ "$#" -ge 2 ] || fail "Missing value for --host"
        API_HOST_OVERRIDE="$2"
        shift 2
        ;;
      --port)
        [ "$#" -ge 2 ] || fail "Missing value for --port"
        API_PORT_OVERRIDE="$2"
        shift 2
        ;;
      --skip-build)
        SKIP_BUILD=1
        shift
        ;;
      *)
        fail "Unknown argument: $1"
        ;;
    esac
  done
}

main() {
  load_env_file "$ROOT_DIR/.env"
  parse_args "$@"

  local api_host="${API_HOST_OVERRIDE:-${ESP_API_HOST:-0.0.0.0}}"
  local api_port="${API_PORT_OVERRIDE:-${ESP_API_PORT:-8000}}"
  local python_bin
  python_bin="$(resolve_python)"

  build_frontend_if_needed

  export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
  log "Starting FastAPI on ${api_host}:${api_port}"
  exec "$python_bin" -m uvicorn server.main:app --host "$api_host" --port "$api_port"
}

main "$@"
