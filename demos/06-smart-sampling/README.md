# smart-sampling — Smart sampling: keep the interesting 1%

Every event gets an interestingness score — fascinating ones are all kept, the noise is deterministically sampled down to 1%.

## Pipeline

`pipeline.yaml` — POST /events in; Jev scores interesting; cascade keeps 100% at score ≥3, else a deterministic 1% via counter.
The Jev call is
`POST ${JEV_API_URL}` with `jev-unavailable` graceful degradation.

`input.jsonl` — sample events for a quick test.

This is a pipeline only. For the full live treatment (generator, dashboard,
outage handling) see [`../01-log-triage/`](../01-log-triage/).

## Try the pipeline now

```bash
expanso-edge validate pipeline.yaml
```
