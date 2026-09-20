# sensitivity-masking — Sensitivity classifier → edge masking

Every record gets sensitivity, PII and credential presence judged inline — restricted quarantines with an alert, the rest tokenize, mask, or pass through.

## Pipeline

`pipeline.yaml` — POST /records in; Jev judges sensitivity, contains_pii, contains_credentials; cascade quarantines+alerts, tokenizes, masks, or passes through.
The Jev call is
`POST ${JEV_API_URL}` with `jev-unavailable` graceful degradation.

`input.jsonl` — sample events for a quick test.

This is a pipeline only. For the full live treatment (generator, dashboard,
outage handling) see [`../01-log-triage/`](../01-log-triage/).

## Try the pipeline now

```bash
expanso-edge validate pipeline.yaml
```
