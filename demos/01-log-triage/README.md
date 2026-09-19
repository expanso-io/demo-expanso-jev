# 01 log triage — every log kept, none understood

A live board over a **real pipeline**, in three acts. No embedded data and no
scripted replay: every square is a log line that was actually produced, and
every coloured square is a record the Edge pipeline actually wrote, to the
bucket it actually chose. The board only observes: deploy from the Expanso
Cloud console, the CLI, or the Jev switch, and the board follows.

Start at the [repository README](../../README.md) for setup. This page is the
detail: how the board reads, how the pieces fit, and what to do when it breaks.

## Prerequisites

- macOS or Linux, `python3`, `just`
- Expanso Edge + CLI v2+ on PATH (`expanso-edge`, `expanso-cli`)
- `JEV_API_URL` and, for Jev's public API, `TYPESAFE_API_KEY`. `just jev-key` sets
  both in `.env`, which is gitignored. Never put a key in a pipeline file.

Everything is stdlib-only Python 3 plus shell. No pip, no emojis, no secrets.

## Run it

From the repo root (the justfile loads `.env`, which is where the Expanso Cloud
and Jev settings live; see `AGENTS.md` for why they are env vars, never flags):

```bash
just doctor    # tools, Cloud credentials, Jev reachability
just up        # opens on act one: nothing deployed, zero counters
just down      # stops everything, including the job in Expanso Cloud
```

Then open **http://127.0.0.1:8890**.

## The three acts

| Act | Do this in Expanso Cloud | CLI equivalent | What the board does |
|---|---|---|---|
| 1 | nothing | `just act1` | Logs flow straight into a raw bucket, kept exactly as written. No Expanso, no Jev on screen. |
| 2 | deploy `pipeline-logging.yaml` (job `log-triage`) | `just act2` | Expanso appears. Every record is structured, counted and archived. No model. |
| 3 | deploy `pipeline-recurrence.yaml` over the same job | `just act3` | Jev appears. The lane forks into "no model call" and "ask Jev", each with its measured share. |

Both files deploy as the **same job**, so act three is a version bump of one
pipeline.

**Selective inference.** An exact allowlist (level INFO + service + the raw
message) sends known-benign lines to the archive with no model call. It matches
raw strings, not the fingerprint: the fingerprint drops the level and erases
every number, so it would wave through `GET /health 500 9000ms`. Changed values,
WARN/ERROR, and novel INFO lines are always judged. Nothing is dropped.
`uv run -s tests/bypass_cases.py` proves it against the live pipeline.

**Named baseline.** Every record carries `baseline`: what severity-only routing
(ERROR→page, WARN→notify, INFO→archive) would have done with the identical
input. The evidence strip shows baseline, what Jev reported, and where the
record actually landed. Destinations are local JSONL demo files, not vendor
receipts, and the events are synthetic.

**The Jev switch.** On the Jev box, macOS-style. On deploys
`pipeline-recurrence.yaml` over the running job through Expanso Cloud; off deploys
`pipeline-logging.yaml` back. A real deploy (about a second), and the board only
changes once the pipeline does. Starting and stopping the pipeline itself stays
in the Cloud console, or `just act1` / `just act2`.

**A Jev outage, and Expanso holding.** *Break the link to Jev* flips a local
fault-injection gate that every Jev call passes through, so Jev appears to
answer 503. It is a **simulated** outage and the board
says so, but the failed call is real and so is what happens next, which is all
in `pipeline-recurrence.yaml`: a record Jev did not answer is neither guessed nor
dropped. It is written once to `data/held.jsonl`, re-submitted to the pipeline's
own input, waits 2-4 s (jittered, so a recovery is not a thundering herd), and
asks again, up to 15 attempts (~45 s) before it goes to REVIEW. Routine traffic
keeps flowing throughout. *Restore the link* reopens the gate and the backlog drains.
In one run against real Jev, 30 records were held over 13 s and all 30 were
released within 4 s of restoring the link. A real outage (endpoint unreachable)
takes exactly the same path; only the label differs.

**Click a bucket** for the latest record's full JSON, syntax coloured and grouped
by who added each field (production, Expanso, Jev). Esc closes it.

If the board ever shows **"MOCK Jev responses"** in red, the gate's upstream is
the repo's mock and the judgments are not real inference.

**Two tabs.** *Live flow* is the board. *Pipeline YAML* shows the checked-in
source of either pipeline, verbatim (`GET /api/pipeline/<logging|recurrence>`, a
closed allowlist; `${JEV_API_URL}` stays a placeholder). It is the source
configuration, not a read-back of the deployed spec.

**Reading the board.** Steps inside Expanso are its real processors. The dashed
line up to Jev is the path unknown records take; the pulse coming back down
into *Gate* is a real answer arriving. The metrics strip counts completed
records of the current run only. "Jev unanswered" records were kept and held
for review, not dropped.

Click a bucket to pin its latest record in the strip; click again to unpin.
**Inject at the source** pushes a real scenario through the live pipeline.

## Logs in Expanso Cloud

Both pipelines emit sampled operational lines, e.g.
`triage fallback -> REVIEW selected, output pending: … event=<hash> fp=<hash>`.
They say a destination was *selected* (the log runs before the output writes),
carry no message text, prompt, URL or credential, pass producer and model
strings only through closed allowlists, and hash every event id and fingerprint
(`sha256(id)[:12]`, recomputable from a local receipt). Only the routine path is
sampled (a bypass checkpoint per fingerprint); **every non-bypass selection is
logged**, so a changed-value line can never be silenced by sharing a fingerprint
with a routine one. Sized for this synthetic demo; production volume would need
a real rate cap. `uv run -s tests/log_safety_test.py` guards it.

Log streaming is **live only**: the node ships nothing until someone is tailing
a *running* job, and there is no history. The console Logs tab and
`expanso-cli job logs` are related but **different** endpoints
(`/logs/proxy` by job id with a browser session, vs `/logs` with an API key), so
evidence about one is not evidence about the other.

To tail from a terminal, use the job's **UUID, not its name** (by name the
handshake is refused), while the job is running:

```bash
just up && just act3
expanso-cli job list --namespace demo    # copy the full j-… id
expanso-cli job logs <job-uuid> | grep triage
```

The stream carries DEBUG framework lines too, hence the `grep triage` (in the
console, filter on `triage`).

## How the pieces fit

```
generator2.py --POST :8080/logs--> Expanso Edge, job `log-triage` (deployed via Cloud)
      |   \                                | shape, fingerprint
      |    \ refused (act 1)               v
      |     +--> server.py /raw        counter.py (:8898 /track)  <- occurrence, history
      |          -> data/raw.jsonl          | [act 3] exact-match known-benign? -> archive, no model call
      |                                     v
      +--beacon: "n lines emitted"     [act 3] Jev API (${JEV_API_URL})  <- judgment
                 |                          | gate on the answers
                 v                          v
            server.py (:8890)  <--tails--  data/{logs,page,notify,review,archive}.jsonl
                 | SSE /events
                 v
            index.html
```

- **Expanso** is the deterministic part: shape, fingerprint, count occurrences
  in a 10-minute window, bypass known-benign lines, recall previous decisions, route.
- **Jev** is the judgment: given that history, how concerning is this line
  *right now*? It is asked only about what the bypass did not clear (measured
  ~11% of completed records), which is what lets the source run at ~40 lines/sec
  against a model that judges ~30/sec.
- If Jev is unreachable the pipeline routes to **review by design**, never
  dropped, and the board turns the Jev node red and says so. `just doctor`
  checks the endpoint before you get that far.
- `server.py` detects the act two ways: a local probe of `:8080` (instant) and
  a 2s poll of Expanso Cloud for the running job's spec (authoritative).

## Env vars

| var | default | what |
|---|---|---|
| `JEV_API_URL` | (required) | The real Jev endpoint. `start.sh` hands it to the dashboard server as `JEV_UPSTREAM_URL` and points the agent at the local gate (`:8897`) instead. |
| `TYPESAFE_API_KEY` | (needed for Jev's public API) | Bearer key for `api.typesafe.ai`. Set with `just jev-key`. Held only by the dashboard server's gate; never in the pipeline, Cloud, or argv. |
| `EXPANSO_CLI_ENDPOINT` `EXPANSO_CLI_AUTH_API_KEY` `EXPANSO_EDGE_BOOTSTRAP_TOKEN` | (required) | Expanso Cloud. The CLIs' own variable names, so no secret reaches argv. See `AGENTS.md`. |
| `JEV_GEN_RATE` | `30` | baseline source rate; observed mean is ~40 lines/sec |
| `JEV_GEN_JAGGED` | `1` | `0` for a flat, metronomic source |
| `JEV_LIVE_PORT` | `8890` | dashboard port |
| `JEV_LIVE_GEN` | `generator2.py` | generator script |
| `JEV_LIVE_PIPELINE` | `http://127.0.0.1:8080/logs` | Edge HTTP input (chaos injection target) |
| `NODE_ID` | `laptop` | node label stamped on events |

The pipeline's output directory is deliberately **not** a variable. It writes
`data/*.jsonl` relative to the Edge agent's working directory, and `start.sh`
`cd`s to this package before launching anything — so the files always land
in `data/` and `server.py` always tails exactly that. Nothing to configure,
nothing to desync, and the package works from any checkout location.

## Troubleshooting

- **`JEV_API_URL is not set`** — export it first; start.sh refuses to run without it.
- **`expanso-edge` / `expanso-cli` not found** — install Expanso Edge v2+ and make
  sure both binaries are on PATH.
- **Port clash on 8890 / 8898 / 8080** — `lsof -i :8890` to find the squatter;
  or set `JEV_LIVE_PORT` to something free (8898 is the counter, 8080 the Edge input).
- **"Lost the dashboard server"** — server.py isn't running or died; check
  `logs/server.log`. The UI never invents events: no stream, no squares.
- **Board says "Jev is not answering", everything lands in REVIEW** — the
  pipeline can't reach Jev. Check `JEV_API_URL` and your key
  (`just doctor` probes the endpoint). This is the designed graceful degradation, not a bug.
- **`just up` sits at "waiting for Expanso Cloud to show the node as connected"** —
  normal. The agent connects in under a second; Cloud's node list takes 40-60s
  to flip from `connecting`. Allow about a minute for `just up`. It only fails if
  the agent never connects (30s) or Cloud never lists the node at all (90s).
- **Deployed in Cloud but the board stays on act one** — the job is running
  but its input never bound `:8080` here. Is the edge agent connected
  (`expanso-cli node list`)? Did the job land on this node?
- **Board serves stale code after a restart** — an older `server.py` still
  holds `:8890`. `just down` now clears listeners by port, not just by pid file.
- **Chaos button does nothing visible** — chaos lines are ~20s apart on purpose;
  give it a minute. Check `logs/server.log` for `chaos <name> line` entries.
- **Clean slate** — `just down` stops the `log-triage` job in Expanso Cloud
  and `just up` truncates `data/*.jsonl`, so every run opens on zero counters.
- **Jev switch off but Jev keeps running, or `just up` fails with "still bound to
  :8080"** — the agent is restarting a pipeline from a job Cloud no longer has.
  `just down`, `just reset-agent`, `just up`.

## Tests

```bash
uv run -s tests/ui_server_tests.py    # dashboard server: endpoints, path safety
uv run -s tests/log_safety_test.py    # nothing sensitive reaches pipeline logs
uv run -s tests/stop_scope_test.py    # `just down` only touches this checkout
uv run -s tests/bypass_cases.py       # needs the stack up on act three
```
