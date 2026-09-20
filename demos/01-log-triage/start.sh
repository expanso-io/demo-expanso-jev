#!/bin/bash
# jev-live/start.sh — bring up the whole live demo stack on this machine.
#
#   1. recurrence tracker  (counter.py, 127.0.0.1:8898)
#   2. Expanso Edge agent  (joined to Expanso Cloud). NO pipeline is deployed:
#      the demo opens on act one, every log pouring into a raw bucket. The
#      presenter deploys from the Expanso Cloud console -- pipeline-logging.yaml,
#      then pipeline-recurrence.yaml over it as the next version of the same
#      job -- and the dashboard detects each one and follows. `just act2` /
#      `just act3` do the same from the CLI if the console misbehaves.
#   3. dashboard server    (server.py, 127.0.0.1:8890)
#   4. log generator       (generator2.py, ~5 lines/sec into the Edge HTTP input)
#
# Requires: python3, expanso-edge + expanso-cli on PATH (Expanso Edge v2+),
#           JEV_API_URL set (the Jev endpoint, or the bundled mock), and
#           EXPANSO_CLI_ENDPOINT / EXPANSO_CLI_AUTH_API_KEY /
#           EXPANSO_EDGE_BOOTSTRAP_TOKEN in .env.
#
# This demo ALWAYS runs through Expanso Cloud. Never --local, and never the
# globally selected CLI profile -- credentials reach both CLIs through their
# own environment variables (so nothing lands in argv or `ps`), and the agent
# keeps its identity in the repo under .expanso/edge rather than ~/.expanso.
set -euo pipefail

# Logs can capture CLI diagnostics that echo a token back. Create every
# file here owner-only.
umask 077

PKG="$(cd "$(dirname "$0")" && pwd)"
LOGS="$PKG/logs"
mkdir -p "$LOGS"

# The pipeline writes its four routed files to the RELATIVE path data/*.jsonl,
# which the Edge agent resolves against its own working directory -- so every
# process here runs from the package root and nothing depends on an absolute
# path. Moving the package moves the outputs with it.
cd "$PKG"

# Refuse to start over a stack that is already running. Without this, a second
# `just up` overwrote logs/pids, failed on the busy ports, and its own cleanup
# then killed the FIRST session's dashboard while orphaning its edge agent.
# Checked before the trap is armed, so refusing touches nothing.
running=""
if [ -f "$LOGS/pids" ]; then
  while read -r pid; do
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && running="$running $pid"
  done < "$LOGS/pids"
fi
busy="$(lsof -ti "tcp:${JEV_LIVE_PORT:-8890}" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$running$busy" ]; then
  echo "ERROR: the demo is already running (pids:$running $busy)." >&2
  echo "  Leaving it alone. Run 'just down' first for a fresh start." >&2
  exit 1
fi

# A start that fails halfway used to leave the counter and the edge agent
# running, holding their ports, so the NEXT `just up` failed for a different
# reason. Anything short of a completed start tears itself down.
STARTED_OK=0
trap 'if [ "$STARTED_OK" != 1 ]; then echo "  start did not complete: stopping what it launched" >&2; bash "$PKG/stop.sh" >/dev/null 2>&1 || true; fi' EXIT

: "${JEV_LIVE_PORT:=8890}"
: "${JEV_LIVE_GEN:=generator2.py}"
: "${NODE_ID:=laptop}"
export JEV_LIVE_PORT JEV_LIVE_GEN NODE_ID

if [ -z "${JEV_API_URL:-}" ]; then
  echo "ERROR: JEV_API_URL is not set." >&2
  echo "  Set it to your Jev endpoint (run 'just jev-key'), or to the bundled mock, then re-run." >&2
  echo "  The pipeline reads it at deploy time; nothing in this package stores it." >&2
  exit 1
fi
for cmd in python3 expanso-edge expanso-cli; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: '$cmd' not found on PATH." >&2
    exit 1
  fi
done

mkdir -p "$PKG/data" "$PKG/agent-data"
: > "$LOGS/pids"

launch() { # name, command...
  local name="$1"; shift
  "$@" >"$LOGS/$name.log" 2>&1 &
  local pid=$!
  echo "$pid" >> "$LOGS/pids"
  echo "  $name  pid $pid  (log: logs/$name.log)"
}

echo "== jev-live starting =="
echo "[1/4] recurrence tracker (:8898)"
launch counter python3 counter.py
sleep 1
if ! curl -sf -o /dev/null -X POST http://127.0.0.1:8898/track -d '{"fingerprint":"ping"}' \
     -H 'Content-Type: application/json'; then
  echo "ERROR: counter.py did not come up. See logs/counter.log" >&2
  exit 1
fi

echo "[2/4] Expanso Edge agent -> Expanso Cloud"

ROOT="$(cd "$PKG/../.." && pwd)"
EDGE_DATA="${EXPANSO_EDGE_HOME:-$ROOT/.expanso/edge}"
case "$EDGE_DATA" in /*) ;; *) EDGE_DATA="$ROOT/$EDGE_DATA" ;; esac

for v in EXPANSO_CLI_ENDPOINT EXPANSO_CLI_AUTH_API_KEY EXPANSO_EDGE_BOOTSTRAP_TOKEN; do
  if [ -z "$(eval "printf '%s' \"\${$v:-}\"")" ]; then
    echo "ERROR: $v is not set. Put it in .env (see .env.example)." >&2
    exit 1
  fi
done

# Every CLI call is pinned to THIS network. A bare expanso-cli would fall back
# to ~/.expanso/cli-client/profiles/current -- whichever Cloud network happened
# to be selected last -- and the job would deploy somewhere else entirely and
# sit "queued / waiting for matching nodes" while nothing bound :8080 here.
# These are the CLI's own environment variables, so no secret ever enters
# argv. EXPANSO_CLI_ENDPOINT is the load-bearing one: without it the CLI falls
# back to ~/.expanso/cli-client/profiles/current -- whichever Cloud network was
# selected last -- and the job deploys somewhere else entirely, sits "queued /
# waiting for matching nodes", and nothing binds :8080 here.
cloudcli() { expanso-cli "$@"; }

if [ ! -f "$EDGE_DATA/auth/credentials.creds" ]; then
  echo "  bootstrapping node into Expanso Cloud (one time)"
  mkdir -p "$EDGE_DATA"
  # Token comes from EXPANSO_EDGE_BOOTSTRAP_TOKEN in the environment, never
  # --token, so it stays out of argv.
  if ! expanso-edge bootstrap --data-dir "$EDGE_DATA" \
       >"$LOGS/bootstrap.log" 2>&1; then
    echo "ERROR: bootstrap failed. See logs/bootstrap.log" >&2
    exit 1
  fi
fi

# The agent reaches Jev through the dashboard server's local fault-injection gate,
# so an outage can be simulated with a real failed call. The real endpoint goes
# to the server as JEV_UPSTREAM_URL; the agent only ever sees the gate.
export JEV_UPSTREAM_URL="$JEV_API_URL"
# The Jev key, if there is one, is for the dashboard server's gate and nobody
# else. Move it to a private, unexported variable now so the counter, the edge
# agent and the generator never have it in their environment.
JEV_KEY_PRIVATE="${TYPESAFE_API_KEY:-}"
unset TYPESAFE_API_KEY
GATE_URL="http://127.0.0.1:${JEV_GATE_PORT:-8897}/v1/systemone"
launch edge env JEV_API_URL="$GATE_URL" expanso-edge run --data-dir "$EDGE_DATA"

# Two separate questions, asked separately, because they have very different
# answers and the old single check conflated them:
#
#   1. Did the agent connect?  Local truth, from the agent's own log. It takes
#      well under a second. If THIS fails, something is actually wrong.
#   2. Has Cloud's node list caught up?  That flips "connecting" -> "connected"
#      on a heartbeat and has been measured at 37-58 s, sometimes more. It
#      matters only because a deploy made while it still says "connecting"
#      waits ~10 s for a node. It is not a failure, so it must not fail the
#      start: the presenter deploys later anyway. Wait for it, then warn.
NODE_ID_FULL="$(awk '/node_id:/{print $2; exit}' "$EDGE_DATA/config.d/50-connection.yaml" 2>/dev/null || true)"
NODE_SHORT="$(printf '%s' "${NODE_ID_FULL:-}" | cut -c1-8)"
echo "  waiting for the agent to connect to $EXPANSO_CLI_ENDPOINT ..."
ok=0
for _ in $(seq 1 30); do
  if grep -q "Edge connected to orchestrator" "$LOGS/edge.log" 2>/dev/null; then ok=1; break; fi
  sleep 1
done
if [ "$ok" != 1 ]; then
  echo "ERROR: the edge agent did not connect to Expanso Cloud within 30s. See logs/edge.log" >&2
  exit 1
fi
echo "  agent connected (node ${NODE_SHORT:-?})"

# Positive control: Cloud must at least LIST our node. A reachable control plane
# that has never heard of this node is the failure worth stopping for.
echo "  waiting for Expanso Cloud to show the node as connected (usually 40-60s) ..."
listed=0; connected=0
for _ in $(seq 1 90); do
  row="$(cloudcli node list --no-style 2>/dev/null | grep "${NODE_SHORT:-__none__}" || true)"
  [ -n "$row" ] && listed=1
  if printf '%s' "$row" | grep -q " connected "; then connected=1; break; fi
  sleep 1
done
if [ "$listed" != 1 ]; then
  echo "ERROR: Expanso Cloud does not list node ${NODE_SHORT:-?} at all. Wrong network or credentials?" >&2
  exit 1
fi
if [ "$connected" != 1 ]; then
  echo "  WARN  Cloud still shows the node as 'connecting' after 90s. The agent IS connected;"
  echo "        a deploy made right now may wait ~10s for a node. Continuing."
fi
echo "  node registered"

# Open on a true zero state: nothing deployed, nothing routed. A job left
# running from a previous take would have the board open mid-story with
# non-zero counters, and a demo has to start from the same place every time.
port_bound() { lsof -ti tcp:8080 -sTCP:LISTEN >/dev/null 2>&1; }
# Always leave the job's LATEST version in Cloud as the Expanso-only pipeline,
# then stop it. A bare stop kept whatever was deployed last, which after any
# take is the Jev version (the switch deploys it), so starting the job from the
# Cloud console opened the story with Jev already on. The deploy is also the
# real transition that makes a stop reach an agent that resumed from its store.
wait_free() { for _ in $(seq 1 40); do port_bound || return 0; sleep 0.5; done; return 1; }
wait_bound() { for _ in $(seq 1 60); do port_bound && return 0; sleep 0.5; done; return 1; }
cloudcli job stop log-triage --namespace demo --force >>"$LOGS/deploy.log" 2>&1 || true
if ! wait_free; then
  # Cloud says stopped, the node disagrees: the agent resumed an execution from
  # its local store, and a stop on an already-stopped job sends it nothing.
  # Force a real transition so a real stop reaches it.
  echo "  pipeline resumed from agent state; cycling it off through Expanso Cloud"
  cloudcli job deploy --force pipeline-logging.yaml >>"$LOGS/deploy.log" 2>&1 || true
  sleep 3
  cloudcli job stop log-triage --namespace demo --force >>"$LOGS/deploy.log" 2>&1 || true
  wait_free || true
fi
if ! port_bound; then
  echo "  resetting the Cloud job to the Expanso-only version, stopped"
  if cloudcli job deploy --force pipeline-logging.yaml >>"$LOGS/deploy.log" 2>&1 && wait_bound; then
    cloudcli job stop log-triage --namespace demo --force >>"$LOGS/deploy.log" 2>&1 || true
    wait_free || true
  else
    echo "  WARN: could not reset the Cloud job; see logs/deploy.log" >&2
  fi
fi
if port_bound; then
  echo "ERROR: a pipeline is still bound to :8080; the demo cannot open on act one." >&2
  echo "  Stop it in the Expanso Cloud console, then re-run." >&2
  exit 1
fi
rm -f "$PKG"/data/*.jsonl
echo "  no pipeline deployed (act one) -- deploy from Expanso Cloud, or: just act2 / just act3"

echo "[3/4] dashboard server (:$JEV_LIVE_PORT)"
# Exported inside a subshell, then exec: the key is in the server's environment
# only, and never in any process's argv.
( [ -n "$JEV_KEY_PRIVATE" ] && export TYPESAFE_API_KEY="$JEV_KEY_PRIVATE"; exec python3 server.py ) >"$LOGS/server.log" 2>&1 &
spid=$!
echo "$spid" >> "$LOGS/pids"
echo "  server  pid $spid  (log: logs/server.log)"
unset JEV_KEY_PRIVATE
sleep 1

echo "[4/4] log generator"
launch generator python3 "$JEV_LIVE_GEN"

echo ""
echo "== live =="
echo "  dashboard : http://127.0.0.1:$JEV_LIVE_PORT"
echo "  Edge input: http://127.0.0.1:8080/logs  (live once a pipeline is switched on)"
echo "  pids      : $(tr '\n' ' ' < "$LOGS/pids")"
echo "  stop      : ./stop.sh"
STARTED_OK=1
