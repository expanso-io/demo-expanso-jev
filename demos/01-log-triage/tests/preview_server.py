# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""LAYOUT PREVIEW ONLY. Not the demo, not evidence of pipeline behaviour.

Serves the board on 127.0.0.1:8891 and REPLAYS records that the real
Cloud-deployed pipeline wrote during the last run (data/*.jsonl), at roughly
their original pace, so the layout can be checked with real receipts while the
demo itself stays down. No Expanso Cloud, no edge agent, no generator, no Jev.
Writes nothing outside the scratch dir. Exits by itself after LIFETIME_S.
"""
import json
import pathlib
import sys
import threading
import time
from http.server import ThreadingHTTPServer

PKG = pathlib.Path(__file__).resolve().parents[1]
SCRATCH = PKG / ".test-scratch/preview-data"
SCRATCH.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(PKG))
import server  # noqa: E402

LIFETIME_S = int(sys.argv[1]) if len(sys.argv) > 1 else 75
server.DATA = str(SCRATCH)
H = server.HUB
H.pipeline_up, H.cloud_ok, H.cloud_mode = True, True, "jev"   # forced: this is a replay
H.replay = True
H.run = H._new_run("jev")

recs = []
for fn, b in server.FILES.items():
    f = PKG / "data" / fn
    if b == "raw" or not f.is_file():
        continue
    for ln in f.read_text().splitlines()[-400:]:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("routed_by") in ("expanso-bypass", "jev"):   # only the Jev-mode pipeline's records
            recs.append((r.get("received_at", ""), b, r))
recs.sort(key=lambda x: x[0])
print(f"replaying {len(recs)} real recorded records; exits in {LIFETIME_S}s", flush=True)


def replay():
    i = 0
    while True:
        for _ in range(4):               # ~40/sec, the source's designed mean
            _, b, r = recs[i % len(recs)]
            H.publish({"t": "src", "n": 1})
            server.ingest(b, r)
            i += 1
            time.sleep(0.025)
        H.publish(H.stats())


srv = ThreadingHTTPServer(("127.0.0.1", 8891), server.Handler)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
if recs:
    threading.Thread(target=replay, daemon=True).start()
try:
    time.sleep(LIFETIME_S)
finally:
    srv.shutdown()
    srv.server_close()
    print("preview server stopped", flush=True)
