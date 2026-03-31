#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/server.log"
API_PORT="${ESP_API_PORT:-8000}"
WEB_URL="${ESP_WEB_URL:-http://localhost:8000/}"

MAX_RESTARTS=3
RESTARTS=0

log() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

health_check() {
  python - <<'PY'
import sys, urllib.request
try:
  urllib.request.urlopen("http://localhost:8000/api/health", timeout=3).read()
  sys.exit(0)
except Exception:
  sys.exit(1)
PY
}

build_frontend_if_needed() {
  if [ ! -d "$ROOT_DIR/dist" ]; then
    log "Building frontend..."
    (cd "$ROOT_DIR" && npm run build) >>"$LOG_FILE" 2>&1
  fi
}

start_api() {
  log "Starting API on port $API_PORT..."
  (cd "$ROOT_DIR" && PYTHONPATH="$ROOT_DIR" python -m uvicorn server.main:app --host 0.0.0.0 --port "$API_PORT") >>"$LOG_FILE" 2>&1 &
  echo $!
}

build_frontend_if_needed

API_PID="$(start_api)"
log "API PID=$API_PID"

sleep 1
if health_check; then
  log "Health check OK: $WEB_URL"
  if command -v npx >/dev/null 2>&1; then
    (cd "$ROOT_DIR" && npx qrcode-terminal "$WEB_URL") || true
  fi
else
  log "Health check failed"
fi

while true; do
  sleep 60
  if ! kill -0 "$API_PID" >/dev/null 2>&1; then
    RESTARTS=$((RESTARTS + 1))
    log "API crashed. Restart attempt $RESTARTS/$MAX_RESTARTS"
    if [ "$RESTARTS" -gt "$MAX_RESTARTS" ]; then
      log "Restart failed. Please check logs."
      exit 1
    fi
    API_PID="$(start_api)"
  fi
done

