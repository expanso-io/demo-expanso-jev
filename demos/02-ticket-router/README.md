# 02 Support ticket router

Every ticket gets a department, an intent, a frustration score and an urgency judgment before a person reads it. Confident urgency pages on-call, strong frustration jumps the line, a weak department match waits for a human, and everything else goes to its department queue.

## Pipeline

`pipeline.yaml` — POST /tickets in; Jev judges department, intent, frustration, urgency; cascade pages on-call, fills the priority queue and department queues, or holds for human triage.
The Jev call is
`POST ${JEV_API_URL}` with `jev-unavailable` graceful degradation.

`input.jsonl` — sample events for a quick test.

The pipeline listens on `${INGEST_ADDRESS}` (default `127.0.0.1:8080`) and asks
`${JEV_API_URL}` (default: the bundled responder on `127.0.0.1:8099`, so nothing
leaves the host until you point it at Jev and set `TYPESAFE_API_KEY`). If Jev
cannot be reached, the pipeline fails safe: department confidence reads as 0, so rule three matches and every ticket waits in human triage.

## Step through it

Open [`index.html`](../../index.html#example=02-ticket-router) and choose this example. It
shows the real message going into and coming out of every stage, the request sent
to Jev and its answer, and the same run with Jev unreachable.

## Run it

```bash
uv run -s tools/fixture-runner.py run --only 02
```

The runner deploys `pipeline.yaml` unmodified to a local Edge agent, posts every
line of `input.jsonl` to `/tickets`, and compares what the pipeline wrote with
`fixtures/main.expected/`. It then repeats with Jev unreachable
(`fixtures/jev_down.expected/`). Jev's answers are replayed from
`fixtures/main.answers.json`; no model is called and no Cloud credentials are
needed. The dated report is in [`docs/verification/`](../../docs/verification/).

To run it by hand against the bundled responder, and to deploy it through
Expanso Cloud, use the run and deploy sections of the explorer page.
