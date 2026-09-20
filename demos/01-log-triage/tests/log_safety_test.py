# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Static guard on what the pipelines send to control-plane logs.

Operational logs are shipped off the node to Expanso Cloud whenever someone is
tailing. This walks both pipeline files, collects every `log` processor plus any
mapping that builds a log line, and fails if one of them could carry message
text, a prompt, a model request/response body, a URL or a credential -- or logs
the raw fingerprint (derived from the message; it can contain a username).
It also checks the wording rules: a log line runs BEFORE the output writes, so
a destination is "selected" with the write pending -- never written, delivered,
kept or retained -- and a fallback is never described as a judgment.

And the pass-through rule: producer-supplied strings (id, service, level) and
model-returned strings (team, severity) are arbitrary, so they may be read only
on a `let` line that allowlists, validates or hashes them. An earlier version of
this test REQUIRED the words "record kept" and so certified the very mistake it
should have caught; the assertions below are written against that.
"""
import pathlib
import re
import sys

import yaml

PKG = pathlib.Path(__file__).resolve().parents[1]
FORBIDDEN = {
    r"\bthis\.msg\b": "raw log message text",
    r"\bcontent\(\)": "whole raw payload",
    r"\bthis\.ts\b": "source timestamp is fine in data, but keep log lines to operational metadata",
    r"JEV_API_URL|https?://": "an endpoint URL",
    r"\bquestions\b|\binstructions\b|\bcriteria\b": "the Jev prompt",
    r"\bthis\.jev\b(?!\.answers|_ok|_decision)": "the whole Jev response body",
    r"root\s*=\s*this\b|root\s*=\s*@": "the whole record or all metadata",
    r"api[_-]?key|token|secret|password|credential": "a credential",
    r"this\.fingerprint(?!\.string\(\)\.hash\()": "the raw fingerprint (hash it)",
    r"this\.id(?!\.string\(\)\.hash\()": "the raw event id (hash it; a pattern match is not proof it was generated)",
}
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")


def walk(node, found, guarded=False):
    """Collect log processors. `guarded` is true only inside a switch case that
    carries a `check`, i.e. the log cannot fire unconditionally for every record."""
    if isinstance(node, dict):
        if "log" in node and isinstance(node["log"], dict):
            found.append(("log", {**node["log"], "_guarded": guarded}))
        if isinstance(node.get("mapping"), str) and "log_summary" in node["mapping"]:  # the line builder
            found.append(("mapping", {"message": node["mapping"]}))
        for k, v in node.items():
            if k == "switch" and isinstance(v, list):
                for case in v:
                    walk(case, found, guarded=isinstance(case, dict) and bool(case.get("check")))
            else:
                walk(v, found, guarded)
    elif isinstance(node, list):
        for v in node:
            walk(v, found, guarded)


for fn in ("pipeline-logging.yaml", "pipeline-recurrence.yaml"):
    print(f"--- {fn}")
    found = []
    walk(yaml.safe_load((PKG / fn).read_text()), found)
    logs = [b for k, b in found if k == "log"]
    check(f"has operational log processors ({len(logs)})", len(logs) >= 1)
    # comments are stripped by the YAML parser for plain keys, but a block scalar
    # keeps its own '#' comment lines; drop those before scanning.
    text = "\n".join(
        ln for _, b in found for part in (b.get("message", ""), b.get("fields_mapping", ""))
        for ln in str(part).splitlines() if not ln.strip().startswith("#"))
    for pat, what in FORBIDDEN.items():
        m = re.search(pat, text, re.I)
        check(f"no {what}", m is None, f"matched {m.group(0)!r}" if m else "")
    check("says 'selected, output pending'; never claims a write or retention",
          "selected, output pending" in text and not re.search(r"\b(written|wrote|delivered|stored|saved|kept|retained|decided)\b", text, re.I))
    check("write_confirmed is false on every log line", all("root.write_confirmed = false" in str(b.get("fields_mapping", "")) for b in logs))
    raw = [ln.strip() for ln in text.splitlines()
           if re.search(r"this\.(id|service|level)\b|\.(team|severity)\.choice", ln) and not ln.strip().startswith("let ")]
    check("producer/model strings are read only on allowlisting `let` lines", not raw, str(raw[:2]))
    check("service, level, team, severity go through closed allowlists",
          all(k in text for k in ('let lvl = if [', 'let svc = if [')) and (fn != "pipeline-recurrence.yaml" or all(k in text for k in ('let sev = if [', 'let team = if ['))))
    check("event id is hashed unconditionally (no pattern pass-through)", 'let eid = this.id.string().hash("sha256")' in text and "re_match" not in text)
    check("sampling is described per fingerprint, never as a global '1 in N' rate", "1 in " not in text and "fingerprint" in text)
    check("every log level is INFO or WARN (no global level change, no DEBUG/ERROR spam added)",
          all(b.get("level") in ("INFO", "WARN") for b in logs), str([b.get("level") for b in logs]))
    check("every log processor sits inside a switch case with a `check` (none fires per record)",
          all(b["_guarded"] for b in logs), str([b["_guarded"] for b in logs]))

print("--- pipeline-recurrence.yaml: only the routine path may be sampled")
rec_src = (PKG / "pipeline-recurrence.yaml").read_text()
kind = rec_src[rec_src.index("meta log_kind = if this.bypass {"):rec_src.index("meta log_summary")]
held = kind[kind.index('} else if this.jev_decision == "held"'):kind.index("} else if !this.jev_ok")]
non_bypass = kind[kind.index("} else if !this.jev_ok"):]
# A held record logs once, when first held. Its retries are the same event coming
# round again and are deliberately silent; the release is logged as a judgment.
check("held: first hold logs, retries are silent, keyed on held_attempts (not occurrence)",
      'if this.held_attempts == 0 { "held" } else { "" }' in held and "$occ" not in held)
check("held_attempts is coerced to a number before use (it is producer-supplied on first arrival)",
      "this.held_attempts.number().catch(0)" in rec_src)
check("bypass checkpoint is sampled per fingerprint", "$occ == 1 || $occ % 250 == 0" in kind)
# The fingerprint erases numbers, so a changed-value line shares a counter with
# the routine one; ANY occurrence test on this branch can silence it.
check("every non-bypass selection logs: no occurrence test on the judged/fallback branch",
      "$occ" not in non_bypass and '""' not in non_bypass, non_bypass.strip().replace("\n", " ")[:120])

print("--- pipeline-recurrence.yaml wording")
rec = (PKG / "pipeline-recurrence.yaml").read_text()
fb = re.search(r'"triage fallback[^"]*"', rec)
check("fallback line exists, is WARN-routed, and claims only a selection", bool(fb) and "selected, output pending" in fb.group(0) and 'log_kind") == "fallback"' in rec)
check("fallback line never calls itself a judgment", bool(fb) and not re.search(r"judged|Jev reported|decided by Jev", fb.group(0)))
check("bypass line states no model call", bool(re.search(r'"triage bypass[^"]*no model call', rec)))
check("judged line attributes scores to the model ('Jev reported'), not to accuracy", "Jev reported actionable=" in rec and "accura" not in rec.lower().split("# 4b.")[1].split("# 5.")[0])

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
