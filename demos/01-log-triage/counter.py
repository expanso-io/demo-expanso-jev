#!/usr/bin/env python3
"""Deterministic recurrence tracker (the Expanso side of the thesis).

In production this would be Redis. Here it's a 40-line sidecar:
the pipeline asks "how many times have we seen this fingerprint in the
last 10 minutes, and what did we decide before?" -- pure counting,
no judgment. Jev does the judging.

Endpoints:
  POST /track  {"fingerprint": "..."} -> {"occurrence": N, "window_s": 600,
      "first_seen_ago_s": S, "previous_decisions": [...]}
  POST /record {"fingerprint": "...", "decision": "page"|...} -> {"ok": true}
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

WINDOW_S = 600  # 10 minutes

store = {}  # fingerprint -> {"events": [ts, ...], "decisions": [...]}
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send({"error": "bad json"}, 400)
        now = time.time()
        with lock:
            if self.path == "/track":
                fp = data.get("fingerprint", "")
                e = store.setdefault(fp, {"events": [], "decisions": []})
                e["events"] = [t for t in e["events"] if now - t < WINDOW_S]
                e["events"].append(now)
                occ = len(e["events"])
                first_ago = int(now - e["events"][0]) if e["events"] else 0
                return self._send({
                    "occurrence": occ,
                    "window_s": WINDOW_S,
                    "first_seen_ago_s": first_ago,
                    "previous_decisions": e["decisions"][-5:],
                })
            if self.path == "/record":
                fp = data.get("fingerprint", "")
                e = store.setdefault(fp, {"events": [], "decisions": []})
                e["decisions"].append(data.get("decision", "unknown"))
                e["decisions"] = e["decisions"][-5:]
                return self._send({"ok": True})
        return self._send({"error": "not found"}, 404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8898), Handler).serve_forever()
    print("recurrence tracker on 127.0.0.1:8898", flush=True)
