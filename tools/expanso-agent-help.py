#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Agent help for expanso-cli and expanso-edge: which env vars actually exist.

Why this exists
---------------
Neither binary documents its environment variables in `--help`, and the names
do not match the flags: `--api-key` is `EXPANSO_CLI_AUTH_API_KEY`, because the
env name is derived from the config key `auth.api_key`, not from the flag.
An agent that guesses from flag names gets nothing, concludes env support does
not exist, and puts the secret in argv where `ps` can read it.

Worse, the failure is silent and looks like success: with an unrecognised env
var and no flags, expanso-cli falls back to whichever profile is selected in
~/.expanso/cli-client/profiles/current and answers from a DIFFERENT network.

Reported to Expanso, with a request for `agent-help` in the binaries themselves. Until that ships, this script is the local stand-in.

It introspects the INSTALLED binaries rather than hardcoding a list, so it
cannot drift from the version actually on PATH.

    uv run -s tools/expanso-agent-help.py            # human table
    uv run -s tools/expanso-agent-help.py --json     # machine readable
    uv run -s tools/expanso-agent-help.py --probe    # prove which ones work
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# Flag <-> env pairs confirmed by hand against v2.1.21. `strings` finds the
# names the binary stores literally; it cannot recover the ones koanf builds at
# runtime from the config struct (EXPANSO_CLI_AUTH_API_KEY is one of those), so
# the known table below fills the gap and the binary scan catches anything new.
KNOWN = {
    "expanso-cli": [
        ("EXPANSO_CLI_ENDPOINT", "--endpoint", False, "API endpoint URL"),
        ("EXPANSO_CLI_AUTH_API_KEY", "--api-key", True, "API key (exp_ak_...)"),
        ("EXPANSO_CLI_PROFILE", "--profile", False, "Named profile to use"),
        ("EXPANSO_CLI_TIMEOUT", "--timeout", False, "Request timeout"),
        ("EXPANSO_CLI_TLS_INSECURE", "--insecure", False, "Skip TLS verification"),
    ],
    "expanso-edge": [
        ("EXPANSO_EDGE_BOOTSTRAP_TOKEN", "--token", True, "Cloud bootstrap token (exp_bk_...)"),
        ("EXPANSO_EDGE_BOOTSTRAP_URL", "--url", False, "Bootstrap service URL"),
        ("EXPANSO_EDGE_ENROLL_TOKEN", "--token", True, "Direct-orchestrator enrollment token"),
        ("EXPANSO_EDGE_ENROLL_ORCHESTRATOR", "--orchestrator", False, "Orchestrator address"),
    ],
}

# Names that look plausible and are silently ignored. Listed so an agent can
# rule them out without burning a probe cycle on each.
IGNORED = [
    "EXPANSO_API_KEY", "EXPANSO_CLI_API_KEY", "EXPANSO_CLI_APIKEY",
    "EXPANSO_AUTH_API_KEY", "EXPANSO_ENDPOINT", "EXPANSO_API_TOKEN",
]


def scan_binary(path: str) -> list[str]:
    """Env-var-shaped strings stored literally in the binary."""
    try:
        out = subprocess.run(["strings", "-a", path], capture_output=True,
                             text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    # Trailing junk is common: `strings` runs adjacent constants together, so
    # EXPANSO_EDGE_BOOTSTRAP_TOKENU is really ...TOKEN followed by a "U".
    found = {m.rstrip("_") for m in re.findall(r"EXPANSO_[A-Z0-9_]{2,}", out)}
    return sorted(n for n in found if not n.endswith("_"))


def probe_cli(endpoint: str, key: str) -> dict[str, bool]:
    """Empirically confirm which names the CLI honours, right now.

    Positive control first: the pair we believe in must WORK, otherwise the
    probe itself is broken and every negative below it is meaningless.
    """
    def run(env_extra: dict[str, str]) -> bool:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("EXPANSO_")}
        env.update(env_extra)
        r = subprocess.run(["expanso-cli", "node", "list"], env=env,
                           capture_output=True, text=True, timeout=30)
        # A wrong/ignored key silently falls through to the global profile, so
        # "exit 0" is not enough -- require no access error on OUR endpoint.
        return r.returncode == 0 and "does not have access" not in (r.stdout + r.stderr)

    control = run({"EXPANSO_CLI_ENDPOINT": endpoint,
                   "EXPANSO_CLI_AUTH_API_KEY": key})
    results = {"__control_EXPANSO_CLI_AUTH_API_KEY": control}
    if not control:
        return results  # probe is untrustworthy; report nothing else
    for name in IGNORED:
        results[name] = run({"EXPANSO_CLI_ENDPOINT": endpoint, name: key})
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--probe", action="store_true",
                    help="confirm against the live network using .env credentials")
    args = ap.parse_args()

    report: dict[str, object] = {"binaries": {}, "silently_ignored": IGNORED}
    for binary, table in KNOWN.items():
        path = shutil.which(binary)
        if not path:
            report["binaries"][binary] = {"installed": False}
            continue
        ver = subprocess.run([binary, "version"], capture_output=True,
                             text=True).stdout.strip().splitlines()
        report["binaries"][binary] = {
            "installed": True,
            "path": path,
            "version": ver[0] if ver else "unknown",
            "env": [{"name": n, "flag": f, "secret": s, "description": d}
                    for n, f, s, d in table],
            "strings_in_binary": scan_binary(path),
        }

    if args.probe:
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        vals = {}
        try:
            for line in open(env_path):
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip()
        except OSError:
            print("--probe needs a readable .env", file=sys.stderr)
            return 2
        ep, key = vals.get("EXPANSO_CLI_ENDPOINT"), vals.get("EXPANSO_CLI_AUTH_API_KEY")
        if not (ep and key):
            print("--probe needs EXPANSO_CLI_ENDPOINT and EXPANSO_CLI_AUTH_API_KEY in .env",
                  file=sys.stderr)
            return 2
        report["probe"] = probe_cli(ep, key)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    for binary, info in report["binaries"].items():
        if not info.get("installed"):
            print(f"{binary}: NOT INSTALLED\n")
            continue
        print(f"{binary}  {info['version']}  ({info['path']})")
        for e in info["env"]:
            mark = "SECRET" if e["secret"] else "      "
            print(f"  {mark}  {e['name']:<32} = {e['flag']:<16} {e['description']}")
        print()
    print("Silently ignored (look right, do nothing):")
    for n in IGNORED:
        print(f"          {n}")
    print("\nPass secrets through the env vars above, never the flags: a flag "
          "value\nis visible in `ps` and world-readable via /proc on Linux.")
    if "probe" in report:
        print("\nProbe:")
        for k, v in report["probe"].items():
            print(f"  {'WORKS  ' if v else 'ignored'}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
