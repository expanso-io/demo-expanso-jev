#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Build the published page and its manifests from the fixture runs.

    uv run -s tools/build-explorers.py           # write everything
    uv run -s tools/build-explorers.py --check   # fail if a committed file is stale

Writes:
  index.html                          the one published page: every example's
                                      explanation, step explorer, run and deploy
  demos/*/fixtures/stages/<id>/*.json the real input and output of every stage
  public-bar.toml                     the manifest the shared public-bar check reads
  public-features.json                the retained-feature baseline

Everything on the page is data the fixture runner recorded: the real message
after every processor, the request to Jev and its answer, and the pipeline source
for each stage. Only the explanation in each demo's `fixture.json` is written by hand.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEMOS = ROOT / "demos"
TEMPLATE = ROOT / "tools" / "explorer" / "template.html"
PROVENANCE = (
    "Jev's answers on this page were recorded and replayed, so nothing called a model. "
    "The investigation answers in the pod-labels example are the real Jev values in "
    "docs/investigation-live-proof.json; every other answer comes from the offline "
    "responder in shared/jev-mock-server.py, which says so in each answer's model field. "
    "Point JEV_API_URL at Jev, with a TypeSafe key, to get its own judgments."
)
BROWSER_PORT = 8777
DEFAULT = {"example": "01-log-triage", "record": 3, "stage": 1}


def esc(text) -> str:
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def latest_report() -> str:
    reports = sorted((ROOT / "docs" / "verification").glob("*-fixture-run.md"))
    return reports[-1].name if reports else "none"


# ------------------------------------------------------------ pipeline text


def slice_by_label(text: str, label: str) -> str:
    """The YAML block that starts at `- label: <label>`, dedented."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)- label: " + re.escape(label) + r"\s*$", line)
        if not m:
            continue
        indent = len(m.group(1))
        block = [line]
        for nxt in lines[i + 1 :]:
            stripped = nxt.strip()
            if stripped and (len(nxt) - len(nxt.lstrip())) <= indent:
                break
            block.append(nxt)
        while block and not block[-1].strip():
            block.pop()
        return "\n".join(l[indent:] if l.startswith(" " * indent) else l for l in block)
    return ""


def section(text: str, key: str) -> str:
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l == f"  {key}:"), None)
    if start is None:
        return ""
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r"^\S", lines[i]) or re.match(r"^  \S", lines[i]):
            end = i
            break
    block = lines[start:end]
    while block and not block[-1].strip():
        block.pop()
    return "\n".join(l[2:] for l in block)


def processors_of(pipe: dict, spec: dict) -> list[dict]:
    procs = pipe["config"]["pipeline"]["processors"]
    if spec.get("harness") == "pod-labels":
        return procs[0]["try"]
    return procs


# ----------------------------------------------------------------- one case


def record_label(obj, trace_rec: dict, index: int) -> str:
    if trace_rec.get("title"):
        return f"{trace_rec.get('pod', '')}: {trace_rec['title']}".strip(": ")
    if not isinstance(obj, dict):
        return f"record {index + 1}"
    for key in ("msg", "subject", "text"):
        if key in obj:
            base = str(obj[key])
            break
    else:
        if "tool" in obj:
            base = f"{obj.get('agent_id', 'agent')} {obj['tool']}"
        elif "sensor_id" in obj:
            base = f"{obj['sensor_id']} {obj.get('temp_c', '')}C"
        else:
            base = next((str(obj[k]) for k in ("record_id", "order_id", "id", "user") if k in obj), f"record {index + 1}")
    base = base.strip()
    return base if len(base) <= 34 else base[:33].rstrip() + "..."


def pipeline_id(demo: Path, fixture: dict, spec: dict) -> str:
    files = {c["pipeline"] for c in fixture["cases"].values()}
    if len(files) == 1:
        return demo.name
    stem = Path(spec["pipeline"]).stem.removeprefix("pipeline-")
    return f"{demo.name}-{stem}"


def build_case(demo: Path, fixture: dict, name: str, spec: dict) -> dict:
    trace = json.loads((demo / "fixtures" / f"{name}.trace.json").read_text())
    pipeline_text = (demo / spec["pipeline"]).read_text()
    pipe = yaml.safe_load(pipeline_text)
    procs = processors_of(pipe, spec)
    labels = [p.get("label") for p in procs]
    if None in labels:
        raise SystemExit(f"{demo.name}:{name}: every processor needs a label")
    stage_spec = spec.get("stages") or fixture["stages"]
    queues = spec.get("queues") or fixture["queues"]
    if len(stage_spec) != len(procs) + 1:
        raise SystemExit(f"{demo.name}:{name}: {len(stage_spec)} stage texts for {len(procs)} processors + route")
    pid = pipeline_id(demo, fixture, spec)
    http = pipe["config"]["input"].get("http_server")
    where = f"a POST to {http.get('path', '/post')}" if http else "a request from the adapter"
    stages = [
        {
            "slug": "input",
            "title": "The input",
            "text": f"The record as the pipeline's input received it: {where} with this JSON body. Nothing has touched it yet.",
            "source": section(pipeline_text, "input"),
        }
    ]
    jev_label = fixture.get("jev_stage")
    for i, proc in enumerate(procs):
        page = {
            "slug": labels[i],
            "title": stage_spec[i]["title"],
            "text": stage_spec[i]["text"],
            "source": slice_by_label(pipeline_text, labels[i]),
        }
        inner = json.dumps(proc.get("branch") or {})
        if labels[i] == jev_label or "JEV_API_URL" in inner or "typesafe" in inner:
            page["jev"] = True
        stages.append(page)
    stages.append(
        {
            "slug": "route",
            "title": stage_spec[-1]["title"],
            "text": stage_spec[-1]["text"],
            "source": section(pipeline_text, "output"),
        }
    )
    records, questions = [], []
    n = trace["stage_count"]
    for rec in trace["records"]:
        states: list = [None] * n
        for s in rec["stages"]:
            states[s["n"]] = s["state"]
        raw = json.loads(rec["input"]) if rec["input"] else {}
        for call in rec["jev"]:
            if not questions and isinstance(call.get("questions"), dict):
                questions = [
                    {"id": k, "type": v.get("type", ""), "instructions": v.get("instructions", "")}
                    for k, v in call["questions"].items()
                ]
        dest = rec["destination"]
        records.append(
            {
                "label": record_label(raw, rec, rec["index"]),
                "input": raw,
                "states": states,
                "jev": rec["jev"],
                "destination": dest,
                "dest_label": queues.get(dest, dest) if dest else "Not written",
            }
        )
    rel = demo.relative_to(ROOT).as_posix()
    return {
        "id": name,
        "scenario": spec.get("scenario") or ("Jev answering" if spec.get("jev") != "down" else "Jev unreachable"),
        "note": spec.get("note") or (fixture.get("if_down") if spec.get("jev") == "down" else None),
        "pipeline_id": pid,
        "pipeline_url": f"{rel}/{spec['pipeline']}",
        "input_url": f"{rel}/{spec['input']}",
        "stages": stages,
        "queues": queues,
        "questions": questions,
        "records": records,
        "replay": bool(spec.get("replay")),
        "_spec": spec,
    }


# -------------------------------------------------------------- static HTML


def command_block(cmd: str) -> str:
    return (
        '<div class="cmd"><pre tabindex="0">'
        + esc(cmd)
        + '</pre><div class="bar"><button type="button" data-copy>Copy command</button>'
        '<span class="status" role="status"></span></div></div>'
    )


def sections_html(items: list[dict]) -> str:
    out = []
    for it in items:
        out.append(f"<h3>{esc(it['title'])}</h3>")
        if it.get("intro"):
            out.append(f"<p>{rich(it['intro'])}</p>")
        out.extend(command_block(c) for c in it.get("commands", []))
        if it.get("after"):
            out.append(f"<p>{rich(it['after'])}</p>")
    return "\n".join(out)


def rich(text: str) -> str:
    parts = str(text).split("`")
    return "".join(f"<code>{esc(p)}</code>" if i % 2 else esc(p) for i, p in enumerate(parts))


def default_run(demo: Path, fixture: dict, first: dict) -> tuple[list, list]:
    num = demo.name.split("-")[0]
    rel = demo.relative_to(ROOT).as_posix()
    spec = first["_spec"]
    pipe = spec["pipeline"]
    pipe_yaml = yaml.safe_load((demo / pipe).read_text())
    path = pipe_yaml["config"]["input"]["http_server"].get("path", "/post")
    data_dir = f"data/{pipe_yaml['name']}"
    run = [
        {
            "title": "Run it with no account",
            "intro": (
                "The fixture runner deploys the pipeline exactly as shipped to a local Edge agent, posts every line "
                "of the input, and compares what the pipeline wrote with the expected output. It also runs the "
                "pipeline again with Jev unreachable. It needs expanso-edge, expanso-cli and uv, and no Expanso "
                "Cloud credentials or Jev key."
            ),
            "commands": [f"uv run -s tools/fixture-runner.py run --only {num}"],
            "after": "Each case prints pass or FAIL with the queues it wrote.",
        },
        {
            "title": "Run it by hand",
            "intro": (
                "The same thing without the runner. The pipeline writes `./data` in the agent's working "
                "directory, so start the agent in a scratch directory."
            ),
            "commands": [
                "uv run shared/jev-mock-server.py &",
                f"mkdir -p /tmp/jev-{num} && cd /tmp/jev-{num}",
                "expanso-edge run --local --no-watch &",
                "export EXPANSO_CLI_ENDPOINT=http://localhost:9010",
                f"expanso-cli job deploy REPO/{rel}/{pipe}",
                "while read -r line; do \\\n"
                f'  curl -s -X POST http://127.0.0.1:8080{path} -d "$line"; \\\n'
                f"done < REPO/{rel}/input.jsonl",
                f"cat {data_dir}/*.jsonl",
                "kill %1 %2",
            ],
            "after": "Replace REPO with the path to your clone. The bundled responder answers with keyword rules; set `JEV_API_URL` and `TYPESAFE_API_KEY` to use Jev.",
        },
    ]
    deploy = [
        {
            "title": "Deploy through Expanso Cloud",
            "intro": (
                "Pipelines here are deployed through Expanso Cloud and run by the Edge agent on your node. "
                "Credentials come from the environment, never from flags."
            ),
            "commands": [
                "export EXPANSO_CLI_ENDPOINT=https://your-network.example.net\nexport EXPANSO_CLI_AUTH_API_KEY=your-api-key",
                f"expanso-cli job deploy {rel}/{pipe}",
            ],
            "after": (
                "`JEV_API_URL` defaults to the local responder on 127.0.0.1:8099, so nothing leaves the host until "
                "you set it to Jev's endpoint and set `TYPESAFE_API_KEY` in the Edge agent's environment. The key "
                "never goes in the job file or in Expanso Cloud. Add a selector with `match_labels` to pin the job "
                "to specific nodes."
            ),
        },
        {
            "title": "Where it listens and where it writes",
            "intro": (
                "The input listens on 127.0.0.1:8080 unless `INGEST_ADDRESS` says otherwise. Put TLS and "
                "authentication in front of it before it accepts traffic from another host. Each queue is a JSONL "
                "file under the agent's working directory; to deliver somewhere else, replace that queue's file "
                "output with the output your system needs. The decision logic upstream does not change."
            ),
            "commands": [],
        },
    ]
    return fixture.get("run") or run, fixture.get("deploy") or deploy


# ------------------------------------------------------------------- build


def toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    return json.dumps(v)


def toml_table(name: str, data: dict, array: bool = False) -> str:
    head = f"[[{name}]]" if array else f"[{name}]"
    return head + "\n" + "\n".join(f"{k} = {toml_value(v)}" for k, v in data.items()) + "\n"


def build() -> dict[Path, str]:
    outputs: dict[Path, str] = {}
    examples = []
    pipelines, stage_entries, yaml_entries = [], [], []
    feature_rows = []
    for fx_path in sorted(DEMOS.glob("*/fixture.json")):
        demo = fx_path.parent
        fixture = json.loads(fx_path.read_text())
        cases = [build_case(demo, fixture, n, s) for n, s in fixture["cases"].items()]
        first = cases[0]
        if fixture.get("run") and fixture.get("deploy"):
            run, deploy = fixture["run"], fixture["deploy"]
        else:
            run, deploy = default_run(demo, fixture, first)
        points = []
        q = next((c["questions"] for c in cases if c["questions"]), [])
        if q:
            points.append(f"Jev is asked {len(q)} question{'s' if len(q) != 1 else ''} about each record: " + ", ".join(x["id"] for x in q) + ".")
        points.append("Every record ends in one place: " + ", ".join(first["queues"].values()) + ".")
        if fixture.get("if_down"):
            points.append("If Jev cannot be reached: " + fixture["if_down"])
        examples.append(
            {"id": demo.name, "title": fixture["title"], "lede": fixture["lede"], "points": points,
             "questions": q, "cases": cases, "run": run, "deploy": deploy}
        )
        # stage files and manifest entries, once per distinct pipeline
        done_pids = set()
        for c in cases:
            pid = c["pipeline_id"]
            if pid in done_pids:
                continue
            done_pids.add(pid)
            canon = next((r for r in c["records"] if r["destination"]), c["records"][0])
            states = canon["states"]
            for i, stage in enumerate(c["stages"]):
                if i == 0:
                    inp = out = canon["input"]
                elif i == len(c["stages"]) - 1:
                    inp = out = states[len(c["stages"]) - 2]
                else:
                    inp, out = states[i - 1], states[i]
                base = demo / "fixtures" / "stages" / pid / f"{stage['slug']}"
                outputs[base.with_suffix(".input.json")] = json.dumps(inp, indent=2, sort_keys=False) + "\n"
                outputs[base.with_suffix(".output.json")] = json.dumps(out, indent=2, sort_keys=False) + "\n"
                stage_id = f"{pid}.{stage['slug']}"
                stage["id"] = stage_id
                stage_entries.append(
                    {
                        "id": stage_id,
                        "pipeline": pid,
                        "selector": f'[data-stage-id="{stage_id}"]',
                        "input": base.with_suffix(".input.json").relative_to(ROOT).as_posix(),
                        "output": base.with_suffix(".output.json").relative_to(ROOT).as_posix(),
                    }
                )
                feature_rows.append((stage_id, f"{fixture['title']}: {stage['title']} stage, with its real input and output"))
            for other in cases:
                if other["pipeline_id"] == pid:
                    other["stages_ids"] = [f"{pid}.{s['slug']}" for s in other["stages"]]
        for c in cases:
            for i, s in enumerate(c["stages"]):
                s["id"] = f"{c['pipeline_id']}.{s['slug']}"
        for c in cases:
            if c["replay"] and c["pipeline_id"] not in {p["id"] for p in pipelines}:
                rel = demo.relative_to(ROOT).as_posix()
                schema = demo / "fixtures" / f"{c['id']}.replay.schema.json"
                count = json.loads(schema.read_text())["minItems"]
                spec = c["_spec"]
                pipelines.append(
                    {
                        "id": c["pipeline_id"],
                        "path": f"{rel}/{spec['pipeline']}",
                        "input": f"{rel}/{spec['input']}",
                        "expected_schema": schema.relative_to(ROOT).as_posix(),
                        "expected_count": count,
                        "timeout_seconds": 60,
                    }
                )
        for c in cases:
            c.pop("_spec", None)
            c.pop("replay", None)
    # the recurrence pipeline must run before the logging one: they share a counter
    pipelines.sort(key=lambda p: (0 if p["id"].endswith("recurrence") else 1, p["id"]))

    # ---- static page parts
    nav = "\n".join(
        f'        <li><button type="button" data-pick="{e["id"]}" aria-pressed="false">{esc(e["id"].split("-", 1)[0])}. {esc(e["title"])}</button></li>'
        for e in examples
    )
    expl = []
    for e in examples:
        qs = "".join(f"<dt>{esc(q['id'])} ({esc(q['type'])})</dt><dd>{esc(q['instructions'])}</dd>" for q in e["questions"])
        expl.append(
            f'    <article data-example="{e["id"]}" hidden>\n      <h3>{esc(e["title"])}</h3>\n      <p>{rich(e["lede"])}</p>\n'
            f'      <ul class="plain">' + "".join(f"<li>{rich(p)}</li>" for p in e["points"]) + "</ul>\n"
            + (f'      <h4>What Jev is asked</h4>\n      <dl class="qs">{qs}</dl>\n' if qs else "")
            + "    </article>"
        )
    bars = []
    seen = set()
    for e in examples:
        for c in e["cases"]:
            if c["pipeline_id"] in seen:
                continue
            seen.add(c["pipeline_id"])
            lis = "".join(
                f'<li><button type="button" data-stage-id="{s["id"]}" aria-label="Stage {i + 1}: {esc(s["title"])}">{i + 1}</button></li>'
                for i, s in enumerate(c["stages"])
            )
            bars.append(f'      <ol class="stagebar" data-pipeline="{c["pipeline_id"]}" aria-labelledby="stage-label" hidden>{lis}</ol>')
    run_html = "\n".join(f'    <div data-example="{e["id"]}" hidden>\n{sections_html(e["run"])}\n    </div>' for e in examples)
    dep_html = "\n".join(f'    <div data-example="{e["id"]}" hidden>\n{sections_html(e["deploy"])}\n    </div>' for e in examples)

    report = latest_report()
    data = {
        "default": DEFAULT,
        "provenance": PROVENANCE,
        "examples": [
            {"id": e["id"], "cases": e["cases"]} for e in examples
        ],
    }
    for ex in data["examples"]:
        for c in ex["cases"]:
            for s in c["stages"]:
                s.pop("slug", None)
            c.pop("stages_ids", None)
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text()
    for key, val in {
        "{{EXAMPLE_NAV}}": nav,
        "{{EXPLANATIONS}}": "\n".join(expl),
        "{{STAGEBARS}}": "\n".join(bars),
        "{{RUN}}": run_html,
        "{{DEPLOY}}": dep_html,
        "{{REPORT}}": report,
        "{{DATA}}": blob,
    }.items():
        html = html.replace(key, val)
    outputs[ROOT / "index.html"] = html

    # ---- manifests
    rel_report = f"docs/verification/{report}"
    manifest = ["# Generated by tools/build-explorers.py from the demos' fixture.json files.", "version = 1", ""]
    manifest.append(toml_table("repository", {"name": "demo-expanso-jev", "published": True}))
    manifest.append(
        toml_table(
            "web",
            {
                "document": "index.html",
                "explanation_selector": "#explanation",
                "explorer_selector": "#explorer",
                "run_selector": "#run",
                "deploy_selector": "#deploy",
            },
        )
    )
    browser = {
        "url": f"http://127.0.0.1:{BROWSER_PORT}/",
        "ready_url": f"http://127.0.0.1:{BROWSER_PORT}/",
        "start_command": ["python3", "tools/serve.py", "static", str(BROWSER_PORT)],
        "stop_command": ["python3", "tools/serve.py", "stop", str(BROWSER_PORT)],
        "theme_toggle_selector": "#theme-toggle",
        "stage_selector": "[data-stage-id]",
        "current_stage_selector": '[data-stage-id][aria-current="step"]',
        "scroll_anchor_selector": "#stage-panel",
        "json_selectors": ["#stage-input", "#stage-output"],
    }
    manifest.append(toml_table("browser", browser))
    controls = [
        {"id": "copy-stage-input", "kind": "copy", "selector": "#copy-stage-input",
         "feedback_selector": "#copy-stage-input-status", "success_text": "Copied", "failure_text": "Copy failed"},
        {"id": "download-pipeline", "kind": "download", "selector": "#download-pipeline",
         "feedback_selector": "#download-pipeline-status", "success_text": "Download started",
         "failure_text": "Download failed", "failure_url_pattern": "**/pipeline*.yaml"},
    ]
    for c in controls:
        manifest.append(toml_table("browser.controls", c, array=True))
    services = [
        {"id": "jev-responder", "command": ["python3", "shared/jev-mock-server.py"],
         "ready_url": "http://127.0.0.1:8099/health", "stop_command": ["python3", "tools/serve.py", "stop", "8099"]},
        {"id": "recurrence-counter", "command": ["python3", "demos/01-log-triage/counter.py"],
         "ready_url": "http://127.0.0.1:8898/health", "stop_command": ["python3", "tools/serve.py", "stop", "8898"]},
        {"id": "recorded-adapter", "command": ["python3", "tools/serve.py", "pods", "8901"],
         "ready_url": "http://127.0.0.1:8901/health", "stop_command": ["python3", "tools/serve.py", "stop", "8901"]},
    ]
    for s in services:
        manifest.append(toml_table("services", s, array=True))
    for p in pipelines:
        manifest.append(toml_table("pipelines", p, array=True))
    for s in stage_entries:
        manifest.append(toml_table("stages", s, array=True))
    for path, role in [
        ("demos/11-pod-labels/simulation/fixtures.yaml", "fixture"),
        ("demos/11-pod-labels/edge.yaml", "support"),
    ]:
        manifest.append(toml_table("yaml", {"path": path, "role": role}, array=True))
    manifest.append(
        toml_table(
            "platforms",
            {
                "name": "kubernetes",
                "profile": "other",
                "files": ["demos/11-pod-labels/rbac/rbac.yaml", "demos/11-pod-labels/rbac/kustomization.yaml"],
                "validators": [["kubectl", "kustomize", "demos/11-pod-labels/rbac"]],
            },
            array=True,
        )
    )
    manifest.append(toml_table("regressions", {"features": "public-features.json", "removal_files": ["public-removals/*.json"]}))
    outputs[ROOT / "public-bar.toml"] = "\n".join(manifest)

    extra = json.loads((ROOT / "tools" / "explorer" / "features.json").read_text())
    features = [{"id": i, "description": d} for i, d in feature_rows] + extra["features"]
    doc = {
        "version": 1,
        "features": features,
        "routes": [{"id": "published-page", "path": "index.html", "description": "The published explorer"}] + extra["routes"],
        "controls": [{"id": "copy-stage-input", "selector": "#copy-stage-input"}],
        "downloads": [{"id": "download-pipeline", "selector": "#download-pipeline"}],
        "browser_assertions": extra["browser_assertions"],
    }
    outputs[ROOT / "public-features.json"] = json.dumps(doc, indent=2) + "\n"
    return outputs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    outputs = build()
    if args.check:
        stale = [p.relative_to(ROOT).as_posix() for p, t in outputs.items() if not p.exists() or p.read_text() != t]
        for s in stale:
            print("FAIL: stale or missing", s, "- run: uv run -s tools/build-explorers.py")
        if not stale:
            print(f"ok: {len(outputs)} generated files match the fixtures")
        return 1 if stale else 0
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    for old in DEMOS.glob("*/explorer.html"):
        old.unlink()
    print(f"wrote {len(outputs)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
