# Runbook

How to run, check and stop everything in this repository. Each section says what
passing looks like, so you know without asking anyone.

## 1. Check that every pipeline runs (no account, no model)

```bash
uv run -s tools/fixture-runner.py run
```

Passing looks like one `pass` line per case and a line ending
`report: docs/verification/<date>-fixture-run.md`. A failing case prints the queue
that differs. The runner needs `expanso-edge`, `expanso-cli` and `uv`; the
pod-labels case also needs Docker and `k3d`.

To check a single example: `--only 02`. To skip the pod-labels cluster run:
`--skip 11`. To re-record an example after you change its pipeline or input:

```bash
uv run -s tools/fixture-runner.py record --only 02
uv run -s tools/build-explorers.py
```

`record` rewrites that example's recorded answers, expected output and trace;
`build-explorers.py` rebuilds `index.html`, the stage files and the two manifests.
Commit all of it together: `tools/fixture-runner.py check` and
`tools/build-explorers.py --check` fail when they disagree.

## 2. Read the explorer

```bash
python3 tools/serve.py static 8777
```

Open http://127.0.0.1:8777, choose an example, a scenario and a record, then page
through the stages with the buttons or the Left and Right arrow keys. Stop it:

```bash
python3 tools/serve.py stop 8777
```

## 3. The shared public-example check

```bash
uv run -s .demo-kit/public-bar.py --selftest
uv run -s .demo-kit/public-bar.py --repo . --manifest public-bar.toml \
  --report artifacts/public-bar.md --lane all
```

The second command starts the services the manifest declares (the Jev responder,
the recurrence counter, the recorded adapter and the page server), replays every
pipeline, drives the page in a headless browser at 320, 400, 768 and 1440 pixels in
light and dark, and stops everything it started. It needs `PUBLIC_BAR_AXE_PATH` to
point at `axe.min.js` from the `axe-core` npm package, and Playwright's Chromium
(`playwright install chromium`). Passing looks like all five criteria `PASS` in
`artifacts/public-bar.md`. The vendored files must match the kit; do not edit them:

```bash
uv run -s <demo-kit>/sync-public-bar.py . --check
```

## 4. The live log-triage board

Needs Expanso Cloud credentials in `.env` (see `README.md`) and either a TypeSafe
key or the bundled responder.

```bash
just init
just jev-key        # optional: stores your TypeSafe key, hidden input
just doctor         # every line must read ok; a WARN about Jev means act three will hold
just up triage
just act2           # Expanso alone
just act3           # Expanso and Jev
just down triage
```

On the board, in act three, check four things:

1. The fine print at top right stays grey. Red means the board is talking to the
   bundled responder, not Jev.
2. PAGE and NOTIFY start filling within about 20 seconds.
3. The evidence strip reads `Decided by, Jev reported` with scores.
4. Click **INFO: health check 500**, wait about ten seconds, then click NOTIFY. A
   changed-value INFO line should reach the evidence strip with a severity-only
   baseline of ARCHIVE and the word "differs". Jev's judgment varies by day: if
   the line lands in REVIEW, a person looks at it; do not call it a notification.

Outage rehearsal: press **Break the link to Jev**, watch the held count climb for
about ten seconds, press **Restore the link**, watch it drain to 0. What happened
the last time this was measured against real Jev is in
[`verification/2026-09-19/real-jev/VERIFIED.md`](verification/2026-09-19/real-jev/VERIFIED.md);
what the Cloud log stream delivered is in
[`verification/2026-09-19/cloud-logs/VERDICT.md`](verification/2026-09-19/cloud-logs/VERDICT.md).

After `just down triage`, nothing should be left:

```bash
lsof -nP -iTCP:8080 -iTCP:8890 -iTCP:8898 -sTCP:LISTEN
```

An empty answer is the pass.

## 5. The live pod-labels board

Needs Docker, `k3d`, `kubectl`, Expanso Cloud credentials and a TypeSafe key.

```bash
just up        # builds a k3d cluster, applies the RBAC, starts the adapter, Edge and the Cloud job
just open      # http://127.0.0.1:8901
just down      # from another terminal; Ctrl-C in the first also works
```

`just up` prints READY when the Cloud execution is running on this node. The
adapter runs with a short-lived token for the least-privilege ServiceAccount; to
prove its grants on any cluster:

```bash
uv run -s demos/11-pod-labels/rbac/verify.py --kubeconfig "$KUBECONFIG" --context "$KUBE_CONTEXT"
```

Every line must read PASS. The manual path for your own cluster, and how to clean
up, is in [`demos/11-pod-labels/MANUAL_SETUP.md`](../demos/11-pod-labels/MANUAL_SETUP.md).

## 6. When something is wrong

- **The Edge agent keeps restarting a job Cloud no longer knows about:**
  `just down`, then `just reset-agent`.
- **A port is in use:** `lsof -nP -iTCP:<port> -sTCP:LISTEN`, then stop its owner.
  The fixture runner names the port it needs.
- **`expanso-cli` answers from the wrong network:** `EXPANSO_CLI_ENDPOINT` is
  mandatory here. See `AGENTS.md`.
- **A recorded answer is missing:** the runner reports it by count. Re-record that
  example (section 1).
