# sensor-triage — Sensor anomaly triage

Every reading gets an anomaly score and a dispatch judgment — real anomalies become work orders, the rest roll up to files.

## Pipeline

`pipeline.yaml` — POST /readings in; Jev scores anomaly and judges dispatch; cascade fires a work-order webhook, flags files, or rolls up.
The Jev call is
`POST ${JEV_API_URL}` with `jev-unavailable` graceful degradation.

`input.jsonl` — sample events for a quick test.

This is a pipeline only. For the full live treatment (generator, dashboard,
outage handling) see [`../01-log-triage/`](../01-log-triage/).

## Try the pipeline now

```bash
expanso-edge validate pipeline.yaml
```
