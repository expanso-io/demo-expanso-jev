#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write a kubeconfig that holds only the pod-label agent's short-lived token.

    uv run -s rbac/mint_kubeconfig.py \
        --admin-kubeconfig .expanso/pod-labels/kubeconfig \
        --admin-context jev-label-demo \
        --namespace jev-label-demo \
        --out .expanso/pod-labels/agent.kubeconfig

The administrator credentials are used once, here, to ask the API server for a
token on the pod-label-agent ServiceAccount (rbac/rbac.yaml). The adapter then
runs with the file this writes and can do nothing the Role and ClusterRole do
not allow. The token expires; mint again to renew it. Credentials go to a file
created with mode 600, never to a command line.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ACCOUNT = "pod-label-agent"


def kubectl(*args: str) -> str:
    result = subprocess.run(
        ["kubectl", *args], capture_output=True, text=True, timeout=60
    )
    if result.returncode:
        raise SystemExit("kubectl " + args[2] + " failed: " + result.stderr.strip())
    return result.stdout


def mint(admin_kubeconfig: Path, admin_context: str, namespace: str, out: Path,
         duration: str = "8h", context_name: str | None = None) -> None:
    base = ["--kubeconfig", str(admin_kubeconfig), "--context", admin_context]
    token = kubectl(*base, "create", "token", ACCOUNT, "-n", namespace,
                    "--duration", duration).strip()
    view = json.loads(kubectl(*base, "config", "view", "--raw", "--minify", "-o", "json"))
    cluster = view["clusters"][0]["cluster"]
    name = context_name or admin_context
    config = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{"name": name, "cluster": {
            key: cluster[key] for key in ("server", "certificate-authority-data") if key in cluster
        }}],
        "users": [{"name": ACCOUNT, "user": {"token": token}}],
        "contexts": [{"name": name, "context": {
            "cluster": name, "user": ACCOUNT, "namespace": namespace}}],
        "current-context": name,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(config, stream, indent=2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--admin-kubeconfig", required=True, type=Path)
    ap.add_argument("--admin-context", required=True)
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--duration", default="8h")
    ap.add_argument("--context-name")
    args = ap.parse_args()
    mint(args.admin_kubeconfig, args.admin_context, args.namespace, args.out,
         args.duration, args.context_name)
    print(f"wrote {args.out} (mode 600, token expires in {args.duration})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
