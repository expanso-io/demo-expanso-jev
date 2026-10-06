#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Prove the pod-label agent's grants against a real cluster.

    uv run -s rbac/verify.py --kubeconfig admin.kubeconfig --context jev-label-demo

Needs an administrator kubeconfig for the cluster you named (it only reads
authorization answers and mints one token). Every kubectl call names its
kubeconfig explicitly; nothing here touches your default context.

  1. `kubectl auth can-i` as the ServiceAccount: each grant the adapter uses
     must be allowed, and writes, secrets and other namespaces must be denied.
  2. The same calls made with the minted token: list, get, patch (an
     annotation, removed again), logs and exec. A Forbidden answer fails the
     check; any other error (a pod that has no shell) still proves the grant.

Exit 1 on any failure.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mint_kubeconfig import ACCOUNT, mint  # noqa: E402

results: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")


def kubectl(kubeconfig: Path, context: str | None, *args: str, timeout: int = 60):
    cmd = ["kubectl", "--kubeconfig", str(kubeconfig)]
    if context:
        cmd += ["--context", context]
    return subprocess.run(cmd + list(args), capture_output=True, text=True, timeout=timeout)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kubeconfig", required=True, type=Path)
    ap.add_argument("--context", required=True)
    ap.add_argument("--namespace", default="jev-label-demo")
    ap.add_argument("--pod", default="checkout-api", help="a pod in the namespace to patch and read")
    args = ap.parse_args()
    ns = args.namespace
    who = f"system:serviceaccount:{ns}:{ACCOUNT}"

    def can(verb: str, resource: str, *scope: str) -> bool:
        r = kubectl(args.kubeconfig, args.context, "auth", "can-i", verb, resource,
                    "--as", who, *scope)
        return r.stdout.strip() == "yes"

    allow = [
        ("list", "pods", ("--all-namespaces",)),
        ("get", "pods", ("-n", ns)),
        ("patch", "pods", ("-n", ns)),
        ("get", "pods/log", ("-n", ns)),
        ("create", "pods/exec", ("-n", ns)),
        ("get", "pods/exec", ("-n", ns)),
    ]
    deny = [
        ("delete", "pods", ("-n", ns)),
        ("create", "pods", ("-n", ns)),
        ("update", "pods", ("-n", ns)),
        ("get", "secrets", ("-n", ns)),
        ("list", "secrets", ("--all-namespaces",)),
        ("create", "rolebindings.rbac.authorization.k8s.io", ("-n", ns)),
        ("patch", "pods", ("-n", "kube-system")),
        ("create", "pods/exec", ("-n", "kube-system")),
        ("get", "pods/log", ("-n", "kube-system")),
        ("get", "pods", ("-n", "kube-system")),
    ]
    for verb, resource, scope in allow:
        check(f"allowed: {verb} {resource} {' '.join(scope)}", can(verb, resource, *scope))
    for verb, resource, scope in deny:
        check(f"denied:  {verb} {resource} {' '.join(scope)}", not can(verb, resource, *scope))

    with tempfile.TemporaryDirectory() as tmp:
        agent = Path(tmp) / "agent.kubeconfig"
        mint(args.kubeconfig, args.context, ns, agent, "10m", "agent")
        listed = kubectl(agent, "agent", "get", "pods", "--all-namespaces", "-o", "json")
        check("token: list pods in every namespace", listed.returncode == 0)
        got = kubectl(agent, "agent", "get", "pod", args.pod, "-n", ns, "-o", "json")
        check(f"token: get pod {args.pod}", got.returncode == 0)
        logs = kubectl(agent, "agent", "logs", args.pod, "-n", ns, "--tail=1")
        check("token: read logs", "forbidden" not in logs.stderr.lower(), logs.stderr.strip()[:80])
        patch = [{"op": "add", "path": "/metadata/annotations/jev.expanso.io~1rbac-probe", "value": "1"}]
        r = subprocess.run(
            ["kubectl", "--kubeconfig", str(agent), "--context", "agent", "-n", ns, "patch", "pod",
             args.pod, "--type=json", "--patch-file=/dev/stdin", "-o", "name"],
            input=json.dumps(patch), capture_output=True, text=True, timeout=60)
        check("token: patch the pod", r.returncode == 0, r.stderr.strip()[:80])
        undo = [{"op": "remove", "path": "/metadata/annotations/jev.expanso.io~1rbac-probe"}]
        subprocess.run(
            ["kubectl", "--kubeconfig", str(agent), "--context", "agent", "-n", ns, "patch", "pod",
             args.pod, "--type=json", "--patch-file=/dev/stdin"],
            input=json.dumps(undo), capture_output=True, text=True, timeout=60)
        ex = kubectl(agent, "agent", "exec", args.pod, "-n", ns, "--", "true")
        check("token: exec in the pod", "forbidden" not in ex.stderr.lower(), ex.stderr.strip()[:80])
        dele = kubectl(agent, "agent", "delete", "pod", args.pod, "-n", ns, "--dry-run=server")
        check("token: delete is refused", "forbidden" in dele.stderr.lower())
        sec = kubectl(agent, "agent", "get", "secrets", "-n", ns)
        check("token: reading secrets is refused", "forbidden" in sec.stderr.lower())
    print(f"{sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
