"""Synthetic demo stimulus, emitted by a real pod's HTTP workload."""

import json
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SCENARIOS = {
    "checkout": {
        "event": "checkout_completed",
        "team": "payments",
        "routing_tier": "stable",
        "status": 200,
        "message": "Checkout request completed; eligible for stable checkout routing",
    },
    "failure": {
        "event": "stable_traffic_denied",
        "routing_tier": "stable",
        "status": 503,
        "message": "Stable checkout traffic fails policy validation; remove stable routing membership",
    },
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        scenario = self.path.removeprefix("/")
        if scenario not in SCENARIOS:
            self.send_error(404)
            return
        event = dict(SCENARIOS[scenario], at=time.time(), synthetic_stimulus=True)
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
        HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
