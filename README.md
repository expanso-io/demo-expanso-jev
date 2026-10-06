# Expanso × Jev

Put a model in the hot path of your logs without paying for it on every line.

![The log triage board: production logs flow into an Expanso Edge pipeline, a small share go up to Jev, and records fan out to page, notify, review and archive](docs/board.png)

Most log lines are routine, and a rule can say so instantly. A few are not, and
no rule you have written yet knows which. This repository shows one way to
handle both in a single pipeline:

- **[Expanso Edge](https://expanso.io)** runs next to the source. It shapes each
  record, fingerprints it, counts how often it has been seen, and sends known
  routine lines straight to the archive with no model call.
- **[Jev](https://typesafe.ai)**, TypeSafe's structured classifier, is asked only
  about what is left. It answers four questions per record (actionable?
  severity? owning team? recurrence concern?) and the pipeline routes on the
  answers: page, notify, review, or archive.
- When Jev cannot be reached, the pipeline **holds** those records, keeps
  routine traffic moving, and releases the backlog when Jev answers again.
  Nothing is guessed and nothing is dropped.

In our runs about nine lines in ten never touched the model. Your number will
differ; the board measures it live.

## Step through every example

Open [`index.html`](index.html) for all eleven examples. Each one has an
explanation, a stage-by-stage explorer that shows the real message going in and
coming out of every processor (page with the buttons or the Left and Right arrow
keys), and run and deploy instructions. To serve it locally:

```bash
python3 tools/serve.py static 8777
```

Then open http://127.0.0.1:8777 and stop it with
`python3 tools/serve.py stop 8777`. Every value on the page was captured from a
run of the pipeline in this repository.

## Check that every pipeline runs, with no account

```bash
uv run -s tools/fixture-runner.py run
```

The runner deploys each shipped pipeline, unmodified, to a local
`expanso-edge run --local` agent, posts every line of its `input.jsonl`, and
compares what the pipeline wrote with the expected output in `fixtures/`.
Examples 02 to 10 and the log-triage outage also run with Jev unreachable. The
pod-labels example runs on a throwaway k3d cluster with the least-privilege
ServiceAccount in [`demos/11-pod-labels/rbac`](demos/11-pod-labels/rbac). Jev's
answers are replayed from recorded files, so nothing calls a model and no
Expanso Cloud credentials are needed. It writes a dated report to
[`docs/verification/`](docs/verification/); the latest is linked from
`index.html`.

It needs `expanso-edge`, `expanso-cli` and [`uv`](https://docs.astral.sh/uv/),
plus Docker and `k3d` for the pod-labels case.

## What you need for the live demos

- macOS or Linux, [`just`](https://github.com/casey/just), `python3`, `curl`,
  and `uv`.
- Expanso Edge and the Expanso CLI, v2 or later, on your `PATH`
  (`expanso-edge`, `expanso-cli`). See the [Expanso docs](https://docs.expanso.io).
- An [Expanso Cloud](https://cloud.expanso.io) network. The live demos deploy
  through Expanso Cloud; the agent on your machine runs the pipelines.
- A TypeSafe API key for Jev. No key yet? Use the bundled responder (below).
  The board labels its answers in red, because they are keyword rules and not
  inference.

## Pod-label browser demo

Three ordinary Kubernetes pods stream logs to Expanso Cloud. Choose a pod
and one of two live workflows:

- **Label:** Jev judges proposed labels and reversals. The board
  shows actual Kubernetes Service membership and observed label sources.
- **Investigate:** Jev assesses restart evidence and returns Wait or
  Investigate. Details stay collapsed; no additional model is invoked.

Source incidents are scripted by the workload in `demos/11-pod-labels/scenario/`. Cloud execution, Jev responses,
Kubernetes patches, and Service membership are real.

```bash
just up
```

Open **http://127.0.0.1:8901** after READY. See the
[pod demo prerequisites and runbook](demos/11-pod-labels/README.md).
Inside `demos/11-pod-labels`, `just up` runs that demo directly.
At the root, `just up`, `just down`, `just open`, `just status`, and
`just test` target the pod demo. Add `triage` to lifecycle commands for
the original log-triage demo.

## Log-triage quickstart

```bash
just init        # creates .env from .env.example
$EDITOR .env     # the three EXPANSO_* values from your Cloud network
just jev-key     # prompts for your TypeSafe key (hidden input)
just doctor      # checks tools, credentials and reachability
just up triage   # takes about a minute; opens on "no pipeline"
just open triage # http://127.0.0.1:8890
```

Then walk through it:

```bash
just act2        # deploy the Expanso-only pipeline
just act3        # deploy the version that adds Jev
just down triage # stop everything, including the job in Cloud
```

You can also deploy the two YAML files from the Expanso Cloud console, or flip
the Jev switch on the board. The board follows whatever is actually running.

**Without a TypeSafe key:** run `uv run shared/jev-mock-server.py` in another
terminal, set `JEV_API_URL=http://127.0.0.1:8099/v1/systemone` in `.env`, and
skip `just jev-key`.

`just` on its own lists every recipe. `just status` shows what is alive,
`just logs <name>` tails a component, and `just reset-agent` clears the agent's
local execution store if it ever restarts a pipeline Cloud no longer knows about.

## The three acts

| | What is deployed | What happens |
|---|---|---|
| 1 | nothing | Every log line is shipped, exactly as written, to a raw bucket. |
| 2 | `pipeline-logging.yaml` | Expanso shapes, fingerprints and counts each record. Everything is archived, now structured. |
| 3 | `pipeline-recurrence.yaml` | Known routine lines skip the model. Everything else goes to Jev, with its history, and is routed on the answer. |

On the board you can inject a log line and follow it as one large square
through the pipeline, up to Jev and back, and into the bucket it really landed
in. **Break the link to Jev** makes every Jev call fail so you can watch the hold and
the release. Click any bucket for the latest record's full JSON, grouped by who
added each field.

Details, environment variables and troubleshooting:
[`demos/01-log-triage/README.md`](demos/01-log-triage/README.md).

## What is in here

| Path | What |
|---|---|
| `demos/01-log-triage/` | The full live demo: generator, two pipelines, dashboard, tests. |
| `demos/02-…` to `demos/10-…` | Nine more Expanso + Jev pipelines, each with a `pipeline.yaml`, a sample `input.jsonl`, recorded fixtures and a README: ticket routing, sensitivity masking, sensor triage, agent guardrails, smart sampling, SOC pre-filtering, data quality, moderation, feedback mining. Each is explained and stepped through in `index.html`. |
| [`demos/11-pod-labels/`](demos/11-pod-labels/README.md) | Keeps Kubernetes pod labels true: Expanso reads pod logs, asks Jev one question when the evidence might change a label, and patches or un-patches it. Runs on a local k3d cluster with one command; the adapter and pipeline work on your own cluster too. |
| `shared/jev-mock-server.py` | A zero-credential responder for Jev's API, using keyword rules. It produced the recorded answers the fixture runs replay. |
| `index.html` | The explorer for all eleven examples. Built by `tools/build-explorers.py` from the fixture runs. |
| `tools/fixture-runner.py` | Runs every pipeline on its shipped input and asserts the output; writes the dated report. |
| `public-bar.toml`, `public-features.json`, `.demo-kit/` | The shared public-example check and the retained-feature baseline. See [`docs/RUNBOOK.md`](docs/RUNBOOK.md). |
| `docs/verification/` | Dated run reports and the earlier Cloud and real-Jev verification reports. |
| `tools/expanso-agent-help.py`, `AGENTS.md` | How the Expanso CLIs take credentials from the environment, for people and coding agents. `just agent-help`. |

## What this does and does not show

- The events are synthetic, and the four destinations are local JSONL files,
  not a pager or a chat tool. The board says so on screen.
- Jev's answers are real when you use a real key, but they are observed
  judgments on sample events. This repository makes no accuracy claim.
- The routine-line allowlist matches exact messages on purpose. A fingerprint
  erases numbers, and `GET /health 500` must not pass as `GET /health 200`.
- The outage comes from a local gate that every Jev call passes through.
  The failed calls, the hold and the release are the pipeline's real behavior.
- Credentials live in `.env` and in a project-local agent directory, both
  gitignored. The TypeSafe key never enters a pipeline file, Expanso Cloud, or
  a command line.

## License

Apache-2.0, see [`LICENSE`](LICENSE). Not covered by it: the vendored fonts under
`demos/01-log-triage/fonts/` (IBM Plex and Big Shoulders Display, SIL Open Font
License 1.1), and the Expanso and TypeSafe marks under
`demos/01-log-triage/assets/`, which are trademarks of their owners.
