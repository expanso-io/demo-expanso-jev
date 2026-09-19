#!/usr/bin/env python3
"""
Mock Jev API server for zero-credential demos.

Emulates POST /v1/systemone well enough to run every pipeline in this
repository end to end without a TYPESAFE_API_KEY.

How it decides: keyword heuristics over the event text plus a few
structural checks. Deterministic, no network, no model. It is NOT real
judgment: it exists so you can see the pattern (Jev decides, code acts on
confidence, uncertainty escalates) before you have a key. The log-triage
board shows a red "MOCK Jev responses" label whenever this is answering.

Usage:
    uv run shared/jev-mock-server.py            # listens on :8099

    # then in .env:
    JEV_API_URL=http://127.0.0.1:8099/v1/systemone
"""
import json
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

WORD = re.compile(r"[a-z]{3,}")
STOPWORDS = {
    "the", "and", "for", "with", "from", "are", "was", "were", "has",
    "have", "had", "will", "would", "could", "should", "shall", "may",
    "might", "can", "you", "your", "our", "their", "its", "this", "that",
    "these", "those", "they", "we", "does", "doesn", "did", "not", "but", "all",
    "any", "get", "got", "into", "over", "under", "such", "after", "before",
    "between", "through", "during", "each", "other", "some", "only", "own",
    "same", "too", "very", "just", "than", "then", "when", "what", "which",
    "who", "how", "why", "once", "here", "there", "where", "while",
    "until", "again", "about",
    # JSON schema words, not content: field names pollute keyword matching
    "content", "record", "records", "customer", "customers", "user", "users",
    "text", "message", "messages", "event", "events", "log", "logs",
    "data", "state", "contain", "contains",
}

# Polarity word lists for score questions (score = 0..n-1 scale).
NEGATIVE = {
    "fatal", "outage", "failed", "failure", "failures", "panic", "breach",
    "fraud", "angry", "furious", "threatening", "hate", "cancel", "churn",
    "broken", "smoke", "grinding", "unreachable", "declined", "escalating",
    "legal", "slow", "query", "error", "terrible", "awful", "disappointed",
    "ridiculous", "unacceptable", "spike", "spiked",
    "waiting", "annoyed", "frustrated", "overheating", "bearing",
}
POSITIVE = {
    "success", "successful", "passed", "great", "love", "fantastic",
    "smooth", "happy", "excellent", "thanks", "awesome",
}
# Score questions where NEGATIVE means a *low* score (bad quality, bad sentiment).
INVERTED_SCORE = {"sentiment", "quality"}

# Extra domain keywords per choice option, beyond the option's own
# description text. Lets the mock resolve the fixture vocabulary
# (fatal, ssn, crypto, ...) to the intended option.
CHOICE_LEXICON = {
    "critical": {"fatal", "outage", "crash", "down", "unreachable", "emergency", "panic"},
    "warning": {"warning", "warn", "unusual", "suspicious", "elevated", "failed",
                "failure", "declined", "error", "soon", "velocity"},
    "restricted": {"ssn", "secret", "password", "passwd", "token", "key",
                   "credential", "regulated", "legal"},
    "confidential": {"salary", "compensation", "performance", "review",
                      "diagnosis", "medical", "confidential", "band"},
    "spam": {"spam", "crypto", "doubling", "guaranteed", "shady", "promo",
             "scam", "winner", "prize", "unsolicited"},
    "hate": {"hate", "shouldn", "ruining", "demean", "attack"},
    "self_harm": {"suicide", "disappeared", "harm", "kill", "die", "worthless"},
    "brute_force": {"brute", "failed", "failure", "failures", "login",
                    "logins", "repeated", "account"},
    "credential_stuffing": {"stuffing", "accounts", "users", "distinct",
                            "tried", "mixed"},
    "benign": {"benign", "normal", "routine", "legitimate", "mfa", "success"},
    "bug": {"bug", "broken", "load", "deploy", "failing", "crash", "error",
            "blocked", "blocking", "broken"},
    "safe": {"benign", "great", "smooth", "love", "thanks", "awesome",
             "good", "excellent", "happy", "question", "asking", "anyone",
             "fine", "read", "search", "query", "lookup", "list", "get", "check"},
    "impossible_travel": {"travel", "impossible", "prev", "login", "geo", "minutes"},
    "billing": {"billing", "charged", "charges", "invoice", "invoices",
                "refund", "refunds", "subscription", "payment", "duplicate"},
    "technical": {"technical", "bug", "bugs", "error", "errors", "api",
                  "webhook", "integration", "sso", "saml"},
    "sales": {"sales", "pricing", "plans", "discount", "upgrade", "upgrades",
              "rollout", "quote", "demo", "trial", "seats", "annual"},
    "irreversible": {"delete", "deletes", "send", "publish", "grant", "spend"},
    "data_exfiltration": {"exfiltrat", "send", "email", "external", "competitor", "leak"},
}

# Signal words per noul question: P(yes) is high when any appear.
NOUL_LEXICON = {
    "dispatch": {"smoke", "fire", "burning", "flames", "explosion", "grinding"},
    "escalate": {"failed", "failure", "failures", "brute", "attack", "breach", "intrusion"},
    "actionable": {"action", "failed", "failure", "exhausted", "declined",
                   "unusual", "attack", "breach", "error", "investigate"},
    "urgent": {"urgent", "immediately", "asap", "critical", "fatal", "outage",
               "emergency", "blocking"},
    "contains_credentials": {"password", "passwd", "secret", "token", "key",
                             "credential", "api"},
    "contains_pii": {"email", "ssn", "phone", "address", "personal", "dob"},
    "churn_risk": {"churn", "cancel", "cancelled", "leave", "leaving",
                   "competitors", "evaluating", "renewal", "refund", "switching"},
    "needs_human": {"crypto", "spam", "scam", "hate", "kill", "suicide",
                    "disappeared", "die", "shouldn", "ruining", "harm"},
}


def words(text):
    """Lowercase alpha tokens, 3+ chars; splits snake_case and dotted names."""
    return set(WORD.findall(re.sub(r"[_\-./]", " ", text.lower())))


def variants(word):
    """Tiny singular/plural stem set so 'charge' matches 'charged'."""
    v = {word}
    if word.endswith("ies"):
        v.add(word[:-3] + "y")
    elif word.endswith("sses"):
        v.add(word[:-2])
    elif word.endswith("s") and not word.endswith("ss"):
        v.add(word[:-1])
    else:
        v.add(word + "s")
    return v


def expanded(state_words):
    out = set(state_words)
    for w in state_words:
        out |= variants(w)
    return out


def content_words(text):
    return {w for w in words(text) if w not in STOPWORDS}


def state_key_words(state):
    """All words appearing in JSON keys — schema, not content."""
    keys = set()

    def walk(v):
        nonlocal keys
        if isinstance(v, dict):
            for k, x in v.items():
                keys |= words(str(k))
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(state)
    return keys


def record_issues(record):
    """Obvious data-quality problems in a JSON record: nulls, negative or
    non-numeric amounts, unknown currencies, absurd outliers, bad timestamps."""
    issues = 0

    def walk(v):
        nonlocal issues
        if v is None:
            issues += 1
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(record)
    amt = record.get("amount")
    if amt is not None and not isinstance(amt, bool):
        if isinstance(amt, (int, float)):
            if amt < 0 or amt > 1_000_000:
                issues += 1
        else:
            issues += 1
    if record.get("currency") not in (None, "USD", "EUR", "GBP"):
        issues += 1
    ts = record.get("ts")
    if ts is not None:
        try:
            datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            issues += 1
    return issues


def answer_noul(qid, q, state_words, state_text, state):
    # Structural special cases first.
    if qid == "intent_match" and isinstance(state, dict) and "user_intent" in state:
        intent = content_words(str(state.get("user_intent", "")))
        tool_text = json.dumps({"tool": state.get("tool"), "args": state.get("args")})
        tool_words = expanded(words(tool_text))
        hit = any(variants(w) & tool_words for w in intent if len(w) > 3)
    elif qid == "conformant" and isinstance(state, dict):
        hit = record_issues(state) == 0
    else:
        lex = NOUL_LEXICON.get(qid, set())
        sw = expanded(state_words)
        hit = any(variants(w) & sw for w in lex)
        if not hit:
            # Fall back to the question's own wording: if it asks about
            # "passwords, API keys, tokens", those words are the signal.
            # Words that only echo the JSON schema (field names) don't count.
            key_words = expanded(state_key_words(state)) if isinstance(state, dict) else set()
            instr_words = content_words(q.get("instructions", "")) | content_words(qid.replace("_", " "))
            hit = any(
                variants(w) & sw and not (variants(w) & key_words)
                for w in instr_words if len(w) > 3
            )
        if not hit and "THIRD" in state_text and ("today" in state_text.lower() or "legal" in state_text.lower()):
            hit = True
    return {"type": "noul", "noul": 0.92 if hit else 0.12}


def value_words(state):
    """All words appearing in JSON values — content, not schema."""
    vals = set()

    def walk(v):
        nonlocal vals
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif v is None or isinstance(v, bool):
            pass
        else:
            vals |= words(str(v))

    walk(state)
    return vals


def answer_choice(qid, q, state_words, state):
    criteria = q.get("criteria", {})
    sw = expanded(state_words)
    if isinstance(state, dict):
        # Schema-only words (field names that never appear in values, like
        # the "service" envelope field) are not evidence when they come
        # from an option's free-text description: "Service-impacting"
        # must not match the "service" field name. Curated lexicon words
        # are exempt — they intentionally name domain signals that often
        # live in field names ("api_key", "prev_login_geo").
        schema_only = expanded(state_key_words(state)) - expanded(value_words(state))
    else:
        schema_only = set()
    best, best_hits = None, 0
    for opt, desc in criteria.items():
        opt_words = content_words(opt.replace("_", " ") + " " + str(desc))
        lex = CHOICE_LEXICON.get(opt, set())
        desc_hits = {
            w for w in opt_words
            if variants(w) & sw and not (variants(w) & schema_only)
        }
        lex_hits = {w for w in lex if variants(w) & sw}
        hits = len(desc_hits | lex_hits)
        if hits > best_hits:
            best, best_hits = opt, hits
    if best is None:
        best = "other" if "other" in criteria else next(iter(criteria), "other")
        confidence = 0.35
    else:
        confidence = 0.92
    n = max(1, len(criteria) - 1)
    probs = {opt: (0.92 if opt == best else round(0.08 / n, 3)) for opt in criteria}
    return {
        "type": "choice",
        "choice": best,
        "probabilities": probs,
        "confidence": confidence,
    }


def answer_score(qid, q, state_words, state):
    n = len(q.get("criteria", [])) or 5
    sw = state_words
    if qid == "quality" and isinstance(state, dict):
        score = max(0, (n - 1) - record_issues(state))
    elif qid in INVERTED_SCORE:
        if POSITIVE & sw:
            score = (n - 1) * 0.85
        elif NEGATIVE & sw:
            score = (n - 1) * 0.15
        else:
            score = (n - 1) * 0.35
    else:
        if NEGATIVE & sw:
            score = (n - 1) * 0.85
        elif POSITIVE & sw:
            score = (n - 1) * 0.15
        else:
            score = (n - 1) * 0.35
    return {
        "type": "score",
        "score": round(score, 2),
        "probabilities": {},
        "confidence": 0.7,
    }


def answer_all(questions, state_text):
    try:
        state = json.loads(state_text)
    except (json.JSONDecodeError, TypeError):
        state = state_text
    if not isinstance(state_text, str):
        state_text = json.dumps(state_text)
    sw = words(state_text)
    answers = {}
    for qid, q in questions.items():
        qtype = q.get("type")
        if qtype == "noul":
            answers[qid] = answer_noul(qid, q, sw, state_text, state)
        elif qtype == "choice":
            answers[qid] = answer_choice(qid, q, sw, state)
        elif qtype == "score":
            answers[qid] = answer_score(qid, q, sw, state)
        else:
            answers[qid] = {"type": qtype, "error": "unknown question type"}
    return answers


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = {}
        state_text = body.get("state", "")
        if not isinstance(state_text, str):
            state_text = json.dumps(state_text)

        answers = answer_all(body.get("questions", {}), state_text)

        resp = {
            "model": "jev-mock",
            "answers": answers,
            "usage": {"input_tokens": max(1, len(state_text) // 4)},
        }
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8099), Handler)
    print("Mock Jev API listening on http://localhost:8099/v1/systemone")
    print("Point the demo at it: JEV_API_URL=http://127.0.0.1:8099/v1/systemone in .env")
    server.serve_forever()
