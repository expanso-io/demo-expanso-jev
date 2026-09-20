# demo-expanso-jev — one entry point for the whole live demo.
#
#   cp .env.example .env    # then set JEV_API_URL
#   just doctor             # verify the machine can run it
#   just up                 # pods + local browser + Expanso Cloud
#   just open               # dashboard in a browser
#   just down               # stop everything this repo started

set dotenv-load := true
set shell := ["bash", "-euo", "pipefail", "-c"]

root := justfile_directory()
demo := env_var_or_default("DEMO", "01-log-triage")
live := root / "demos" / demo

# The pipeline writes data/*.jsonl relative to the Edge agent's working
# directory, and start.sh pins that to demos/$DEMO/. So the output location is a
# fixed convention, not a setting -- only the recipes below need to know it.
data := live / "data"

export JEV_LIVE_PORT := env_var_or_default("JEV_LIVE_PORT", "8890")
export JEV_LIVE_PIPELINE := env_var_or_default("JEV_LIVE_PIPELINE", "http://[::1]:8080/logs")
export NODE_ID := env_var_or_default("NODE_ID", "laptop")

_default:
    @just --list --unsorted

# Copy .env.example to .env if it isn't there yet.
init:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -f "{{ root }}/.env" ]; then
      echo "ok: .env already exists"
    else
      cp "{{ root }}/.env.example" "{{ root }}/.env"
      echo "created .env — set JEV_API_URL in it, then run: just doctor"
    fi

# Check every prerequisite before you waste a take on a broken machine.
doctor:
    #!/usr/bin/env bash
    set -uo pipefail
    fail=0
    for cmd in python3 expanso-edge expanso-cli curl; do
      if command -v "$cmd" >/dev/null 2>&1; then
        echo "  ok    $cmd  ($(command -v "$cmd"))"
      else
        echo "  MISS  $cmd  not on PATH"; fail=1
      fi
    done
    if [ -z "${JEV_API_URL:-}" ]; then
      echo "  MISS  JEV_API_URL unset — run 'just init' and edit .env"; fail=1
    elif [[ "${JEV_API_URL}" == *replace-me* ]]; then
      echo "  MISS  JEV_API_URL is still the placeholder"; fail=1
    else
      echo "  ok    JEV_API_URL set (${JEV_API_URL%%/*}//…)"
      # Set is not the same as reachable. When the endpoint is down the
      # pipeline degrades on purpose and sends every event to REVIEW, which on
      # camera looks like Jev having no opinions. Probe the socket.
      hp="${JEV_API_URL#*://}"; hp="${hp%%/*}"
      case "$hp" in *:*) ;; *) case "$JEV_API_URL" in https://*) hp="$hp:443" ;; *) hp="$hp:80" ;; esac ;; esac
      if python3 -c "import socket,sys; h,_,p=sys.argv[1].rpartition(':'); socket.create_connection((h.strip('[]'), int(p)), 3)" "$hp" 2>/dev/null; then
        echo "  ok    Jev endpoint reachable ($hp)"
      else
        # WARN, not MISS: acts one and two do not need Jev, and the board turns
        # red by itself in act three. Blocking `just up` would stop rehearsal.
        echo "  WARN  nothing answering at $hp — Jev unreachable: act three will hold, then send everything to REVIEW"
        echo "        run 'just jev-key' to store a key for Jev's API"
      fi
    fi
    # Jev's public API needs a Bearer key; the dashboard server's gate adds it.
    case "${JEV_API_URL:-}" in
      *api.typesafe.ai*)
        if [ -n "${TYPESAFE_API_KEY:-}" ]; then echo "  ok    TYPESAFE_API_KEY set (the gate will add Bearer auth)"
        else echo "  WARN  JEV_API_URL is Jev's public API but TYPESAFE_API_KEY is unset — run: just jev-key"; fi ;;
    esac
    # Expanso Cloud is not optional for this demo -- there is no local mode.
    # Only ever report set/unset. Never echo any part of a key.
    for v in EXPANSO_CLI_ENDPOINT EXPANSO_CLI_AUTH_API_KEY EXPANSO_EDGE_BOOTSTRAP_TOKEN; do
      if [ -z "$(eval "printf '%s' \"\${$v:-}\"")" ]; then
        echo "  MISS  $v unset — put it in .env"; fail=1
      else
        echo "  ok    $v set"
      fi
    done
    if [ -n "${EXPANSO_CLI_ENDPOINT:-}" ]; then
      # Prove the credentials can actually READ the network. An endpoint that
      # merely answers, or a key that authenticates but sees nothing, is the
      # green check that hides a broken demo.
      # Credentials come from the environment (dotenv-load), never argv.
      if expanso-cli node list >/dev/null 2>&1; then
        echo "  ok    Expanso Cloud reachable"
      else
        echo "  MISS  cannot reach Expanso Cloud with these credentials"; fail=1
      fi
    fi
    echo "  data  {{ data }}"
    echo "  port  $JEV_LIVE_PORT"
    if lsof -ti :"$JEV_LIVE_PORT" >/dev/null 2>&1; then
      echo "  WARN  port $JEV_LIVE_PORT already in use"
    fi
    for p in 8080 8898; do
      if lsof -ti :$p >/dev/null 2>&1; then
        echo "  WARN  port $p already in use (stale 'just up'? run 'just down')"
      fi
    done
    exit $fail

# Validate every pipeline config locally, before the agent sees it.
validate:
    #!/usr/bin/env bash
    set -euo pipefail
    for f in "{{ live }}/pipeline-logging.yaml" \
             "{{ live }}/pipeline-recurrence.yaml" \
             "{{ root }}"/demos/*/pipeline.yaml; do
      expanso-edge validate "$f"
    done

# Start the pod demo. Use `just up triage` for the log-triage demo.
up target="pods":
    @case "{{ target }}" in pods) uv run "{{ root }}/demos/11-pod-labels/simulation/local.py" up ;; triage) just --justfile "{{ root }}/justfile" _triage-up ;; *) echo "Choose pods or triage" >&2; exit 2 ;; esac

# Stop the selected demo.
down target="pods":
    @case "{{ target }}" in pods) uv run "{{ root }}/demos/11-pod-labels/simulation/local.py" down ;; triage) just --justfile "{{ root }}/justfile" _triage-down ;; *) echo "Choose pods or triage" >&2; exit 2 ;; esac

restart: down up

# Open the selected demo's local browser UI.
open target="pods":
    @case "{{ target }}" in pods) open http://127.0.0.1:8901 ;; triage) just --justfile "{{ root }}/justfile" _triage-open ;; *) echo "Choose pods or triage" >&2; exit 2 ;; esac

# Show the selected demo's status.
status target="pods":
    @case "{{ target }}" in pods) just --justfile "{{ root }}/justfile" pod-labels-status ;; triage) just --justfile "{{ root }}/justfile" _triage-status ;; *) echo "Choose pods or triage" >&2; exit 2 ;; esac

# Verify the pod demo without starting services.
test: pod-labels-test

# Bring up the full stack: counter, Edge agent + pipeline, dashboard, generator.
_triage-up: doctor validate
    bash "{{ live }}/start.sh"

# Stop everything start.sh launched.
_triage-down:
    bash "{{ live }}/stop.sh"



# Which of our processes are alive, and what the routes have collected.
_triage-status:
    #!/usr/bin/env bash
    set -uo pipefail
    pids="{{ live }}/logs/pids"
    if [ -s "$pids" ]; then
      while read -r pid; do
        [ -n "$pid" ] || continue
        if kill -0 "$pid" 2>/dev/null; then
          echo "  up    $pid  $(ps -o command= -p "$pid" | cut -c1-60)"
        else
          echo "  dead  $pid"
        fi
      done < "$pids"
    else
      echo "  nothing running (no logs/pids)"
    fi
    for f in page notify review archive; do
      path="{{ data }}/$f.jsonl"
      [ -f "$path" ] && echo "  $f: $(wc -l < "$path" | tr -d ' ') records"
    done
    exit 0

# Tail a component log: counter | edge | server | generator | deploy
logs name="server":
    tail -f "{{ live }}/logs/{{ name }}.log"

# Open the demo in the configured display layer (DISPLAY_MODE=business|fancy).
_triage-open:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${DISPLAY_MODE:-business}" = "fancy" ]; then
      open "{{ root }}/display/fancy/jev-flow.html"
    else
      open "http://127.0.0.1:$JEV_LIVE_PORT"
    fi

# The fancy display layer directly — no stack needed.
flow:
    open "{{ root }}/display/fancy/jev-flow.html"

# Push one chaos scenario through the live pipeline.
# scenario: brute | ghost | disk | cert | crash
chaos scenario="brute":
    curl -sf -X POST "http://127.0.0.1:$JEV_LIVE_PORT/chaos/{{ scenario }}" && echo

# Remove run artifacts (logs, agent state, routed output). Leaves .env alone.
clean: down
    rm -rf "{{ live }}/logs" "{{ live }}/agent-data"
    rm -f "{{ data }}"/{page,notify,review,archive}.jsonl
    @echo "cleaned."

# What an agent needs to know about Expanso credentials. See AGENTS.md.
agent-help *ARGS:
    uv run -s "{{ root }}/tools/expanso-agent-help.py" {{ ARGS }}

# ---- the three acts, from the CLI ------------------------------------------
# The demo is meant to be driven from the Expanso Cloud console; the dashboard
# detects whatever is running and follows. These are the same deploys from the
# terminal: a rehearsal shortcut and a fallback. Credentials come from .env via
# the CLI's own env vars, never flags.

# Act one: no pipeline. Logs pour into the raw bucket.
act1:
    expanso-cli job stop log-triage --namespace demo --force || true

# Act two: Expanso alone. Shape, fingerprint, count, collapse repeats, archive.
act2:
    cd "{{ live }}" && expanso-cli job deploy --force pipeline-logging.yaml

# Act three: the same job, next version, now asking Jev.
act3:
    cd "{{ live }}" && expanso-cli job deploy --force pipeline-recurrence.yaml

# Point this demo straight at Jev's API and store your key in .env (gitignored,
# owner-only). Prompts silently: the key never appears on screen, in argv, or in
# shell history.
jev-key:
    #!/usr/bin/env bash
    set -euo pipefail
    env_file="{{ root }}/.env"
    [ -f "$env_file" ] || { echo "no .env yet — run: just init"; exit 1; }
    read -rsp 'TypeSafe API key (input hidden): ' K && echo
    case "$K" in ""|*'<'*|*your*|*replace*|*xxx*|*...*) echo "refusing: empty or looks like a placeholder"; exit 1 ;; esac
    K="$K" uv run python - "$env_file" <<'PY'
    import os, re, sys, pathlib
    p = pathlib.Path(sys.argv[1]); s = p.read_text(); k = os.environ["K"]
    def put(s, name, val):
        line = f"{name}={val}"
        return re.sub(rf"(?m)^{name}=.*$", lambda _: line, s) if re.search(rf"(?m)^{name}=", s) else s.rstrip("\n") + "\n" + line + "\n"
    s = put(s, "TYPESAFE_API_KEY", k)
    s = put(s, "JEV_API_URL", "https://api.typesafe.ai/v1/systemone")
    p.write_text(s); os.chmod(p, 0o600)
    print("saved TYPESAFE_API_KEY (" + str(len(k)) + " chars) and JEV_API_URL=https://api.typesafe.ai/v1/systemone to .env")
    PY
    unset K
    echo "next: just doctor && just restart"

# Clear the edge agent's local execution store (keeps its identity and login).
# For when it restarts pipelines from jobs that no longer exist in Cloud: they
# hold :8080, Cloud cannot stop them, and the Jev switch appears stuck on.
reset-agent:
    #!/usr/bin/env bash
    set -euo pipefail
    if pgrep -f 'expanso-edge run' >/dev/null; then echo "agent is running: just down first" >&2; exit 1; fi
    b=".expanso/edge-stale-state-$(date +%Y-%m-%dT%H%M%S)"
    mkdir -p "$b"
    for d in state executions; do [ -e ".expanso/edge/$d" ] && mv ".expanso/edge/$d" "$b/$d"; done
    echo "moved the agent's execution store to $b (identity untouched)"

# Pod-label demo: one foreground command for local k3s + Cloud.
pod-labels-up:
    just --justfile "{{ root }}/demos/11-pod-labels/justfile" up

pod-labels-down:
    just --justfile "{{ root }}/demos/11-pod-labels/justfile" down

# Pod-label demo: foreground adapter, driven only by the Cloud pipeline.
pod-labels-adapter:
    uv run "{{ root }}/demos/11-pod-labels/adapter.py"

# Dedicated Cloud-connected node; Ctrl-C stops this foreground agent.
pod-labels-edge:
    #!/usr/bin/env bash
    set -euo pipefail
    : "${EXPANSO_EDGE_BOOTSTRAP_TOKEN:?Set the Cloud bootstrap token}"
    : "${POD_LABEL_TOKEN:?Set the adapter token in .env}"
    edge_data="{{ root }}/.expanso/pod-labels"
    unset TYPESAFE_API_KEY EXPANSO_EDGE_HOME
    if [ ! -f "$edge_data/config.d/50-connection.yaml" ]; then
      expanso-edge bootstrap --data-dir "$edge_data"
    fi
    exec expanso-edge run --data-dir "$edge_data" \
      --api-listen 127.0.0.1:9016 \
      --config "{{ root }}/demos/11-pod-labels/edge.yaml"

# Inspect only the pinned Cloud network, never the global CLI profile.
pod-labels-nodes:
    : "${EXPANSO_CLI_ENDPOINT:?Set the Cloud endpoint}"
    : "${EXPANSO_CLI_AUTH_API_KEY:?Set the Cloud API key}"
    expanso-cli node list --label demo=jev-pod-labels

# Local tests do not use a cluster, Cloud, or paid inference.
pod-labels-test:
    uv run "{{ root }}/demos/11-pod-labels/test_adapter.py"
    uv run "{{ root }}/demos/11-pod-labels/test_investigation.py"
    uv run "{{ root }}/demos/11-pod-labels/test_routing.py"
    uv run "{{ root }}/demos/11-pod-labels/simulation/test_local.py"
    POD_LABEL_TOKEN=offline-validation-placeholder-only expanso-edge validate "{{ root }}/demos/11-pod-labels/pipeline.yaml"

# Run after inspecting pod-labels-nodes; selectors are validated by Cloud.
pod-labels-deploy:
    uv run "{{ root }}/demos/11-pod-labels/deploy.py"

pod-labels-status:
    : "${EXPANSO_CLI_ENDPOINT:?Set the Cloud endpoint}"
    : "${EXPANSO_CLI_AUTH_API_KEY:?Set the Cloud API key}"
    expanso-cli job describe jev-pod-labels --namespace demo
    expanso-cli execution list --namespace demo

pod-labels-stop:
    : "${EXPANSO_CLI_ENDPOINT:?Set the Cloud endpoint}"
    : "${EXPANSO_CLI_AUTH_API_KEY:?Set the Cloud API key}"
    expanso-cli job stop jev-pod-labels --namespace demo --force
