# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Post matched inputs through the LIVE pipeline and report which ones bypassed.

Run with the generator paused and pipeline-recurrence.yaml deployed. Reads the
pipeline's own output records, so the verdict is what the pipeline did, not what
this script expects it to do. Exit 1 on any mismatch.
"""
import json
import pathlib
import sys
import time
import urllib.request

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
CASES = [  # (label, level, service, msg, expect_bypass)
    ("known benign, exact",            "INFO",  "api",   "GET /health 200 2ms",                        True),
    ("known benign, exact",            "INFO",  "cache", "cache hit rate 0.94 window=5m",              True),
    ("changed status 200 -> 500",      "INFO",  "api",   "GET /health 500 2ms",                        False),
    ("changed latency 2ms -> 9000ms",  "INFO",  "api",   "GET /health 200 9000ms",                     False),
    ("changed rate 0.94 -> 0.01",      "INFO",  "cache", "cache hit rate 0.01 window=5m",              False),
    ("changed gc pause 12ms -> 8400ms","INFO",  "api",   "gc pause 8400ms heap=1.2gb",                 False),
    ("WARN carrying a benign message", "WARN",  "api",   "GET /health 200 2ms",                        False),
    ("ERROR carrying a benign message","ERROR", "api",   "GET /health 200 2ms",                        False),
    ("benign message, wrong service",  "INFO",  "db",    "GET /health 200 2ms",                        False),
    ("novel INFO (the quiet one)",     "INFO",  "api",   "config reload requested by unknown actor",   False),
]
run = int(time.time())
for i, (_, level, service, msg, _) in enumerate(CASES):
    ev = {"id": f"case-{run}-{i}", "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
          "level": level, "service": service, "msg": msg}
    req = urllib.request.Request("http://[::1]:8080/logs", data=json.dumps(ev).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=60).read()
time.sleep(3)
got = {}
for f in DATA.glob("*.jsonl"):
    for ln in f.read_text().splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if str(r.get("id", "")).startswith(f"case-{run}-"):
            got[int(r["id"].rsplit("-", 1)[1])] = (r, f.name)
bad = 0
print(f"{'case':34s} {'level':6s} {'bypass':7s} {'inference':22s} {'baseline':9s} -> {'landed in':14s} verdict")
for i, (label, level, _, _, expect) in enumerate(CASES):
    if i not in got:
        print(f"{label:34s} {level:6s} MISSING FROM OUTPUT")
        bad += 1
        continue
    r, fn = got[i]
    ok = r.get("bypass") is expect and (("jev" in r) is (not expect))
    bad += not ok
    # "attempted" is not "judged": if the endpoint did not answer, the pipeline
    # fell back to review and no model judgment exists for that record.
    inf = "none" if "jev" not in r else ("judged by Jev" if r.get("jev_ok") else "attempted -> fallback")
    print(f"{label:34s} {level:6s} {str(r.get('bypass')):7s} {inf:22s} "
          f"{r.get('baseline','?'):9s} -> {fn:14s} {'PASS' if ok else 'FAIL'}")
print(f"\n{len(CASES)-bad}/{len(CASES)} passed")
sys.exit(1 if bad else 0)
