# inbox-triage — Gmail triage with Jev

Every email gets a tray (needs reply, updates, promos, sales, spam), an urgency score and a human-written judgment inline — urgent human mail raises an alert, uncertain mail queues for review, everything else files itself.

## Pipeline

`pipeline.yaml` — POST /inbox in; Jev judges tray, urgency and whether a human wrote it; the confidence-gated cascade raises alerts, fills the reply queue and review queue, archives spam, and files the rest by tray.
The Jev call is
`POST ${JEV_API_URL}` with `jev-unavailable` graceful degradation.

`input.jsonl` — sample events for a quick test.

`gmail_fetch.py` — the production fetch leg: a read-only Gmail API poller that dedupes by message ID and POSTs only new mail to /inbox.

## How it differs from jevmail

jevmail asks the same Jev judgment call on Gmail — five trays, a 1-5 urgency, a human-written check — but runs it as a local one-shot script. This demo wraps the same call in Expanso's deterministic substrate:

- **Deterministic dedupe** — the fetch leg tracks every forwarded message ID, so a redelivered or re-polled message is never judged twice.
- **Audit log of every judgment** — each event leaves the pipeline carrying its full Jev answers (tray, probabilities, urgency, human-written, model, latency) alongside the decision.
- **Confidence-gated review queue** — any tray judgment under 0.5 confidence lands in `review` instead of being filed on a guess.
- **Multi-user / team routing** — the fan-out output writes one queue per decision, ready to route to different people, tools or webhooks in production.

## Try the pipeline now

```bash
expanso-edge validate pipeline.yaml
```
