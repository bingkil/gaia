#!/usr/bin/env bash
# Start, stop, or restart the GAIA backend + frontend dev servers.
#
# Usage:
#   scripts/dev.sh start   [--port 8000] [--backend-only] [--frontend-only]
#   scripts/dev.sh stop
#   scripts/dev.sh restart [--port 8000] [--backend-only] [--frontend-only]
#
# The backend port is auto-bumped past anything already listening, starting
# from --port. The frontend always asks Vite for its own port (5173, bumped
# by Vite itself if that is taken) and is pointed at wherever the backend
# landed via GAIA_API. PIDs and the chosen ports are recorded in
# .dev/dev-pids so `stop`/`restart` can find and fully tear down both process
# trees, plus anything left listening on a previously used port.

set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
state_dir="$root/.dev"
pid_file="$state_dir/dev-pids"
mkdir -p "$state_dir"

action="${1:-start}"
shift || true

port=8000
backend_only=false
frontend_only=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) port="$2"; shift 2 ;;
    --backend-only) backend_only=true; shift ;;
    --frontend-only) frontend_only=true; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

port_in_use() { nc -z 127.0.0.1 "$1" >/dev/null 2>&1; }

find_free_port() {
  local p=$1
  while port_in_use "$p"; do p=$((p + 1)); done
  echo "$p"
}

# Post-order kill: children first, in case the parent respawns them on TERM.
# `npm run dev` in particular fans out through the npm shim into the real
# node/vite process, so killing just the top PID would leave that orphaned.
kill_tree() {
  local target=$1
  local child
  for child in $(pgrep -P "$target" 2>/dev/null || true); do
    kill_tree "$child"
  done
  kill "$target" 2>/dev/null || true
}

wait_dead() {
  local target=$1
  for _ in 1 2 3 4 5; do
    kill -0 "$target" 2>/dev/null || return 0
    sleep 0.3
  done
  kill -9 "$target" 2>/dev/null || true
}

pids_listening_on() {
  lsof -ti tcp:"$1" -sTCP:LISTEN 2>/dev/null || true
}

stop_dev() {
  local stopped=false
  local ports=(8000 5173)

  if [[ -f "$pid_file" ]]; then
    ports=()
    while read -r name value; do
      case "$name" in
        backend|frontend)
          if [[ -n "$value" ]] && kill -0 "$value" 2>/dev/null; then
            echo "==> Stopping $name tree (PID $value)"
            kill_tree "$value"
            wait_dead "$value"
            stopped=true
          fi
          ;;
        port|frontend_port) ports+=("$value") ;;
      esac
    done < "$pid_file"
    rm -f "$pid_file"
    [[ ${#ports[@]} -eq 0 ]] && ports=(8000 5173)
  fi

  local p listener
  for p in "${ports[@]}"; do
    for listener in $(pids_listening_on "$p"); do
      echo "==> Stopping stray listener on port $p (PID $listener)"
      kill_tree "$listener"
      wait_dead "$listener"
      stopped=true
    done
  done

  if [[ "$stopped" == true ]]; then echo "==> Stopped"; else echo "==> Nothing was running"; fi
}

start_dev() {
  cd "$root"
  : > "$pid_file"
  local backend_port frontend_port=""

  if [[ "$frontend_only" != true ]]; then
    backend_port=$(find_free_port "$port")
    echo "==> Starting backend on http://127.0.0.1:$backend_port"
    nohup uv run gaia serve --port "$backend_port" > "$state_dir/backend.log" 2>&1 &
    echo "backend $!" >> "$pid_file"
    echo "port $backend_port" >> "$pid_file"
  else
    backend_port="$port"
  fi

  if [[ "$backend_only" != true ]]; then
    echo "==> Starting frontend (Vite picks its own port, bumping past 5173 if busy)"
    (
      cd web
      GAIA_API="http://127.0.0.1:$backend_port" nohup npm run dev > "$state_dir/frontend.log" 2>&1 &
      echo "frontend $!" >> "$pid_file"
    )

    for _ in 1 2 3 4 5 6 7 8 9 10; do
      sleep 0.5
      if [[ -f "$state_dir/frontend.log" ]]; then
        frontend_port=$(grep -oE "Local:[[:space:]]+http://localhost:[0-9]+" "$state_dir/frontend.log" | grep -oE "[0-9]+$" | head -1 || true)
        [[ -n "$frontend_port" ]] && break
      fi
    done
    [[ -n "$frontend_port" ]] && echo "frontend_port $frontend_port" >> "$pid_file"
  fi

  echo "==> Backend log:  $state_dir/backend.log"
  [[ "$frontend_only" != true ]] && echo "==> Backend:      http://127.0.0.1:$backend_port"
  if [[ "$backend_only" != true ]]; then
    echo "==> Frontend log: $state_dir/frontend.log"
    if [[ -n "$frontend_port" ]]; then
      echo "==> Frontend:     http://localhost:$frontend_port"
    else
      echo "==> Frontend:     check $state_dir/frontend.log for the URL"
    fi
  fi
}

case "$action" in
  start) start_dev ;;
  stop) stop_dev ;;
  restart) stop_dev; sleep 1; start_dev ;;
  *) echo "Usage: $0 {start|stop|restart} [--port N] [--backend-only|--frontend-only]" >&2; exit 1 ;;
esac
