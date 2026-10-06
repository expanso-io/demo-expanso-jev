#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Build every example's explorer page from its fixtures.

    uv run -s tools/build-explorers.py           # write demos/*/explorer.html and index.html
    uv run -s tools/build-explorers.py --check   # fail if a committed page is stale

Each page embeds the data the fixture runner recorded: the real message after
every processor, the real request to Jev and its answer, the pipeline source
for each stage, and the files from the run. Nothing on a page is typed in by
hand except the explanation in each demo's `fixture.json`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEMOS = ROOT / "demos"
TEMPLATE = ROOT / "tools" / "explorer" / "template.html"
REPO_URL = "https://github.com/expanso-io/demo-expanso-jev"
ANSWERS_NOTE = (
    "Jev's answers on this page were recorded from the offline responder in "
    "shared/jev-mock-server.py and replayed by the fixture runner, so nothing "
    "called a model. Point JEV_API_URL at Jev with a TypeSafe key to get its "
    "own judgments."
)


def latest_report() -> str | None:
    reports = sorted((ROOT / "docs" / "verification").glob("*-fixture-run.md"))
    return reports[-1].name if reports else None


# ------------------------------------------------------------ pipeline text


def processor_slices(text: str) -> dict[str, str]:
    """label -> the processor's YAML, dedented, from the shipped file."""
    lines = text.splitlines()
    out: dict[str, str] = {}
    in_procs = False
    label = None
    buf: list[str] = []

    def flush():
        nonlocal label, buf
        if label:
            while buf and not buf[-1].strip():
                buf.pop()
            out[label] = "\n".join(l[6:] if l.startswith("      ") else l for l in buf)
        label, buf = None, []

    for line in lines:
        if re.match(r"^    processors:", line):
            in_procs = True
            continue
        if in_procs and re.match(r"^  \S", line):  # output: or another key
            flush()
            in_procs = False
        if not in_procs:
            continue
        m = re.match(r"^      - label: (\S+)", line)
        if m:
            flush()
            label = m.group(1)
            buf = [line]
        elif re.match(r"^      (#|- )", line):
            flush()  # a comment or an unlabeled item ends the previous block
        elif label:
            buf.append(line)
    flush()
    return out


def section(text: str, key: str) -> str:
    """A two-space-indented top-level config section (input/output)."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l == f"  {key}:"), None)
    if start is None:
        return ""
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r"^  \S", lines[i]) or re.match(r"^\S", lines[i]):
            end = i
            break
    block = lines[start:end]
    while block and not block[-1].strip():
        block.pop()
    return "\n".join(l[2:] for l in block)


# ----------------------------------------------------------------- one case


def record_label(obj, index: int, seen: dict) -> str:
    if not isinstance(obj, dict):
        return f"record {index + 1}"
    if "msg" in obj:
        base = str(obj["msg"])
    elif "subject" in obj:
        base = str(obj["subject"])
    elif "text" in obj:
        base = str(obj["text"])
    elif "tool" in obj:
        base = f"{obj.get('agent_id', 'agent')} {obj['tool']}"
    elif "sensor_id" in obj:
        base = f"{obj['sensor_id']} {obj.get('temp_c', '')}C"
    else:
        base = next(
            (str(obj[k]) for k in ("record_id", "order_id", "id", "user") if k in obj),
            f"record {index + 1}",
        )
    base = base.strip()
    return base if len(base) <= 34 else base[:33].rstrip() + "..."


def build_case(demo: Path, fixture: dict, name: str, spec: dict) -> dict:
    fx = demo / "fixtures"
    trace = json.loads((fx / f"{name}.trace.json").read_text())
    pipeline_text = (demo / spec["pipeline"]).read_text()
    pipe = yaml.safe_load(pipeline_text)
    procs = pipe["config"]["pipeline"]["processors"]
    labels = [p.get("label") for p in procs]
    slices = processor_slices(pipeline_text)
    stage_spec = spec.get("stages") or fixture["stages"]
    queues = spec.get("queues") or fixture["queues"]
    if len(stage_spec) != len(procs) + 1:
        raise SystemExit(
            f"{demo.name}:{name}: {len(stage_spec)} stage texts for {len(procs)} processors + route"
        )
    http_path = pipe["config"]["input"]["http_server"].get("path", "/post")
    stages = [
        {
            "title": "The input",
            "text": (
                f"The record as the pipeline's HTTP input received it: a POST to {http_path} "
                "with this JSON body. Nothing has touched it yet."
            ),
            "source": section(pipeline_text, "input"),
        }
    ]
    questions: list[dict] = []
    for i, proc in enumerate(procs):
        label = labels[i]
        page = {
            "title": stage_spec[i]["title"],
            "text": stage_spec[i]["text"],
            "source": slices.get(label, ""),
        }
        branch = proc.get("branch") or {}
        inner = json.dumps(branch)
        if "JEV_API_URL" in inner or "typesafe" in inner:
            page["jev"] = True
        stages.append(page)
    stages.append(
        {
            "title": stage_spec[-1]["title"],
            "text": stage_spec[-1]["text"],
            "source": section(pipeline_text, "output"),
        }
    )
    records = []
    seen: dict = {}
    for rec in trace["records"]:
        n = trace["stage_count"]
        states: list = [None] * n
        for s in rec["stages"]:
            states[s["n"]] = s["state"]
        # Drop trailing gaps (a stage that removed the record) as missing.
        states = [s if s is not None else None for s in states]
        shaped = []
        for s in states:
            shaped.append(s)
        raw = json.loads(rec["input"])
        for call in rec["jev"]:
            if not questions and isinstance(call.get("questions"), dict):
                questions = [
                    {"id": k, "type": v.get("type", ""), "instructions": v.get("instructions", "")}
                    for k, v in call["questions"].items()
                ]
        dest = rec["destination"]
        records.append(
            {
                "label": record_label(raw, rec["index"], seen),
                "states": [s if s is not None else None for s in shaped],
                "jev": rec["jev"],
                "destination": dest,
                "dest_label": queues.get(dest, dest) if dest else "Not written",
            }
        )
    # JSON null is a legal state value elsewhere; here null means "missing".
    for r in records:
        for i, s in enumerate(r["states"]):
            if s is None:
                r["states"][i] = None
    return {
        "id": name,
        "scenario": spec.get("scenario") or ("Jev answering" if spec.get("jev") != "down" else "Jev unreachable"),
        "note": spec.get("note") or (fixture.get("if_down") if spec.get("jev") == "down" else None),
        "stages": stages,
        "queues": queues,
        "questions": questions,
        "records": records,
    }


# ---------------------------------------------------------------- one page


def commands(demo: Path, fixture: dict) -> tuple[list, list]:
    num = demo.name.split("-")[0]
    rel = demo.relative_to(ROOT).as_posix()
    cases = fixture["cases"]
    first = next(iter(cases.values()))
    pipe = first["pipeline"]
    pipe_yaml = yaml.safe_load((demo / pipe).read_text())
    path = pipe_yaml["config"]["input"]["http_server"].get("path", "/post")
    data_dir = f"data/{pipe_yaml['name']}" if pipe_yaml["name"].startswith("jev-") else "data"
    run = fixture.get("run") or [
        {
            "title": "Run it with no account",
            "intro": (
                "The fixture runner deploys the pipeline exactly as shipped to a local "
                "Edge agent, posts every line of the input, and compares what the pipeline "
                "wrote with the expected output. It needs expanso-edge, expanso-cli and uv, "
                "and no Expanso Cloud credentials or Jev key."
            ),
            "commands": [f"uv run -s tools/fixture-runner.py run --only {num}"],
            "after": "Each case prints pass or FAIL with the queues it wrote.",
        },
        {
            "title": "Run it by hand",
            "intro": (
                "The same thing without the runner. The pipeline writes ./data in the "
                "agent's working directory, so start the agent in a scratch directory."
            ),
            "commands": [
                "uv run shared/jev-mock-server.py &",
                "mkdir -p /tmp/jev-" + num + " && cd /tmp/jev-" + num,
                "export TYPESAFE_API_KEY=local-only \\\n"
                "  JEV_API_URL=http://127.0.0.1:8099/v1/systemone \\\n"
                "  INGEST_ADDRESS=127.0.0.1:8080",
                "expanso-edge run --local --no-watch &",
                "export EXPANSO_CLI_ENDPOINT=http://localhost:9010",
                f"expanso-cli job deploy $OLDPWD/{pipe}".replace(
                    f"$OLDPWD/{pipe}", f"<repo>/{rel}/{pipe}"
                ),
                "while read -r line; do \\\n"
                f"  curl -s -X POST http://127.0.0.1:8080{path} -d \"$line\"; \\\n"
                f"done < <repo>/{rel}/input.jsonl",
                f"cat {data_dir}/*.jsonl",
                "kill %1 %2",
            ],
            "after": (
                "Replace <repo> with the path to your clone. The mock answers with keyword "
                "rules; use your own Jev endpoint and key to see Jev's judgments."
            ),
        },
    ]
    deploy = fixture.get("deploy") or [
        {
            "title": "Deploy it through Expanso Cloud",
            "intro": (
                "Pipelines here are deployed through Expanso Cloud and run by the Edge agent "
                "on your node. Credentials come from the environment, never from flags."
            ),
            "commands": [
                "export EXPANSO_CLI_ENDPOINT=<your network endpoint>\n"
                "export EXPANSO_CLI_AUTH_API_KEY=<your API key>",
                f"expanso-cli job deploy {rel}/{pipe}",
            ],
            "after": (
                "Set TYPESAFE_API_KEY in the environment of the Edge agent that runs the job. "
                "It never goes in the job file or in Expanso Cloud. Add a selector with "
                "match_labels to pin the job to specific nodes."
            ),
        },
        {
            "title": "Where it listens and where it writes",
            "intro": (
                "The input listens on 127.0.0.1:8080 unless INGEST_ADDRESS says otherwise. "
                "Put TLS and authentication in front of it before it accepts traffic from "
                "another host. Each queue is a JSONL file under the agent's working directory; "
                "to deliver somewhere else, replace that queue's file output with the output "
                "your system needs. The decision logic upstream does not change."
            ),
            "commands": [],
        },
    ]
    return run, deploy


def build_page(demo: Path) -> tuple[str, dict]:
    fixture = json.loads((demo / "fixture.json").read_text())
    cases = [build_case(demo, fixture, n, s) for n, s in fixture["cases"].items()]
    first_spec = next(iter(fixture["cases"].values()))
    run, deploy = commands(demo, fixture)
    files, seen = [], set()
    rel = demo.relative_to(ROOT).as_posix()
    for n, spec in fixture["cases"].items():
        for fname in (spec["pipeline"], spec["input"]):
            if fname not in seen:
                seen.add(fname)
                files.append(
                    {
                        "name": f"{rel}/{fname}",
                        "text": (demo / fname).read_text(),
                        "type": "application/x-yaml" if fname.endswith(".yaml") else "application/x-ndjson",
                    }
                )
        exp = demo / "fixtures" / f"{n}.expected"
        for path in sorted(exp.glob("*.jsonl")):
            files.append(
                {
                    "name": f"{rel}/fixtures/{n}.expected/{path.name}",
                    "text": path.read_text(),
                    "type": "application/x-ndjson",
                }
            )
    points = []
    q = cases[0]["questions"]
    if q:
        points.append(
            f"Jev is asked {len(q)} question{'s' if len(q) != 1 else ''} about each record: "
            + ", ".join(x["id"] for x in q)
            + "."
        )
    labels = list(cases[0]["queues"].values())
    points.append("Every record ends in one place: " + ", ".join(labels) + ".")
    if fixture.get("if_down"):
        points.append("If Jev cannot be reached: " + fixture["if_down"])
    report = latest_report()
    data = {
        "id": demo.name,
        "title": fixture["title"],
        "lede": fixture["lede"],
        "points": points,
        "explore_intro": (
            "Pick a record, then page through the stages with the buttons or the Left and Right "
            "arrow keys. Every value below was captured from a real run of the pipeline in this "
            "repository: the message after each processor, the request to Jev, and its answer."
        ),
        "cases": cases,
        "run": run,
        "deploy": deploy,
        "files": files,
        "provenance": ANSWERS_NOTE,
        "report": f"../../docs/verification/{report}" if report else None,
        "repo": REPO_URL,
    }
    html = TEMPLATE.read_text()
    blob = json.dumps(data, indent=None, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    html = (
        html.replace("{{TITLE}}", f"{fixture['title']}: step explorer")
        .replace("{{FONTS}}", "../01-log-triage/fonts/fonts.css")
        .replace("{{HUB}}", "../../index.html")
        .replace("{{DATA}}", blob)
    )
    return html, fixture


HUB = """<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="data:,">
<link rel="stylesheet" href="demos/01-log-triage/fonts/fonts.css">
<title>Expanso and Jev: examples</title>
<style>
:root{color-scheme:light;--bg:#f6f4fa;--surface:#ffffff;--text:#1b1530;--muted:#4d4666;--soft:#d6d0e4;--link:#5224c4;--btn-bg:#5224c4;--btn-text:#ffffff;--line:#8c82a8;--sans:"IBM Plex Sans",sans-serif}
:root[data-theme=dark]{color-scheme:dark;--bg:#12101c;--surface:#1b1729;--text:#ece8f7;--muted:#bdb5d3;--soft:#3a3452;--link:#c0acff;--btn-bg:#c0acff;--btn-text:#12101c;--line:#8a80a6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 var(--sans);overflow-wrap:anywhere}
a{color:var(--link);text-underline-offset:3px}
a:focus-visible,button:focus-visible{outline:3px solid var(--link);outline-offset:2px}
.wrap{max-width:1120px;margin:0 auto;padding:0 16px 64px}
.top{display:flex;justify-content:flex-end;padding:16px 0}
button{font:500 15px/1.2 var(--sans);color:var(--text);background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:11px 14px;min-height:44px;cursor:pointer}
h1{font:600 clamp(28px,5vw,44px)/1.1 var(--sans);margin:16px 0 12px}
h2{font:600 22px/1.25 var(--sans);margin:0 0 6px}
p{margin:0 0 12px;max-width:72ch}
.lede{font-size:19px;max-width:68ch}
ol{list-style:none;margin:32px 0 0;padding:0;display:grid;gap:16px}
li{background:var(--surface);border:1px solid var(--soft);border-radius:8px;padding:16px}
li p{margin:0 0 8px}
.links{display:flex;flex-wrap:wrap;gap:16px}
.muted{color:var(--muted)}
</style>
</head>
<body>
<div class="wrap">
<header class="top"><button id="theme" type="button" aria-pressed="false">Dark mode</button></header>
<main>
<h1>Expanso and Jev: examples</h1>
<p class="lede">Eleven pipelines where Expanso Edge handles what rules can handle and asks Jev, TypeSafe's structured classifier, only about the rest. Each one has a page that steps through a real run, one stage at a time, with the actual message going in and coming out.</p>
<p class="muted">Every pipeline here runs on its shipped input with <code>uv run -s tools/fixture-runner.py run</code>; the latest dated report is <a href="docs/verification/{{REPORT}}">{{REPORT}}</a>.</p>
<ol>
{{ITEMS}}
</ol>
</main>
</div>
<script>
"use strict";
(function () {
  const root = document.documentElement, b = document.getElementById("theme");
  function apply(t) { root.setAttribute("data-theme", t); b.setAttribute("aria-pressed", String(t === "dark")); b.textContent = t === "dark" ? "Light mode" : "Dark mode"; }
  let s = null; try { s = localStorage.getItem("jev-theme"); } catch (e) { s = null; }
  apply(s === "dark" ? "dark" : "light");
  b.addEventListener("click", function () {
    const n = root.getAttribute("data-theme") === "dark" ? "light" : "dark"; apply(n);
    try { localStorage.setItem("jev-theme", n); } catch (e) { /* the choice still applies for this visit */ }
  });
})();
</script>
</body>
</html>
"""


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_hub(items: list[tuple[Path, dict]]) -> str:
    li = []
    for demo, fixture in items:
        rel = demo.relative_to(ROOT).as_posix()
        extra = fixture.get("hub_links") or []
        links = [f'<a href="{rel}/explorer.html">Step through it</a>', f'<a href="{rel}/README.md">README</a>']
        links += [f'<a href="{esc(h["href"])}">{esc(h["text"])}</a>' for h in extra]
        li.append(
            f"<li><h2>{esc(demo.name.split('-', 1)[0])}. {esc(fixture['title'])}</h2>"
            f"<p>{esc(fixture['lede'])}</p><div class=\"links\">{''.join(links)}</div></li>"
        )
    report = latest_report() or ""
    return HUB.replace("{{ITEMS}}", "\n".join(li)).replace("{{REPORT}}", report)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    outputs: dict[Path, str] = {}
    items = []
    for fixture_path in sorted(DEMOS.glob("*/fixture.json")):
        demo = fixture_path.parent
        html, fixture = build_page(demo)
        outputs[demo / "explorer.html"] = html
        items.append((demo, fixture))
    outputs[ROOT / "index.html"] = build_hub(items)
    stale = []
    for path, text in outputs.items():
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(path.relative_to(ROOT).as_posix())
        else:
            path.write_text(text)
    if args.check:
        for s in stale:
            print("FAIL: stale or missing", s, "- run: uv run -s tools/build-explorers.py")
        if not stale:
            print(f"ok: {len(outputs)} explorer pages match their fixtures")
        return 1 if stale else 0
    print(f"wrote {len(outputs)} pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
