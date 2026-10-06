# Cloud log observability — current verdict, 2026-09-19

| Claim | Status |
|---|---|
| Operational logs emitted correctly on the node | **PASS** (local evidence) |
| Delivery through Expanso Cloud's log WebSocket, by job UUID | **PASS** |
| The console's log-tailing sequence, as read in source | **DID NOT PASS**: its first step, `POST /jobs/<uuid>/logs`, returned 404 |
| The deployed browser Logs tab | **UNVERIFIED**: nobody opened it |

## Delivery through Cloud: PASS

Run `1789843827` (`console-stream-check-*.txt`, capture `console-stream-capture-*.txt`).
Existing job `log-triage` (`j-d08c2d08-14c7-4e22-a716-72befb89e956`) rerun by
UUID, no redeploy; running execution confirmed on node `0c2d2a69`;
`wss://…/api/v1/jobs/<uuid>/logs/proxy` opened with the console's LogQL query and
an API key as a Bearer header. Two events posted after the socket opened came
back through Cloud, matched by `sha256(id)[:12]`:

```
triage fallback -> REVIEW selected, output pending: Jev gave no answer, nothing guessed (…) event=ab7ab76931a1 fp=ce248a777bc6 occ=1 svc=net lvl=WARN
triage bypass -> ARCHIVE selected, output pending: known-routine line, no model call (…) event=473d8390ccaa fp=2375b9c133c1 occ=1 svc=api lvl=INFO
```

No message text in either. No `judged` line, correctly: Jev was unreachable and
no mock was used, so the judged format is unexercised. By UUID, both `/logs`
and `/logs/proxy` accepted the handshake (101).

## The console: sequence did not pass, tab unverified

The harness continued past the 404 on `POST /jobs/<uuid>/logs`. The inspected
`useLogTailing.ts` does not: it returns on that error, so that checkout would
stop before opening the socket. That checkout may be older than the deployed
frontend, so this does not show the deployed console is stale or broken. The
harness also authenticated with an API key where a browser uses a session
cookie. One look at the tab in a real browser, on a running job, settles it.

## Using it

Tail by the job's **UUID, not its name**, while the job is running. Streaming is
live-only: nothing is shipped until someone is tailing, and there is no history.

```bash
expanso-cli job list --namespace demo     # copy the full j-… id
expanso-cli job logs <job-uuid> | grep triage
```

By name, `expanso-cli job logs log-triage` was refused with
`websocket: bad handshake` on two runs, including with the job running. The
endpoint accepts the UUID; upstream source (`ff83c399`, `node_resolver.go`) looks
executions up by the raw value with no name resolution. `expanso-cli job logs
<uuid>` itself has not been run, and that source is not proven to match the
deployed binaries, so treat name-vs-id as the likely cause, not a proven one.

## What the log lines are

- A destination was **selected**, the write is pending: the log runs before the
  output does. `write_confirmed=false`. Never "written", "kept" or "retained".
- Nothing passes through raw. Level, service, team and severity go through
  closed allowlists; every event id and fingerprint is `sha256[:12]`,
  recomputable from a local receipt. No message text, prompt, model body, URL or
  credential. `log_safety_test.py`: 44/44, with a negative control.
- **Only the routine path is sampled**: a bypass checkpoint on a fingerprint's
  first occurrence and every 250th after, per fingerprint, not a global rate.
  **Every non-bypass selection is logged**, judged (INFO) or fallback (WARN).
  The fingerprint erases numbers, so `GET /health 500` shares a counter with the
  routine `GET /health 200`; sampling that branch by occurrence would silence
  exactly the changed-value line worth seeing.
- Limit, stated plainly: this is sized for a synthetic demo where non-routine
  traffic is a few lines a second. With Jev unreachable, every non-routine
  record is a WARN. High-volume production traffic needs a real rate cap, which
  needs state this pipeline does not keep.

## Two things the stream showed that are not ours

- Its default level includes **DEBUG**: 7 of 9 lines received were framework
  chatter ("Consumed 1 messages", "Successfully wrote"). Filter on `triage`.
- The framework's own ERROR line for a failed model call ships the endpoint URL
  to Cloud (`http://127.0.0.1:8899/v1/systemone` here, a localhost tunnel). A
  real `JEV_API_URL` would be shipped the same way.

## What the evidence covers, exactly

The Cloud run exercised the config as deployed at v19/v20, where the fallback
branch was still sampled. The change to log every non-bypass selection was made
afterwards and is **not deployed and not re-run**: the checked-in
`pipeline-recurrence.yaml` is ahead of the stopped Cloud job. The Cloud evidence
establishes delivery and line format for the two cases emitted. It does not
establish the new every-record behaviour; that is covered by `expanso-edge
validate` and the static guard only, until the next deploy.

Local-only evidence (`local-pipeline-log-evidence.txt`): 12 fallback lines on
the node, none with payload text, all 12 correlating by hash to local receipts.

## State

Job `log-triage` stopped at **v20** (`job rerun` creates a version). Node
`0c2d2a69` disconnected. No listeners, no processes. Spec and `data/*.jsonl`
were copied to `.codex-work/2026-09-19/jev-cloud-logs/preserve/` before every
run; the appended `logcheck-` receipts were kept. Earlier attempts and their
reports are preserved alongside this file.
