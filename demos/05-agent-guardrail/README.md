# agent-guardrail — Agent guardrail: safety check on every tool call

Every tool call is judged for intent match and risk before it runs — exfiltration and privilege escalation block with an alert, the gray zone holds for approval.

## Pipeline

`pipeline.yaml` — POST /tool-calls in; Jev judges intent_match and risk; cascade blocks+alerts, holds for approval, or allows.
The Jev call is
`POST ${JEV_API_URL}` with `jev-unavailable` graceful degradation.

`input.jsonl` — sample events for a quick test.

This is a pipeline only. For the full live treatment (generator, dashboard,
outage handling) see [`../01-log-triage/`](../01-log-triage/).

## Try the pipeline now

```bash
expanso-edge validate pipeline.yaml
```
