# feedback-miner — Feedback miner

Every feedback item gets topic, sentiment and churn risk — at-risk accounts alert their team, bugs flow to eng, everything lands in analytics.

## Pipeline

`pipeline.yaml` — POST /feedback in; Jev judges topic, sentiment, churn_risk; cascade alerts the account team, queues eng, or records analytics.
The Jev call is
`POST ${JEV_API_URL}` with `jev-unavailable` graceful degradation.

`input.jsonl` — sample events for a quick test.

This is a pipeline only. For the full live treatment (generator, dashboard,
outage handling) see [`../01-log-triage/`](../01-log-triage/).

## Try the pipeline now

```bash
expanso-edge validate pipeline.yaml
```
