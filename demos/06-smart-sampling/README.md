# 06 Smart sampling

Every event is scored for how interesting it is. Interesting events are all kept; routine noise is sampled at one in a hundred. How much volume this saves depends on how noisy your source is.

## Pipeline

`pipeline.yaml` — POST /events in; Jev scores interesting; cascade keeps 100% at score ≥3, else a deterministic 1% via counter.
The Jev call is
`POST ${JEV_API_URL}` with `jev-unavailable` graceful degradation.

`input.jsonl` — sample events for a quick test.

The pipeline listens on `${INGEST_ADDRESS}` (default `127.0.0.1:8080`) and asks
`${JEV_API_URL}` (default: the bundled responder on `127.0.0.1:8099`, so nothing
leaves the host until you point it at Jev and set `TYPESAFE_API_KEY`). If Jev
cannot be reached, the pipeline fails safe: every event is kept. Losing data costs more than the extra volume, so sampling pauses until Jev answers.

## Step through it

Open [`index.html`](../../index.html#example=06-smart-sampling) and choose this example. It
shows the real message going into and coming out of every stage, the request sent
to Jev and its answer, and the same run with Jev unreachable.

## Run it

```bash
uv run -s tools/fixture-runner.py run --only 06
```

The runner deploys `pipeline.yaml` unmodified to a local Edge agent, posts every
line of `input.jsonl` to `/events`, and compares what the pipeline wrote with
`fixtures/main.expected/`. It then repeats with Jev unreachable
(`fixtures/jev_down.expected/`). Jev's answers are replayed from
`fixtures/main.answers.json`; no model is called and no Cloud credentials are
needed. The dated report is in [`docs/verification/`](../../docs/verification/).

To run it by hand against the bundled responder, and to deploy it through
Expanso Cloud, use the run and deploy sections of the explorer page.
