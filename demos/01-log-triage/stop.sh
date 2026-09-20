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

while read -r pid; do
  [ -n "$pid" ] || continue
  if kill -0 "$pid" 2>/dev/null; then
    echo "stopping pid $pid"
    kill "$pid" 2>/dev/null || true
  fi
done < "$LOGS/pids"

sleep 2
while read -r pid; do
  [ -n "$pid" ] || continue
  if kill -0 "$pid" 2>/dev/null; then
    echo "force-killing pid $pid"
    kill -9 "$pid" 2>/dev/null || true
  fi
done < "$LOGS/pids"

# Anything from an earlier run that logs/pids has forgotten: a generator that
# server.py restarted, or a server/counter still holding its port so the next
# one cannot bind and the dashboard silently serves old code.
#
# Scoped to THIS checkout. A process is ours only if its working directory is
# this package -- start.sh and server.py both launch from here. Matching on a
# script name or a port alone would reach into other demos on the same machine
# (several share generator2.py and these ports), so candidates are found that
# way and then each one is verified before it is touched.
ours() {  # pid -> 0 if its cwd is this package
  [ "$(lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)" = "$PKG" ]
}
candidates="$(pgrep -f "$(basename "${JEV_LIVE_GEN:-generator2.py}")" 2>/dev/null || true)"
# An edge agent whose pid was lost keeps the state db locked, so the next
# start cannot open it. ours() below still scopes it to this checkout.
candidates="$candidates $(pgrep -f 'expanso-edge run' 2>/dev/null || true)"
for port in "${JEV_LIVE_PORT:-8890}" 8898; do
  candidates="$candidates $(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null || true)"
done
for pid in $candidates; do
  if ours "$pid"; then
    echo "stopping stray process from this checkout (pid $pid)"
    kill "$pid" 2>/dev/null || true
  else
    echo "leaving pid $pid alone: not started from $PKG"
  fi
done

: > "$LOGS/pids"
echo "stopped."
echo "pipelines stopped in Expanso Cloud."
