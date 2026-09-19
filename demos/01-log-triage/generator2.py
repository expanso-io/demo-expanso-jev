#!/usr/bin/env python3
"""Generator v2: bursty background traffic + a recurrence scenario.

Scenario: the same auth-failure line repeats 4x, ~25s apart, in a loop.
Occurrence #1 should look like noise (archive). By #4, the recurrence
history ("4th occurrence in 10 minutes, previous: archive x3") should
push Jev's actionable score up -- same input, different judgment.

Traffic shape
-------------
Real log volume is not a metronome, and a flat line on the dashboard is the
tell that a demo is synthetic. Three things make it jagged here:

  * heavy-tailed gaps -- arrivals are exponential, not fixed, so even a calm
    stretch has visible texture rather than a straight line;
  * batch arrivals -- one request writes several lines, so events land in
    clumps of 1..12 instead of singly;
  * regimes -- the generator wanders between calm, normal and storm. A storm
    is a retry loop or crash loop: one template repeating fast for a few
    seconds, which is also what real recurrence looks like to the pipeline.

Mean rate over minutes lands near 40/sec. Most of it is routine INFO that the
pipeline collapses, so Jev judges only a few per second; it just arrives unevenly. Tune
with JEV_GEN_RATE, or set JEV_GEN_JAGGED=0 for the old flat behaviour.
"""
import json
import os
import random
import signal
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = "http://[::1]:8080/logs"

# The dashboard draws the SOURCE side of the picture from these beacons, not
# from pipeline output -- because in act one there is no pipeline, and the
# whole point is to watch logs being produced before anything processes them.
# A beacon says "n lines were just emitted".
BEACON = "http://127.0.0.1:%s/beacon" % os.environ.get("JEV_LIVE_PORT", "8890")

# Baseline events/sec. The regime multipliers average out ~1.3x, so the
# observed mean over minutes lands near 40/sec. Instantaneous rate swings well above and below; that is
# the point.
RATE = float(os.environ.get("JEV_GEN_RATE", "30"))

# Jev judges ~30 events/sec on a laptop before latency runs away. The pipeline
# collapses repeated INFO lines before asking Jev, and ~90% of this traffic is
# routine INFO, so Jev sees roughly a seventh of the source rate. MAX_RATE and
# STORM_SHARE together keep the judged rate under that ceiling: a burst should
# look like a burst, not knock the pipeline over on camera.
MAX_RATE = float(os.environ.get("JEV_GEN_MAX_RATE", "85"))
STORM_SHARE = 0.15   # fraction of a storm's lines that are the repeating line
JAGGED = os.environ.get("JEV_GEN_JAGGED", "1") != "0"

# A burst can fire a dozen posts at once, and each one waits on the pipeline.
# Without a pool the burst just serialises and the jaggedness is lost in
# transit -- the dashboard would show the smoothed arrival rate, not ours.
POOL = ThreadPoolExecutor(max_workers=64)

TEMPLATES = [
    (56, "INFO", "api", "GET /health 200 2ms"),
    (40, "INFO", "api", "GET /metrics 200 5ms"),
    (32, "INFO", "worker", "cron heartbeat ok job=nightly-rollup"),
    (32, "INFO", "cache", "cache hit rate 0.94 window=5m"),
    (24, "INFO", "api", "gc pause 12ms heap=1.2gb"),
    (20, "INFO", "deploy", "rollout step 3/8 complete service=checkout"),
    (20, "INFO", "db", "connection pool idle 45/50"),
    (4, "WARN", "db", "slow query 4.2s on orders table rows=120k"),
    (3, "WARN", "edge", "TLS certificate expiring in 72 hours, renewal failed twice"),
    (3, "WARN", "api", "memory usage 87% on api-3"),
    (3, "WARN", "db", "replica lag 45s on read-replica-2"),
    (2, "WARN", "api", "error rate 2.1% on /payments threshold=2%"),
    (2, "WARN", "infra", "disk usage 82% on /var node=worker-9"),
    (2, "ERROR", "api", "OOMKilled container api-7 exit=137"),
    (1, "ERROR", "db", "database primary unreachable, failover initiated"),
    (1, "ERROR", "api", "payment webhook failing 100% for 5m endpoint=/v1/charge"),
    (2, "WARN", "net", "unusual traffic pattern from 10.0.4.0/24 rate=8x baseline"),
    (1, "INFO", "api", "config reload requested by unknown actor"),
    (1, "WARN", "infra", "timestamp drift 800ms on worker-9"),
    (1, "WARN", "api", "deprecated API v1 called 400x in 1m client=unknown"),
    (1, "WARN", "infra", "pod restarted 3 times in 10m CrashLoop suspected"),
    (1, "WARN", "edge", "certificate serial changed unexpectedly cn=api.expanso.io"),
]

WEIGHTS = [t[0] for t in TEMPLATES]
POP = [(t[1], t[2], t[3]) for t in TEMPLATES]

# The fingerprint strips digits, so the source IP cannot distinguish cycles --
# the username does. Each cycle is a clean occurrence 1..4 escalation of a line
# the counter has not seen in its window.
SCENARIO_USERS = ["admin", "root", "deploy", "jenkins", "backup", "oracle",
                  "postgres", "ubuntu", "ansible", "gitlab"]
SCENARIO_TIMES = [8, 33, 58, 83]   # seconds into each cycle
SCENARIO_CYCLE_S = 130

counter = 0
counter_lock = threading.Lock()
errors = 0


def make_event(level=None, service=None, msg=None):
    global counter
    with counter_lock:
        counter += 1
        n = counter
    if msg is None:
        level, service, msg = random.choices(POP, weights=WEIGHTS, k=1)[0]
    return {
        "id": f"evt-{n:06d}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": level, "service": service, "msg": msg,
    }


def post(event):
    req = urllib.request.Request(
        URL, data=json.dumps(event).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=45) as r:
        r.read()


# name, weight, duration range (s), rate multiplier range, storm?
REGIMES = [
    ("calm",   28, (6, 20),  (0.35, 0.65), False),
    ("normal", 50, (20, 55), (0.85, 1.40), False),
    ("busy",   16, (8, 25),  (1.8, 2.8),   False),
    ("storm",   6, (3, 10),  (1.6, 2.2),   True),
]
REGIME_NAMES = [r[0] for r in REGIMES]
REGIME_WEIGHTS = [r[1] for r in REGIMES]

# Templates a retry/crash loop would hammer. A storm repeats ONE of these
# rather than drawing fresh each time -- that is what makes it a storm and not
# just more noise, and it is what the recurrence counter is built to notice.
STORM_TEMPLATES = [
    ("ERROR", "api", "payment webhook failing 100% for 5m endpoint=/v1/charge"),
    ("WARN", "infra", "pod restarted 3 times in 10m CrashLoop suspected"),
    ("ERROR", "db", "database primary unreachable, failover initiated"),
    ("WARN", "api", "error rate 2.1% on /payments threshold=2%"),
    ("WARN", "net", "unusual traffic pattern from 10.0.4.0/24 rate=8x baseline"),
]


def batch_size():
    """Most arrivals are single lines; a minority are clumps.

    Heavy tail on purpose. One HTTP request that fails writes an access line, a
    stack trace and a retry line together, so a flat "one event per arrival"
    model never produces the clumping you see in a real tail -f.
    """
    r = random.random()
    if r < 0.50:
        return 1
    if r < 0.86:
        return random.randint(2, 4)
    if r < 0.99:
        return random.randint(5, 10)
    return random.randint(12, 20)   # a spike worth seeing on the dashboard


_oks = 0
_oks_lock = threading.Lock()

# Set on SIGTERM. Producers stop, in-flight posts are allowed to finish, the
# last "accepted" count is flushed, THEN the process exits. Dying mid-flight
# left the board's stages permanently out of step: lines already reported as
# produced were never sent, and lines the pipeline did process never had their
# acceptance reported.
STOP = threading.Event()


def ok_flusher():
    """Tell the board how many lines the pipeline ACCEPTED, batched per 0.5s.

    "Produced" is not "accepted": a post can be refused or still in flight. The
    board shows both so its counters never imply the pipeline saw a line it
    did not.
    """
    global _oks
    while not STOP.is_set():
        time.sleep(0.5)
        flush_oks()


def flush_oks():
    global _oks
    with _oks_lock:
        k, _oks = _oks, 0
    if k:
        beacon({"ok": k})


RAW = "http://127.0.0.1:%s/raw" % os.environ.get("JEV_LIVE_PORT", "8890")


def _post_json(url, payload, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()


def beacon(payload):
    """Fire-and-forget. The dashboard being down must never slow the source."""
    try:
        _post_json(BEACON, payload, 1)
    except Exception:
        pass


def post_many(events):
    if STOP.is_set():
        return  # never announce lines we are not going to send

    def send(ev):
        global errors
        global _oks
        try:
            post(ev)
            with _oks_lock:
                _oks += 1
        except Exception:
            # Not an error condition. With no pipeline deployed nothing listens
            # on :8080 and the post is refused. Production does not stop writing
            # logs because nobody is processing them -- the line goes where it
            # always went, verbatim into the raw bucket. That is act one.
            errors += 1
            for _ in range(30):
                try:
                    _post_json(RAW, ev, 2)
                    return
                except urllib.error.HTTPError as e:
                    if e.code != 503:
                        return
                except Exception:
                    return
                # 503: the pipeline is between versions, not absent. Wait and
                # give the line to the pipeline, as a real shipper would.
                time.sleep(1.0)
                try:
                    post(ev)
                    with _oks_lock:
                        _oks += 1
                    return
                except Exception:
                    pass
    POOL.submit(beacon, {"n": len(events)})
    for ev in events:
        POOL.submit(send, ev)


def traffic():
    """Single scheduler: pick a regime, then emit batches on jagged gaps."""
    while not STOP.is_set():
        name, _, dur, mult, is_storm = random.choices(
            REGIMES, weights=REGIME_WEIGHTS, k=1)[0]
        until = time.time() + random.uniform(*dur)
        rate = min(RATE * random.uniform(*mult), MAX_RATE)
        storm_line = random.choice(STORM_TEMPLATES) if is_storm else None
        if is_storm:
            print(f"regime={name} rate~{rate:.1f}/s line={storm_line[2][:40]}",
                  flush=True)

        while time.time() < until and not STOP.is_set():
            n = batch_size()
            if storm_line:
                # A retry loop rides on top of normal traffic; it does not
                # replace it. Every repeat of a WARN/ERROR is judged, so the
                # share is what keeps a storm inside Jev's throughput.
                events = [make_event(*storm_line) if random.random() < STORM_SHARE
                          else make_event() for _ in range(n)]
            else:
                events = [make_event() for _ in range(n)]
            post_many(events)

            # Exponential gaps scaled so batches * rate lands near the target.
            # random() alone would give uniform gaps, which still reads as
            # mechanical; the exponential is what makes the line ragged.
            gap = random.expovariate(max(rate, 0.1) / max(n, 1))
            time.sleep(min(gap, 2.5))   # cap so a long tail is not dead air

        if random.random() < 0.10:
            # Occasional real silence. Logs do stop -- but keep it short: a
            # demo board that sits still for seconds reads as broken, not calm.
            time.sleep(random.uniform(0.6, 1.8))


def worker(wid):
    """Flat fallback: the original one-post-per-second-per-thread behaviour."""
    while True:
        post_many([make_event()])
        time.sleep(1.0)


def scenario():
    """Emit the SAME line 4x, ~25s apart, so recurrence escalates it.

    Loops forever: the presenter decides when Jev gets switched on, so an
    escalation has to be in flight whenever that happens, not only in the
    first two minutes after the generator starts.
    """
    cycle = 0
    while not STOP.is_set():
        user = SCENARIO_USERS[cycle % len(SCENARIO_USERS)]
        msg = f"auth failed for user {user} from 10.0.9.12"
        t0 = time.time()
        for i, at in enumerate(SCENARIO_TIMES, 1):
            time.sleep(max(0, t0 + at - time.time()))
            post_many([make_event("WARN", "auth", msg)])
            print(f"SCENARIO {user} occurrence #{i} sent", flush=True)
        time.sleep(max(0, t0 + SCENARIO_CYCLE_S - time.time()))
        cycle += 1


def main():
    if JAGGED:
        print(f"starting bursty traffic (mean {RATE}/sec) + scenario -> {URL}",
              flush=True)
        threading.Thread(target=traffic, daemon=True).start()
    else:
        print(f"starting 6 flat workers + scenario -> {URL}", flush=True)
        for i in range(6):
            threading.Thread(target=worker, args=(i,), daemon=True).start()
    threading.Thread(target=scenario, daemon=True).start()
    threading.Thread(target=ok_flusher, daemon=True).start()

    # Report the peak second alongside the mean. A mean alone hides exactly the
    # property we just built, and would read identically to the flat version.
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    last = 0
    while not STOP.is_set():
        peak = 0
        for _ in range(10):
            if STOP.is_set():
                break
            with counter_lock:
                a = counter
            time.sleep(1)
            with counter_lock:
                b = counter
            peak = max(peak, b - a)
        with counter_lock:
            n = counter
        print(f"sent={n} mean={(n - last) / 10:.1f}/sec peak={peak}/sec "
              f"to_raw_bucket={errors}", flush=True)
        last = n

    print("stopping: draining in-flight posts", flush=True)
    POOL.shutdown(wait=True)      # every post already announced gets its answer
    flush_oks()
    print("drained, exiting", flush=True)


if __name__ == "__main__":
    main()
