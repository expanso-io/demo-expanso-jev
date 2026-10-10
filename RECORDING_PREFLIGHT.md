---
status: PASS
record_check: PASS
record_check_evidence: "2026-10-10: just record-check passed (pipeline validate, pod-labels tests, ui-server tests, log safety tests, public-bar static lane 12/12 replays, lint-demo-ui --video clean, Playwright headless proof at 1440x900 and 1920x1080 with committed screenshots under docs/proof/)."
accepted_warnings: []
---

# Recording preflight — Expanso × Cribl Log Triage

## Claim

Deterministic edge filtering eliminates 70%+ of telemetry noise and costs before calling local decision models, routing exceptions live without unvetted cloud egress or dropped events during model degradation.

## Audience and objection

Platform, security, and observability engineers who believe deploying machine learning in hot telemetry ingestion paths is either too expensive, too slow, or risks dropping vital records during endpoint outages. This take proves deterministic pre-filtering keeps model costs bounded, while on-device buffers (`--kept`) prevent record loss when models fail.

## Capture surface

Local presenter browser at http://127.0.0.1:8890 (or http://127.0.0.1:54165 for replay proof) displaying the Expanso × Cribl triage board in 16:9 at 1440x900 and 1920x1080. Light mode by default with dark mode toggle available. No browser chrome in frame.

## Opening state

Act One opening: Synthetic production log flow active, straight ingest into raw log bucket with zero pipeline processing. Repeat messages accumulate unshaped. Ledger shows completed count rising, 0% model bypass, and identical recurring messages in the inspection card.

## Operator action

Three distinct acts:
1. Act One to Act Two: Operator deploys deterministic Expanso pipeline (`pipeline-logging.yaml`) via Cloud console or CLI. Edge agent shapes, hashes fingerprints, collapses duplicates, and routes routine traffic to archive.
2. Act Two to Act Three: Operator switches on Cribl decision model (`cribl-decision-1.0` 4B open weights served on-machine via `shared/cribl-decision-server.py`). The pipeline questions the model (Actionable, Severity, Team, Recurrence) only on unbypassed events.
3. Fault injection & recovery: Operator clicks "Break the link to model". Edge holds unrouted records locally in `--kept` buffer rather than guessing, then releases them once connectivity restores.

## Visible outcome

1. Stage routes split cleanly into four classified destinations: Page (critical severity), Notify (actionable team alert), Review (uncertain/human review), and Archive (routine).
2. Injection of disguised log ("INFO: health check 500") triggers model flag and routes to `notify` rather than baseline `archive`.
3. Link severance shows rising held count badge (`held on edge (--kept)`); restoring the link drains the buffer into correct downstream destinations with zero records dropped.

## Truth boundary

- Telemetry source: Synthetic application and auth server cluster generating 14 standard log patterns.
- Pipeline execution: Real Expanso Edge node running locally, connected to Expanso Cloud control plane.
- Decision model: Cribl `cribl-decision-1.0` (4B LoRA adapter on Qwen3.5-4B-Base) running on local machine via `shared/cribl-decision-server.py` on `:8100`, or local zero-credential mock server for offline verification. No external cloud inference calls.
- Destinations: Local JSONL sinks under `demos/01-log-triage/data/`.

## Proof evidence

1. Automated public-bar static lane acceptance across all 12 demo examples (`artifacts/public-bar.md`).
2. Mechanical preflight validation via `lint-demo-ui.py --video` reporting zero errors and zero warnings.
3. Isolated headless Playwright verification screenshots committed under `docs/proof/1440x900-triage-board.png` and `docs/proof/1920x1080-triage-board.png` confirming zero horizontal overflow, visible region callouts, and correct Expanso × Cribl branding.

## Decision

PASS for recording and review. All mechanical checks and layout invariants are verified and proven in headless automation. Cloud credentials and live cluster runs remain strictly segregated from the worktree.
