#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#     "torch>=2.4",
#     "transformers>=4.48",
#     "peft>=0.12",
#     "safetensors",
#     "huggingface_hub",
#     "accelerate",
# ]
# ///
"""
Local Cribl cribl-decision-1.0 decision server.

"Info is not enough, part two": the same POST /v1/systemone API the Jev
demos speak, answered on this machine by Cribl's open-weight decision
model instead of a cloud API. No API key, no relay, no network at request
time -- that is the whole point.

  cribl-decision-1.0: 4B LoRA adapter on Qwen3.5-4B-Base (Apache-2.0)
  https://huggingface.co/cribl-ai/cribl-decision-1.0
  https://cribl.io/blog/cribl-decision-1-0-a-foundation-for-telemetry-decision-models/

How it answers: the state and each question are formatted with the
model's chat template, then every candidate option is scored by its
log-probability as a continuation of the prompt -- one batched forward
pass per question -- and the scores are softmaxed into probabilities.
No free-form text is ever generated, so there is nothing to parse: the
model can only distribute probability mass over the options you supplied.

Usage:
    uv run -s shared/cribl-decision-server.py                 # listens on :8100
    uv run -s shared/cribl-decision-server.py --download-only # fetch weights once

    # then point a demo at it (no key, no other change):
    JEV_API_URL=http://127.0.0.1:8100/v1/systemone

Env:
    CRIBL_DECISION_PORT   listen port (default 8100)
    CRIBL_DECISION_CACHE  weights/cache dir (default ~/.cache/cribl-decision)

The pipeline needs no changes: it already reads answers generically by
question id, and treats any model name other than "jev-unavailable" as a
real answer. This server reports "cribl-decision-1.0-local".
"""

import argparse
import json
import math
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_ID = "Qwen/Qwen3.5-4B-Base"
BASE_REVISION = "1001bb4d826a52d1f399e183466143f4da7b741b"  # pinned by the Cribl model card
ADAPTER_ID = "cribl-ai/cribl-decision-1.0"
MODEL_NAME = "cribl-decision-1.0-local"
MAX_CONTEXT = 8192  # training max per the model card

SYSTEM_PROMPT = (
    "You are a decision model. Read the state and answer the question "
    "with exactly one of the listed options. Output only the option."
)

_tokenizer = None
_model = None
_device = None
_infer_lock = threading.Lock()


def log(msg):
    print(f"[cribl-decision] {msg}", file=sys.stderr, flush=True)


def cache_dir():
    return Path(os.environ.get("CRIBL_DECISION_CACHE", Path.home() / ".cache" / "cribl-decision"))


def ensure_downloaded(cache):
    """Fetch the base model (pinned revision) and the LoRA adapter once."""
    from huggingface_hub import snapshot_download

    base_dir = cache / "base"
    adapter_dir = cache / "adapter"
    if not (base_dir / "config.json").exists():
        log(f"downloading {BASE_ID}@{BASE_REVISION[:12]} (~8GB, one time)...")
        snapshot_download(repo_id=BASE_ID, revision=BASE_REVISION, local_dir=str(base_dir))
    if not (adapter_dir / "adapter_model.safetensors").exists():
        log(f"downloading {ADAPTER_ID} (~77MB, one time)...")
        snapshot_download(repo_id=ADAPTER_ID, local_dir=str(adapter_dir))
    return base_dir, adapter_dir


def load_model(cache):
    """Load base + adapter once, merge the LoRA, park on MPS (or CPU).

    The adapter was trained against Qwen3_5ForConditionalGeneration (the
    checkpoint's own architecture -- the text decoder lives at
    model.language_model). Loading the CausalLM variant instead leaves
    every LoRA key unmatched, so this is load-bearing, not cosmetic.
    """
    global _tokenizer, _model, _device
    import torch
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
    from peft import PeftModel

    base_dir, adapter_dir = ensure_downloaded(cache)
    t0 = time.time()
    _device = "mps" if torch.backends.mps.is_available() else "cpu"
    log(f"loading tokenizer from {adapter_dir.name}/ ...")
    _tokenizer = AutoTokenizer.from_pretrained(str(adapter_dir), trust_remote_code=False)
    if _tokenizer.pad_token_id is None:
        _tokenizer.pad_token = _tokenizer.eos_token
    log(f"loading base model ({BASE_ID}, fp16, conditional-generation arch) ...")
    try:
        base = Qwen3_5ForConditionalGeneration.from_pretrained(
            str(base_dir), dtype=torch.float16, trust_remote_code=False
        )
    except Exception as e:
        log(f"standard modeling code failed ({e}); retrying with trust_remote_code=True")
        base = Qwen3_5ForConditionalGeneration.from_pretrained(
            str(base_dir), dtype=torch.float16, trust_remote_code=True
        )
    log("attaching the cribl-decision-1.0 LoRA adapter ...")
    peft_model = PeftModel.from_pretrained(base, str(adapter_dir))
    n_lora = sum(p.numel() for n, p in peft_model.named_parameters() if "lora_" in n)
    log(f"LoRA params attached: {n_lora}")
    if n_lora == 0:
        raise RuntimeError("no LoRA weights attached -- adapter does not match the base model")
    log(f"merging adapter and moving to {_device} ...")
    _model = peft_model.merge_and_unload()
    _model.to(_device)
    _model.eval()
    log(f"ready in {time.time() - t0:.1f}s on {_device}")


def build_prompt(state_text, q):
    """(messages, candidates) for one question."""
    qtype = q.get("type")
    instructions = q.get("instructions", "")
    if qtype == "choice":
        criteria = dict(q.get("criteria", {}) or {})
        if not criteria and q.get("choices"):
            criteria = {c: c for c in q["choices"]}
        if not criteria:
            raise ValueError("choice question has no criteria or choices")
        opts = "\n".join(f"- {k}: {v}" for k, v in criteria.items())
        keys = ", ".join(criteria.keys())
        user = (
            f"State:\n{state_text}\n\nQuestion: {instructions}\n\n"
            f"Options:\n{opts}\n\nAnswer with exactly one option key: {keys}"
        )
        candidates = list(criteria.keys())
    elif qtype == "noul":
        user = (
            f"State:\n{state_text}\n\nQuestion: {instructions}\n\n"
            f"Answer with exactly one word: yes or no."
        )
        candidates = ["yes", "no"]
    elif qtype == "score":
        crit = list(q.get("criteria", []) or [])
        n = len(crit) or 5
        levels = "\n".join(
            f"- {i}: {crit[i]}" if i < len(crit) else f"- {i}" for i in range(n)
        )
        nums = ", ".join(str(i) for i in range(n))
        user = (
            f"State:\n{state_text}\n\nQuestion: {instructions}\n\n"
            f"Levels:\n{levels}\n\nAnswer with exactly one level number: {nums}"
        )
        candidates = [str(i) for i in range(n)]
    else:
        raise ValueError(f"unknown question type {qtype!r}")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    return messages, candidates


def candidate_logprobs(prompt_ids, candidates):
    """Log P(candidate tokens | prompt) for each candidate, one batched pass."""
    import torch

    cand_ids = []
    for c in candidates:
        ids = _tokenizer.encode(c, add_special_tokens=False)
        if not ids:
            raise ValueError(f"candidate {c!r} tokenizes to nothing")
        cand_ids.append(ids)
    room = MAX_CONTEXT - max(len(c) for c in cand_ids)
    if len(prompt_ids) > room:
        log(f"prompt truncated from {len(prompt_ids)} to {room} tokens")
        prompt_ids = prompt_ids[-room:]
    P = len(prompt_ids)
    max_c = max(len(c) for c in cand_ids)
    pad_id = _tokenizer.pad_token_id
    batch, mask = [], []
    for c in cand_ids:
        ids = prompt_ids + c
        pad = max_c - len(c)
        batch.append(ids + [pad_id] * pad)
        mask.append([1] * len(ids) + [0] * pad)
    input_ids = torch.tensor(batch, device=_device)
    attention_mask = torch.tensor(mask, device=_device)
    with _infer_lock, torch.inference_mode():
        logits = _model(input_ids=input_ids, attention_mask=attention_mask).logits
    logprobs = torch.log_softmax(logits.float(), dim=-1)
    out = []
    for b, c in enumerate(cand_ids):
        lp = 0.0
        for j, tok in enumerate(c):
            lp += logprobs[b, P - 1 + j, tok].item()
        out.append(lp)
    return out


def softmax(logps):
    m = max(logps)
    exps = [math.exp(lp - m) for lp in logps]
    s = sum(exps)
    return [e / s for e in exps]


def answer_question(qid, q, state_text):
    messages, candidates = build_prompt(state_text, q)
    enc = _tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True
    )
    # tokenize=True may return a BatchEncoding instead of a plain list
    prompt_ids = enc["input_ids"] if not isinstance(enc, list) else enc
    prompt_ids = list(prompt_ids)
    probs = softmax(candidate_logprobs(prompt_ids, candidates))
    best = max(range(len(probs)), key=lambda i: probs[i])
    qtype = q.get("type")
    if qtype == "choice":
        return {
            "type": "choice",
            "choice": candidates[best],
            "probabilities": {c: round(p, 4) for c, p in zip(candidates, probs)},
            "confidence": round(probs[best], 4),
        }
    if qtype == "noul":
        p_yes = probs[candidates.index("yes")]
        return {"type": "noul", "noul": round(p_yes, 4)}
    if qtype == "score":
        expected = sum(i * p for i, p in enumerate(probs))
        return {
            "type": "score",
            "score": round(expected, 2),
            "probabilities": {c: round(p, 4) for c, p in zip(candidates, probs)},
            "confidence": round(probs[best], 4),
        }
    raise ValueError(f"unknown question type {qtype!r}")


def answer_all(questions, state_text):
    if not isinstance(state_text, str):
        state_text = json.dumps(state_text, sort_keys=True)
    state_text = state_text[:4000]
    answers = {}
    for qid, q in questions.items():
        t0 = time.time()
        try:
            answers[qid] = answer_question(qid, q, state_text)
            log(f"{qid} ({q.get('type')}) {time.time() - t0:.2f}s -> "
                f"{json.dumps(answers[qid])[:160]}")
        except Exception as e:  # never fail the whole request on one question
            log(f"{qid} ({q.get('type')}) ERROR {e}")
            answers[qid] = {"type": q.get("type"), "error": str(e)[:200]}
    return answers


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload, code=200):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"status": "ok", "model": MODEL_NAME})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = {}
        t0 = time.time()
        answers = answer_all(body.get("questions", {}), body.get("state", ""))
        state_text = body.get("state", "")
        if not isinstance(state_text, str):
            state_text = json.dumps(state_text, sort_keys=True)
        self._send({
            "model": MODEL_NAME,
            "answers": answers,
            "usage": {
                "input_tokens": max(1, len(state_text) // 4),
                "latency_s": round(time.time() - t0, 2),
            },
        })

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description="Local Cribl cribl-decision-1.0 /v1/systemone server")
    ap.add_argument("--download-only", action="store_true",
                    help="fetch the weights once, then exit")
    args = ap.parse_args()
    cache = cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    if args.download_only:
        ensure_downloaded(cache)
        log(f"weights are in {cache}")
        return
    load_model(cache)
    port = int(os.environ.get("CRIBL_DECISION_PORT", "8100"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Cribl cribl-decision-1.0 listening on http://127.0.0.1:{port}/v1/systemone",
          flush=True)
    print("No API key. No relay. The model runs on this machine.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
