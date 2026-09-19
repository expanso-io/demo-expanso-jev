# A pod-label agent with Expanso Cloud and Jev

Implements [Nathan LeClaire's example](https://x.com/dotpem/status/2101432286214525156):
discover labels on every pod in a cluster, compare them with each target pod,
ask Jev whether to add missing labels, and reconsider additions when signals
change. Jev selects observed key/value pairs; it cannot invent labels.

Expanso Cloud schedules the pipeline on a selected Edge node. Every 15 seconds
the pipeline requests a fresh Kubernetes inventory, selects a candidate, calls
Jev through the local adapter, and requests a guarded patch. The adapter has
no timer or background reconciliation loop. Stopping the Cloud job stops
reconciliation. Everything uses the existing TypeSafe System One API.

The fixture makes labels matter: the `stable-checkout` Kubernetes Service
selects pods with `app=checkout` and `routing-tier=stable`. Adding the latter
label changes actual service membership. A signal about misrouted traffic can
cause Jev to remove it. The fixture includes an unrelated analytics pod so
copying every observed label is visibly wrong.

## Run

Requires `uv`, `kubectl`, Expanso CLI/Edge and a reachable Kubernetes cluster.
The optional disposable cluster below additionally needs a running Docker
daemon and `minikube`. From the repository root:

```bash
minikube start -p jev-label-demo --driver=docker
export KUBE_CONTEXT=jev-label-demo
kubectl --context "$KUBE_CONTEXT" apply \
-f demos/11-pod-labels/fixtures.yaml
```

For an existing cluster, explicitly set its context instead. The adapter reads
pods cluster-wide but only patches namespaces named in `POD_LABEL_NAMESPACES`.
Its Kubernetes identity needs `list` on pods cluster-wide, plus `get` and
`patch` on pods in the target namespaces. Use a disposable cluster for the
example: labels can change service routing, policy selection, and controller
behavior.

Configure root `.env` using the existing `.env.example`, then add settings
from this directory's `.env.example`. Keep it gitignored and mode 600.
The existing three Expanso credentials and `TYPESAFE_API_KEY` are required.
Generate `POD_LABEL_TOKEN` with a password manager or:

```bash
uv run python -c 'import secrets; print(secrets.token_hex(32))'
```

Place the output in `.env`; never pass credentials as command flags. Set
`POD_LABEL_APPLY=true` for actual writes. The default emits `dry-run` receipts
after real Jev inference and freshness checks.

In one terminal, run the adapter:

```bash
just pod-labels-adapter
```

In another, bootstrap and run a dedicated Cloud-connected agent. Its identity
and state remain under this repo's ignored `.expanso/pod-labels/` directory:

```bash
just pod-labels-edge
```

In a third terminal, inspect the intended network and node before deployment:

```bash
just pod-labels-nodes
just pod-labels-deploy
just pod-labels-status
```

The node list must show exactly one connected node labeled
`demo=jev-pod-labels`. The deploy helper enforces that count and checks the
local adapter can read Kubernetes before submission. Check the execution list:
it must name that node,
not merely show a stored job. Receipts are printed in the Edge terminal.

Observe the actual Kubernetes labels and Service endpoints:

```bash
export KUBE_CONTEXT=jev-label-demo
kubectl --context "$KUBE_CONTEXT" -n jev-label-demo \
get pods --show-labels
kubectl --context "$KUBE_CONTEXT" -n jev-label-demo \
get endpointslices -l kubernetes.io/service-name=stable-checkout
```

Jev's decisions are probabilistic. Expect matching checkout labels to be
favored and analytics labels rejected, but verify receipts and cluster state.
The default Noul threshold is 0.9; it is a demo policy, not an accuracy claim.
Only one candidate from a pod snapshot can be applied: each write advances
its resource version, so further changes wait for the next fresh tick.

## Supply a rollback signal

After `checkout-new` gains `routing-tier=stable`, inject a clearly identified
synthetic operational signal:

```bash
signal='Synthetic test: routing-tier=stable sent checkout traffic'
signal="$signal to this pod before rollout approval. Remove that"
signal="$signal routing label; team=payments remains correct."
kubectl --context "$KUBE_CONTEXT" -n jev-label-demo \
annotate pod checkout-new "jev.expanso.io/signal=$signal" \
--overwrite
```

When this candidate is next evaluated, the Cloud pipeline sends this signal,
pod status and the recorded change to Jev. A full cursor rotation may take
several minutes. An `undone` receipt plus the missing label and Service endpoints
prove the round trip. Readiness and container status are real Kubernetes
observations. The annotation above is synthetic evidence, not a measured
Istio outage or Kyverno denial. There is no bundled Istio or Kyverno install;
those systems can supply observations through the same signal annotation.

## What protects the round trip

- Only observed labels are candidates. Existing keys are never overwritten.
- Pod UID and resource version are checked both before mutation and inside
  the atomic Kubernetes JSON patch. Recreated or changed pods are held.
- Label addition and its ownership journal are one atomic patch. Restarting
  the adapter does not lose the information needed for undo.
- Undo removes only an addition still matching this agent's journal. Changes
  made by another writer are preserved. Withdrawn keys are not re-added.
- Jev failures, malformed answers, stale candidates and uncertain judgments
  cause no writes. `held`, `dry-run`, `applied` and `undone` are distinct.
- The loopback adapter authenticates every request, stores the actual Jev
  answer server-side, and rejects caller-supplied decisions. TypeSafe keys
  never enter Cloud job definitions or the Edge environment.

To reset the demonstration, stop the Cloud job and recreate the fixture
namespace. Clearing the journal while leaving its labels in place would lose
ownership; do not do that. This is a small demo, not a scalable controller:
all candidates are enumerated, but a rotating cursor selects just one per
tick so inference cannot build an expired batch. Tokens expire after 120
seconds. Larger clusters need batching and admission-policy integration.
Malformed ownership journals quarantine only the affected pod and are
reported in the adapter terminal.

## Stop and verify

```bash
just pod-labels-stop
just pod-labels-status
```

Wait for executions to stop, then Ctrl-C both foreground terminals. If you
created the disposable cluster above, remove it with:

```bash
minikube delete -p jev-label-demo
```

Do not delete an existing cluster. To remove only the fixture from an
existing cluster, delete the `jev-label-demo` namespace after stopping the
job. The example does not alter the existing log-triage processes or job.

## Local verification

```bash
just pod-labels-test
```

Tests cover discovery, namespace scope, inference failures, dry-run, patch
ownership, UID/resource-version changes, replay, restart-safe undo and
withdrawal. Pipeline validation is offline and does not prove Cloud
assignment, a real Jev response, or a Kubernetes mutation.
