"""Fixture run for demos/11-pod-labels, called by tools/fixture-runner.py.

Unlike the HTTP pipelines this one reads from, and writes to, a Kubernetes
cluster, so the run uses a real one:

  1. a throwaway k3d cluster (named jev-fixture-<hex>, deleted at the end) with
     the example's fixture pods and its RBAC applied,
  2. the real adapter.py, started with a kubeconfig that holds only the
     pod-label-agent ServiceAccount's token (never the administrator's),
  3. the shipped pipeline.yaml on a local `expanso-edge run --local` agent,
  4. six scripted events sent through the adapter's own browser endpoints:
     three investigations and three label events, then the lease expiry,
  5. Jev answers replayed from the recorded file: the investigation answers are
     the real Jev values committed in docs/investigation-live-proof.json, and
     the label answers come from the offline responder.

It compares the adapter's event feed, the labels on the pods and the pipeline's
own stdout receipts with the expected files, then deletes the cluster.

For development, JEV_FIXTURE_KUBECONFIG and JEV_FIXTURE_CONTEXT reuse an
existing cluster that already has the fixtures and RBAC applied; nothing is
created or deleted then.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

NS = "jev-label-demo"
TERMINAL = {"applied", "undone", "held", "error", "investigation_waiting", "investigation_ready"}
SCRIPT = [
    ("investigate", "checkout-api", "restart", "Investigate one restart"),
    ("investigate", "checkout-api", "context", "Investigate release context"),
    ("investigate", "checkout-api", "evidence", "Investigate memory evidence"),
    ("event", "orders-api", "batch", "Batch finished"),
    ("event", "checkout-api", "oom", "Out of memory"),
    ("event", "analytics-worker", "probe", "Failing readiness"),
]
DROP = {"seq", "at", "event_id", "request_id", "id", "uid", "elapsed_ms", "investigation",
        "displayed_at", "expires_at", "workload", "resource_version"}


def semantic_key(body: dict) -> str:
    """Investigations by scenario, label questions by their scrubbed evidence."""
    state = body.get("state", {})
    if isinstance(state, dict) and state.get("operation") == "investigate":
        return "investigate:" + str(state.get("scenario"))
    text = json.dumps(state, sort_keys=True)
    text = re.sub(r'(\\*"at\\*": )[0-9.]+', r"\g<1>0", text)
    return hashlib.sha256(text.encode()).hexdigest()


class Responder:
    """Replays recorded Jev answers; also collects the pipeline's trace taps."""

    def __init__(self, answers_path: Path, record: bool, lib, root: Path):
        self.lib, self.root, self.record = lib, root, record
        self.path = answers_path
        self.entries: dict[str, dict] = {}
        self.mock = lib.load_mock() if record else None
        if record:
            self.entries.update(self.investigation_entries())
        elif answers_path.exists():
            for e in json.loads(answers_path.read_text())["answers"]:
                self.entries[e["key"]] = e
        self.misses = 0
        self.calls: list[dict] = []
        self.trace: list[dict] = []
        self.lock = threading.Lock()
        self.current = -1
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def investigation_entries(self) -> dict:
        proof = json.loads((self.root / "docs" / "investigation-live-proof.json").read_text())
        out = {}
        for phase in proof["phases"]:
            key = "investigate:investigate_" + phase["phase"]
            out[key] = {
                "key": key,
                "source": f"docs/investigation-live-proof.json, real Jev, verified {proof['verified_at']}",
                "response": {
                    "model": "jev-latest",
                    "answers": {"act": {"type": "noul", "noul": phase["receipt"]["noul"]}},
                },
            }
        return out

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "note": "Recorded Jev answers for the pod-labels run. Investigation answers are "
                    "the real Jev values in docs/investigation-live-proof.json; label answers come "
                    "from the offline responder in shared/jev-mock-server.py. No model was called.",
                    "answers": sorted(self.entries.values(), key=lambda e: e["key"]),
                },
                indent=2,
            )
            + "\n"
        )

    def _handler(self):
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, payload):
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path == "/trace":
                    with me.lock:
                        me.trace.append({"index": me.current, "stage": body["stage"], "content": body["content"]})
                    return self._send(200, {"ok": True})
                key = semantic_key(body)
                with me.lock:
                    entry = me.entries.get(key)
                    if entry is None and me.record:
                        text = body.get("state", "")
                        text = text if isinstance(text, str) else json.dumps(text)
                        entry = {
                            "key": key,
                            "source": "offline responder, shared/jev-mock-server.py",
                            "state": body.get("state"),
                            "response": {
                                "model": "jev-mock",
                                "answers": me.mock.answer_all(body.get("questions", {}), text),
                            },
                        }
                        me.entries[key] = entry
                    if entry is None:
                        me.misses += 1
                        return self._send(500, {"error": "no recorded answer"})
                    me.calls.append(
                        {"index": me.current, "state": body.get("state"),
                         "questions": body.get("questions", {}), "response": entry["response"]}
                    )
                return self._send(200, entry["response"])

        return H


def kubectl(kubeconfig, *args, context=None, input_text=None, timeout=120):
    cmd = ["kubectl", "--kubeconfig", str(kubeconfig)]
    if context:
        cmd += ["--context", context]
    r = subprocess.run(cmd + list(args), capture_output=True, text=True, input=input_text, timeout=timeout)
    if r.returncode:
        raise RuntimeError("kubectl " + " ".join(args[:3]) + " failed: " + r.stderr.strip()[:300])
    return r.stdout


def instrument_pipeline(spec: dict, port: int) -> dict:
    """Taps inside the try-chain: the event, then each step's output."""
    import copy

    spec = copy.deepcopy(spec)
    chain = spec["config"]["pipeline"]["processors"][0]["try"]

    def tap(n):
        return {
            "label": f"trace_{n}",
            "branch": {
                "request_map": 'root = {"stage": %d, "content": content().string()}' % n,
                "processors": [{"http": {
                    "url": f"http://127.0.0.1:{port}/trace", "verb": "POST",
                    "headers": {"Content-Type": "application/json"}, "timeout": "5s"}}],
            },
        }

    out = [tap(0)]
    for n, step in enumerate(chain, start=1):
        out += [step, tap(n)]
    spec["config"]["pipeline"]["processors"][0]["try"] = out
    return spec


class Pass:
    """One cluster state, one adapter, one Edge agent, one scripted session."""

    def __init__(self, lib, case, responder, admin, ctx, tmp, instrumented):
        self.lib, self.case, self.resp = lib, case, responder
        self.admin, self.ctx, self.tmp = admin, ctx, tmp
        self.instrumented = instrumented
        self.procs = []
        self.port = lib.free_port()
        self.api = lib.free_port()
        self.token = secrets.token_hex(32)
        self.events: dict[int, dict] = {}
        self.stop_poll = threading.Event()
        self.csrf = None

    def _spawn(self, name, args, env, cwd):
        log = open(self.tmp / f"{name}.log", "wb")
        p = subprocess.Popen(args, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
        self.procs.append(p)
        return p

    def http(self, path, body=None, post=False):
        headers = {"Host": f"127.0.0.1:{self.port}"}
        data = None
        if post:
            data = json.dumps(body).encode()
            headers.update({"Content-Type": "application/json",
                            "Origin": f"http://127.0.0.1:{self.port}", "X-CSRF-Token": self.csrf})
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                     headers=headers, method="POST" if post else "GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)

    def poll(self):
        while not self.stop_poll.is_set():
            try:
                feed = self.http("/api/events?after=0")
                for e in feed.get("events", feed):
                    self.events[e["seq"]] = e
            except Exception:  # noqa: BLE001 - the adapter may be starting or stopping
                pass
            time.sleep(0.4)

    def start(self):
        lib, d = self.lib, self.case.dir
        sys_path = str(d / "rbac")
        import sys
        if sys_path not in sys.path:
            sys.path.insert(0, sys_path)
        from mint_kubeconfig import mint

        agent = self.tmp / "agent.kubeconfig"
        mint(self.admin, self.ctx, NS, agent, "30m", "jev-label-demo")
        env = lib.clean_env(
            KUBECONFIG=str(agent), KUBE_CONTEXT="jev-label-demo", POD_LABEL_NAMESPACES=NS,
            POD_LABEL_TOKEN=self.token, POD_LABEL_PORT=str(self.port), POD_LABEL_APPLY="true",
            POD_LABEL_AUTO="false", POD_LABEL_THRESHOLD="0.8", TYPESAFE_API_KEY=lib.FIXTURE_KEY,
            JEV_API_URL=f"http://127.0.0.1:{self.resp.port}/v1/systemone",
            POD_LABEL_GENERAL_LOG=str(self.tmp / "general.jsonl"),
        )
        self._spawn("adapter", ["python3", str(d / "adapter.py")], env, self.tmp)
        lib.wait_for(lambda: self._ok(lambda: self.http("/api/session")), 40, "the adapter")
        self.csrf = self.http("/api/session")["csrf_token"]
        threading.Thread(target=self.poll, daemon=True).start()
        pipeline = d / "pipeline.yaml"
        if self.instrumented:
            import yaml

            pipeline = self.tmp / "pipeline.yaml"
            pipeline.write_text(yaml.safe_dump(
                instrument_pipeline(yaml.safe_load((d / "pipeline.yaml").read_text()), self.resp.port),
                sort_keys=False))
        self._spawn("edge", ["expanso-edge", "run", "--local", "--no-watch", "--data-dir",
                             str(self.tmp / "edge"), "--api-listen", f"127.0.0.1:{self.api}",
                             "--config", str(d / "edge.yaml")], env, self.tmp)
        cli = lib.clean_env(EXPANSO_CLI_ENDPOINT=f"http://127.0.0.1:{self.api}")
        lib.wait_for(lambda: subprocess.run(["expanso-cli", "job", "list"], env=cli, cwd=self.tmp,
                                            capture_output=True).returncode == 0, 60, "the local agent")
        dep = subprocess.run(["expanso-cli", "job", "deploy", "--force", str(pipeline)], env=cli,
                             cwd=self.tmp, capture_output=True, text=True, timeout=60)
        if dep.returncode:
            raise lib.RunError("deploy failed: " + (dep.stderr or dep.stdout).strip())

    @staticmethod
    def _ok(fn):
        try:
            fn()
            return True
        except Exception:  # noqa: BLE001
            return False

    def labels(self, pod):
        meta = json.loads(kubectl(self.admin, "get", "pod", pod, "-n", NS, "-o", "json",
                                  context=self.ctx))["metadata"]
        return dict(sorted(meta.get("labels", {}).items()))

    def drive(self):
        done = []
        for i, (kind, pod, what, title) in enumerate(SCRIPT):
            self.resp.current = i
            body = {"namespace": NS, "pod": pod}
            body.update({"phase": what} if kind == "investigate" else {"scenario": what})
            queued = self.http("/api/investigate" if kind == "investigate" else "/api/event", body, True)
            rid = queued["request_id"]

            def terminal():
                return [e for e in self.events.values()
                        if e.get("request_id") == rid and e["stage"] in TERMINAL]

            self.lib.wait_for(terminal, 90, f"event {i + 1} ({what}) to finish", 0.3)
            labels = self.labels(pod)
            done.append({"index": i, "request_id": rid, "kind": kind, "pod": pod, "what": what,
                         "title": title, "labels": labels})
        # The ten-second lease: each applied label comes off again.
        applied = sum(1 for d in done if any(
            e.get("request_id") == d["request_id"] and e["stage"] == "applied" for e in self.events.values()))
        self.resp.current = len(SCRIPT)
        if applied:
            self.lib.wait_for(
                lambda: sum(1 for e in self.events.values() if e["stage"] == "expired") >= applied,
                60, "the label leases to expire", 0.5)
        time.sleep(1.5)
        self.after = {p: self.labels(p) for p in ("checkout-api", "orders-api", "analytics-worker")}
        return done

    def stop(self):
        self.stop_poll.set()
        for p in reversed(self.procs):
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        for p in self.procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait(timeout=5)
        leaked = [x for x in (self.port, self.api) if self.lib.port_open(x)]
        if leaked:
            raise self.lib.RunError(f"ports still in use after stopping: {leaked}")

    # ---- what the run produced, normalized for comparison

    def clean(self, obj):
        if isinstance(obj, dict):
            return {k: self.clean(v) for k, v in sorted(obj.items()) if k not in DROP}
        if isinstance(obj, list):
            return [self.clean(v) for v in obj]
        if isinstance(obj, float):
            return round(obj, 3)
        return obj

    def outputs(self, done):
        rids = {d["request_id"]: d for d in done}
        events = []
        for e in sorted(self.events.values(), key=lambda e: e["seq"]):
            if e.get("request_id") in rids and e["stage"] != "queued":
                events.append(self.clean({"step": rids[e["request_id"]]["index"] + 1, **e}))
            elif e["stage"] == "expired":
                events.append(self.clean({"step": 0, **e}))
        events.sort(key=lambda e: (e["step"] == 0, e["step"], e["stage"] == "expired"))
        labels = [self.clean({"step": d["index"] + 1, "pod": d["pod"], "scenario": d["what"],
                              "labels_when_finished": d["labels"]}) for d in done]
        labels.append({"step": "after expiry", "labels": self.after})
        receipts = []
        for line in (self.tmp / "edge.log").read_text(errors="replace").splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and ("result" in obj or "stage" in obj) and obj.get("stage") != "routine":
                    receipts.append(self.clean(obj))
        # Only receipts for the scripted requests (the id is dropped; match by scenario/pod).
        receipts = [r for r in receipts if r.get("pod") in {d["pod"] for d in done} or "result" in r]
        return {
            "events": [json.dumps(e, sort_keys=True) for e in events],
            "labels": [json.dumps(l, sort_keys=True) for l in labels],
            "receipts": [json.dumps(r, sort_keys=True) for r in receipts],
        }


def build_trace(case, done, responder, instrumented: Pass):
    chains: dict[int, dict[int, object]] = {}
    current_chain = None
    for ev in responder.trace:
        try:
            content = json.loads(ev["content"])
        except (TypeError, json.JSONDecodeError):
            content = ev["content"]
        if ev["stage"] == 0:
            current_chain = None
            rid = content.get("request_id") if isinstance(content, dict) else None
            for d in done:
                if d["request_id"] == rid:
                    current_chain = d["index"]
                    chains[current_chain] = {}
        if current_chain is not None:
            chains[current_chain][ev["stage"]] = content
    jev_by = {}
    for c in responder.calls:
        jev_by.setdefault(c["index"], []).append(c)
    records = []
    for d in done:
        stages = chains.get(d["index"], {})
        records.append({
            "index": d["index"], "input": json.dumps(stages.get(0, {})),
            "stages": [{"n": n, "state": s} for n, s in sorted(stages.items())],
            "jev": [{"request": c["state"], "questions": c["questions"], "response": c["response"]}
                    for c in jev_by.get(d["index"], [])],
            "destination": "receipts",
            "title": d["title"], "pod": d["pod"],
        })
    return {"volatile": [], "stage_count": 6, "records": records}


def write_replay_files(case, trace, lib):
    """What the shared check needs to run the pipeline without a cluster."""
    events, candidates, judge, apply, outputs = [], {}, {}, {}, []
    for rec in trace["records"]:
        st = {s["n"]: s["state"] for s in rec["stages"]}
        events.append(json.dumps(st[0], sort_keys=True))
        token = st[1][0]["id"]
        candidates[str(st[0]["request_id"])] = st[1]
        judge[token] = st[4]
        apply[token] = st[5]
        outputs.append(st[5])
    (case.dir / "fixtures").mkdir(exist_ok=True)
    case.input.write_text("\n".join(events) + "\n")
    (case.dir / "fixtures" / "adapter-replay.json").write_text(
        json.dumps({"candidates": candidates, "judge": judge, "apply": apply}, indent=2) + "\n")
    (case.fx / f"{case.name}.replay.schema.json").write_text(
        json.dumps(lib.replay_schema(outputs, [], False), indent=2) + "\n")


def run(case, record: bool, lib, result: dict) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="jev-pods-"))
    created = None
    problems = result["problems"]
    responder = Responder(case.answers, record, lib, lib.ROOT)
    try:
        for tool in ("docker", "k3d", "kubectl", "expanso-edge", "expanso-cli"):
            if not shutil.which(tool):
                raise lib.RunError(f"{tool} is not on PATH (pod-labels needs a container runtime and k3d)")
        if subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode:
            raise lib.RunError("the Docker daemon is not running; start it and re-run")
        reuse = os.environ.get("JEV_FIXTURE_KUBECONFIG")
        if reuse:
            admin, ctx = Path(reuse), os.environ["JEV_FIXTURE_CONTEXT"]
        else:
            created = "jev-fixture-" + secrets.token_hex(3)
            admin, ctx = tmp / "admin.kubeconfig", "k3d-" + created
            subprocess.run(["k3d", "cluster", "create", created, "--kubeconfig-update-default=false",
                            "--kubeconfig-switch-context=false", "--wait"],
                           capture_output=True, text=True, check=True, timeout=300)
            fd = os.open(admin, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(subprocess.run(["k3d", "kubeconfig", "get", created],
                                            capture_output=True, text=True, check=True).stdout)
        sim = case.dir / "simulation" / "fixtures.yaml"

        def fresh_pods():
            kubectl(admin, "delete", "pod", "--all", "-n", NS, "--wait=true", "--ignore-not-found",
                    context=ctx, timeout=180)
            kubectl(admin, "apply", "-f", str(sim), context=ctx)
            kubectl(admin, "apply", "-k", str(case.dir / "rbac"), context=ctx)
            kubectl(admin, "wait", "pod", "--all", "-n", NS, "--for=condition=Ready",
                    "--timeout=240s", context=ctx, timeout=260)

        def one_pass(instrumented):
            fresh_pods()
            run_ = Pass(lib, case, responder, admin, ctx, tmp / ("trace" if instrumented else "ship"), instrumented)
            run_.tmp.mkdir(parents=True, exist_ok=True)
            try:
                run_.start()
                done = run_.drive()
                outs = run_.outputs(done)
            finally:
                run_.stop()
            return run_, done, outs

        ship, done, outs = one_pass(False)
        if responder.misses:
            raise lib.RunError(f"{responder.misses} Jev request(s) had no recorded answer")
        result["queues"] = {q: len(v) for q, v in sorted(outs.items())}
        result["jev_calls"] = len(responder.calls)
        norm = {q: [json.loads(l) for l in v] for q, v in outs.items()}
        if record:
            exp = case.expected_dir
            if exp.exists():
                shutil.rmtree(exp)
            exp.mkdir(parents=True)
            for q, recs in norm.items():
                (exp / f"{q}.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in recs))
            responder.calls.clear()
            responder.trace.clear()
            inst, done2, outs2 = one_pass(True)
            same = {q: [json.loads(l) for l in v] for q, v in outs2.items()}
            for q in ("events", "labels"):
                if same[q] != norm[q]:
                    raise lib.RunError(f"the instrumented copy changed the '{q}' output")
            trace = build_trace(case, done2, responder, inst)
            case.trace_path.write_text(json.dumps(trace, indent=2) + "\n")
            responder.save()
            write_replay_files(case, trace, lib)
        else:
            problems += lib.compare(case, norm)
    except (lib.RunError, subprocess.SubprocessError, RuntimeError) as exc:
        problems.append(str(exc))
    finally:
        responder.stop()
        if created:
            subprocess.run(["k3d", "cluster", "delete", created], capture_output=True, timeout=180)
            left = subprocess.run(["k3d", "cluster", "list", "-o", "json"], capture_output=True, text=True)
            if created in left.stdout:
                problems.append(f"cluster {created} was not deleted")
        shutil.rmtree(tmp, ignore_errors=True)
