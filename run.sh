#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-"$ROOT_DIR/.venv"}"
APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-5000}"
CDP_PORT="${CDP_PORT:-9222}"
CHROME_PROFILE_DIR="${CHROME_PROFILE_DIR:-"$ROOT_DIR/.pw-user-data/chrome-debug-profile"}"
APP_URL="http://$APP_HOST:$APP_PORT"
CDP_URL="http://127.0.0.1:$CDP_PORT/json/version"

cd "$ROOT_DIR"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Virtual environment not found: $VENV_DIR"
  echo "Run setup first:"
  echo "  python3 -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  python -m pip install -r requirements.txt"
  echo "  python -m playwright install chromium"
  exit 1
fi

PYTHON="$VENV_DIR/bin/python"

mkdir -p "$CHROME_PROFILE_DIR" logs

cleanup() {
  if [[ -n "${WEBAPP_PID:-}" ]] && kill -0 "$WEBAPP_PID" >/dev/null 2>&1; then
    kill "$WEBAPP_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

if curl -fsS "$APP_URL" >/dev/null 2>&1; then
  echo "Using existing webapp at $APP_URL"
  WEBAPP_PID=""
else
  echo "Starting webapp at $APP_URL ..."
  FLASK_DEBUG=0 "$PYTHON" webapp.py &
  WEBAPP_PID=$!

  for _ in {1..40}; do
    if curl -fsS "$APP_URL" >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "$WEBAPP_PID" >/dev/null 2>&1; then
      echo "webapp exited before it became ready."
      wait "$WEBAPP_PID"
      exit 1
    fi
    sleep 0.25
  done
fi

if ! curl -fsS "$APP_URL" >/dev/null 2>&1; then
  echo "webapp did not become ready at $APP_URL"
  exit 1
fi

echo "Opening Chrome with CDP on port $CDP_PORT ..."
open -na "Google Chrome" --args \
  --remote-debugging-port="$CDP_PORT" \
  --user-data-dir="$CHROME_PROFILE_DIR" \
  "$APP_URL"

for _ in {1..20}; do
  if curl -fsS "$CDP_URL" >/dev/null 2>&1; then
    echo "CDP ready: http://127.0.0.1:$CDP_PORT"
    break
  fi
  sleep 0.25
done

echo
echo "Mercari Agent is ready."
echo "Web UI: $APP_URL"
echo "CDP URL in the webapp: http://127.0.0.1:$CDP_PORT"
if [[ -n "$WEBAPP_PID" ]]; then
  echo "Press Ctrl+C here to stop the webapp."
else
  echo "The webapp was already running, so this script will exit now."
  exit 0
fi

wait "$WEBAPP_PID"
