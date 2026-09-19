# moderation — Moderation pre-filter

Every piece of content gets a category and a needs-human judgment — safe content auto-allows, the gray zone queues by (1 − confidence).

## Pipeline

`pipeline.yaml` — POST /content in; Jev judges category and needs_human; cascade auto-allows or queues for review.
The Jev call is
`POST ${JEV_API_URL}` with `jev-unavailable` graceful degradation.

`input.jsonl` — sample events for a quick test.

This is a pipeline only. For the full live treatment (generator, dashboard,
outage handling) see [`../01-log-triage/`](../01-log-triage/).

## Try the pipeline now

```bash
expanso-edge validate pipeline.yaml
```
