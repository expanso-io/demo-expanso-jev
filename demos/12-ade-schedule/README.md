# 12 ADE schedule builder

Twenty-nine real Amsterdam Dance Event 2026 parties go in; three ranked lists
come out. Expanso enriches each event (epoch times, weekday, time slot, lineup
size), scores it against your taste with deterministic rules, and routes it to
**must-see**, **worth-it**, or **pass**.

No model is called anywhere in this pipeline. That is the point: it is the
deterministic substrate the other examples pair with Jev. Where those examples
spend model calls on judgment, this one shows what plain Expanso rules can do
when the decision is fully specified.

## Pipeline

`pipeline.yaml` — POST /events in; enrich, score, decide, route. Taste comes
from the agent's environment:

- `ADE_GENRES` — comma-separated genres you love (default `techno,house`)
- `ADE_ARTISTS` — comma-separated artists you follow (default
  `ben klock,dvs1,kink,amelie lens`)
- `ADE_LATE_NIGHT=yes` — opt in to post-midnight starts (default: penalized)

`input.jsonl` — 29 representative ADE 2026 events from public sources
(amsterdam-dance-event.nl). A sample, not the full program; some published
times were approximate.

The pipeline listens on `${INGEST_ADDRESS}` (default `127.0.0.1:8080`).

## Step through it

Open [`index.html`](../../index.html#example=12-ade-schedule) and choose this example. It
shows the real event going into and coming out of every stage.

## Run it

```bash
uv run -s tools/fixture-runner.py run --only 12
```

The runner deploys `pipeline.yaml` unmodified to a local Edge agent, posts every
line of `input.jsonl` to `/events`, and compares what the pipeline wrote with
`fixtures/main.expected/`. No model is called and no Cloud credentials are
needed. The dated report is in [`docs/verification/`](../../docs/verification/).

To run it by hand and to deploy it through Expanso Cloud, use the run and
deploy sections of the explorer page.
