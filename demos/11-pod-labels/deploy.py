"""Submit only to a known connected adapter host in the pinned Cloud network."""

import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request


def selected_node(nodes):
    if len(nodes) != 1 or nodes[0]["status"]["connection_state"] != "connected":
        raise ValueError("exactly one connected demo=jev-pod-labels node is required")
    return nodes[0]["id"]


def main():
    for name in ("EXPANSO_CLI_ENDPOINT", "EXPANSO_CLI_AUTH_API_KEY", "POD_LABEL_TOKEN"):
        if not os.environ.get(name):
            raise ValueError(name + " must be set; no global-profile fallback")
    result = subprocess.run(
        [
            "expanso-cli",
            "node",
            "list",
            "--label",
            "demo=jev-pod-labels",
            "--limit",
            "2",
            "--format",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    node_id = selected_node(json.loads(result.stdout))
    root = Path(__file__).resolve().parents[2]
    connection = root / ".expanso/pod-labels/config.d/50-connection.yaml"
    local_ids = re.findall(
        r"(?m)^\s*node_id:\s*[\"']?([0-9a-f-]{36})", connection.read_text()
    )
    if local_ids != [node_id]:
        raise ValueError(
            "selected Cloud node does not match this adapter host's identity"
        )
    # Prove the intended local adapter can read the intended Kubernetes API.
    req = urllib.request.Request(
        "http://127.0.0.1:8901/candidates",
        data=b"{}",
        headers={
            "Authorization": "Bearer " + os.environ["POD_LABEL_TOKEN"],
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        if not isinstance(json.load(response), list):
            raise ValueError("adapter did not return a candidate list")
    pipeline = str(Path(__file__).with_name("pipeline.yaml"))
    subprocess.run(["expanso-edge", "validate", pipeline], check=True, timeout=30)
    subprocess.run(["expanso-cli", "job", "deploy", pipeline], check=True, timeout=30)
    print("Submitted to Cloud; verify running execution on node " + node_id)


if __name__ == "__main__":
    main()
