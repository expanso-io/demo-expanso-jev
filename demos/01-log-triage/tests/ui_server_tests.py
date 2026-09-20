# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Bounded local tests for the dashboard server. No Expanso Cloud, no pipeline,
no demo start: the HTTP handler runs on an ephemeral localhost port against a
scratch data directory, and is shut down in `finally`.

Covers: the Pipeline-YAML route cannot disclose anything outside its allowlist;
metric arithmetic; empty / zero / error states; and that a no-model record, a
judged record and a fallback record are accounted on three separate paths.
"""
import hashlib
import http.client
import json
import pathlib
import re
import sys
import threading
import time
from http.server import ThreadingHTTPServer

PKG = pathlib.Path(__file__).resolve().parents[1]
SCRATCH = PKG / ".test-scratch/ui-server-tests-data"
SCRATCH.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(PKG))
import server  # noqa: E402  (module import starts no threads; main() is guarded)

server.DATA = str(SCRATCH)
SECRETish = re.compile(rb"exp_(ak|bk)_|JEV_API_URL=|EXPANSO_CLI_|BEGIN [A-Z ]*PRIVATE KEY|api_key")
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")


srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]


def req(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, body=body)   # http.client sends the path verbatim, unnormalised
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, data, dict(r.getheaders())


try:
    print("--- 1. the YAML route serves exactly two files, verbatim")
    for key, fn in server.PIPELINE_FILES.items():
        st, data, hdr = req("GET", f"/api/pipeline/{key}")
        disk = (PKG / fn).read_bytes()
        check(f"GET /api/pipeline/{key} -> 200, byte-identical to {fn}", st == 200 and data == disk, f"{len(data)} bytes")
        check(f"  declares its file name ({hdr.get('X-Pipeline-File')})", hdr.get("X-Pipeline-File") == fn)
    st, data, _ = req("GET", "/api/pipeline/recurrence")
    check("  ${JEV_API_URL} is served as a literal placeholder, not interpolated", b"${JEV_API_URL}" in data)
    check("  served YAML contains no credential-shaped content", not SECRETish.search(data.replace(b"${JEV_API_URL}", b"")))

    print("--- 2. positive control: the static route really does serve files")
    st, data, _ = req("GET", "/fonts/fonts.css")
    check("GET /fonts/fonts.css -> 200 (so the 404s below mean something)", st == 200 and b"@font-face" in data)
    st, data, hdr = req("GET", "/assets/typesafe-mark.png")
    check("GET /assets/typesafe-mark.png -> 200 image/png", st == 200 and hdr.get("Content-Type") == "image/png" and data[:4] == b"\x89PNG")
    st, data, hdr = req("GET", "/assets/expanso-logo-full-violet.svg")
    check("GET /assets/expanso-logo-full-violet.svg -> 200 image/svg+xml", st == 200 and hdr.get("Content-Type") == "image/svg+xml")

    print("--- 3. nothing else is reachable")
    attacks = [
        "/api/pipeline/../.env", "/api/pipeline/..%2f.env", "/api/pipeline/%2e%2e/%2e%2e/.env",
        "/api/pipeline/.env", "/api/pipeline/server.py", "/api/pipeline/logging/../../.env",
        "/api/pipeline/pipeline-logging.yaml", "/api/pipeline//etc/passwd", "/api/pipeline/",
        "/api/pipeline/logging%00", "/api/pipeline/LOGGING",
        "/.env", "/../.env", "/../../.env", "/../../.scratch", "/.scratch", "/fonts/../.env",
        "/fonts/../../../.env", "/fonts/../server.py", "/fonts/..%2f..%2f.env", "/etc/passwd",
        "/fonts/../../../.env%00.css", "/../../.expanso/edge/auth/credentials.creds",
        "/fonts/../../../.expanso/edge/config.d/50-connection.yaml", "/server.py", "/data/raw.jsonl",
        # image types are servable now, but ONLY from fonts/ and assets/
        "/tests/ui_server_tests.py", "/assets/../tests/ui_server_tests.py", "/assets/../index.html.png",
        "/assets/../../../.expanso/edge/auth/credentials.creds", "/assets/../.env.png",
    ]
    for path in attacks:
        st, data, _ = req("GET", path)
        check(f"GET {path} -> {st}", st in (400, 404) and not SECRETish.search(data))

    print("--- 4. the route is read-only")
    before = {fn: hashlib.sha256((PKG / fn).read_bytes()).hexdigest() for fn in server.PIPELINE_FILES.values()}
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        st, _, _ = req(method, "/api/pipeline/logging", body=b"name: pwned\n")
        check(f"{method} /api/pipeline/logging -> {st} (not 2xx)", not 200 <= st < 300)
    after = {fn: hashlib.sha256((PKG / fn).read_bytes()).hexdigest() for fn in server.PIPELINE_FILES.values()}
    check("pipeline files unchanged on disk", before == after)

    print("--- 5. empty / zero state")
    H = server.HUB
    H.run = H._new_run("jev")
    H.per_sec.clear()
    s = H.stats()
    json.dumps(s)  # must be serialisable as sent to the browser
    r = s["run"]
    check("fresh run: completed 0, rate 0.0, 60-point series, no exception",
          r["completed"] == 0 and r["rate"] == 0.0 and len(r["spark"]) == 60 and sum(r["spark"]) == 0)
    check("fresh run: all three paths are zero", r["bypassed"] == r["judged"] == r["jev_failed"] == 0)

    print("--- 6. three paths, accounted separately, summing to completed")
    base = {"level": "INFO", "service": "api", "msg": "m", "baseline": "archive"}
    for _ in range(7):   # known routine: matched the rules, no model call, no jev block
        server.ingest("archive", {**base, "bypass": True, "routed_by": "expanso-bypass", "jev_decision": "archive"})
    server.ingest("notify", {**base, "bypass": False, "routed_by": "jev", "jev_ok": True, "jev_decision": "notify",
                             "jev": {"answers": {"actionable": {"noul": 0.9}}}})       # judged, and a "caught"
    server.ingest("page", {**base, "level": "ERROR", "baseline": "page", "bypass": False, "routed_by": "jev",
                           "jev_ok": True, "jev_decision": "page", "jev": {"answers": {}}})  # judged, agrees with baseline
    server.ingest("review", {**base, "bypass": False, "routed_by": "jev", "jev_ok": False, "jev_decision": "review",
                             "jev": {"answers": {}}})                                  # inference failed; record KEPT
    r = H.stats()["run"]
    check("bypassed=7 judged=2 jev_failed=1", (r["bypassed"], r["judged"], r["jev_failed"]) == (7, 2, 1), str((r["bypassed"], r["judged"], r["jev_failed"])))
    check("bypassed + judged + jev_failed == completed == 10", r["bypassed"] + r["judged"] + r["jev_failed"] == r["completed"] == 10)
    check("a bypassed record never counts as judged (no model path stays separate)", r["judged"] == 2)
    check("the fallback record was retained, not dropped (it is in REVIEW)", r["received"]["review"] == 1)
    check("no-model share = 7/10 = 70%", round(r["bypassed"] / r["completed"] * 100) == 70)
    check("'caught' counts only a real judgment that beat the baseline (1), never a fallback", r["caught"] == 1)

    print("--- 7. rate is measured over the stated window, excluding the partial second")
    H.per_sec.clear()
    now = int(time.time())
    for i in range(1, 11):
        H.per_sec[now - i] = 5
    H.per_sec[now] = 999   # the still-filling second must not count
    r = H.stats()["run"]
    check(f"50 records over {r['rate_window_s']} s -> 5.0 /sec", r["rate"] == 5.0 and r["rate_window_s"] == 10, str(r["rate"]))

    print("--- 8. error state is reported, not hidden")
    H.jev_fail.clear()
    for _ in range(5):
        H.jev_fail.append(True)
    check("five straight unanswered judgments -> jev_down true", H.stats()["jev_down"] is True)
    H.jev_fail.append(False)
    check("one answer clears it", H.stats()["jev_down"] is False)
    print("--- 9. hold accounting: a held record is in flight, not completed")
    H.run = H._new_run("jev")
    H.jev_fail.clear()
    held = {**base, "level": "WARN", "baseline": "notify", "jev_ok": False, "jev_decision": "held", "held_attempts": 0, "jev": {"answers": {}}}
    for _ in range(5):
        server.ingest("held", held)
    r = H.stats()["run"]
    check("5 hold receipts: held_in=5, holding=5, completed stays 0", (r["held_in"], r["holding"], r["completed"]) == (5, 5, 0), str((r["held_in"], r["holding"], r["completed"])))
    check("a hold receipt is none of bypassed/judged/jev_failed", r["bypassed"] == r["judged"] == r["jev_failed"] == 0)
    for _ in range(3):   # Jev came back: the same records, judged on a later attempt
        server.ingest("notify", {**held, "jev_ok": True, "jev_decision": "notify", "held_attempts": 4, "routed_by": "jev", "jev": {"model": "m", "answers": {}}})
    server.ingest("review", {**held, "jev_ok": False, "jev_decision": "review", "held_attempts": 15, "routed_by": "jev"})   # gave up
    r = H.stats()["run"]
    check("released=3 gave_up=1 holding=1", (r["released"], r["gave_up"], r["holding"]) == (3, 1, 1), str((r["released"], r["gave_up"], r["holding"])))
    check("held_in == released + gave_up + holding", r["held_in"] == r["released"] + r["gave_up"] + r["holding"])
    check("completed counts the 4 resolved records and no hold receipts", r["completed"] == 4)
    check("bypassed + judged + jev_failed == completed still holds", r["bypassed"] + r["judged"] + r["jev_failed"] == r["completed"])
    check("a release is a real judgment; a give-up is a failure, never a judgment", r["judged"] == 3 and r["jev_failed"] == 1)

    print("--- 10. the fault-injection gate")
    gate = ThreadingHTTPServer(("127.0.0.1", 0), server.Gate)
    gate.daemon_threads = True
    threading.Thread(target=gate.serve_forever, daemon=True).start()
    gport = gate.server_address[1]

    def gpost():
        c = http.client.HTTPConnection("127.0.0.1", gport, timeout=5)
        c.request("POST", "/v1/systemone", body=b"{}", headers={"Content-Type": "application/json"})
        rr = c.getresponse()
        d = rr.read()
        c.close()
        return rr.status, d

    try:
        for mode, code in (("overloaded", 503), ("credential", 401)):
            st, _, _ = req("POST", "/api/gate", body=json.dumps({"mode": mode}).encode())
            gs, gd = gpost()
            check(f"gate {mode}: control 200, the pipeline's call gets HTTP {code}, body marked simulated",
                  st == 200 and gs == code and json.loads(gd).get("simulated") is True)
        st, _, _ = req("POST", "/api/gate", body=b'{"mode": "open"}')
        server.UPSTREAM = ""
        gs, _ = gpost()
        check("gate open with no upstream configured -> 502, never a fabricated answer", st == 200 and gs == 502)
        server.UPSTREAM = "http://127.0.0.1:9/nothing-listens-here"
        gs, gd = gpost()
        check("gate open, upstream unreachable -> 502 and upstream_ok false (a REAL outage, not labelled simulated)",
              gs == 502 and b"simulated" not in gd and H.stats()["upstream_ok"] is False)
        # an upstream that records what the gate sent it
        from http.server import BaseHTTPRequestHandler
        seen = {}

        class Echo(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                seen["auth"] = self.headers.get("Authorization")
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                body = b'{"model": "echo", "answers": {}}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        up = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
        up.daemon_threads = True
        threading.Thread(target=up.serve_forever, daemon=True).start()
        try:
            server.UPSTREAM = f"http://127.0.0.1:{up.server_address[1]}/v1/systemone"
            server._JEV_KEY = ""
            gs, _ = gpost()
            check("no key: the gate forwards with NO Authorization header", gs == 200 and seen.get("auth") is None)
            FAKE = "test-only-not-a-real-key-0123456789"
            server._JEV_KEY = FAKE
            gs, _ = gpost()
            check("key present: the gate adds 'Authorization: Bearer <key>'", gs == 200 and seen.get("auth") == "Bearer " + FAKE)
            blob = json.dumps(H.stats())
            st, hbody, _ = req("GET", "/health")
            check("the key never appears in stats or /health; only its presence does",
                  FAKE not in blob and FAKE.encode() not in hbody and H.stats()["upstream_auth"] is True)
            server._JEV_KEY = ""
        finally:
            up.shutdown()
            up.server_close()
        check("server.py took TYPESAFE_API_KEY out of its environment at import", "TYPESAFE_API_KEY" not in __import__("os").environ)
        st, _, _ = req("POST", "/api/gate", body=b'{"mode": "explode"}')
        check("unknown gate mode -> 400, gate unchanged", st == 400 and H.stats()["gate"] == "open")
    finally:
        gate.shutdown()
        gate.server_close()
finally:
    srv.shutdown()
    srv.server_close()
    print(f"\ntest server on :{port} shut down")

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
