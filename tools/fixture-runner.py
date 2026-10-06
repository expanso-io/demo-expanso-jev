#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Run every shipped pipeline on its shipped input and assert the output.

    uv run -s tools/fixture-runner.py run                # assert, write the dated report
    uv run -s tools/fixture-runner.py run --only 02      # one example
    uv run -s tools/fixture-runner.py record --only 02   # re-record answers, expected output and trace
    uv run -s tools/fixture-runner.py check              # offline: the committed report matches the files

What a run does, per example:

  1. starts a local replay of Jev's API that answers only from the recorded
     file `fixtures/answers.json` (an unrecorded request fails the run),
  2. starts `expanso-edge run --local` in an empty directory, with no Expanso
     Cloud credentials and no TypeSafe key in its environment,
  3. deploys the pipeline YAML exactly as shipped, posts every line of
     `input.jsonl` to its input, one at a time,
  4. compares what the pipeline wrote with `fixtures/expected/*.jsonl`
     (volatile fields such as `received_at` removed from both sides),
  5. stops everything it started and proves the ports are free again.

`record` additionally runs an instrumented copy of the pipeline that reports
the message after every top-level processor. That trace is what the example's
explorer page shows, so the explorer holds real per-stage input and output.

No model is called: the recorded answers were produced once by the offline
responder in `shared/jev-mock-server.py`, and each recorded answer says so in
its `model` field.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEMOS = ROOT / "demos"
REPORT_DIR = ROOT / "docs" / "verification"
FIXTURE_KEY = "fixture-run-no-key"  # a literal, not a credential
POST_TIMEOUT = 40
CASE_TIMEOUT = 240


class RunError(Exception):
    pass


# ----------------------------------------------------------------- helpers


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def port_free(port: int) -> bool:
    """True when nothing is listening on the port (TIME_WAIT does not count)."""
    return not port_open(port)


def wait_for(predicate, timeout: float, what: str, step: float = 0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(step)
    raise RunError(f"timed out after {timeout:.0f}s waiting for {what}")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scrub(obj, paths):
    """Remove volatile fields. `a.b` removes key b under key a at the root."""
    obj = copy.deepcopy(obj)
    for path in paths:
        parts = path.split(".")
        node = obj
        for part in parts[:-1]:
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict):
            node.pop(parts[-1], None)
    return obj


def queue_name(rel: str) -> str:
    stem = Path(rel).name
    stem = re.sub(r"\.jsonl$", "", stem)
    return re.sub(r"-\d{4}-\d{2}-\d{2}$", "", stem)


def clean_env(**extra) -> dict:
    keep = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "LANG") if k in os.environ}
    keep.update(extra)
    return keep


# ------------------------------------------------------------ the replay


def load_mock():
    spec = importlib.util.spec_from_file_location(
        "jev_mock", ROOT / "shared" / "jev-mock-server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Replay:
    """Jev's API, answered from a recorded file. Also collects trace events."""

    def __init__(
        self, answers_path: Path, volatile_request, record: bool, down: bool = False
    ):
        self.down = down
        self.path = answers_path
        self.volatile_request = volatile_request
        self.record = record
        self.mock = load_mock() if record else None
        self.entries: dict[str, dict] = {}
        if answers_path.exists() and not record and not down:
            for entry in json.loads(answers_path.read_text())["answers"]:
                self.entries[entry["key"]] = entry
        self.misses = 0
        self.calls: list[dict] = []
        self.trace: list[dict] = []
        self.current = -1
        self.lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def key_for(self, body: dict):
        state = body.get("state", "")
        if isinstance(state, str):
            try:
                state = json.loads(state)
            except json.JSONDecodeError:
                pass
        if isinstance(state, dict):
            state = scrub(state, self.volatile_request)
        normalized = {"state": state, "questions": body.get("questions", {})}
        digest = hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return digest, state

    def answer(self, body: dict):
        key, state = self.key_for(body)
        if self.down:
            with self.lock:
                self.calls.append(
                    {
                        "index": self.current,
                        "state": state,
                        "questions": body.get("questions", {}),
                        "response": {"status": 503, "error": "Jev is unreachable"},
                    }
                )
            return "DOWN", key
        with self.lock:
            entry = self.entries.get(key)
            if entry is None and self.record:
                state_text = body.get("state", "")
                if not isinstance(state_text, str):
                    state_text = json.dumps(state_text)
                response = {
                    "model": "jev-mock",
                    "answers": self.mock.answer_all(body.get("questions", {}), state_text),
                }
                entry = {
                    "key": key,
                    "state": state,
                    "questions": sorted(body.get("questions", {})),
                    "response": response,
                }
                self.entries[key] = entry
            if entry is None:
                self.misses += 1
                return None, key
            self.calls.append(
                {
                    "index": self.current,
                    "state": entry["state"],
                    "questions": body.get("questions", {}),
                    "response": entry["response"],
                }
            )
            return entry["response"], key

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(self.entries.values(), key=lambda e: e["key"])
        self.path.write_text(
            json.dumps(
                {
                    "note": "Recorded answers, replayed by tools/fixture-runner.py. "
                    "Produced by the offline responder in shared/jev-mock-server.py; "
                    "no model was called.",
                    "answers": ordered,
                },
                indent=2,
            )
            + "\n"
        )

    def _handler(self):
        replay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, payload):
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) or b"{}"
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    return self._send(400, {"error": "bad json"})
                if self.path == "/trace":
                    with replay.lock:
                        replay.trace.append(
                            {
                                "index": replay.current,
                                "stage": body.get("stage"),
                                "content": body.get("content"),
                            }
                        )
                    return self._send(200, {"ok": True})
                response, _ = replay.answer(body)
                if response == "DOWN":
                    return self._send(503, {"error": "service unavailable"})
                if response is None:
                    return self._send(
                        500, {"error": "no recorded answer for this request"}
                    )
                return self._send(200, response)

        return Handler


# ----------------------------------------------------------------- a case


class Case:
    def __init__(self, directory: Path, name: str, spec: dict):
        self.dir = directory
        self.name = name
        self.spec = spec
        self.fx = directory / "fixtures"

    @property
    def pipeline(self) -> Path:
        return self.dir / self.spec["pipeline"]

    @property
    def input(self) -> Path:
        return self.dir / self.spec["input"]

    @property
    def id(self) -> str:
        return self.spec["id"]

    @property
    def answers(self) -> Path:
        return self.fx / f"{self.name}.answers.json"

    @property
    def expected_dir(self) -> Path:
        return self.fx / f"{self.name}.expected"

    @property
    def trace_path(self) -> Path:
        return self.fx / f"{self.name}.trace.json"


def discover(only: str | None) -> list[Case]:
    cases = []
    for fixture in sorted(DEMOS.glob("*/fixture.json")):
        spec = json.loads(fixture.read_text())
        for name, case in spec["cases"].items():
            case = dict(case)
            case["id"] = f"{fixture.parent.name}:{name}" if len(spec["cases"]) > 1 else fixture.parent.name
            if only and only not in case["id"]:
                continue
            cases.append(Case(fixture.parent, name, case))
    return cases


class Run:
    """One edge agent, one deploy, one pass over the input."""

    def __init__(self, case: Case, pipeline_text: Path, replay: Replay, tmp: Path):
        self.case = case
        self.pipeline_file = pipeline_text
        self.replay = replay
        self.tmp = tmp
        self.work = tmp / "work"
        self.work.mkdir()
        self.procs: list[subprocess.Popen] = []
        self.ports: list[int] = []
        self.ingest_port = free_port()
        self.api_port = free_port()
        self.ports += [self.ingest_port, self.api_port]

    def _spawn(self, name, args, cwd, env):
        log = open(self.tmp / f"{name}.log", "wb")
        proc = subprocess.Popen(
            args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.procs.append(proc)
        return proc

    def env(self):
        return clean_env(
            JEV_API_URL=f"http://127.0.0.1:{self.replay.port}/v1/systemone",
            TYPESAFE_API_KEY=FIXTURE_KEY,
            INGEST_ADDRESS=f"127.0.0.1:{self.ingest_port}",
            INGEST_PORT=str(self.ingest_port),
            NODE_ID="fixture-node",
        )

    def start(self):
        for svc in self.case.spec.get("services", []):
            port = svc["port"]
            if not port_free(port):
                raise RunError(
                    f"port {port} is in use; stop its owner (needed by {svc['cmd'][0]})"
                )
            self._spawn(
                "service-" + Path(svc["cmd"][-1]).stem,
                svc["cmd"], self.case.dir, self.env(),
            )
            self.ports.append(port)
            wait_for(lambda p=port: port_open(p), 15, f"service on :{port}")
        edge_env = self.env()
        self._spawn(
            "edge",
            [
                "expanso-edge", "run", "--local", "--no-watch",
                "--data-dir", str(self.tmp / "edge"),
                "--api-listen", f"127.0.0.1:{self.api_port}",
            ],
            self.work, edge_env,
        )
        cli_env = clean_env(EXPANSO_CLI_ENDPOINT=f"http://127.0.0.1:{self.api_port}")

        def cli_ready():
            r = subprocess.run(
                ["expanso-cli", "job", "list"], env=cli_env, cwd=self.tmp,
                capture_output=True, timeout=20,
            )
            return r.returncode == 0

        wait_for(cli_ready, 60, "the local agent's API")
        deploy = subprocess.run(
            ["expanso-cli", "job", "deploy", "--force", str(self.pipeline_file)],
            env=cli_env, cwd=self.tmp, capture_output=True, text=True, timeout=60,
        )
        if deploy.returncode:
            raise RunError("deploy failed: " + (deploy.stderr or deploy.stdout).strip())
        wait_for(lambda: port_open(self.ingest_port), 40, "the pipeline's input")

    def endpoint(self):
        spec = yaml.safe_load(self.case.pipeline.read_text())
        path = spec["config"]["input"]["http_server"].get("path", "/post")
        return f"http://127.0.0.1:{self.ingest_port}{path}"

    def outputs(self):
        """{queue: [raw line, ...]} from every jsonl the pipeline wrote."""
        found: dict[str, list[str]] = {}
        for path in sorted((self.work).rglob("*.jsonl")):
            rel = path.relative_to(self.work).as_posix()
            found.setdefault(queue_name(rel), []).extend(
                line for line in path.read_text().splitlines() if line.strip()
            )
        return found

    def total(self):
        return sum(len(v) for v in self.outputs().values())

    def post_all(self, lines, mode="ack", settle=25.0):
        url = self.endpoint()
        for i, line in enumerate(lines):
            self.replay.current = i
            before = self.total()
            req = urllib.request.Request(
                url, data=line.encode(), method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=POST_TIMEOUT) as resp:
                    if resp.status != 200:
                        raise RunError(f"input {i + 1}: HTTP {resp.status}")
            except urllib.error.HTTPError as exc:
                raise RunError(f"input {i + 1}: HTTP {exc.code}") from exc
            if mode == "land":
                # The input acknowledges once queued; wait for it to be written.
                try:
                    wait_for(lambda b=before: self.total() > b, settle, "an output", 0.1)
                except RunError:
                    pass
        # Quiesce: output and trace both stable for 1.2 s.
        last = (-1, -1)
        stable_since = time.time()
        deadline = time.time() + settle
        while time.time() < deadline:
            now = (self.total(), len(self.replay.trace))
            if now != last:
                last, stable_since = now, time.time()
            elif time.time() - stable_since >= 1.2:
                return
            time.sleep(0.2)
        raise RunError("output kept changing; the run did not settle")

    def stop(self):
        for proc in reversed(self.procs):
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        for proc in self.procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                proc.wait(timeout=5)
        leaked = [p for p in self.ports if not port_free(p)]
        if leaked:
            time.sleep(2)
            leaked = [p for p in self.ports if not port_free(p)]
        if leaked:
            raise RunError(f"ports still in use after stopping: {leaked}")


# ------------------------------------------------------ instrumented copy


def instrument(case: Case, trace_port: int) -> dict:
    """The shipped pipeline plus one trace branch before and after every processor."""
    spec = yaml.safe_load(case.pipeline.read_text())
    procs = spec["config"]["pipeline"]["processors"]

    def tap(n):
        return {
            "label": f"trace_{n}",
            "branch": {
                "request_map": 'root = {"stage": %d, "content": content().string()}' % n,
                "processors": [
                    {
                        "http": {
                            "url": f"http://127.0.0.1:{trace_port}/trace",
                            "verb": "POST",
                            "headers": {"Content-Type": "application/json"},
                            "timeout": "5s",
                        }
                    }
                ],
            },
        }

    out = [tap(0)]
    for n, proc in enumerate(procs, start=1):
        out += [proc, tap(n)]
    spec["config"]["pipeline"]["processors"] = out
    return spec


# --------------------------------------------------------------- the work


def read_inputs(case: Case) -> list[str]:
    return [l for l in case.input.read_text().splitlines() if l.strip()]


def normalize_lines(lines, volatile):
    out = []
    for line in lines:
        out.append(scrub(json.loads(line), volatile))
    return out


def run_case(case: Case, record: bool) -> dict:
    started = time.time()
    lines = read_inputs(case)
    volatile = case.spec.get("volatile", [])
    result = {
        "id": case.id,
        "pipeline": case.pipeline.relative_to(ROOT).as_posix(),
        "pipeline_sha256": sha256_file(case.pipeline),
        "input": case.input.relative_to(ROOT).as_posix(),
        "input_sha256": sha256_file(case.input),
        "inputs": len(lines),
        "queues": {},
        "ok": False,
        "problems": [],
    }
    tmp = Path(tempfile.mkdtemp(prefix="jev-fixture-"))
    replay = Replay(
        case.answers,
        case.spec.get("volatile_request", []),
        record,
        down=case.spec.get("jev") == "down",
    )
    replay.start()
    run = None
    try:
        # Pass 1: the pipeline exactly as shipped.
        (tmp / "ship").mkdir()
        run = Run(case, case.pipeline, replay, tmp / "ship")
        run.start()
        run.post_all(lines, case.spec.get("completion", "ack"))
        shipped = run.outputs()
        run.stop()
        run = None
        if replay.misses:
            raise RunError(f"{replay.misses} request(s) had no recorded answer")
        shipped_norm = {
            q: normalize_lines(v, volatile) for q, v in shipped.items()
        }
        result["queues"] = {q: len(v) for q, v in sorted(shipped.items())}
        result["jev_calls"] = len(replay.calls)

        if record:
            exp = case.expected_dir
            if exp.exists():
                shutil.rmtree(exp)
            exp.mkdir(parents=True)
            for q, recs in shipped_norm.items():
                (exp / f"{q}.jsonl").write_text(
                    "".join(json.dumps(r, sort_keys=True) + "\n" for r in recs)
                )
        else:
            result["problems"] += compare(case, shipped_norm)

        # Pass 2 (record only): the instrumented copy, for the explorer.
        if record:
            replay.calls.clear()
            replay.trace.clear()
            (tmp / "trace").mkdir()
            inst = tmp / "trace" / "pipeline.yaml"
            inst.write_text(yaml.safe_dump(instrument(case, replay.port), sort_keys=False))
            run = Run(case, inst, replay, tmp / "trace")
            run.start()
            run.post_all(lines, case.spec.get("completion", "ack"), settle=15.0)
            traced = run.outputs()
            run.stop()
            run = None
            traced_norm = {q: normalize_lines(v, volatile) for q, v in traced.items()}
            if traced_norm != shipped_norm:
                raise RunError(
                    "the instrumented copy produced different output than the shipped pipeline"
                )
            case.trace_path.write_text(
                json.dumps(build_trace(case, lines, replay, traced), indent=2) + "\n"
            )
            if not replay.down:
                replay.save()
        result["ok"] = not result["problems"]
    except (RunError, subprocess.TimeoutExpired) as exc:
        result["problems"].append(str(exc))
    finally:
        if run is not None:
            try:
                run.stop()
            except RunError as exc:
                result["problems"].append(str(exc))
        replay.stop()
        if port_open(replay.port):
            result["problems"].append(f"replay port {replay.port} still open after stop")
        shutil.rmtree(tmp, ignore_errors=True)
    result["ok"] = not result["problems"]
    result["seconds"] = round(time.time() - started, 1)
    return result


def compare(case: Case, shipped_norm: dict) -> list[str]:
    problems = []
    exp_dir = case.expected_dir
    if not exp_dir.exists():
        return [f"no expected output at {exp_dir.relative_to(ROOT)}; run `record`"]
    expected = {}
    for path in sorted(exp_dir.glob("*.jsonl")):
        expected[path.stem] = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    for q in sorted(set(expected) | set(shipped_norm)):
        want, got = expected.get(q), shipped_norm.get(q)
        if want is None:
            problems.append(f"unexpected queue '{q}' with {len(got)} record(s)")
        elif got is None:
            problems.append(f"queue '{q}' expected {len(want)} record(s), got none")
        elif want != got:
            problems.append(
                f"queue '{q}' differs: expected {len(want)} record(s), got {len(got)}"
                + ("" if len(want) != len(got) else " with different content")
            )
    return problems


def build_trace(case: Case, lines, replay: Replay, traced_outputs: dict) -> dict:
    volatile = case.spec.get("volatile", [])
    by_index: dict[int, dict[int, object]] = {}
    for event in replay.trace:
        content = event["content"]
        try:
            state = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            state = content
        by_index.setdefault(event["index"], {})[event["stage"]] = state
    jev_by_index: dict[int, list] = {}
    for call in replay.calls:
        jev_by_index.setdefault(call["index"], []).append(
            {"request": call["state"], "questions": call["questions"], "response": call["response"]}
        )
    flat = []
    for q, raw in sorted(traced_outputs.items()):
        for line in raw:
            flat.append((q, json.loads(line)))
    records = []
    for i, line in enumerate(lines):
        stages = by_index.get(i, {})
        final = stages.get(max(stages)) if stages else None
        dest = None
        if isinstance(final, dict):
            for q, obj in flat:
                if obj == final:
                    dest = q
                    break
        records.append(
            {
                "index": i,
                "input": line,
                "stages": [
                    {"n": n, "state": stages[n]} for n in sorted(stages)
                ],
                "jev": jev_by_index.get(i, []),
                "destination": dest,
            }
        )
    return {
        "volatile": volatile,
        "stage_count": 1 + len(yaml.safe_load(case.pipeline.read_text())["config"]["pipeline"]["processors"]),
        "records": records,
    }


# ----------------------------------------------------------------- report


def tool_version(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return (r.stdout + r.stderr).strip().splitlines()[0]
    except Exception:  # noqa: BLE001
        return "unknown"


def write_report(results: list[dict], path: Path):
    today = dt.date.today().isoformat()
    lines = [
        f"# Fixture run, {today}",
        "",
        "Every shipped pipeline was deployed unmodified to a local `expanso-edge run --local` "
        "agent and fed its shipped input one record at a time. Jev answers were replayed from "
        "each example's recorded file; nothing called a model, and the agent had no Expanso Cloud "
        "credentials. What each pipeline wrote was compared with the committed expected output "
        "(`received_at`-style fields removed from both sides).",
        "",
        f"- Date: {today}",
        f"- Agent: {tool_version(['expanso-edge', 'version'])}",
        f"- Command: `uv run -s tools/fixture-runner.py run`",
        f"- Result: **{sum(r['ok'] for r in results)} of {len(results)} pipelines passed**",
        "",
        "| Pipeline | Inputs | Jev calls | Queues written | Seconds | Result |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        queues = ", ".join(f"{q} {n}" for q, n in r["queues"].items()) or "none"
        lines.append(
            f"| `{r['pipeline']}` | {r['inputs']} | {r.get('jev_calls', 0)} | {queues} | "
            f"{r['seconds']} | {'pass' if r['ok'] else 'FAIL'} |"
        )
    lines += ["", "## Files exercised", "", "| File | sha256 |", "|---|---|"]
    for r in results:
        lines.append(f"| `{r['pipeline']}` | `{r['pipeline_sha256']}` |")
        lines.append(f"| `{r['input']}` | `{r['input_sha256']}` |")
    for r in results:
        for p in r["problems"]:
            lines.append("")
            lines.append(f"Problem in `{r['id']}`: {p}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def latest_report() -> Path | None:
    reports = sorted(REPORT_DIR.glob("*-fixture-run.md"))
    return reports[-1] if reports else None


def check() -> int:
    """Offline: the newest report covers every pipeline and its hashes still match."""
    report = latest_report()
    if report is None:
        print("FAIL: no docs/verification/*-fixture-run.md; run `run` first")
        return 1
    text = report.read_text()
    bad = []
    for case in discover(None):
        for f in (case.pipeline, case.input):
            rel = f.relative_to(ROOT).as_posix()
            m = re.search(rf"`{re.escape(rel)}` \| `([0-9a-f]{{64}})`", text)
            if not m:
                bad.append(f"{rel} is not in {report.name}")
            elif m.group(1) != sha256_file(f):
                bad.append(f"{rel} changed since {report.name}; re-run the fixtures")
        if not case.expected_dir.exists() or not case.answers.exists():
            bad.append(f"{case.id}: missing recorded answers or expected output")
    if "FAIL" in text.split("## Files exercised")[0]:
        bad.append(f"{report.name} records a failing run")
    for b in bad:
        print("FAIL:", b)
    if not bad:
        print(f"ok: {report.name} covers every pipeline and matches the files")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["run", "record", "check"])
    ap.add_argument("--only")
    ap.add_argument("--report", help="report path (default docs/verification/<date>-fixture-run.md)")
    args = ap.parse_args()
    if args.mode == "check":
        return check()
    for tool in ("expanso-edge", "expanso-cli"):
        if not shutil.which(tool):
            print(f"FAIL: {tool} is not on PATH")
            return 1
    cases = discover(args.only)
    if not cases:
        print("FAIL: no matching cases")
        return 1
    results = []
    for case in cases:
        print(f"-- {case.id}", flush=True)
        res = run_case(case, record=args.mode == "record")
        results.append(res)
        print(
            f"   {'pass' if res['ok'] else 'FAIL'}  {res['inputs']} in, "
            f"queues {res['queues']}  ({res['seconds']}s)",
            flush=True,
        )
        for p in res["problems"]:
            print("   problem:", p)
    if args.mode == "run" and not args.only:
        path = Path(args.report) if args.report else REPORT_DIR / f"{dt.date.today().isoformat()}-fixture-run.md"
        write_report(results, path)
        print("report:", path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
