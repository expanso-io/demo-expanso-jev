# ticket-router — Support ticket router

Every ticket gets department, intent, frustration and urgency judged inline — confidently urgent pages on-call, uncertain ones queue for humans.

## Pipeline

`pipeline.yaml` — POST /tickets in; Jev judges department, intent, frustration, urgency; cascade pages on-call, fills the priority queue and department queues, or holds for human triage.
The Jev call is
`POST ${JEV_API_URL}` with `jev-unavailable` graceful degradation.

`input.jsonl` — sample events for a quick test.

This is a pipeline only. For the full live treatment (generator, dashboard,
outage handling) see [`../01-log-triage/`](../01-log-triage/).

## Try the pipeline now

```bash
expanso-edge validate pipeline.yaml
```
