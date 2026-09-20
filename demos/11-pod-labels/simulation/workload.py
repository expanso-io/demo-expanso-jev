"""Synthetic pod workload: steady routine logs, plus one named signal on request.

Runs inside each demo pod. The adapter imports SCENARIOS too, so the event
catalog, the label each event argues about, and the legend text live in one
place. fixtures.yaml embeds this file verbatim; test_adapter.py keeps them equal.

Each scenario carries:
  message  the log line the pod writes; the evidence Jev reads
  prefer   ordered label operations Expanso may propose for this evidence.
           The first one that is possible on the pod right now is the single
           question put to Jev. Code, not Jev, decides what may be asked.
  lane     investigation routes evidence without proposing a label change
  title    legend name
  why      legend text: why a rule alone does not settle it
"""

import json
import random
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SCENARIOS = {
    "investigate_restart": {
        "event": "investigation_restart",
        "lane": "investigation",
        "synthetic_stimulus": True,
        "restarts": 1,
        "message": "Synthetic incident: container restarted once; termination details and stack trace are unavailable. Cause unknown.",
        "prefer": [],
        "title": "Investigate one restart",
        "why": "A single restart with no termination evidence cannot establish a cause.",
    },
    "investigate_context": {
        "event": "investigation_context",
        "lane": "investigation",
        "synthetic_stimulus": True,
        "restarts": 5,
        "window": "4m",
        "release_sha": "7c9e2a1",
        "timeline": [
            "12:00 UTC: release 7c9e2a1 deployed (synthetic)",
            "12:02-12:06 UTC: five container restarts (synthetic)",
        ],
        "message": "Synthetic incident: five restarts in four minutes after recent release 7c9e2a1. Timeline: release at 12:00 UTC, restarts from 12:02 to 12:06 UTC. Correlation only; cause unknown, termination details and stack trace unavailable.",
        "prefer": [],
        "title": "Investigate release context",
        "why": "Repeated restarts and a nearby release narrow the search but do not prove the cause.",
    },
    "investigate_evidence": {
        "event": "investigation_evidence",
        "lane": "investigation",
        "synthetic_stimulus": True,
        "reason": "OOMKilled",
        "exit_code": 137,
        "memory_limit": "512Mi",
        "stack": "java.lang.OutOfMemoryError: Java heap space at OrderCache.load:212",
        "release_sha": "7c9e2a1",
        "recent_change": "Release 7c9e2a1 increased the cache limit from 10000 to 100000 entries (synthetic)",
        "message": "Synthetic incident: OOMKilled, exit 137, memory limit 512Mi. java.lang.OutOfMemoryError: Java heap space at OrderCache.load:212. Recent release 7c9e2a1 increased the cache limit from 10000 to 100000 entries. Evidence supports investigating cache memory growth; the change is not a proven root cause.",
        "prefer": [],
        "title": "Investigate memory evidence",
        "why": "Termination evidence, a cache stack and a recent cache limit change support a focused investigation.",
    },
    "crashloop": {
        "event": "container_restart_backoff",
        "reason": "CrashLoopBackOff",
        "restarts": 5,
        "window": "4m",
        "exit_code": 137,
        "message": "Back-off restarting failed container api: 5 restarts in 4m, last exit code 137; the container is not staying up",
        "prefer": [["add", "health", "degraded"]],
        "title": "Crash loop",
        "why": "One restart is noise. Five in four minutes is a pattern, and only the sequence says so.",
    },
    "restart": {
        "event": "container_restarted",
        "reason": "NodeDrain",
        "restarts": 1,
        "message": "Container api restarted once after a planned node drain; ready again in 3s",
        "prefer": [["add", "restart", "expected"]],
        "title": "One restart",
        "why": "A planned drain and quick recovery make this an expected restart, not a failure.",
    },
    "oom": {
        "event": "container_oom_killed",
        "reason": "OOMKilled",
        "message": "OOMKilled. java.lang.OutOfMemoryError: Java heap space at OrderCache.load(OrderCache.java:212); working set 498Mi of 512Mi limit; killed for its own memory use while traffic was flat",
        "prefer": [["add", "pressure", "memory"]],
        "title": "Out of memory",
        "why": "The stack trace names the cause: a cache, not traffic. That is a memory label, not a health one.",
    },
    "squeeze": {
        "event": "resource_contention",
        "cpu_throttled_pct": 71,
        "memory_pct": 93,
        "p99_ms": 1840,
        "slo_ms": 400,
        "message": "CPU throttled in 71% of periods while memory is at 93% of limit and p99 latency is 1840ms against a 400ms SLO; requests are timing out and the pod cannot keep up with HTTP traffic",
        "prefer": [["add", "cpu", "throttled"]],
        "title": "Resource squeeze",
        "why": "CPU contention, high memory use and slow requests together identify a pod that cannot keep up.",
    },
    "probe": {
        "event": "readiness_probe_failed",
        "consecutive_failures": 6,
        "message": "Readiness probe failed 6 consecutive times: GET /ready 503, upstream db timeout after 2000ms; the pod cannot serve HTTP requests right now",
        "prefer": [["add", "traffic", "drain"]],
        "title": "Failing readiness",
        "why": "Six failures with the same upstream timeout justify marking the pod for draining.",
    },
    "egress": {
        "event": "network_policy_denied",
        "denied": 14,
        "message": "NetworkPolicy denied 14 egress connections to 203.0.113.9:4444 in 60s; running image digest differs from the deployed manifest; treat as possible compromise",
        "prefer": [["add", "security", "suspicious"]],
        "title": "Denied egress",
        "why": "Denied egress alone is common. Paired with an image digest mismatch, it is not.",
    },
    "healthy": {
        "event": "steady_state",
        "message": "Steady state for 10m: all probes passing, 0 restarts, p99 118ms, error rate 0.02%, memory at 41% of limit; healthy and serving HTTP traffic normally",
        "prefer": [["add", "health", "healthy"]],
        "title": "Back to healthy",
        "why": "Sustained clean metrics justify classifying the pod as healthy again.",
    },
    "attested": {
        "event": "image_attested",
        "message": "Image digest re-verified against the deployed manifest; no denied egress for 15m; the quarantine condition no longer holds",
        "prefer": [["add", "image", "verified"]],
        "title": "Image verified",
        "why": "Verification requires evidence about the image, not just good latency numbers.",
    },
    "batch": {
        "event": "batch_completed",
        "message": "Nightly batch finished: 2,140,000 rows in 11m, queue empty, no HTTP listeners active; this pod does batch work, not HTTP serving",
        "prefer": [["add", "workload", "batch"]],
        "title": "Batch finished",
        "why": "Nothing failed. The completed job and absence of HTTP listeners identify batch work.",
    },
}

ROUTINE = [
    "GET /healthz 200 1ms",
    "GET /api/v1/items 200 14ms",
    "POST /api/v1/orders 201 38ms",
    "GET /metrics 200 3ms",
    "cache hit ratio 0.97",
    "worker heartbeat ok",
    "GET /api/v1/cart 200 9ms",
    "connection pool 12/50 in use",
]


def routine_logs():
    while True:
        print(
            json.dumps(
                {
                    "event": "routine_heartbeat",
                    "at": time.time_ns(),
                    "message": random.choice(ROUTINE),
                    "synthetic_stimulus": True,
                }
            ),
            flush=True,
        )
        time.sleep(random.uniform(0.15, 0.5))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        scenario = self.path.removeprefix("/")
        if scenario not in SCENARIOS:
            self.send_error(404)
            return
        spec = SCENARIOS[scenario]
        event = {k: v for k, v in spec.items() if k not in {"prefer", "title", "why"}}
        event.update(at=time.time(), synthetic_stimulus=True)
        print(json.dumps(event), flush=True)
        payload = json.dumps(event).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in SCENARIOS:
        request = urllib.request.Request(
            "http://127.0.0.1:8080/" + sys.argv[1], data=b""
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            print(response.read().decode())
    else:
        threading.Thread(target=routine_logs, daemon=True).start()
        HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
