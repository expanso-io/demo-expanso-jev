#!/bin/bash
# jev-live/stop.sh — stop everything start.sh launched (pids tracked in logs/pids).
set -uo pipefail

PKG="$(cd "$(dirname "$0")" && pwd)"
LOGS="$PKG/logs"

port_bound() { lsof -ti tcp:8080 -sTCP:LISTEN >/dev/null 2>&1; }

# Stop the job in Expanso Cloud BEFORE killing the agent. The agent persists its
# executions locally; if it dies without hearing the stop, the next agent to
# start resumes the pipeline by itself while Cloud shows the job stopped -- and
# the demo opens mid-story. Credentials come from the environment (`just down`
# loads .env); without them, skip rather than fall back to a global profile.
if [ -n "${EXPANSO_CLI_ENDPOINT:-}" ] && [ -n "${EXPANSO_CLI_AUTH_API_KEY:-}" ]; then
  expanso-cli job stop log-triage --namespace demo --force >/dev/null 2>&1 || true
  for _ in $(seq 1 20); do port_bound || break; sleep 0.5; done
  if port_bound; then echo "WARN: pipeline input :8080 still bound after job stop"; fi
fi

if [ ! -f "$LOGS/pids" ]; then
  echo "nothing to stop (no logs/pids)"
  exit 0
fi

for pidfile in "$LOGS"/*.pid; do
  [ -f "$pidfile" ] || continue
  case "${pidfile##*/}" in
    counter.pid) marker=counter.py ;;
    server.pid) marker=server.py ;;
    generator.pid) marker="${JEV_LIVE_GEN##*/}"; marker="${marker:-generator2.py}" ;;
    *) marker="expanso-edge run" ;;
  esac
  uv run --no-project "$PKG/../../scripts/stop-owned.py" stop \
    --pidfile "$pidfile" --root "$PKG" --match "$marker" || exit 1
done
if [ -s "$LOGS/pids" ] && ! ls "$LOGS"/*.pid.identity.json >/dev/null 2>&1; then
  while read -r pid; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "ERROR: live legacy PID has no ownership identity; leaving it alone" >&2
      exit 1
    fi
  done < "$LOGS/pids"
fi
: > "$LOGS/pids"
echo "stopped."
