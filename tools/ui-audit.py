#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Browser audit of every published page, in its own agent-browser session.

    uv run -s tools/ui-audit.py                 # every page, 4 widths, light and dark
    uv run -s tools/ui-audit.py --only 02       # pages whose path contains "02"
    uv run -s tools/ui-audit.py --quick         # 320 and 1440 only

For each page, width and theme it checks:

  * no horizontal page scroll (and names any element wider than the viewport),
  * every text node meets WCAG AA contrast against its real, composited
    background (4.5:1, or 3:1 for large text),
  * explorer pages: Right and Left arrow keys page the stages and leave the
    scroll position where it was.

It uses its own named session, closes only that session, and never touches
another browser. Exit 1 on any failure.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION = "pbjev-audit"
WIDTHS = [(320, 800), (400, 860), (768, 1024), (1440, 900)]

PAGES = [
    "index.html",
    *sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "demos").glob("*/explorer.html")),
    "demos/01-log-triage/index.html",
    "demos/11-pod-labels/web/index.html",
]

CONTRAST_JS = r"""
(() => {
  const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const over = (top, bot) => { const a = top.a + bot.a * (1 - top.a);
    if (a === 0) return { r: 0, g: 0, b: 0, a: 0 };
    return { r: (top.r * top.a + bot.r * bot.a * (1 - top.a)) / a, g: (top.g * top.a + bot.g * bot.a * (1 - top.a)) / a, b: (top.b * top.a + bot.b * bot.a * (1 - top.a)) / a, a }; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a, b) => { const la = lum(a), lb = lum(b); return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05); };
  const bgOf = (node) => { const chain = []; for (let n = node; n && n.nodeType === 1; n = n.parentElement) chain.push(n);
    let acc = { r: 255, g: 255, b: 255, a: 1 };
    const root = getComputedStyle(document.documentElement).backgroundColor; const rc = parse(root);
    if (rc && rc.a > 0) acc = over(rc, { r: 255, g: 255, b: 255, a: 1 });
    for (const n of chain.reverse()) { const cs = getComputedStyle(n); const c = parse(cs.backgroundColor); if (c && c.a > 0) acc = over(c, acc); }
    return acc; };
  const bad = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const t = walker.currentNode; if (!t.nodeValue.trim()) continue;
    const el = t.parentElement; if (!el || seen.has(el)) continue; seen.add(el);
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || +cs.opacity === 0) continue;
    const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) continue;
    if (el.closest(".vh")) continue;
    const fg0 = parse(cs.color); if (!fg0) continue;
    const bg = bgOf(el); const fg = over(fg0, bg);
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const need = large ? 3 : 4.5; const got = ratio(fg, bg);
    if (got < need) bad.push({ text: t.nodeValue.trim().slice(0, 40), got: +got.toFixed(2), need, el: el.tagName.toLowerCase() + (el.className && typeof el.className === "string" ? "." + el.className.split(" ")[0] : "") });
  }
  return bad.slice(0, 8);
})()
"""

OVERFLOW_JS = r"""
(() => {
  const vw = document.documentElement.clientWidth;
  const doc = document.documentElement.scrollWidth;
  const off = [];
  for (const e of document.querySelectorAll("body *")) {
    const r = e.getBoundingClientRect();
    if (r.width > 0 && (r.right > vw + 1 || r.left < -1)) {
      const cs = getComputedStyle(e);
      if (cs.position === "fixed" || e.closest("[hidden]")) continue;
      off.push(e.tagName.toLowerCase() + (typeof e.className === "string" && e.className ? "." + e.className.split(" ")[0] : "") + " " + Math.round(r.left) + ".." + Math.round(r.right));
    }
  }
  return { vw, doc, over: doc > vw, off: off.slice(0, 6) };
})()
"""

KEYS_JS = r"""
(() => ({ y: window.scrollY, where: (document.querySelector(".where") || {}).textContent || null }))()
"""


def ab(*args: str, check: bool = True) -> str:
    env = dict(os.environ, AGENT_BROWSER_SESSION=SESSION)
    r = subprocess.run(["agent-browser", *args], capture_output=True, text=True, env=env, timeout=90)
    if check and r.returncode:
        raise RuntimeError(f"agent-browser {' '.join(args[:2])}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def ev(js: str):
    out = ab("eval", js)
    try:
        value = json.loads(out)
        return json.loads(value) if isinstance(value, str) and value[:1] in "[{" else value
    except json.JSONDecodeError:
        return out


def set_theme(want: str):
    ev(
        "(() => { const b = document.getElementById('theme'); "
        "if (b && document.documentElement.getAttribute('data-theme') !== '" + want + "') b.click(); "
        "return document.documentElement.getAttribute('data-theme'); })()"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    widths = [WIDTHS[0], WIDTHS[-1]] if args.quick else WIDTHS
    pages = [p for p in PAGES if (ROOT / p).exists() and (not args.only or args.only in p)]
    failures: list[str] = []
    try:
        for page in pages:
            states = ["#case=main&record=0&stage=0", "#case=main&record=2&stage=4", "#case=main&record=2&stage=99"]
            is_explorer = page.endswith("explorer.html")
            for w, h in widths:
                for theme in ("light", "dark"):
                    ab("set", "viewport", str(w), str(h))
                    for st in states if is_explorer else [""]:
                        ab("open", f"file://{ROOT / page}{st}")
                        ab("reload")
                        set_theme(theme)
                        label = f"{page} {w}px {theme} {st}".strip()
                        o = ev(OVERFLOW_JS)
                        if o.get("over"):
                            failures.append(f"{label}: horizontal scroll {o['doc']} > {o['vw']}; {o['off']}")
                        c = ev(CONTRAST_JS)
                        for b in c if isinstance(c, list) else []:
                            failures.append(f"{label}: contrast {b['got']} < {b['need']} on {b['el']} '{b['text']}'")
                    if is_explorer and w in (320, 1440):
                        ab("open", f"file://{ROOT / page}#case=main&record=0&stage=1")
                        ab("reload")
                        ev("document.getElementById('explore-h').scrollIntoView(); window.scrollBy(0, 40); 0")
                        before = ev(KEYS_JS)
                        ab("press", "ArrowRight")
                        mid = ev(KEYS_JS)
                        ab("press", "ArrowLeft")
                        after = ev(KEYS_JS)
                        if not (before["y"] == mid["y"] == after["y"]):
                            failures.append(f"{page} {w}px: arrow paging moved scroll {before['y']} -> {mid['y']} -> {after['y']}")
                        if mid["where"] == before["where"] or after["where"] != before["where"]:
                            failures.append(f"{page} {w}px: arrow keys did not page ({before['where']} / {mid['where']} / {after['where']})")
            print(("ok   " if not any(f.startswith(page + " ") for f in failures) else "FAIL ") + page, flush=True)
    finally:
        subprocess.run(["agent-browser", "close"], env=dict(os.environ, AGENT_BROWSER_SESSION=SESSION), capture_output=True)
    for f in failures:
        print("  -", f)
    print(f"{len(failures)} problem(s) across {len(pages)} page(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
