# soc-prefilter — SOC pre-filter

Every auth event gets a threat classification — brute force and credential stuffing escalate to the SIEM, benign noise goes to cold storage.

## Pipeline

`pipeline.yaml` — POST /auth-events in; Jev classifies threat and judges escalation; cascade hits the SIEM webhook, warm storage, or cold storage.
The Jev call is
`POST ${JEV_API_URL}` with `jev-unavailable` graceful degradation.

`input.jsonl` — sample events for a quick test.

This is a pipeline only. For the full live treatment (generator, dashboard,
outage handling) see [`../01-log-triage/`](../01-log-triage/).

## Try the pipeline now

```bash
expanso-edge validate pipeline.yaml
```
