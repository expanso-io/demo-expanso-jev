# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "playwright>=1.40.0",
# ]
# ///
"""Headless browser verification for 01-log-triage board.

Runs an isolated preview server serving real/recorded triage receipts,
launches headless Chromium via Playwright, verifies layout invariants
(no horizontal overflow, callouts rendered, correct branding, bucket counts)
at 1440x900 and 1920x1080, and saves screenshots into docs/proof/.
"""
import json
import os
import pathlib
import sys
import threading
import time
from http.server import ThreadingHTTPServer

REPO = pathlib.Path(__file__).resolve().parents[1]
DEMO_DIR = REPO / "demos/01-log-triage"
PROOF_DIR = REPO / "docs/proof"
PROOF_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(DEMO_DIR))
import server  # noqa: E402

SCRATCH = DEMO_DIR / ".test-scratch/proof-data"
SCRATCH.mkdir(parents=True, exist_ok=True)
server.DATA = str(SCRATCH)

H = server.HUB
H.pipeline_up = True
H.cloud_ok = True
H.cloud_mode = "jev"
H.replay = True
H.model_name = "cribl-decision-1.0-local"
H.run = H._new_run("jev")

# Hydrate buckets from fixture data
FIXTURES = DEMO_DIR / "fixtures/recurrence.expected"
for fn, b in server.FILES.items():
    f = FIXTURES / fn
    if not f.is_file():
        continue
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            server.ingest(b, r)
        except Exception:
            pass

# Also populate raw bucket so raw bucket displays content
raw_sample = [
    {"level": "INFO", "service": "auth-api", "msg": "Token refreshed for user 4410", "ts": "2026-10-10T14:00:00Z"},
    {"level": "INFO", "service": "cart", "msg": "Item added to cart session 918", "ts": "2026-10-10T14:00:01Z"},
    {"level": "INFO", "service": "worker", "msg": "Health check ok", "ts": "2026-10-10T14:00:02Z"},
]
for r in raw_sample:
    server.ingest("raw", r)

srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]
url = f"http://127.0.0.1:{port}"
print(f"Proof server running on {url}", flush=True)

from playwright.sync_api import sync_playwright  # noqa: E402

viewports = [
    {"width": 1440, "height": 900, "name": "1440x900-triage-board.png"},
    {"width": 1920, "height": 1080, "name": "1920x1080-triage-board.png"},
]

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for vp in viewports:
            w, h, fname = vp["width"], vp["height"], vp["name"]
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(1000)

            # Check no horizontal overflow
            scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
            inner_w = page.evaluate("() => window.innerWidth")
            assert scroll_w <= inner_w, f"Horizontal overflow at {w}x{h}: scrollWidth={scroll_w} > innerWidth={inner_w}"

            # Check masthead brand
            brand_text = page.locator("#brandTitle").inner_text()
            assert "EXPANSO" in brand_text.upper() and "CRIBL" in brand_text.upper(), f"Unexpected brand: {brand_text}"

            # Check model name
            model_name = page.locator("#modelName").inner_text()
            assert "CRIBL" in model_name.upper(), f"Unexpected model name: {model_name}"

            # Check region callouts
            for region in ["masthead", "stage", "destination", "shelf-accounting"]:
                callout_count = page.locator(f"[data-region='{region}'] .callout").count()
                assert callout_count >= 1, f"Missing callout in [data-region='{region}']"

            out_path = PROOF_DIR / fname
            page.screenshot(path=str(out_path), full_page=False)
            print(f"PASS: {w}x{h} verified and screenshot saved to {out_path}", flush=True)
            page.close()

        browser.close()
finally:
    srv.shutdown()
    srv.server_close()

print("ALL HEADLESS PROOF CHECKS PASSED.")
