#!/usr/bin/env python3
"""jev-live server: serves the dashboard and streams what is really happening.

Stdlib only. No secrets here -- the Jev endpoint lives in the Edge pipeline's
JEV_API_URL, and the Expanso credentials reach expanso-cli through its own
environment variables (EXPANSO_CLI_ENDPOINT / EXPANSO_CLI_AUTH_API_KEY), which
this process inherits from start.sh and never reads or logs.

This server OBSERVES the pipeline, with ONE control: the Jev switch on the board.
Turning Jev on deploys pipeline-recurrence.yaml over the running job through
Expanso Cloud; turning it off deploys pipeline-logging.yaml back. Same job, next
version, real deploy -- the board still only changes once the pipeline does.
Starting and stopping the pipeline itself stays with the presenter, in the Cloud
console (or `just act1/act2`). Three acts, each a real state of the
world rather than a view:

  off      no pipeline. Nothing listens on :8080, so production's logs take the
           only path they have: straight into the raw bucket (data/raw.jsonl),
           every line, unshaped. It fills fast.
  expanso  pipeline-logging.yaml is running. Logs are shaped, fingerprinted and
           counted, repeats are collapsed, and the rest go to the log archive.
  jev      pipeline-recurrence.yaml is running (same job, next version). Same
           front half, then Jev judges each event: page / notify / review /
           archive.

Which act we are in is detected two ways, because each covers the other's blind
spot: a local probe of :8080 (instant, but cannot tell the two pipelines apart)
and a poll of Expanso Cloud for the running job's spec (authoritative, ~2s late).

Endpoints:
  GET  /                  the dashboard
  GET  /events            Server-Sent Events: src / rec / stats messages
  GET  /api/bucket/<bin>  the most recent records that landed in a bucket
  GET  /api/evidence      records where Jev and the severity-only baseline disagreed
  GET  /api/pipeline/<logging|recurrence>  the checked-in pipeline YAML, verbatim
  POST /api/gate          {"mode": open|overloaded|credential}: simulate a Jev outage at the local gate
  POST /api/jev           {"on": true|false}: deploy the Jev / Expanso-only version via Cloud
  POST /beacon            from the generator: {"n": k} lines just emitted
  POST /raw               from the generator: a log line the pipeline refused
  POST /chaos/<name>      inject a scenario through the live pipeline
  POST /generator/start | /generator/stop
  GET  /health
"""
import collections
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("JEV_LIVE_PORT", "8890"))
HERE = os.path.dirname(os.path.abspath(__file__))
# Fixed, not configurable: the pipelines write to the relative path data/*.jsonl
# and start.sh runs the Edge agent from this directory, so a configurable tail
# path could only ever drift out of sync with it.
DATA = os.path.join(HERE, "data")
GEN = os.environ.get("JEV_LIVE_GEN", os.path.join(HERE, "generator2.py"))
PIPELINE_URL = os.environ.get("JEV_LIVE_PIPELINE", "http://[::1]:8080/logs")
LOG_DIR = os.path.join(HERE, "logs")

# file -> bucket. The Expanso-only pipeline and Jev's "archive" decision both
# end up in the same place as far as an operator is concerned: the log archive.
FILES = {
    "page.jsonl": "page",
    "notify.jsonl": "notify",
    "review.jsonl": "review",
    "archive.jsonl": "archive",
    "logs.jsonl": "archive",
    "raw.jsonl": "raw",
    "held.jsonl": "held",   # a hold RECEIPT, written once when a record is first held; not a destination
}
BINS = ["page", "notify", "review", "archive", "raw", "held"]
HOLD_MAX_ATTEMPTS = 15      # mirrors the gate in pipeline-recurrence.yaml

# The fault-injection gate. The pipeline calls Jev THROUGH this local proxy
# (start.sh points the agent's JEV_API_URL at it and hands the real endpoint to
# this process as JEV_UPSTREAM_URL). Open, it forwards verbatim. Blocked, it
# answers the way a struggling Jev would, so the pipeline's hold path is
# exercised by a real failed call rather than an animation. It is a SIMULATED
# outage and the board says so.
GATE_PORT = int(os.environ.get("JEV_GATE_PORT", "8897"))
UPSTREAM = os.environ.get("JEV_UPSTREAM_URL", "")
# Jev is a plain HTTPS API authenticated with a Bearer key. When a key is present
# the gate adds the header itself, so the pipeline can reach Jev directly and no
# separate proxy is needed. The key lives ONLY here: it is taken out of
# the environment immediately so nothing this process starts (the generator,
# expanso-cli) can inherit it; it is never logged, never reported by /health,
# never written to the pipeline spec, and so never reaches Expanso Cloud.
_JEV_KEY = os.environ.pop("TYPESAFE_API_KEY", "") or ""
GATE_FAULTS = {
    "overloaded": (503, {"error": "simulated outage: Jev overloaded", "simulated": True}),
    "credential": (401, {"error": "simulated outage: credential rejected", "simulated": True}),
}

STATIC_TYPES = {"css": "text/css", "woff2": "font/woff2", "woff": "font/woff",
                "svg": "image/svg+xml", "png": "image/png"}
STATIC_DIRS = ("fonts", "assets")   # nothing else in this package is servable

# The "Pipeline YAML" tab. A closed allowlist: the request supplies a KEY, never
# a path, and the key is looked up here. Nothing from the URL is ever joined
# into a filename, so there is no traversal to defend against. Files are served
# verbatim -- ${JEV_API_URL} stays a placeholder, nothing is interpolated -- and
# this is the checked-in source, not a read-back of what Expanso Cloud is running.
PIPELINE_FILES = {
    "logging": "pipeline-logging.yaml",
    "recurrence": "pipeline-recurrence.yaml",
}
RATE_WINDOW_S = 10

NAMESPACE = "demo"

CHAOS = {
    # NOTE: each scenario's message is worded to fingerprint uniquely --
    # nothing in generator2.py's ambient templates or its built-in scenario
    # may normalize to the same fingerprint, so a chaos run is always a
    # clean occurrence 1..N escalation of a novel event.
    # Deliberately NOT unique: it shares a fingerprint with the routine
    # "GET /health 200 2ms" (the fingerprint erases numbers). That is the point --
    # an exact-match bypass lets the 200 through and sends the 500 to Jev.
    "health500": [("INFO", "api", "GET /health 500 2ms")] * 3,
    "brute": [("WARN", "auth", "auth failed for user root from 198.51.100.23")] * 4,
    "ghost": [("INFO", "api", "config reload requested by unknown actor session=chaosghost")] * 3,
    "disk": [("WARN", "infra", "disk usage %d%% on /data node=chaosprobe-1" % p)
             for p in (82, 88, 93, 96)],
    "cert": [("WARN", "edge", "certificate serial changed unexpectedly cn=chaos.example.com")] * 3,
    "crash": [("WARN", "infra", "pod restarted 5 times in 10m CrashLoop suspected deploy=chaoscanary")] * 4,
}
CHAOS_GAP_S = 20  # spacing so recurrence escalation is visible


def log(*a):
    print("[jev-live]", *a, flush=True)


# ---- shared state + fan-out to every connected dashboard ---------------------
class Hub:
    def __init__(self):
        self.lock = threading.Lock()
        self.subs = set()
        self.src_total = 0
        self.bins = {b: 0 for b in BINS}
        self.recent = {b: collections.deque(maxlen=30) for b in BINS}
        self.cloud_mode = "off"    # what Expanso Cloud says is running
        self.cloud_ok = False      # did the last Cloud poll succeed
        self.last_kind = None      # "expanso" | "jev": who wrote the last record
        self.pipeline_up = False   # is anything actually listening on :8080
        self.raw_bytes = 0
        self.jev_fail = collections.deque(maxlen=12)   # recent judged records: did Jev answer?
        self.run = self._new_run("off")
        self.per_sec = collections.Counter()   # epoch second -> completed records, this run
        self.replay = False   # set only by review/preview_server.py; the board says so on screen
        self.model = None      # model name on the last real judgment; the board shows it
        self.gate = "open"     # "open" | "overloaded" | "credential"
        self.upstream_ok = None  # did the last forwarded Jev call reach the real endpoint
        self.switching = None  # "jev" | "expanso" while a Jev-switch deploy is in flight
        self.switch_from = None
        self.switch_error = None
        self.caught = collections.deque(maxlen=8)    # severity-only: archive, Jev: page/notify
        self.quieted = collections.deque(maxlen=8)   # severity-only: page/notify, Jev: archive

    @staticmethod
    def _new_run(mode):
        """Counters for ONE run: the span since the current pipeline took over.

        The board's claims use ONE denominator: completed receipts, i.e. records
        the pipeline actually wrote. bypassed + judged + jev_failed == received,
        exactly. `produced` and `accepted` are counted at the source, earlier in
        time and across run boundaries, so they are diagnostics only (visible in
        /health) and are never divided into anything on screen.
        """
        return {"mode": mode, "started": time.time(), "produced": 0, "accepted": 0,
                "bypassed": 0, "judged": 0, "jev_failed": 0, "caught": 0, "quieted": 0,
                # hold path: held_in = records first held; released = later judged
                # for real; gave_up = sent to review after HOLD_MAX_ATTEMPTS
                "held_in": 0, "released": 0, "gave_up": 0,
                "received": {b: 0 for b in BINS}}

    def _rates(self):
        """Completed-record rate, measured, over a stated window. Caller holds the lock.

        Counts receipts (records the pipeline wrote), bucketed by arrival second.
        The current, still-filling second is excluded so the figure does not
        sag at the start of every second.
        """
        now = int(time.time())
        for sec in [k for k in self.per_sec if k < now - 90]:
            del self.per_sec[sec]
        window = [self.per_sec.get(now - i, 0) for i in range(1, RATE_WINDOW_S + 1)]
        # a hold receipt is not a completion: the record is still in flight
        return {"completed": sum(v for k, v in self.run["received"].items() if k != "held"),
                "holding": max(0, self.run["held_in"] - self.run["released"] - self.run["gave_up"]),
                "rate": round(sum(window) / RATE_WINDOW_S, 1), "rate_window_s": RATE_WINDOW_S,
                "spark": [self.per_sec.get(now - i, 0) for i in range(60, 0, -1)]}

    def mode(self):
        """Caller holds the lock. Port first: a job can be 'running' in Cloud a
        beat before its input binds here, and until it binds the logs are still
        going to the raw bucket."""
        if self.switching:
            # A version bump stops one execution and starts the next, so :8080 is
            # unbound for a moment. Hold the act we came from instead of flashing
            # "no pipeline"; the board flips only when the new version is live.
            return self.switch_from
        if not self.pipeline_up:
            return "off"
        if self.cloud_ok and self.cloud_mode != "off":
            return self.cloud_mode
        return self.last_kind or "expanso"

    def publish(self, msg):
        line = json.dumps(msg, separators=(",", ":"))
        with self.lock:
            subs = list(self.subs)
        for q in subs:
            try:
                q.put_nowait(line)
            except queue.Full:
                pass  # a stalled browser tab must not back-pressure the demo

    def stats(self):
        with self.lock:
            return {
                "t": "stats", "src": self.src_total, "bins": dict(self.bins),
                "mode": self.mode(), "up": self.pipeline_up,
                "raw_bytes": self.raw_bytes, "cloud_ok": self.cloud_ok,
                # Jev is "down" only when the recent run of judgments ALL failed;
                # one timeout in a burst is not an outage.
                "jev_down": len(self.jev_fail) >= 4 and all(self.jev_fail),
                "replay": self.replay,
                "switching": self.switching, "switch_error": self.switch_error,
                # The board reloads itself when this changes, so an open tab can
                # never silently keep showing an older version of the page.
                "ui_rev": int(os.path.getmtime(os.path.join(HERE, "index.html"))),
                "model": self.model, "mock": bool(self.model and "mock" in str(self.model).lower()),
                "gate": self.gate, "upstream_ok": self.upstream_ok, "upstream_set": bool(UPSTREAM),
                "upstream_auth": bool(_JEV_KEY),   # presence only; the value is never exposed
                "run": {**self.run, "received": dict(self.run["received"]),
                        "age_s": round(time.time() - self.run["started"], 1),
                        **self._rates()},
                "gen": generator_running() or self.replay,
            }


HUB = Hub()


def port_up():
    """Is the pipeline's HTTP input really accepting connections right now?

    This, not the mode flag, decides whether logs are landing or being refused.
    A job can be "deployed" in Cloud for a second before its input binds here,
    and during that second the honest picture is still "going nowhere".
    """
    for host, fam in (("::1", socket.AF_INET6), ("127.0.0.1", socket.AF_INET)):
        try:
            s = socket.socket(fam, socket.SOCK_STREAM)
            s.settimeout(0.3)
            s.connect((host, 8080))
            s.close()
            return True
        except OSError:
            continue
    return False


# ---- watching Expanso Cloud --------------------------------------------------
def cloud_poll():
    """What is running in the network right now, according to Expanso Cloud.

    Read-only. The Jev pipeline is recognised by its spec carrying Jev's
    `questions`, not by a job name -- the presenter may deploy from the console
    under any name they like.
    """
    r = subprocess.run(
        ["expanso-cli", "job", "list", "--namespace", NAMESPACE, "--format", "json"],
        capture_output=True, text=True, timeout=20, cwd=HERE)
    if r.returncode != 0:
        out = (r.stderr or r.stdout).strip().splitlines()
        raise RuntimeError(out[-1] if out else "expanso-cli failed")
    mode = "off"
    # With no jobs at all the CLI prints "No jobs found" even under --format
    # json, so an empty network is not valid JSON. It is still a clean answer.
    out = r.stdout.strip()
    for job in (json.loads(out) if out.startswith("[") else []):
        if job.get("status", {}).get("state", {}).get("state_type") != "running":
            continue
        # The config sits in the spec as text, so match the mapping that builds
        # Jev's request, not a JSON key.
        is_jev = "root.questions" in json.dumps(job.get("spec", {}))
        mode = "jev" if is_jev else ("expanso" if mode != "jev" else mode)
    return mode


_switch_lock = threading.Lock()
SWITCH_SPECS = {"jev": "pipeline-recurrence.yaml", "expanso": "pipeline-logging.yaml"}


def jev_switch(target):
    """Deploy the Jev (or Expanso-only) version of the job through Expanso Cloud."""
    with _switch_lock:
        with HUB.lock:
            HUB.switch_from, HUB.switching, HUB.switch_error = HUB.mode(), target, None
        HUB.publish(HUB.stats())
        err = None
        try:
            if not (os.environ.get("EXPANSO_CLI_ENDPOINT") and os.environ.get("EXPANSO_CLI_AUTH_API_KEY")):
                raise RuntimeError("no Expanso Cloud credentials in the environment")
            # Stop FIRST and wait for the input port to go quiet. A bare version
            # bump starts the new execution while the old one still owns :8080; the
            # new one fails to bind, Cloud marks the job degraded, and the OLD
            # pipeline keeps running -- so "Jev off" left Jev on. Seen 2026-09-19.
            subprocess.run(["expanso-cli", "job", "stop", "log-triage", "--namespace", NAMESPACE, "--force"],
                           capture_output=True, text=True, timeout=60, cwd=HERE)
            t0 = time.time()
            while port_up():
                if time.time() - t0 > 30:
                    raise RuntimeError("the running pipeline would not release its input port")
                time.sleep(0.3)
            # --force: an identical redeploy is otherwise refused (NO_CHANGES_DETECTED).
            r = subprocess.run(["expanso-cli", "job", "deploy", "--force", SWITCH_SPECS[target]],
                               capture_output=True, text=True, timeout=90, cwd=HERE)
            if r.returncode != 0:
                out = (r.stderr or r.stdout).strip().splitlines()
                raise RuntimeError(out[-1] if out else "deploy failed")
            log("jev switch -> %s: %s" % (target, (r.stdout.strip().splitlines() or ["ok"])[-1]))
            t0 = time.time()
            while not port_up():          # the new version binds the input
                if time.time() - t0 > 45:
                    raise RuntimeError("deployed, but the pipeline input never came back up")
                time.sleep(0.3)
            # A bound port proves A pipeline is up, not WHICH. Ask Cloud.
            t0 = time.time()
            while cloud_poll() != target:
                if time.time() - t0 > 30:
                    raise RuntimeError("deployed, but Expanso Cloud is not running the %s version" % target)
                time.sleep(1.0)
        except Exception as e:  # noqa: BLE001 - shown on the board
            err = str(e)
            log("jev switch to %s failed: %s" % (target, err))
        finally:
            with HUB.lock:
                if not err:
                    HUB.cloud_mode, HUB.cloud_ok = target, True   # we know what we just deployed
                HUB.pipeline_up = port_up()
                HUB.switching, HUB.switch_from, HUB.switch_error = None, None, err
            HUB.publish(HUB.stats())


def detector():
    if not (os.environ.get("EXPANSO_CLI_ENDPOINT") and os.environ.get("EXPANSO_CLI_AUTH_API_KEY")):
        # Without these expanso-cli falls back to ~/.expanso's globally selected
        # profile -- some other network entirely. Local port detection still works.
        log("no Expanso Cloud endpoint in the environment; cloud polling disabled")
        return
    warned = False
    while True:
        try:
            mode, ok = cloud_poll(), True
            warned = False
        except Exception as e:  # noqa: BLE001 - offline is survivable
            mode, ok = "off", False
            if not warned:
                log("cloud poll failed (falling back to local detection): %s" % e)
                warned = True
        with HUB.lock:
            HUB.cloud_mode, HUB.cloud_ok = mode, ok
        time.sleep(2)


# ---- generator subprocess management ---------------------------------------
_gen_proc = None
_gen_lock = threading.Lock()
_raw_lock = threading.Lock()


def _pgrep_gen():
    """Best-effort: is any generator2.py already running (e.g. from start.sh)?"""
    try:
        out = subprocess.run(["pgrep", "-f", "generator2.py"],
                             capture_output=True, text=True, timeout=5).stdout
        pids = [p for p in out.split() if p.strip()]
        return pids[0] if pids else None
    except Exception:
        return None


def generator_start():
    global _gen_proc
    with _gen_lock:
        if _gen_proc and _gen_proc.poll() is None:
            return {"ok": True, "already": True, "pid": _gen_proc.pid}
        pid = _pgrep_gen()
        if pid:
            return {"ok": True, "already": True, "pid": int(pid)}
        if not os.path.isfile(GEN):
            return {"ok": False, "error": "generator not found: %s" % GEN}
        os.makedirs(LOG_DIR, exist_ok=True)
        fh = open(os.path.join(LOG_DIR, "generator.log"), "ab")
        try:
            _gen_proc = subprocess.Popen([sys.executable, GEN], stdout=fh,
                                         stderr=subprocess.STDOUT)
        except Exception as e:  # noqa: BLE001 - report, don't crash
            fh.close()
            return {"ok": False, "error": str(e)}
        log("generator started pid=%d" % _gen_proc.pid)
        return {"ok": True, "pid": _gen_proc.pid}


def generator_stop():
    global _gen_proc
    with _gen_lock:
        stopped = []
        if _gen_proc and _gen_proc.poll() is None:
            _gen_proc.terminate()
            try:
                # it drains in-flight posts first; a judged line can take several seconds
                _gen_proc.wait(timeout=45)
            except subprocess.TimeoutExpired:
                _gen_proc.kill()
            stopped.append(_gen_proc.pid)
            _gen_proc = None
        pid = _pgrep_gen()
        if pid:
            try:
                subprocess.run(["kill", pid], timeout=5)
                stopped.append(int(pid))
            except Exception:  # noqa: BLE001
                pass
        log("generator stopped pids=%s" % stopped)
        return {"ok": True, "stopped": stopped}


_gen_cache = (0.0, False)


def generator_running():
    # pgrep forks; stats asks once a second per dashboard. Cache briefly.
    global _gen_cache
    now = time.time()
    if now - _gen_cache[0] < 1.5:
        return _gen_cache[1]
    with _gen_lock:
        alive = bool(_gen_proc and _gen_proc.poll() is None)
    alive = alive or _pgrep_gen() is not None
    _gen_cache = (now, alive)
    return alive


# ---- chaos injection ---------------------------------------------------------
def _post_line(payload):
    req = urllib.request.Request(
        PIPELINE_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def chaos_inject(name):
    """Background thread: push the scenario's lines through the real pipeline."""
    lines = CHAOS[name]
    base = int(time.time())
    for i, (level, service, msg) in enumerate(lines):
        payload = {
            "id": "evt-chaos-%d-%d" % (base, i),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": level, "service": service, "msg": msg,
        }
        with HUB.lock:
            HUB.src_total += 1
        # "hero": the board draws this one line large and follows it by id.
        HUB.publish({"t": "src", "n": 0, "hero": payload["id"], "scenario": name})
        try:
            _post_line(payload)
            log("chaos %s line %d/%d sent" % (name, i + 1, len(lines)))
        except Exception as e:  # noqa: BLE001 - pipeline down; fail gracefully
            log("chaos %s line %d failed: %s" % (name, i + 1, e))
            return
        if i < len(lines) - 1:
            time.sleep(CHAOS_GAP_S)


# ---- tailing the pipeline's real output --------------------------------------
def _read_new(path, offset):
    """Return (new_offset, [lines]) for lines appended since offset."""
    try:
        size = os.path.getsize(path)
        if size < offset:
            offset = 0  # truncated underneath us (a fresh `just up`)
        # Binary on purpose: offsets are byte positions, and a text-mode seek to
        # an arbitrary byte offset is undefined once a line holds non-ASCII.
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read()
        # Only consume whole lines; a half-written record stays for next pass.
        end = chunk.rfind(b"\n")
        if end < 0:
            return offset, []
        text = chunk[:end].decode("utf-8", "replace")
        return offset + end + 1, [ln for ln in text.splitlines() if ln.strip()]
    except OSError:
        return offset, []


def ingest(b, rec):
    """Account for ONE record the pipeline wrote to bucket `b`.

    In a Jev-mode run (pipeline-recurrence.yaml) every receipt is exactly one of
    the three classes below, and they sum to the run's completed count. Outside
    Jev mode that invariant does not apply: a raw-bucket line or an Expanso-only
    record is in none of the three, and only `received` / `completed` count it.
      bypassed    routed_by == "expanso-bypass": matched the rules, NO model call
      judged      has a `jev` block and Jev answered
      jev_failed  has a `jev` block but Jev did not answer; the record was KEPT
                  (held for review), so this is an inference failure, not a drop
    """
    if b == "held":
        # First hold of a record. Not one of the three completed classes: it has
        # not completed. It resolves later as `released` or `gave_up`.
        with HUB.lock:
            HUB.bins[b] += 1
            HUB.recent[b].append(rec)
            HUB.run["received"][b] += 1
            HUB.run["held_in"] += 1
            HUB.jev_fail.append(True)
        HUB.publish({"t": "rec", "bin": "held", "judged": False, "bypassed": False, "ok": False,
                     "hero": _hero(rec)})
        return
    judged = "jev" in rec
    bypassed = rec.get("routed_by") == "expanso-bypass"
    try:
        attempts = int(rec.get("held_attempts") or 0)
    except (TypeError, ValueError):
        attempts = 0
    with HUB.lock:
        HUB.bins[b] += 1
        HUB.recent[b].append(rec)
        run = HUB.run
        run["received"][b] += 1
        HUB.per_sec[int(time.time())] += 1
        if b != "raw":
            HUB.last_kind = "jev" if "jev_decision" in rec else "expanso"
        if bypassed:
            run["bypassed"] += 1
        if judged:
            ok = rec.get("jev_ok", True)
            HUB.jev_fail.append(not ok)
            if ok:
                HUB.model = (rec.get("jev") or {}).get("model")
            run["judged" if ok else "jev_failed"] += 1
            if attempts > 0:
                run["released" if ok else "gave_up"] += 1
            base, got = rec.get("baseline"), rec.get("jev_decision")
            if ok and base == "archive" and got in ("page", "notify"):
                run["caught"] += 1
                HUB.caught.append(rec)
            elif ok and base in ("page", "notify") and got == "archive":
                run["quieted"] += 1
                HUB.quieted.append(rec)
    HUB.publish({"t": "rec", "bin": b, "judged": judged, "bypassed": bypassed,
                 "ok": bool(judged and rec.get("jev_ok", True)), "released": attempts > 0,
                 "hero": _hero(rec)})


def _hero(rec):
    """The id of an injected line, so the board can land the particle it launched."""
    i = str(rec.get("id") or "")
    return i if i.startswith("evt-chaos-") else None


def tailer():
    offsets = {}
    # Seed from whatever is already on disk so a server restart mid-demo keeps
    # honest counts. start.sh truncates these files, so a fresh run starts at 0.
    for fn, b in FILES.items():
        path = os.path.join(DATA, fn)
        offsets[path], lines = _read_new(path, 0)
        with HUB.lock:
            HUB.bins[b] += len(lines)
        for ln in lines[-30:]:
            try:
                HUB.recent[b].append(json.loads(ln))
            except ValueError:
                pass
    while True:
        time.sleep(0.2)
        for fn, b in FILES.items():
            path = os.path.join(DATA, fn)
            offsets[path], lines = _read_new(path, offsets.get(path, 0))
            for ln in lines:
                try:
                    rec = json.loads(ln)
                except ValueError:
                    continue
                ingest(b, rec)


class Gate(BaseHTTPRequestHandler):
    """Forward the pipeline's Jev calls, or fail them on purpose."""
    server_version = "jev-gate/1.0"

    def log_message(self, *a):
        pass

    def _reply(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        payload = self.rfile.read(n)
        with HUB.lock:
            fault = GATE_FAULTS.get(HUB.gate)
        if fault:
            return self._reply(fault[0], json.dumps(fault[1]).encode())
        if not UPSTREAM:
            return self._reply(502, b'{"error": "gate has no JEV_UPSTREAM_URL"}')
        try:
            headers = {"Content-Type": self.headers.get("Content-Type", "application/json")}
            if _JEV_KEY:
                headers["Authorization"] = "Bearer " + _JEV_KEY
            req = urllib.request.Request(UPSTREAM, data=payload, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=45) as r:
                code, body, ctype = r.status, r.read(), r.headers.get("Content-Type", "application/json")
            ok = True
        except urllib.error.HTTPError as e:
            code, body, ctype, ok = e.code, e.read(), e.headers.get("Content-Type", "application/json"), True
        except Exception:  # noqa: BLE001 - endpoint unreachable: a real outage, not a simulated one
            code, body, ctype, ok = 502, b'{"error": "Jev endpoint unreachable"}', "application/json", False
        with HUB.lock:
            HUB.upstream_ok = ok
        self._reply(code, body, ctype)


def heartbeat():
    while True:
        time.sleep(0.5)
        up = port_up()
        try:
            raw_bytes = os.path.getsize(os.path.join(DATA, "raw.jsonl"))
        except OSError:
            raw_bytes = 0
        with HUB.lock:
            HUB.pipeline_up = up
            HUB.raw_bytes = raw_bytes
            mode = HUB.mode()
            if mode != HUB.run["mode"]:
                HUB.run = HUB._new_run(mode)
                HUB.per_sec.clear()

                HUB.caught.clear()
                HUB.quieted.clear()
        HUB.publish(HUB.stats())


class Handler(BaseHTTPRequestHandler):
    server_version = "jev-live/2.0"

    def log_message(self, fmt, *args):
        # quiet: only surface errors
        if isinstance(args, tuple) and len(args) > 1:
            try:
                code = int(str(args[1]))
            except Exception:  # noqa: BLE001
                code = 0
            if code >= 400:
                log("HTTP %s %s -> %s" % (self.command, self.path, args[1]))

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, OSError):
            return {}

    def _send_html(self):
        try:
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                body = f.read()
        except FileNotFoundError:
            return self._send_json({"error": "index.html missing"}, 500)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._send_html()
        if path == "/health":
            return self._send_json({"ok": True, **HUB.stats()})
        if path.startswith("/api/bucket/"):
            b = path.rsplit("/", 1)[-1]
            if b not in BINS:
                return self._send_json({"error": "unknown bucket"}, 404)
            with HUB.lock:
                recs = list(HUB.recent[b])[-30:]
                total = HUB.bins[b]
            return self._send_json({"bin": b, "total": total,
                                    "records": recs[::-1]})
        if path.startswith("/api/pipeline/"):
            fn = PIPELINE_FILES.get(path[len("/api/pipeline/"):])
            if fn is None:
                return self._send_json({"error": "unknown pipeline"}, 404)
            with open(os.path.join(HERE, fn), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Pipeline-File", fn)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(body)
        if path == "/api/evidence":
            with HUB.lock:
                return self._send_json({"caught": list(HUB.caught)[::-1],
                                        "quieted": list(HUB.quieted)[::-1]})
        if path == "/events":
            return self._serve_sse()
        if path.rsplit(".", 1)[-1] in STATIC_TYPES:
            return self._send_static(path)
        return self._send_json({"error": "not found"}, 404)

    def _send_static(self, path):
        # Fonts are vendored beside the page so the demo never needs the network
        # to render. Resolve, then confirm the result is still inside HERE.
        full = os.path.realpath(os.path.join(HERE, path.lstrip("/")))
        roots = [os.path.realpath(os.path.join(HERE, d)) + os.sep for d in STATIC_DIRS]
        if not any(full.startswith(r) for r in roots) or not os.path.isfile(full):
            return self._send_json({"error": "not found"}, 404)
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", STATIC_TYPES[path.rsplit(".", 1)[-1]])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/beacon":
            body = self._body()
            n, ok = int(body.get("n") or 0), int(body.get("ok") or 0)
            if n:
                with HUB.lock:
                    HUB.src_total += n
                    HUB.run["produced"] += n
                HUB.publish({"t": "src", "n": n})
            if ok:
                # the pipeline's HTTP input answered 200 for these
                with HUB.lock:
                    HUB.run["accepted"] += ok
            return self._send_json({"ok": True})
        if self.path == "/api/gate":
            mode = self._body().get("mode")
            if mode not in ("open", *GATE_FAULTS):
                return self._send_json({"error": "mode must be open|overloaded|credential"}, 400)
            with HUB.lock:
                HUB.gate = mode
            log("gate -> %s%s" % (mode, "" if mode == "open" else " (SIMULATED outage)"))
            HUB.publish(HUB.stats())
            return self._send_json({"ok": True, "gate": mode})
        if self.path == "/api/jev":
            on = self._body().get("on")
            if not isinstance(on, bool):
                return self._send_json({"error": "body must be {\"on\": true|false}"}, 400)
            with HUB.lock:
                mode, busy = HUB.mode(), HUB.switching
            if busy:
                return self._send_json({"error": "a switch is already in flight"}, 409)
            if mode == "off":
                return self._send_json({"error": "no pipeline is running; deploy Expanso first"}, 409)
            target = "jev" if on else "expanso"
            if target == mode:
                return self._send_json({"ok": True, "unchanged": True})
            threading.Thread(target=jev_switch, args=(target,), daemon=True).start()
            return self._send_json({"ok": True, "target": target}, 202)
        if self.path == "/raw":
            with HUB.lock:
                mid_switch = bool(HUB.switching)
            if mid_switch:
                # A pipeline exists; it is between versions. The source retries.
                return self._send_json({"ok": False, "retry": True}, 503)
            # The pipeline refused this line (there is no pipeline). Production
            # does what production does: dumps it, verbatim, in the raw bucket.
            line = json.dumps(self._body(), separators=(",", ":"))
            with _raw_lock:
                with open(os.path.join(DATA, "raw.jsonl"), "a") as f:
                    f.write(line + "\n")
            return self._send_json({"ok": True})
        if self.path.startswith("/chaos/"):
            name = self.path.rsplit("/", 1)[-1]
            if name not in CHAOS:
                return self._send_json({"error": "unknown scenario"}, 404)
            threading.Thread(target=chaos_inject, args=(name,),
                             daemon=True).start()
            log("chaos %s accepted (%d lines)" % (name, len(CHAOS[name])))
            return self._send_json({"ok": True, "scenario": name,
                                    "lines": len(CHAOS[name])}, 202)
        if self.path == "/generator/start":
            r = generator_start()
            return self._send_json(r, 200 if r["ok"] else 500)
        if self.path == "/generator/stop":
            return self._send_json(generator_stop())
        return self._send_json({"error": "not found"}, 404)

    def _serve_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        q = queue.Queue(maxsize=4000)
        with HUB.lock:
            HUB.subs.add(q)
        try:
            self.wfile.write(("data: %s\n\n" % json.dumps(HUB.stats())).encode())
            self.wfile.flush()
            while True:
                try:
                    line = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    continue
                # Drain whatever else is queued into one write: at burst rates
                # a flush per message is the bottleneck, not the network.
                out = ["data: %s\n\n" % line]
                try:
                    while len(out) < 200:
                        out.append("data: %s\n\n" % q.get_nowait())
                except queue.Empty:
                    pass
                self.wfile.write("".join(out).encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # client went away; thread ends
        except Exception as e:  # noqa: BLE001
            log("sse error: %s" % e)
        finally:
            with HUB.lock:
                HUB.subs.discard(q)


def main():
    os.makedirs(DATA, exist_ok=True)
    threading.Thread(target=tailer, daemon=True).start()
    threading.Thread(target=heartbeat, daemon=True).start()
    threading.Thread(target=detector, daemon=True).start()
    gate = ThreadingHTTPServer(("127.0.0.1", GATE_PORT), Gate)
    gate.daemon_threads = True
    threading.Thread(target=gate.serve_forever, daemon=True).start()
    log("jev gate on http://127.0.0.1:%d -> %s, %s" % (
        GATE_PORT, "upstream set" if UPSTREAM else "NO UPSTREAM",
        "adds Bearer auth" if _JEV_KEY else "no key: forwards unauthenticated"))
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    log("serving dashboard on http://127.0.0.1:%d  (data: %s)" % (PORT, DATA))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("shutting down")


if __name__ == "__main__":
    main()
