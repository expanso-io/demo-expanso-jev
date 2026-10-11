# 01 log triage — every log kept, none understood

A live board over a **real pipeline**, in three acts. Its moving squares
illustrate the route at presentation speed. Counters, destinations, and record
details come from the Edge pipeline's receipts. Expanso Cloud owns the job;
the local gate controls whether Cribl receives candidate requests.

Start at the [repository README](../../README.md) for setup. This page is the
detail: how the board reads, how the pieces fit, and what to do when it breaks.

## Verify it with no account

```bash
uv run -s tools/fixture-runner.py run --only 01
```

This deploys both pipelines, unmodified, to a local Edge agent, starts the
recurrence counter, posts the 16 lines in `input.jsonl`, and compares what each
pipeline wrote with `fixtures/*.expected/`. A third case makes Jev answer 503 and
shows the hold: two routine lines reach the archive with no model call, and the
WARN record is written once to `held`, re-submitted every 2 to 4 seconds and
handed to review after 15 attempts. Jev's answers are replayed from
`fixtures/recurrence.answers.json`. Step through the same runs, stage by stage,
in [`index.html`](../../index.html#example=01-log-triage).

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
just up        # deploys the Cloud pipeline with Cribl locally off
just down     # stops the managed demos and triage job in Cloud
```

Then open **http://127.0.0.1:8890**.
To start the three-act walkthrough with no pipeline, use `just up-triage`
and deploy it later with `just act2`.

## The three acts

| Act | Do this in Expanso Cloud | CLI equivalent | What the board does |
|---|---|---|---|
| 1 | nothing | `just act1` | Logs flow straight into a raw bucket, kept exactly as written. No Expanso, no Jev on screen. |
| 2 | deploy `pipeline-recurrence.yaml` (job `log-triage`) | `just act2` | Expanso appears. Every record is structured, counted and archived. The local gate is off. |
| 3 | keep the same Cloud job running | `just act3` | The local gate starts forwarding candidate requests to Cribl. The lane forks into measured no-call and judged paths. |

The switch does not deploy or restart the Cloud job.

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

**The Cribl switch.** The switch changes the dashboard server's local gate.
Off returns a disabled result without calling Cribl; the pipeline archives
those records and does not count them as judgments. On forwards candidate
requests to Cribl. Starting and stopping the pipeline stays in Cloud or with
`just act1` / `just act2`.

**A Jev outage, and Expanso holding.** *Break the link to Jev* flips a local
fault-injection gate that every Jev call passes through, so Jev appears to
answer 503. It is an outage produced at a local gate, and the board
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
`pipeline-recurrence.yaml` source; `${JEV_API_URL}` stays a placeholder. It is
the source configuration, not a read-back of the deployed spec.

**Reading the board.** Steps inside Expanso are its real processors. The dashed
line shows the path unknown records take to the decision model. Moving squares
illustrate that path at presentation speed; the counters and detail strip come
from pipeline receipts. A real answer lights the *Gate* chip. Unanswered
records are held for review.

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
just up-triage && just act2 && just act3
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
- **The decision model** judges lines the bypass did not clear. Its capacity
  depends on the selected model and hardware. The local Cribl adapter completed
  about 0.12 four-question decisions/sec in a nine-request check on this machine
  (2026-10-10); concurrency from one to three did not improve throughput.
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
| `JEV_GEN_RATE` | `1.67` | baseline source rate, about 100 lines/minute |
| `JEV_GEN_JAGGED` | `1` | `0` for a flat, metronomic source |
| `JEV_LIVE_PORT` | `8890` | dashboard port |
| `JEV_LIVE_GEN` | `generator2.py` | generator script |
| `JEV_LIVE_PIPELINE` | `http://127.0.0.1:8080/logs` | Edge HTTP input (chaos injection target) |
| `NODE_ID` | `laptop` | node label stamped on events |
| `CRIBL_DECISION_PORT` | `8100` | Local Cribl decision server listen port. |
| `CRIBL_DECISION_CACHE` | `~/.cache/cribl-decision` | Weights dir for the local Cribl server (~8GB). |

The pipeline's output directory is deliberately **not** a variable. It writes
`data/*.jsonl` relative to the Edge agent's working directory, and `start.sh`
`cd`s to this package before launching anything — so the files always land
in `data/` and `server.py` always tails exactly that. Nothing to configure,
nothing to desync, and the package works from any checkout location.

## Part two: run the decision model locally (Cribl cribl-decision-1.0)

Act three sends candidate records through the local gate. With the endpoint
below, answers come from [Cribl's cribl-decision-1.0](https://huggingface.co/cribl-ai/cribl-decision-1.0)
on this machine. The Cloud job and its four questions stay the same. It is
a 4B open-weight (Apache-2.0) decision model released October 2026
([announcement](https://cribl.io/blog/cribl-decision-1-0-a-foundation-for-telemetry-decision-models/)).

It speaks the same typed-question API as Jev -- `noul`, `choice`, `score`
over options you supply, probabilities out of a single forward pass, no
free-form text to parse -- so the pipeline needs no changes: point
`JEV_API_URL` at the local server and the cascade, the hold-and-release
degradation, and the dashboard all behave exactly as before. The only
difference is where the judgment happens.

```bash
# one time: fetch the weights (~8GB base + 77MB adapter)
uv run -s shared/cribl-decision-server.py --download-only

# every demo: start the local decision server (:8100)
uv run -s shared/cribl-decision-server.py

# in .env, alongside the other settings:
JEV_API_URL=http://127.0.0.1:8100/v1/systemone

# from the repository root, use a steady source rate:
JEV_GEN_RATE=1.67 JEV_GEN_JAGGED=0 just up-triage
just act2
just act3
```

Cribl requires no TypeSafe key or relay tunnel. The
server loads the weights once at startup (about 15s on Apple silicon after
the first run), then answers each 4-question request in ~5s on an M5 Max
with per-question latency on stderr. It reports
`"model": "cribl-decision-1.0-local"`, which the pipeline accepts like any
real answer -- only `"jev-unavailable"` triggers the hold path.

Two honest caveats. First, probabilities out of a 4B local model are
scores, not calibrated certainties: the cascade's confidence thresholds
were tuned against Jev, and in our side-by-side the local model runs
hotter on `actionable` (0.70s where the mock says 0.45) -- so watch where
it lands before trusting a page, and expect more `review` while you
recalibrate. Second, the weights live in `$CRIBL_DECISION_CACHE`
(default `~/.cache/cribl-decision`, ~8.8GB); Apple-silicon GPU via MPS
with a CPU fallback elsewhere.

## Troubleshooting

- **`JEV_API_URL is not set`** — export it first; start.sh refuses to run without it.
- **`expanso-edge` / `expanso-cli` not found** — install Expanso Edge v2+ and make
  sure both binaries are on PATH.
- **Port clash on 8890 / 8898 / 8080** — `lsof -i :8890` to find the squatter;
  or set `JEV_LIVE_PORT` to something free (8898 is the counter, 8080 the Edge input).
- **"Lost the dashboard server"** — server.py isn't running or died; check
  `logs/server.log`. The counters require receipts; flow motion is illustrative.
- **Board says "Jev is not answering", everything lands in REVIEW** — the
  pipeline can't reach Jev. Check `JEV_API_URL` and your key
  (`just doctor` probes the endpoint). This is the designed graceful degradation, not a bug.
- **Cloud lists the node as `connecting` after `just up`** — the Edge agent
may already be connected. The node list catches up on its next heartbeat;
the Cloud job can queue briefly while that happens.
- **Deployed in Cloud but the board stays on act one** — the job is running
  but its input never bound `:8080` here. Is the edge agent connected
  (`expanso-cli node list`)? Did the job land on this node?
- **Board serves stale code after a restart** — an older `server.py` still
  holds `:8890`. `just down` stops only processes whose saved identity matches.
- **Chaos button does nothing visible** — chaos lines are ~20s apart on purpose;
  give it a minute. Check `logs/server.log` for `chaos <name> line` entries.
- **Clean slate** — `just down` stops the `log-triage` job in Expanso Cloud
  and `just up-triage` truncates `data/*.jsonl`, so every run opens on zero counters.
- **`just up-triage` fails with "still bound to :8080"** — the agent is restarting
  a pipeline from a job Cloud no longer has. Run `just down`, then
  `just reset-agent`, then `just up-triage`.

## Tests

```bash
uv run -s tests/ui_server_tests.py    # dashboard server: endpoints, path safety
uv run -s tests/log_safety_test.py    # nothing sensitive reaches pipeline logs
uv run -s tests/stop_scope_test.py    # `just down` only touches this checkout
uv run -s tests/bypass_cases.py       # needs the stack up on act three
```
