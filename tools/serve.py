#!/usr/bin/env python3
"""Local servers the published page and the public-bar check rely on.

    python3 tools/serve.py static 8777     # the repository root, over http on 127.0.0.1
    python3 tools/serve.py pods 8901       # recorded adapter answers for the pod-labels pipeline
    python3 tools/serve.py stop 8777 8901  # stop whatever this repository started on those ports

All of them bind 127.0.0.1 only. `stop` signals only a process whose command line
names this file, one of the repository's other helper scripts, or `http.server`.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "demos" / "11-pod-labels" / "fixtures" / "adapter-replay.json"
OWNED = ("tools/serve.py", "jev-mock-server.py", "counter.py", "http.server")


class NoStore(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


def pods_handler(data: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, payload):
            raw = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self._send(200, {"status": "ok"})

        def do_POST(self):
            size = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(size) or b"{}")
            if self.path == "/candidates":
                found = data["candidates"].get(str(body.get("request_id")))
            elif self.path == "/judge":
                found = data["judge"].get(str(body.get("id")))
            elif self.path == "/apply":
                found = data["apply"].get(str(body.get("id")))
            else:
                found = None
            if found is None:
                return self._send(404, {"error": "no recorded answer"})
            return self._send(200, found)

    return Handler


def serve(handler, port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    try:
        server.serve_forever()
    finally:
        server.server_close()


def stop(ports: list[int]) -> int:
    for port in ports:
        out = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True
        ).stdout.split()
        for pid in out:
            cmd = subprocess.run(
                ["ps", "-p", pid, "-o", "command="], capture_output=True, text=True
            ).stdout
            if any(name in cmd for name in OWNED) and int(pid) != os.getpid():
                os.kill(int(pid), signal.SIGTERM)
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "static":
        serve(partial(NoStore, directory=str(ROOT)), int(sys.argv[2]))
    elif mode == "pods":
        serve(pods_handler(json.loads(REPLAY.read_text())), int(sys.argv[2]))
    elif mode == "stop":
        return stop([int(p) for p in sys.argv[2:]])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
