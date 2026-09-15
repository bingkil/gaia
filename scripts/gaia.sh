#!/usr/bin/env bash
# Start, stop, or restart a packaged GAIA release build, for end users who
# just want to run the app rather than do frontend/backend development. This
# is a single self-contained process serving both the API and the built UI on
# one port - see scripts/dev.sh for the separate backend+Vite dev workflow.
#
# Usage:
#   scripts/gaia.sh start   [--port 8000]
#   scripts/gaia.sh stop
#   scripts/gaia.sh restart [--port 8000]
#
# The GAIA binary is looked for next to this script first (a standalone
# release download that ships the script alongside the binary: GAIA.app on
# macOS, a bare GAIA binary on Linux), then ../dist/ (a local release build in
# this repo checkout), then falls back to whatever "GAIA" resolves to on PATH
# (an installed copy).
#
# The packaged entry point (packaging/gaia_app.py) always runs `gaia serve`
# regardless of any arguments passed to the executable, so the port can only
# be set via the GAIA_PORT environment variable. It is auto-bumped past
# anything already listening.

set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

port=8000
action="${1:-start}"
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) port="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# A macOS .app bundle is a directory; the real executable is inside it.
resolve_gaia_binary() {
  local candidate=$1
  if [[ -d "$candidate" && -x "$candidate/Contents/MacOS/GAIA" ]]; then
    echo "$candidate/Contents/MacOS/GAIA"
  elif [[ -x "$candidate" ]]; then
    echo "$candidate"
  fi
}

find_gaia_binary() {
  local candidate found
  for candidate in \
    "$script_dir/GAIA.app" "$script_dir/GAIA" \
    "$repo_root/dist/GAIA.app" "$repo_root/dist/GAIA"
  do
    found=$(resolve_gaia_binary "$candidate")
    [[ -n "$found" ]] && { echo "$found"; return; }
  done
  command -v GAIA 2>/dev/null || true
}

gaia_bin="$(find_gaia_binary)"
if [[ -n "$gaia_bin" ]]; then
  exe_dir="$(cd "$(dirname "$gaia_bin")" && pwd)"
else
  exe_dir="$repo_root"
fi
state_dir="$exe_dir/.gaia-state"
pid_file="$state_dir/gaia-pid"

port_in_use() { nc -z 127.0.0.1 "$1" >/dev/null 2>&1; }

find_free_port() {
  local p=$1
  while port_in_use "$p"; do p=$((p + 1)); done
  echo "$p"
}

# Post-order kill: children first, in case the parent respawns them on TERM.
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

stop_gaia() {
  local stopped=false
  local ports=("$port")

  if [[ -f "$pid_file" ]]; then
    local saved_pid saved_port
    saved_pid=$(sed -n '1p' "$pid_file")
    saved_port=$(sed -n '2p' "$pid_file")
    if [[ -n "$saved_pid" ]] && kill -0 "$saved_pid" 2>/dev/null; then
      echo "==> Stopping GAIA (PID $saved_pid)"
      kill_tree "$saved_pid"
      wait_dead "$saved_pid"
      stopped=true
    fi
    [[ -n "$saved_port" ]] && ports=("$saved_port")
    rm -f "$pid_file"
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

start_gaia() {
  if [[ -z "$gaia_bin" ]]; then
    echo "GAIA binary not found next to this script, in dist/, or on PATH." >&2
    echo "Build it with scripts/build-release-macos.sh, or place it next to this script." >&2
    exit 1
  fi
  mkdir -p "$state_dir"
  local free_port log
  free_port=$(find_free_port "$port")
  log="$state_dir/gaia.log"

  echo "==> Starting GAIA ($gaia_bin) on http://127.0.0.1:$free_port"
  ( cd "$exe_dir" && GAIA_PORT="$free_port" nohup "$gaia_bin" > "$log" 2>&1 & echo $! > "$pid_file" )
  echo "$free_port" >> "$pid_file"
  echo "==> GAIA: http://127.0.0.1:$free_port  (PID $(sed -n '1p' "$pid_file"), log: $log)"
}

case "$action" in
  start) start_gaia ;;
  stop) stop_gaia ;;
  restart) stop_gaia; sleep 1; start_gaia ;;
  *) echo "Usage: $0 {start|stop|restart} [--port N]" >&2; exit 1 ;;
esac
