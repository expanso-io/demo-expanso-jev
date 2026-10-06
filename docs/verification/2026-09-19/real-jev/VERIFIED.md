# Verified against real Jev — 2026-09-19

Model `jev-1.13.0` at `https://api.typesafe.ai/v1/systemone`, reached through
the dashboard server's gate, which adds the Bearer key. No relay, no tunnel, no
mock: the board's `mock` flag was `false` throughout. Pipeline deployed through
Expanso Cloud (job `log-triage`, node `0c2d2a69`). Events are synthetic and the
destinations are local JSONL demo files.

## 1. Auth and reachability

Unauthenticated call to the API: HTTP 403. Through the gate with the key: a
real response from Jev. `/health` reports `upstream_auth: true` and never the
key itself.

## 2. Selective inference, measured

First run, 35 s: 1,091 completed records, **942 skipped the model (86.3%)**, 149
judged, 0 failed. Destinations: page 23, notify 93, review 29, archive 946.
`skipped + judged + failed == completed`.

## 3. The quiet INFO line

`INFO api: config reload requested by unknown actor`. The severity-only baseline
(ERROR→page, WARN→notify, INFO→archive) archives it every time. Real Jev
**never archived it**: 6× REVIEW, 3× NOTIFY. Reported actionable 0.65–0.69,
severity `warning` at 0.57–0.80 confidence.

Recurrence visibly moves the judgment. The injected
`… session=chaosghost` line, same text each time:

| Occurrence | actionable | severity (confidence) | destination |
|---|---|---|---|
| 1 | 0.21 | info (0.40) | review |
| 2 | 0.35 | warning (0.51) | review |
| 3 | 0.66 | warning (0.59) | review |

## 4. The bypass contract, with real judgments

`bypass-cases-real-jev.txt`, 10/10. Exact known-benign lines: archived, no model
call. Everything else was judged by Jev, and the results are the demo's best
material, because every one of these is labelled INFO and a severity rule files
them all away:

| Input (level INFO) | Severity-only | Real Jev |
|---|---|---|
| `GET /health 500 2ms` | archive | **notify** |
| `cache hit rate 0.01 window=5m` | archive | **notify** |
| `gc pause 8400ms heap=1.2gb` | archive | **notify** |
| `config reload requested by unknown actor` | archive | **notify** |
| `GET /health 200 9000ms` | archive | review |

And the other direction: an **ERROR** whose message was the routine
`GET /health 200 2ms` went to the **archive**; four routine WARNs
(timestamp drift, a deprecated-API notice, one auth failure) were archived
where the baseline would have notified.

These are single observed judgments on selected synthetic inputs. They show what
Jev did here. They are not an accuracy measurement and must not be presented as
one. A rule could catch any of these lines once someone knew to write it.

## 5. Outage, hold, release

Gate set to `overloaded` for 13 s: **30 records held**, routine traffic steady at
~30/s, nothing judged, nothing failed. Gate reopened: **all 30 released within
4 s** as real Jev judgments. `released == held_in`, `gave_up == 0`.

## Screenshots (real system, 1728×1000)

`real-act3-flow`, `real-modal-notify`, `real-outage-held`,
`real-outage-released`.

## Still not verified

- The Expanso Cloud **Logs tab** in a browser (WebSocket delivery by job UUID is
  verified; the rendered page is not).
- The actual recording viewport on the recording machine.
- The `start.sh` cleanup-on-failed-start path.
