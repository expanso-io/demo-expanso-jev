#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Validate a demo's human recording-readiness declaration without side effects.

Usage: uv run -s ../_demo-kit/recording-preflight.py .

This intentionally does not run `just record-check`, start a server, open a
browser, record, deploy, publish, or change Cloud state. The operator runs the
mechanical check first and records its observed result in RECORDING_PREFLIGHT.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PREFLIGHT = "RECORDING_PREFLIGHT.md"
REQUIRED_FIELDS = {"status", "record_check", "record_check_evidence", "accepted_warnings"}
REQUIRED_SECTIONS = (
    "Claim",
    "Audience and objection",
    "Capture surface",
    "Opening state",
    "Operator action",
    "Visible outcome",
    "Truth boundary",
    "Proof evidence",
    "Decision",
)
STATUSES = {"PASS", "PASS_WITH_NAMED_WARNINGS", "BLOCKED"}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)


def front_matter(text: str) -> tuple[dict[str, str], str] | None:
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, re.DOTALL)
    if not match:
        return None
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        values[key.strip()] = value.strip().strip('"')
    return values, match.group(2)


def section_value(body: str, heading: str) -> str | None:
    pattern = rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, body, re.MULTILINE | re.DOTALL)
    if not match:
        return None
    return match.group(1).strip()


def is_filled(value: str) -> bool:
    collapsed = re.sub(r"\s+", " ", value).strip()
    return bool(collapsed) and "<" not in collapsed and ">" not in collapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("demo", nargs="?", type=Path, default=Path("."), help="demo root (default: .)")
    args = parser.parse_args()

    path = args.demo / PREFLIGHT
    if not path.is_file():
        fail(f"missing {path}; copy _demo-kit/RECORDING_PREFLIGHT.template.md before recording")
        return 1

    parsed = front_matter(path.read_text())
    if parsed is None:
        fail(f"{path} needs YAML front matter delimited by ---")
        return 1
    metadata, body = parsed
    missing = REQUIRED_FIELDS - metadata.keys()
    if missing:
        fail(f"{path} is missing front-matter fields: {', '.join(sorted(missing))}")
        return 1

    errors: list[str] = []
    status = metadata["status"]
    if status not in STATUSES:
        errors.append("status must be PASS, PASS_WITH_NAMED_WARNINGS, or BLOCKED")
    if metadata["record_check"] != "PASS":
        errors.append("record_check must be PASS; run `just record-check` separately first")
    if not is_filled(metadata["record_check_evidence"]):
        errors.append("record_check_evidence must name the observed check result")

    warnings = metadata["accepted_warnings"].strip()
    if status == "PASS" and warnings != "[]":
        errors.append("PASS cannot carry accepted_warnings; use PASS_WITH_NAMED_WARNINGS")
    if status == "PASS_WITH_NAMED_WARNINGS" and warnings in {"", "[]"}:
        errors.append("PASS_WITH_NAMED_WARNINGS requires at least one named warning")
    if status == "BLOCKED":
        errors.append("status is BLOCKED; resolve the named blocker before recording")

    for heading in REQUIRED_SECTIONS:
        value = section_value(body, heading)
        if value is None:
            errors.append(f"missing section: {heading}")
        elif not is_filled(value):
            errors.append(f"unfinished section: {heading}")

    if errors:
        for error in errors:
            fail(error)
        return 1

    suffix = " with named warnings" if status == "PASS_WITH_NAMED_WARNINGS" else ""
    print(f"PASS: recording preflight declared ready{suffix}: {path}")
    print("No recorder, runtime, deployment, publish action, or Cloud state was started or changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
