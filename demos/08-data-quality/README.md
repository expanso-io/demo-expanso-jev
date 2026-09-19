# data-quality — Data quality firewall

Every row gets a quality score and a conformance judgment — garbage quarantines before it can poison the warehouse.

## Pipeline

`pipeline.yaml` — POST /rows in; Jev scores quality and judges conformance; cascade quarantines to file or passes to the warehouse file.
The Jev call is
`POST ${JEV_API_URL}` with `jev-unavailable` graceful degradation.

`input.jsonl` — sample events for a quick test.

This is a pipeline only. For the full live treatment (generator, dashboard,
outage handling) see [`../01-log-triage/`](../01-log-triage/).

## Try the pipeline now

```bash
expanso-edge validate pipeline.yaml
```
