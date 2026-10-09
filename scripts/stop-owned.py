#!/usr/bin/env python3
"""Record and stop a demo process only while its saved identity still matches."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def output(*args):
    result = subprocess.run(args, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def identity(pid):
    if output("ps", "-p", str(pid), "-o", "stat=").startswith("Z"):
        return None
    start = output("ps", "-p", str(pid), "-o", "lstart=")
    command = output("ps", "-p", str(pid), "-o", "command=")
    if not start or not command:
        return None
    proc = Path(f"/proc/{pid}/cwd")
    if proc.exists():
        cwd = str(proc.resolve())
    else:
        entries = output("lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn").splitlines()
        cwd = next((line[1:] for line in entries if line.startswith("n")), "")
    return {
        "pid": pid,
        "start": start,
        "command_hash": hashlib.sha256(command.encode()).hexdigest(),
        "cwd": cwd,
    }


def sidecar(pidfile):
    return pidfile.with_name(pidfile.name + ".identity.json")


def record(pidfile, root, match):
    pid = int(pidfile.read_text().strip())
    # uv and shell wrappers can exec shortly after launch; wait for the marker.
    for _ in range(30):
        saved = identity(pid)
        command = output("ps", "-p", str(pid), "-o", "command=")
        if saved and saved["cwd"] == str(root) and match in command:
            time.sleep(0.1)
            if identity(pid) != saved:
                continue
            sidecar(pidfile).write_text(json.dumps(saved) + "\n")
            return
        time.sleep(0.1)
    raise ValueError("Started process identity does not match this checkout")


def stop(pidfile, root, match):
    if not pidfile.exists():
        return
    pid = int(pidfile.read_text().strip())
    current = identity(pid)
    if current is None:
        pidfile.unlink()
        sidecar(pidfile).unlink(missing_ok=True)
        return
    if not sidecar(pidfile).exists():
        raise ValueError("No saved process identity; refusing to stop legacy PID")
    saved = json.loads(sidecar(pidfile).read_text())
    command = output("ps", "-p", str(pid), "-o", "command=")
    if current != saved or current["cwd"] != str(root) or match not in command:
        raise ValueError("Saved PID belongs to another process; leaving it alone")
    rows = output("ps", "-axo", "pid=,ppid=").splitlines()
    parents = {int(row.split()[0]): int(row.split()[1]) for row in rows}
    descendants = [pid]
    for parent in descendants:
        descendants.extend(child for child, owner in parents.items() if owner == parent)
    snapshots = {target: identity(target) for target in descendants}
    for target in reversed(descendants):
        owner_now = identity(pid)
        if owner_now is not None and owner_now != saved:
            raise ValueError("Owner identity changed during shutdown; leaving it alone")
        before = snapshots[target]
        if before is None:
            continue
        if identity(target) != before:
            raise ValueError(
                "Process identity changed during shutdown; leaving it alone"
            )
        try:
            os.kill(target, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for _ in range(50):
        if not any(
            identity(target) == snapshot
            for target, snapshot in snapshots.items()
            if snapshot
        ):
            pidfile.unlink(missing_ok=True)
            sidecar(pidfile).unlink(missing_ok=True)
            return
        time.sleep(0.1)
    raise ValueError("Owned process has not stopped; retaining its identity")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("record", "stop"))
    parser.add_argument("--pidfile", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--match", required=True)
    args = parser.parse_args()
    try:
        globals()[args.action](args.pidfile.resolve(), args.root.resolve(), args.match)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
